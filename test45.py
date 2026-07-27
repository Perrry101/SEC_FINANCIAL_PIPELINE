"""
Filter SEC companies down to a target list of US-based, 10-K-filing companies
(the recommended pool for a USD-only, us-gaap-taxonomy bankruptcy-prediction
dataset, per our earlier discussion).

Input:
    all_sec_companies_categorized.csv   (from test3.py: ticker, cik, company,
                                          sic_code, sic_description, target_sector)

What this script adds, per company, using SEC's bulk submissions data:
    - stateOfIncorporation           (US state code if domestic, else foreign code)
    - country                        (business address country)
    - files_10K                      (True if a 10-K appears in filing history)
    - files_20F_or_40F                (True if a 20-F/40-F appears -> foreign private issuer)
    - entityType                     (operating company vs other)
    - exchanges

Filtering logic (the recommended pool):
    - has filed at least one 10-K                  (US domestic annual report, us-gaap, USD)
    - has NOT filed 20-F or 40-F                    (excludes foreign private issuers / Canadian MJDS filers)
    - entityType == 'operating'                     (excludes trusts, shell/asset-backed entities, etc.)
    - sic_code present                              (excludes unclassifiable / shell-like entries)

Output:
    target_companies_for_extraction.csv
        -> the exact CIK list to feed into your companyfacts JSON download step,
           one row per company, with a ready-to-use 10-digit `cik_padded` column
           for building URLs like:
           https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json

Usage:
    python filter_us_companies.py all_sec_companies_categorized.csv
    python filter_us_companies.py all_sec_companies_categorized.csv --sector Technology
    python filter_us_companies.py all_sec_companies_categorized.csv --max 500
"""

import io
import json
import os
import sys
import zipfile
import argparse
import pandas as pd
import requests

BULK_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
BULK_ZIP_CACHE = "submissions_bulk.zip"   # cached locally so re-runs don't re-download ~100MB
HEADERS = {
    # SEC requires a real contact email in the User-Agent -- replace with yours
    "User-Agent": "DataCollector/1.0 (myprojectemail@example.com)",
    "Accept-Encoding": "gzip, deflate",
}


def get_bulk_zip_bytes() -> bytes:
    """Download the SEC bulk submissions archive, or reuse a local cached copy."""
    if os.path.exists(BULK_ZIP_CACHE):
        print(f"Using cached {BULK_ZIP_CACHE} (delete this file to force a fresh download).")
        with open(BULK_ZIP_CACHE, "rb") as f:
            return f.read()

    print("Downloading SEC bulk submissions archive (~1GB, this can take a few minutes)...")
    resp = requests.get(BULK_ZIP_URL, headers=HEADERS, stream=True)
    if resp.status_code != 200:
        print(f"Error downloading bulk file. HTTP {resp.status_code}. "
              f"Make sure your User-Agent has a real contact email.", file=sys.stderr)
        sys.exit(1)
    content = resp.content
    with open(BULK_ZIP_CACHE, "wb") as f:
        f.write(content)
    print("Download complete and cached locally.")
    return content


def enrich_with_submissions(df_original: pd.DataFrame) -> pd.DataFrame:
    df_original = df_original.copy()
    df_original["cik_clean"] = df_original["cik"].astype(str).str.lstrip("0")
    ciks_to_find = set(df_original["cik_clean"])

    zip_bytes = get_bulk_zip_bytes()
    rows = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        cik_files = [
            f for f in z.namelist()
            if f.split("/")[-1].startswith("CIK") and f.endswith(".json")
        ]
        print(f"Scanning {len(cik_files)} filer records for matches against your {len(ciks_to_find)} target CIKs...")

        for filename in cik_files:
            base = filename.split("/")[-1]
            cik_from_file = base.replace("CIK", "").replace(".json", "").lstrip("0")
            if cik_from_file not in ciks_to_find:
                continue
            try:
                with z.open(filename) as f:
                    profile = json.loads(f.read().decode("utf-8"))
            except Exception:
                continue

            filings = profile.get("filings") or {}
            recent = filings.get("recent") or {}
            forms = recent.get("form") or []
            addresses = profile.get("addresses") or {}
            business_addr = addresses.get("business") or {}

            rows.append({
                "cik_clean": cik_from_file,
                "entityType": profile.get("entityType", ""),
                "stateOfIncorporation": profile.get("stateOfIncorporation", ""),
                "country": business_addr.get("stateOrCountryDescription", ""),
                "exchanges": ",".join(str(e) for e in (profile.get("exchanges") or []) if e),
                "files_10K": "10-K" in forms,
                "files_20F_or_40F": ("20-F" in forms) or ("40-F" in forms),
                "fiscalYearEnd": profile.get("fiscalYearEnd", ""),
            })

    df_meta = pd.DataFrame(rows)
    merged = df_original.merge(df_meta, on="cik_clean", how="left")
    return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_csv", nargs="?", default="all_sec_companies_categorized.csv",
                     help="Path to all_sec_companies_categorized.csv (default: %(default)s, "
                          "looked for in the current directory)")
    ap.add_argument("-o", "--output", default="target_companies_for_extraction.csv")
    ap.add_argument("--sector", default=None,
                     help="Optional: restrict to one target_sector value, e.g. Technology")
    ap.add_argument("--max", type=int, default=None, help="Optional: cap the number of output rows")
    args = ap.parse_args()

    if not os.path.exists(args.input_csv):
        print(f"Error: could not find '{args.input_csv}' in the current directory.\n"
              f"Run this from D:\\SEC_FINANCIAL_PIPELINE, or pass the path explicitly:\n"
              f"  python test45.py path\\to\\all_sec_companies_categorized.csv", file=sys.stderr)
        sys.exit(1)

    if "myprojectemail@example.com" in HEADERS["User-Agent"]:
        print("Reminder: edit HEADERS['User-Agent'] near the top of this script to use your "
              "real contact email before running -- SEC blocks the placeholder address.\n")

    print(f"Loading {args.input_csv}...")
    df_original = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df_original)} companies.")

    merged = enrich_with_submissions(df_original)

    # --- apply the "US-based, 10-K, recommended pool" filter ---
    filtered = merged[
        (merged["files_10K"] == True)
        & (merged["files_20F_or_40F"] == False)
        & (merged["entityType"].str.lower() == "operating")
        & (merged["sic_code"].notna())
    ].copy()

    if args.sector:
        filtered = filtered[filtered["target_sector"] == args.sector]

    filtered["cik_padded"] = filtered["cik_clean"].astype(str).str.zfill(10)
    filtered = filtered.sort_values("company")

    if args.max:
        filtered = filtered.head(args.max)

    cols = ["ticker", "cik_padded", "company", "sic_code", "sic_description",
            "target_sector", "stateOfIncorporation", "country", "exchanges",
            "fiscalYearEnd"]
    filtered = filtered[cols]
    filtered.to_csv(args.output, index=False)

    print("\n" + "=" * 60)
    print(f"Started with:              {len(df_original)} companies")
    print(f"Matched in SEC bulk data:  {merged['entityType'].notna().sum()}")
    print(f"US-based 10-K filers:      {len(filtered)}")
    print(f"Saved to:                  {args.output}")
    print("=" * 60)
    print("\nNext step: download companyfacts JSON for each cik_padded value, e.g.")
    print("  https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json")


if __name__ == "__main__":
    main()