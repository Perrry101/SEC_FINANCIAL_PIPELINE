"""
extract_specific_fields.py

Focused extractor for 16 specific financial fields from SEC Company Facts.

Key design decisions to minimize NaN values:
  1. Groups data by FISCAL YEAR (not period_end) — this aligns balance sheet,
     income statement, and DEI fields that report on different calendar dates.
  2. Filters to fiscal year >= 2016 for better data density.
  3. For each (company, fiscal_year) group: takes the LATEST filing value per field.
  4. Multiple XBRL tag fallbacks per field, sourced from real tag-frequency analysis.
  5. Drops rows where ALL financial fields are NaN.

Fields extracted:
  - Current Assets, COGS, Depreciation & Amortization, Inventory
  - Net Income, Total Receivables, Market Value (EntityPublicFloat)
  - Net Sales, Total Assets, Long-Term Debt, Gross Profit
  - Current Liabilities, Retained Earnings, Total Revenue
  - Total Liabilities, Total Operating Expenses
  - Bonus: Shares Outstanding

Output: data/processed/specific_fields_dataset.csv
"""

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from config import (
    COMPANY_FACTS_DIR,
    LOG_SEPARATOR,
    logger,
)
from download_companies import get_company_list


# =============================================================================
# FIELD MAPPING — tag frequency verified from 200+ random JSON files
# =============================================================================

US_GAAP_FIELDS = {
    "current_assets": [
        "AssetsCurrent",
    ],
    "cost_of_goods_sold": [
        "CostOfGoodsAndServicesSold",    # most common (123/200)
        "CostOfGoodsSold",
        "CostOfRevenue",
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",  # most common (160/200)
        "DepreciationAndAmortization",
        "Depreciation",
        "AmortizationOfIntangibleAssets",
    ],
    "inventory": [
        "InventoryNet",                  # most common (173/200)
        "InventoryCurrent",
        "InventoryFinishedGoods",
        "InventoryGross",
    ],
    "net_income": [
        "NetIncomeLoss",                 # near-universal (198/200)
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "total_receivables": [
        "AccountsReceivableNetCurrent",  # most common (171/200)
        "ReceivablesNetCurrent",
        "AccountsReceivableNet",
    ],
    "net_sales": [
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
    "total_assets": [
        "Assets",                        # universal (196/200)
    ],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermBorrowings",
    ],
    "gross_profit": [
        "GrossProfit",                   # most common (151/200)
    ],
    "current_liabilities": [
        "LiabilitiesCurrent",            # near-universal (195/200)
    ],
    "retained_earnings": [
        "RetainedEarningsAccumulatedDeficit",  # near-universal (192/200)
        "RetainedEarnings",
    ],
    "total_revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # most common (140/200)
        "SalesRevenueNet",
        "Revenues",
    ],
    "total_liabilities": [
        "Liabilities",                   # most common (169/200)
    ],
    "total_operating_expenses": [
        "OperatingExpenses",             # most common standalone (101/200)
        "OperatingCostsAndExpenses",
        "CostsAndExpenses",
    ],
}

DEI_FIELDS = {
    "market_value": [
        "EntityPublicFloat",
    ],
    "shares_outstanding": [
        "EntityCommonStockSharesOutstanding",
    ],
}

ACCEPTED_FORMS = {"10-K", "10-K/A"}
MIN_FISCAL_YEAR = 2016


# =============================================================================
# EXTRACT RAW VALUES PER FIELD — NO MERGE BY PERIOD YET
# =============================================================================

def extract_tag_values(facts_section: dict, tag_name: str) -> list:
    """
    Extract all (period_end, fiscal_year, fiscal_quarter, value, filing_date)
    tuples for one XBRL tag, filtered to 10-K forms.

    Returns a flat list — no dedup yet. The caller handles dedup.
    """

    if tag_name not in facts_section:
        return []

    tag_data = facts_section[tag_name]
    units = tag_data.get("units", {})

    # Try USD, USD/shares, shares, then any unit
    matched_unit = None
    for u in ["USD", "USD/shares", "shares"]:
        if u in units:
            matched_unit = u
            break
    if matched_unit is None and units:
        matched_unit = next(iter(units))
    if matched_unit is None:
        return []

    results = []

    for item in units[matched_unit]:

        form = item.get("form", "")
        if form not in ACCEPTED_FORMS:
            continue

        period = item.get("end")
        value = item.get("val")
        filed = item.get("filed")
        if not period or value is None:
            continue

        try:
            period_dt = pd.to_datetime(period)
        except Exception:
            continue

        fyear = int(period_dt.year)

        # Skip years before our cutoff
        if fyear < MIN_FISCAL_YEAR:
            continue

        # Determine fiscal quarter from the filing's 'fp' field
        # (more reliable than period_dt.quarter)
        fp = item.get("fp", "")
        qmap = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}
        fquarter = qmap.get(fp, int(period_dt.quarter))

        results.append({
            "period_end": period,
            "fiscal_year": fyear,
            "fiscal_quarter": fquarter,
            "value": value,
            "filing_date": filed or "",
        })

    return results


# =============================================================================
# EXTRACT ALL FIELDS → COLLAPSE INTO ONE ROW PER (COMPANY × FISCAL YEAR)
# =============================================================================

def extract_company(file_path: Path) -> pd.DataFrame:
    """
    Load one JSON file, extract all fields, collapse to one row per fiscal year.

    Key insight: Different field types (balance sheet, income statement, DEI)
    often have different period_end dates for the same fiscal year. By grouping
    on fiscal_year instead of period_end, we keep all data that belongs together.
    """

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return pd.DataFrame()

    entity_name = data.get("entityName", "")
    cik = str(data.get("cik", "")).zfill(10)
    ticker = file_path.stem

    facts = data.get("facts", {})
    usgaap = facts.get("us-gaap", {})
    dei = facts.get("dei", {})

    # --- Step 1: Collect all raw values ---
    # Structure: {fiscal_year: {field: {filing_date, value, period_end}}}
    # For each (company, fiscal_year, field), we keep the latest filing value.

    year_data = {}  # {fyear: {field: {filing_date, value, period_end}}}

    def ingest_field(column: str, tag_list: list, facts_section: dict):
        """Try each tag in priority, first match wins per field."""
        for tag in tag_list:
            records = extract_tag_values(facts_section, tag)
            if not records:
                continue
            # First tag that returns data wins for this field
            for rec in records:
                fyear = rec["fiscal_year"]
                if fyear not in year_data:
                    year_data[fyear] = {
                        "company": entity_name,
                        "ticker": ticker,
                        "cik": cik,
                        "fiscal_year": fyear,
                    }
                row = year_data[fyear]
                # Keep latest filing for this field
                current = row.get(column)
                if current is None:
                    row[column] = {
                        "value": rec["value"],
                        "filing_date": rec["filing_date"],
                        "period_end": rec["period_end"],
                    }
                elif rec["filing_date"] and current["filing_date"] and rec["filing_date"] > current["filing_date"]:
                    row[column] = {
                        "value": rec["value"],
                        "filing_date": rec["filing_date"],
                        "period_end": rec["period_end"],
                    }
            break  # Stop after first matching tag

    # Extract us-gaap fields
    for column, tag_list in US_GAAP_FIELDS.items():
        ingest_field(column, tag_list, usgaap)

    # Extract DEI fields
    for column, tag_list in DEI_FIELDS.items():
        ingest_field(column, tag_list, dei)

    if not year_data:
        return pd.DataFrame()

    # --- Step 2: Unpack year_data into rows ---
    rows = []
    for fyear, row in sorted(year_data.items()):
        flat = {
            "company": row["company"],
            "ticker": row["ticker"],
            "cik": row["cik"],
            "fiscal_year": fyear,
            "fiscal_quarter": 4,  # Annual filing default
        }
        # Pick the most representative period_end (prefer balance sheet)
        # Fallback: earliest period_end, then latest
        period_ends_with_field = []

        # Unpack field values
        for field in list(US_GAAP_FIELDS.keys()) + list(DEI_FIELDS.keys()):
            entry = row.get(field)
            if entry is not None:
                flat[field] = entry["value"]
                period_ends_with_field.append((field, entry["period_end"]))
            else:
                flat[field] = pd.NA

        # Determine canonical period_end: use total_assets period if available
        canonical_end = None
        for field in ["total_assets", "total_revenue", "net_income"]:
            entry = row.get(field)
            if entry is not None and entry["period_end"]:
                canonical_end = entry["period_end"]
                break
        if canonical_end is None:
            # Fallback: any reported period_end
            for entry in row.values():
                if isinstance(entry, dict) and "period_end" in entry:
                    canonical_end = entry["period_end"]
                    break
        flat["period_end"] = canonical_end

        # Determine canonical filing_date
        all_filing_dates = []
        for entry in row.values():
            if isinstance(entry, dict) and "filing_date" in entry and entry["filing_date"]:
                all_filing_dates.append(entry["filing_date"])
        flat["filing_date"] = max(all_filing_dates) if all_filing_dates else pd.NA

        rows.append(flat)

    return pd.DataFrame(rows)


# =============================================================================
# MERGE COMPANY METADATA
# =============================================================================

def merge_metadata(dataset: pd.DataFrame) -> pd.DataFrame:
    """
    Merge sic_code, sic_description, target_sector from companies.csv.
    """
    companies = get_company_list()
    merge_columns = ["cik", "sic_code", "sic_description", "target_sector"]
    companies = companies[merge_columns]

    dataset = dataset.merge(companies, on="cik", how="left")
    return dataset


# =============================================================================
# CLEAN: DROP ROWS THAT ARE MOSTLY NaNs
# =============================================================================

def clean_sparse_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows where too many fields are NaN.
    Keeps a row if at least 3 financial fields have values.
    """
    financial_fields = list(US_GAAP_FIELDS.keys()) + list(DEI_FIELDS.keys())
    present = df[financial_fields].notna().sum(axis=1)
    before = len(df)
    df = df[present >= 3].copy()
    dropped = before - len(df)
    if dropped:
        logger.info("Dropped %d sparse rows (< 3 fields with data)", dropped)
    return df


# =============================================================================
# EXTRACT ALL COMPANIES
# =============================================================================

def extract_all() -> pd.DataFrame:
    """
    Iterate all JSON files, extract by fiscal year, merge, clean, return.
    """
    files = sorted(COMPANY_FACTS_DIR.glob("*.json"))
    logger.info("Processing %d Company Facts files...", len(files))

    all_frames = []
    for file in tqdm(files, desc="Extracting"):
        df = extract_company(file)
        if not df.empty:
            all_frames.append(df)

    if not all_frames:
        logger.warning("No data extracted from any file.")
        return pd.DataFrame()

    dataset = pd.concat(all_frames, ignore_index=True)
    logger.info("Raw rows extracted: %d", len(dataset))

    # Merge metadata
    dataset = merge_metadata(dataset)

    # Ensure all expected columns exist
    all_fields = list(US_GAAP_FIELDS.keys()) + list(DEI_FIELDS.keys())
    for col in all_fields:
        if col not in dataset.columns:
            dataset[col] = pd.NA

    # Deduplicate (safety — shouldn't be needed with the new logic)
    dataset = dataset.drop_duplicates(
        subset=["ticker", "fiscal_year"],
        keep="last",
    ).reset_index(drop=True)

    # Sort
    dataset = dataset.sort_values(
        ["ticker", "fiscal_year"]
    ).reset_index(drop=True)

    # Drop sparse rows
    dataset = clean_sparse_rows(dataset)

    # --- Smart field combination: maximize coverage ---
    # Many SEC filers tag revenue differently:
    #   "SalesRevenueNet" (net_sales) vs "RevenueFromContract..." (total_revenue)
    # These are often the same figure with different tag names.
    # Fill each from the other when one is missing.
    if "net_sales" in dataset.columns and "total_revenue" in dataset.columns:
        from_other = dataset["total_revenue"].fillna(dataset["net_sales"])
        dataset["net_sales"] = dataset["net_sales"].fillna(from_other)
        dataset["total_revenue"] = from_other

    # Reorder columns
    ordered = [
        "company", "ticker", "cik",
        "sic_code", "sic_description", "target_sector",
        "filing_date", "period_end", "fiscal_year", "fiscal_quarter",
    ]
    ordered += all_fields

    ordered = [c for c in ordered if c in dataset.columns]
    dataset = dataset[ordered]

    return dataset


# =============================================================================
# SAVE
# =============================================================================

def save_dataset(df: pd.DataFrame):
    output_path = Path(__file__).resolve().parent / "data" / "processed" / "specific_fields_dataset.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info("Dataset saved: %s", output_path)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print(LOG_SEPARATOR)
    print("EXTRACT SPECIFIC FIELDS — 10-K ANNUAL (FY >= 2016)")
    print(LOG_SEPARATOR)

    dataset = extract_all()

    if dataset.empty:
        logger.warning("No data extracted.")
        return

    # Replace NaN → empty string for cleaner CSV display (optional)
    # (Only for non-numeric columns to keep numeric cells as NaN)
    save_dataset(dataset)

    # Summary
    print()
    print(LOG_SEPARATOR)
    print("SUMMARY")
    print(LOG_SEPARATOR)
    logger.info("Total Rows       : %d", len(dataset))
    logger.info("Companies        : %d", dataset["ticker"].nunique())
    logger.info("Fiscal Years     : %s – %s",
                dataset["fiscal_year"].min(), dataset["fiscal_year"].max())
    logger.info("Columns          : %d", len(dataset.columns))

    print()
    logger.info("MISSING VALUES (2016+ filtered dataset)")
    missing = dataset.isna().sum().sort_values(ascending=False)
    for col, count in missing.items():
        pct = count / len(dataset) * 100
        print(f"  {col:30s}  {count:>8,}  ({100-pct:5.1f}% coverage)")

    print()
    logger.info("SAMPLE (first 10 rows)")
    print(dataset.head(10).to_string())

    print()
    logger.info("DONE.")


if __name__ == "__main__":
    main()
