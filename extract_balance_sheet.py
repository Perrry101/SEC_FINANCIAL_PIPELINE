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
    unit: str = "USD",
):
    """
    Extract one XBRL tag.

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

    try:

        units = (
            company_data["facts"]
            ["us-gaap"]
            [tag_name]
            ["units"]
        )

    except KeyError:

        return {}

    if unit not in units:

        return {}

    extracted = {}

    for item in units[unit]:

        # -----------------------------------------------------
        # Keep quarterly and annual reports
        # -----------------------------------------------------

        if item.get("form") not in ("10-Q", "10-K"):

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

def extract_all_balance_sheets():

    all_frames = []

    files = sorted(

        COMPANY_FACTS_DIR.glob(

            "*.json"

        )

    )

    logger.info("Processing %d Company Facts files...", len(files))

    for file in files:

        company_json = load_company_json(

            file

        )

        if not company_json:

            continue

        df = extract_balance_sheet(

            company_json

        )

        if df.empty:

            continue

        # ---------------------------------------------
        # Add ticker from filename
        # ---------------------------------------------

        df.insert(

            1,

            "ticker",

            file.stem,

        )

        all_frames.append(

            df

        )

    if not all_frames:

        return pd.DataFrame()

    dataset = pd.concat(

        all_frames,

        ignore_index=True,

    )

    # ---------------------------------------------
    # Merge metadata
    # ---------------------------------------------

    dataset = merge_company_metadata(

        dataset

    )

    # ---------------------------------------------
    # Validate accounting identity
    # ---------------------------------------------

    dataset = validate_balance_sheet(

        dataset

    )

    # ---------------------------------------------
    # Sort records
    # ---------------------------------------------

    dataset = dataset.sort_values(

        [

            "ticker",

            "period_end",

        ]

    ).reset_index(

        drop=True

    )
    # ---------------------------------------------
    # Remove duplicate records
    # ---------------------------------------------

    dataset = dataset.drop_duplicates(

        subset=[

            "ticker",

            "period_end",

        ]

    ).reset_index(

        drop=True

    )

    # ---------------------------------------------
    # Ensure every configured financial column exists
    # ---------------------------------------------

    financial_columns = list(
        BALANCE_SHEET_TAGS.keys()
    )

    for column in financial_columns:

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

    ordered_columns.extend(
        financial_columns
    )

    ordered_columns.extend(

        [

            "balance_sheet_difference",

            "balance_sheet_valid",

        ]

    )

    dataset = dataset[
        ordered_columns
    ]

    return dataset


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":

    logger.info("EXTRACT BALANCE SHEETS")

    dataset = extract_all_balance_sheets()

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
