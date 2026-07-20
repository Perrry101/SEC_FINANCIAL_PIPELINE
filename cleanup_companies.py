"""
cleanup_companies.py

Deduplicates companies.csv:
  - Drops warrant, preferred share, foreign OTC, and class B/C tickers
  - Keeps one primary ticker per CIK
  - Removes orphan JSON files for companies not in the cleaned list
  - Saves cleaned companies.csv

Usage:
    python cleanup_companies.py
"""

import os
from pathlib import Path

import pandas as pd

from config import COMPANY_FACTS_DIR, LOG_SEPARATOR, logger


# =============================================================================
# TICKER CLASSIFICATION
# =============================================================================

def classify_ticker(ticker: str) -> str:
    """
    Classify a ticker as PRIMARY, WARRANT, PREFERRED,
    CLASS_SHARE, or FOREIGN_OTC.

    Conservative approach — only flag well-known patterns to avoid
    dropping legitimate tickers that happen to end in certain letters.
    """

    t = str(ticker).upper().strip()

    # --- Foreign OTC: tickers ending in OTC suffixes ---
    # These follow the pattern: 2-3 letter root + F/FF/YF/SF/XF/OF
    # e.g. AMSYF (ArcelorMittal), CXMSF (CEMEX), HLNCF (Haleon)
    foreign_otc_suffixes = ("YF", "SF", "XF", "OF", "FF")
    if t.endswith(foreign_otc_suffixes) and len(t) > 4:
        return "FOREIGN_OTC"

    # Single F ending only for clearly OTC patterns (long tickers)
    if t.endswith("F") and len(t) > 5:
        return "FOREIGN_OTC"

    # --- Warrants: end in W but not genuine tickers ---
    # Pattern: 2-4 letter root + W (e.g. LNZAW, ASTLW, PCTTW)
    if t.endswith("WT") or t.endswith("WS"):
        return "WARRANT"

    # --- Preferred shares: explicit -PX pattern ---
    if "-PA" in t or "-PB" in t or "-PC" in t:
        return "PREFERRED"

    # --- Class shares: explicit dash pattern ---
    # Only flag if there is a dash: BIO-B, GEF-B, CTA-PA
    if "-" in t and len(t) <= 6:
        # e.g. BIO-B, GEF-B, CTA-PB
        suffix = t.split("-")[-1]
        if suffix in ("A", "B", "C", "PA", "PB", "PC"):
            return "CLASS_SHARE"

    return "PRIMARY"


# =============================================================================
# MAIN
# =============================================================================

def main():

    logger.info(LOG_SEPARATOR)
    logger.info("CLEANUP COMPANIES.CSV")
    logger.info(LOG_SEPARATOR)

    # ------------------------------------------------------------------
    # 1. Load companies.csv
    # ------------------------------------------------------------------

    df = pd.read_csv("companies.csv")
    df["ticker_upper"] = df["ticker"].astype(str).str.upper().str.strip()
    df["cik_str"] = df["cik"].astype(str).str.zfill(10)

    logger.info("Loaded %d companies from companies.csv", len(df))

    # ------------------------------------------------------------------
    # 2. Classify each ticker
    # ------------------------------------------------------------------

    df["ticker_type"] = df["ticker_upper"].apply(classify_ticker)

    type_counts = df["ticker_type"].value_counts()
    for t, count in type_counts.items():
        logger.info("  %s: %d", t, count)

    # ------------------------------------------------------------------
    # 3. Keep only PRIMARY tickers
    # ------------------------------------------------------------------

    df_primary = df[df["ticker_type"] == "PRIMARY"].copy()
    df_dropped = df[df["ticker_type"] != "PRIMARY"].copy()

    logger.info(
        "Kept %d primary tickers, dropped %d duplicates",
        len(df_primary),
        len(df_dropped),
    )

    # ------------------------------------------------------------------
    # 4. Handle remaining CIK duplicates
    #    (two PRIMARY tickers sharing a CIK)
    # ------------------------------------------------------------------

    cik_dupes = (
        df_primary.groupby("cik_str")
        .filter(lambda x: len(x) > 1)
    )

    if len(cik_dupes) > 0:
        logger.warning(
            "Found %d CIKs with multiple PRIMARY tickers — "
            "keeping shortest ticker as main",
            cik_dupes["cik_str"].nunique(),
        )

        # Keep shortest ticker per CIK (main listing)
        df_primary = (
            df_primary
            .sort_values("ticker_upper", key=lambda x: x.str.len())
            .drop_duplicates(subset="cik_str", keep="first")
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------
    # 5. Deduplicate by ticker as well
    # ------------------------------------------------------------------

    df_primary = df_primary.drop_duplicates(
        subset="ticker_upper"
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 6. Add missing metadata columns if absent
    # ------------------------------------------------------------------

    optional = ["sic_code", "sic_description", "target_sector"]
    for col in optional:
        if col not in df_primary.columns:
            df_primary[col] = ""

    # ------------------------------------------------------------------
    # 7. Standardize CIK format
    # ------------------------------------------------------------------

    df_primary["cik"] = (
        pd.to_numeric(df_primary["cik"], errors="coerce")
        .fillna(0)
        .astype(int)
        .astype(str)
        .str.zfill(10)
    )

    # ------------------------------------------------------------------
    # 8. Select final columns
    # ------------------------------------------------------------------

    final = df_primary[[
        "ticker_upper",
        "cik",
        "company",
        "sic_code",
        "sic_description",
        "target_sector",
    ]].copy()

    final = final.rename(columns={"ticker_upper": "ticker"})
    final = final.sort_values("ticker").reset_index(drop=True)

    logger.info("Final: %d unique companies", len(final))

    # ------------------------------------------------------------------
    # 9. Save
    # ------------------------------------------------------------------

    final.to_csv("companies.csv", index=False)
    logger.info("Saved cleaned companies.csv (%d rows)", len(final))

    # ------------------------------------------------------------------
    # 10. Remove orphan JSON files
    # ------------------------------------------------------------------

    if COMPANY_FACTS_DIR.exists():

        json_files = [
            f for f in COMPANY_FACTS_DIR.glob("*.json")
        ]

        clean_tickers = set(final["ticker"].str.upper())
        orphan_count = 0

        for json_file in json_files:
            ticker = json_file.stem.upper()
            if ticker not in clean_tickers:
                logger.info("Removing orphan JSON: %s", json_file.name)
                json_file.unlink()
                orphan_count += 1

        logger.info(
            "Removed %d orphan JSON files, %d remain",
            orphan_count,
            len(json_files) - orphan_count,
        )

    # ------------------------------------------------------------------
    # 11. Summary
    # ------------------------------------------------------------------

    print()
    print("=" * 60)
    print("CLEANUP COMPLETE")
    print("=" * 60)
    print(f"  Before: 525 rows (includes warrants, foreign OTC, class shares)")
    print(f"  After:  {len(final)} rows (one primary ticker per company)")
    print(f"  Removed: {525 - len(final)} duplicate/warrant/preferred/foreign entries")
    print(f"  Orphan JSONs removed: {orphan_count}")
    print("=" * 60)
    print()


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
