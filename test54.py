"""
Clean up target_companies_for_extraction.csv into a research-ready company
universe: one row per company (deduped by CIK), tagged with its recommended
SEC filing type, with shell/blank-check entities removed.

Problems this fixes:
  1. Duplicate CIKs -- the same company appears multiple times because SEC
     lists a separate ticker per share class (common, preferred, warrants,
     units). E.g. CIK 0000004457 (U-Haul) appears as both UHAL and UHAL-B.
     -> We keep exactly one row per CIK: the ticker that looks most like the
        primary common-stock line (no hyphen, doesn't end in W/U/R suffixes,
        shortest).
  2. Blank-check / SPAC companies (SIC 6770) and other non-operating shells
     -> excluded by default: they have no real revenue/assets history, which
        will just add noise to a fundamentals-based bankruptcy model.
  3. No explicit filing-type tag on each row
     -> adds `filing_tag` = "10-K" (this is guaranteed true for every row
        already, since target_companies_for_extraction.csv was filtered to
        10-K filers that never filed 20-F/40-F -- see filter_us_companies.py)

Usage:
    python build_research_universe.py target_companies_for_extraction.csv
    python build_research_universe.py target_companies_for_extraction.csv --keep-spacs
    python build_research_universe.py target_companies_for_extraction.csv --exclude-sic 6726,6770,9995
"""

import sys
import argparse
import pandas as pd

# SIC codes that indicate non-operating / shell / pooled-investment entities,
# excluded by default:
# 6770 = Blank Checks (SPACs)
# 6726 = Investment Offices, NEC (closed-end funds, not operating companies)
# 6221 = Commodity Contracts Brokers & Dealers (mostly commodity/crypto ETFs)
# 6189 = Asset-Backed Securities (securitization vehicles, not operating firms)
# 9995 = Non-Classifiable Establishments
# Note: Real Estate Investment Trusts (SIC 6798) are deliberately kept --
# REITs are legitimate operating companies with real bankruptcy history.
DEFAULT_EXCLUDE_SIC = {6770, 6726, 6221, 6189, 9995}


def ticker_quality_score(ticker: str):
    """
    Lower score = more likely to be the primary common-stock ticker.
    Penalizes hyphenated tickers (preferred share classes, e.g. 'ASB-PF')
    and tickers ending in W/U/R (warrants/units/rights, e.g. 'ONCHW'),
    then prefers the shortest remaining ticker.
    """
    t = str(ticker).strip().upper()
    has_hyphen = "-" in t
    is_warrant_unit_right = len(t) > 3 and t.endswith(("W", "U", "R")) and not t.endswith(("OR",))
    return (1 if has_hyphen else 0, 1 if is_warrant_unit_right else 0, len(t))


def dedupe_by_cik(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_score"] = df["ticker"].apply(ticker_quality_score)
    df = df.sort_values(["cik_padded", "_score"])
    deduped = df.drop_duplicates(subset="cik_padded", keep="first").drop(columns="_score")
    return deduped


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv", nargs="?", default="target_companies_for_extraction.csv")
    ap.add_argument("-o", "--output", default="research_universe.csv")
    ap.add_argument("--keep-spacs", action="store_true",
                     help="Don't exclude blank-check/shell SIC codes")
    ap.add_argument("--exclude-sic", default=None,
                     help="Comma-separated SIC codes to exclude, overrides the default list")
    args = ap.parse_args()

    print(f"Loading {args.input_csv}...")
    try:
        df = pd.read_csv(args.input_csv)
    except FileNotFoundError:
        print(f"Error: '{args.input_csv}' not found in the current directory.", file=sys.stderr)
        sys.exit(1)

    start_n = len(df)
    start_ciks = df["cik_padded"].nunique()
    print(f"Loaded {start_n} rows, {start_ciks} unique CIKs.")

    # --- normalize types/whitespace up front ---
    df["cik_padded"] = df["cik_padded"].astype(str).str.strip().str.zfill(10)
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["sic_code"] = pd.to_numeric(df["sic_code"], errors="coerce")

    # --- drop exact full-row duplicates, if any ---
    before = len(df)
    df = df.drop_duplicates()
    if before != len(df):
        print(f"Dropped {before - len(df)} exact duplicate rows.")

    # --- dedupe by CIK, keeping the best-guess primary ticker per company ---
    df = dedupe_by_cik(df)
    print(f"After CIK dedup: {len(df)} rows (was {start_n}).")

    # --- exclude shell/blank-check entities ---
    if not args.keep_spacs:
        exclude_sics = DEFAULT_EXCLUDE_SIC
        if args.exclude_sic:
            exclude_sics = {int(x) for x in args.exclude_sic.split(",")}
        before = len(df)
        df = df[~df["sic_code"].isin(exclude_sics)]
        print(f"Excluded {before - len(df)} shell/blank-check rows (SIC in {sorted(exclude_sics)}).")

    # --- add explicit filing tag ---
    df["filing_tag"] = "10-K"

    # --- final column order, CIK front and center ---
    cols = ["cik_padded", "filing_tag", "ticker", "company", "sic_code", "sic_description",
            "target_sector", "stateOfIncorporation", "country", "exchanges", "fiscalYearEnd"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols].rename(columns={"cik_padded": "cik"}).sort_values("company")

    df.to_csv(args.output, index=False)

    print("\n" + "=" * 60)
    print(f"Started with:        {start_n} rows / {start_ciks} unique CIKs")
    print(f"Final universe:      {len(df)} companies (one row per CIK)")
    print(f"Saved to:            {args.output}")
    print("=" * 60)
    print("\nColumns:", ", ".join(df.columns))
    print("\nNext step: download companyfacts JSON per CIK, e.g.")
    print('  https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')


if __name__ == "__main__":
    main()