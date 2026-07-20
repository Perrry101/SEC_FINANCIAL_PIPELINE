"""
extract_balance_sheet.py

Generic financial statement extractor for SEC Company Facts.

This version improves the original extractor by:

1. Supporting multiple XBRL tags per financial concept.
2. Keeping the latest filing for duplicate periods.
3. Extracting filing metadata.
4. Preparing the extractor to be reused for Income Statement
   and Cash Flow statements later.

Part 1
"""

import json
from pathlib import Path

import pandas as pd

from config import (
    COMPANY_FACTS_DIR,
    BALANCE_SHEET_TAGS,
    INCOME_STATEMENT_TAGS,
    CASH_FLOW_TAGS,
    VALIDATION_ABS_TOLERANCE,
    VALIDATION_PCT_TOLERANCE,
    LOG_SEPARATOR,
    logger,
)

from download_companies import get_company_list


# =============================================================================
# LOAD JSON
# =============================================================================

def load_company_json(file_path: Path) -> dict:
    """
    Load one SEC Company Facts JSON file.
    Returns empty dict on failure.
    """

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error("Corrupt JSON: %s — %s", file_path.name, e)
        return {}
    except OSError as e:
        logger.error("Cannot read file: %s — %s", file_path.name, e)
        return {}


# =============================================================================
# EXTRACT SINGLE XBRL TAG
# =============================================================================

def extract_tag(
    company_data: dict,
    tag_name: str,
    unit=None,
):
    """
    Extract one XBRL tag.

    Parameters
    ----------
    company_data : dict
        Parsed SEC Company Facts JSON.

    tag_name : str
        XBRL tag to extract (e.g. "Assets").

    unit : str or list, optional
        Accepted unit(s). Defaults to ["USD", "USD/shares"].

    Returns
    -------
    dict

    {
        period_end:
        {
            value,
            filing_date,
            fiscal_year,
            fiscal_quarter
        }
    }
    """

    if unit is None:
        unit = ["USD", "USD/shares"]
    elif isinstance(unit, str):
        unit = [unit]

    try:

        units = (
            company_data["facts"]
            ["us-gaap"]
            [tag_name]
            ["units"]
        )

    except KeyError:

        return {}

    # Find first matching unit
    matched_unit = None
    for u in unit:
        if u in units:
            matched_unit = u
            break

    if matched_unit is None:

        return {}

    extracted = {}

    for item in units[matched_unit]:

        # -----------------------------------------------------
        # Keep accepted SEC filing types
        # -----------------------------------------------------

        if item.get("form") not in ("10-Q", "10-K", "10-K/A", "10-Q/A", "20-F", "20-F/A", "40-F"):

            continue

        period = item.get("end")

        if period is None:

            continue

        value = item.get("val")

        if value is None:

            continue

        filing_date = item.get("filed")

        period_dt = pd.to_datetime(period)

        record = {

            "value": value,

            "filing_date": filing_date,

            "fiscal_year": int(period_dt.year),

            "fiscal_quarter": int(period_dt.quarter),
        }

        # -----------------------------------------------------
        # Keep latest filing if duplicate period exists
        # -----------------------------------------------------

        if period not in extracted:

            extracted[period] = record

        else:

            existing = extracted[period]

            if (
                filing_date
                and existing["filing_date"]
                and filing_date > existing["filing_date"]
            ):

                extracted[period] = record

    return extracted


# =============================================================================
# GENERIC STATEMENT EXTRACTOR
# =============================================================================

def extract_statement(
    company_json: dict,
    tag_dictionary: dict,
):
    """
    Generic extraction engine.

    Parameters
    ----------
    company_json : dict

    tag_dictionary : dict

    Returns
    -------
    pandas.DataFrame
    """

    entity_name = company_json.get(
        "entityName",
        ""
    )

    cik = str(
        company_json.get("cik", "")
    ).zfill(10)

    periods = {}

    # ---------------------------------------------------------
    # Iterate through every financial concept
    # ---------------------------------------------------------

    for column, tag_list in tag_dictionary.items():

        combined_values = {}

        # -----------------------------------------------------
        # Try every alternate XBRL tag
        # -----------------------------------------------------

        for tag in tag_list:

            values = extract_tag(
                company_json,
                tag,
            )

            for period, record in values.items():

                # First successful tag wins.
                if period not in combined_values:

                    combined_values[period] = record

        # -----------------------------------------------------
        # Merge into period dictionary
        # -----------------------------------------------------

        for period, record in combined_values.items():

            if period not in periods:

                periods[period] = {

                    "company": entity_name,

                    "cik": cik,

                    "period_end": period,

                    "filing_date": record["filing_date"],

                    "fiscal_year": record["fiscal_year"],

                    "fiscal_quarter": record["fiscal_quarter"],
                }

            periods[period][column] = record["value"]

    # ---------------------------------------------------------
    # Build DataFrame
    # ---------------------------------------------------------

    if not periods:

        return pd.DataFrame()

    df = pd.DataFrame(
        periods.values()
    )

    df = df.sort_values(
        "period_end"
    ).reset_index(
        drop=True
    )

    return df


# =============================================================================
# BALANCE SHEET WRAPPER
# =============================================================================

def extract_balance_sheet(
    company_json: dict,
) -> pd.DataFrame:
    """
    Extract balance sheet using the generic
    statement extraction engine.
    """

    return extract_statement(
        company_json,
        BALANCE_SHEET_TAGS,
    )


# =============================================================================
# INCOME STATEMENT WRAPPER
# =============================================================================

def extract_income_statement(
    company_json: dict,
) -> pd.DataFrame:
    """
    Extract income statement using the generic
    statement extraction engine.
    """

    return extract_statement(
        company_json,
        INCOME_STATEMENT_TAGS,
    )


# =============================================================================
# CASH FLOW WRAPPER
# =============================================================================

def extract_cash_flow(
    company_json: dict,
) -> pd.DataFrame:
    """
    Extract cash flow statement using the generic
    statement extraction engine.
    """

    return extract_statement(
        company_json,
        CASH_FLOW_TAGS,
    )


# =============================================================================
# COMPANY METADATA
# =============================================================================

def merge_company_metadata(
    dataset: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge metadata from companies.csv.

    Adds

    ticker
    company
    sic_code
    sic_description
    target_sector
    """

    companies = get_company_list()

    # Dataset already has ticker and company (from entityName),
    # so only merge the columns it doesn't have yet.
    merge_columns = [
        "cik",
        "sic_code",
        "sic_description",
        "target_sector",
    ]

    companies = companies[merge_columns]

    dataset = dataset.merge(
        companies,
        on="cik",
        how="left",
    )

    

    return dataset


# =============================================================================
# ACCOUNTING VALIDATION
# =============================================================================

def validate_balance_sheet(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Validate the accounting equation:
    Assets ≈ Liabilities + Equity

    A row is valid if the absolute difference is within
    VALIDATION_ABS_TOLERANCE (e.g. $1M) OR within
    VALIDATION_PCT_TOLERANCE (e.g. 1%) of total_assets,
    whichever is more lenient.
    """

    df = df.copy()

    required = [
        "total_assets",
        "total_liabilities",
        "equity",
    ]

    for column in required:
        if column not in df.columns:
            df[column] = pd.NA

    difference = (
        df["total_assets"]
        - (df["total_liabilities"] + df["equity"])
    ).abs()

    df["balance_sheet_difference"] = difference

    # Relative tolerance: 1% of total_assets (floor = $1M)
    assets = df["total_assets"].fillna(0).abs()
    threshold = (
        assets * VALIDATION_PCT_TOLERANCE
    ).clip(lower=VALIDATION_ABS_TOLERANCE)

    df["balance_sheet_valid"] = difference <= threshold

    return df


# =============================================================================
# EXTRACT ALL COMPANIES
# =============================================================================

def extract_all_statements():
    """
    Extract balance sheet, income statement, and cash flow
    for every company in company_facts/.

    For each company:
      1. Extract all three statements independently
      2. Left-join on period identifiers (balance sheet is the base)
      3. Add ticker from filename

    Returns a wide-format DataFrame with all financial fields.
    """

    all_frames = []

    files = sorted(
        COMPANY_FACTS_DIR.glob("*.json")
    )

    logger.info("Processing %d Company Facts files...", len(files))

    for file in files:

        company_json = load_company_json(file)

        if not company_json:
            continue

        # -------------------------------------------------
        # Extract each statement independently
        # -------------------------------------------------

        df_bs = extract_balance_sheet(company_json)
        df_is = extract_income_statement(company_json)
        df_cf = extract_cash_flow(company_json)

        # Skip if nothing extractable at all
        if df_bs.empty and df_is.empty and df_cf.empty:
            continue

        # -------------------------------------------------
        # Merge on shared period keys
        # Balance sheet is the base (left join)
        # -------------------------------------------------

        merge_keys = [
            "company",
            "cik",
            "period_end",
            "filing_date",
            "fiscal_year",
            "fiscal_quarter",
        ]

        if not df_bs.empty:
            df = df_bs.copy()
        elif not df_is.empty:
            df = df_is.copy()
        else:
            df = df_cf.copy()

        if not df_is.empty:
            df = df.merge(
                df_is,
                on=merge_keys,
                how="left",
                suffixes=("", "_is"),
            )

        if not df_cf.empty:
            df = df.merge(
                df_cf,
                on=merge_keys,
                how="left",
                suffixes=("", "_cf"),
            )

        # -------------------------------------------------
        # Add ticker from filename
        # -------------------------------------------------

        df.insert(1, "ticker", file.stem)

        all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    dataset = pd.concat(all_frames, ignore_index=True)

    # ---------------------------------------------
    # Merge metadata
    # ---------------------------------------------

    dataset = merge_company_metadata(dataset)

    # ---------------------------------------------
    # Validate accounting identity
    # ---------------------------------------------

    dataset = validate_balance_sheet(dataset)

    # ---------------------------------------------
    # Sort records
    # ---------------------------------------------

    dataset = dataset.sort_values(
        ["ticker", "period_end"]
    ).reset_index(drop=True)

    # ---------------------------------------------
    # Remove duplicate records
    # ---------------------------------------------

    dataset = dataset.drop_duplicates(
        subset=["ticker", "period_end"]
    ).reset_index(drop=True)

    # ---------------------------------------------
    # Ensure every configured financial column exists
    # ---------------------------------------------

    all_financial_columns = (
        list(BALANCE_SHEET_TAGS.keys())
        + list(INCOME_STATEMENT_TAGS.keys())
        + list(CASH_FLOW_TAGS.keys())
    )

    for column in all_financial_columns:
        if column not in dataset.columns:
            dataset[column] = pd.NA

    # ---------------------------------------------
    # Final column ordering
    # ---------------------------------------------

    ordered_columns = [
        "company",
        "ticker",
        "cik",
        "sic_code",
        "sic_description",
        "target_sector",
        "filing_date",
        "period_end",
        "fiscal_year",
        "fiscal_quarter",
    ]

    # Balance sheet columns
    ordered_columns.extend(BALANCE_SHEET_TAGS.keys())

    # Income statement columns
    ordered_columns.extend(INCOME_STATEMENT_TAGS.keys())

    # Cash flow columns
    ordered_columns.extend(CASH_FLOW_TAGS.keys())

    # Validation columns
    ordered_columns.extend([
        "balance_sheet_difference",
        "balance_sheet_valid",
    ])

    # Only select columns that actually exist
    ordered_columns = [
        c for c in ordered_columns if c in dataset.columns
    ]

    dataset = dataset[ordered_columns]

    return dataset


# Backward compatibility alias
extract_all_balance_sheets = extract_all_statements


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":

    logger.info("EXTRACT ALL FINANCIAL STATEMENTS")

    dataset = extract_all_statements()

    if dataset.empty:

        logger.warning("No balance sheet data extracted.")

    else:

        print()

        print(dataset.head())

        print()

        print(dataset.info())

        print()

        logger.info("SUMMARY")

        logger.info("Rows: %d", len(dataset))
        logger.info("Companies: %d", dataset["ticker"].nunique())
        logger.info(
            "Fiscal Years: %s - %s",
            dataset["fiscal_year"].min(),
            dataset["fiscal_year"].max(),
        )
        logger.info("Latest Period: %s", dataset["period_end"].max())
        logger.info(
            "Valid Balance Sheets: %d",
            dataset["balance_sheet_valid"].sum(),
        )
        logger.info(
            "Invalid Balance Sheets: %d",
            (~dataset["balance_sheet_valid"]).sum(),
        )
        logger.info(
            "Columns: %d",
            len(dataset.columns),
        )

        print()

        logger.info("MISSING VALUES")

        print(
            dataset.isna().sum().sort_values(
                ascending=False
            )
        )

        print()

        logger.info("NUMERIC SUMMARY")

        print(
            dataset.describe(
                include="all"
            )
        )
