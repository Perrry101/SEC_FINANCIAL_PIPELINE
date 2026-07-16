"""
create_dataset.py

Creates the final financial dataset from the extracted
SEC Company Facts data.
"""

import pandas as pd

from extract_balance_sheet import extract_all_balance_sheets

from config import (
    OUTPUT_DATASET,
    LOG_SEPARATOR,
)


# ==============================================================================
# CLEAN DATASET
# ==============================================================================

def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Basic cleaning.
    """

    df = df.copy()

    # -------------------------------------------------------------------------
    # Convert dates
    # -------------------------------------------------------------------------

    df["period_end"] = pd.to_datetime(df["period_end"])

    df["filing_date"] = pd.to_datetime(df["filing_date"])

    # -------------------------------------------------------------------------
    # Sort records
    # -------------------------------------------------------------------------

    df = df.sort_values(
        [
            "ticker",
            "fiscal_year",
            "fiscal_quarter",
            "period_end",
        ]
    )

    # -------------------------------------------------------------------------
    # Remove duplicate company-quarter observations
    # -------------------------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "ticker",
            "period_end",
        ]
    )

    df.reset_index(
        drop=True,
        inplace=True
    )

    return df


# ==============================================================================
# FEATURE ENGINEERING
# ==============================================================================

def calculate_financial_ratios(
    df: pd.DataFrame
) -> pd.DataFrame:

    df = df.copy()

    # -------------------------------------------------------------------------
    # Working Capital
    # -------------------------------------------------------------------------

    df["working_capital"] = (

        df["current_assets"]

        -

        df["current_liabilities"]

    )

    # -------------------------------------------------------------------------
    # Liquidity Ratios
    # -------------------------------------------------------------------------

    df["current_ratio"] = (

        df["current_assets"]

        /

        df["current_liabilities"].replace(0, pd.NA)

    )

    df["cash_ratio"] = (

        df["cash"]

        /

        df["current_liabilities"].replace(0, pd.NA)

    )

    # -------------------------------------------------------------------------
    # Leverage Ratios
    # -------------------------------------------------------------------------

    df["debt_to_equity"] = (

        df["total_liabilities"]

        /

        df["equity"].replace(0, pd.NA)

    )

    df["debt_to_assets"] = (

        df["total_liabilities"]

        /

        df["total_assets"].replace(0, pd.NA)

    )

    # -------------------------------------------------------------------------
    # Round ratios
    # -------------------------------------------------------------------------

    ratio_columns = [

        "working_capital",

        "current_ratio",

        "cash_ratio",

        "debt_to_equity",

        "debt_to_assets",

    ]

    df[ratio_columns] = df[
        ratio_columns
    ].round(4)

    return df


# ==============================================================================
# SAVE DATASET
# ==============================================================================

def save_dataset(
    df: pd.DataFrame
):

    OUTPUT_DATASET.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_DATASET,
        index=False,
        encoding="utf-8-sig"
    )

    print()

    print(
        f"Dataset saved to:\n{OUTPUT_DATASET}"
    )


# ==============================================================================
# MAIN PIPELINE
# ==============================================================================

def main():

    print(LOG_SEPARATOR)
    print("CREATE FINANCIAL DATASET")
    print(LOG_SEPARATOR)

    # -------------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------------

    print("\nExtracting financial statements...\n")

    df = extract_all_balance_sheets()

    print(
        f"Rows extracted : {len(df):,}"
    )

    # -------------------------------------------------------------------------
    # Cleaning
    # -------------------------------------------------------------------------

    print("\nCleaning dataset...\n")

    df = clean_dataset(df)

    print(
        f"Rows after cleaning : {len(df):,}"
    )

    # -------------------------------------------------------------------------
    # Feature Engineering
    # -------------------------------------------------------------------------

    print("\nCalculating financial ratios...\n")

    df = calculate_financial_ratios(df)

    # -------------------------------------------------------------------------
    # Preview
    # -------------------------------------------------------------------------

    print(LOG_SEPARATOR)
    print("DATASET PREVIEW")
    print(LOG_SEPARATOR)

    print(df.head())

    # -------------------------------------------------------------------------
    # Save
    # -------------------------------------------------------------------------

    save_dataset(df)

    # -------------------------------------------------------------------------
    # Dataset Info
    # -------------------------------------------------------------------------

    print()

    print(LOG_SEPARATOR)
    print("DATASET INFO")
    print(LOG_SEPARATOR)

    print(df.info())

    # -------------------------------------------------------------------------
    # Accounting Validation
    # -------------------------------------------------------------------------

    print()

    print(LOG_SEPARATOR)
    print("ACCOUNTING VALIDATION")
    print(LOG_SEPARATOR)

    print(
        df["balance_sheet_valid"]
        .value_counts(dropna=False)
    )

    # -------------------------------------------------------------------------
    # Missing Values
    # -------------------------------------------------------------------------

    print()

    print(LOG_SEPARATOR)
    print("MISSING VALUES")
    print(LOG_SEPARATOR)

    print(
        df.isna()
        .sum()
        .sort_values(
            ascending=False
        )
    )

    # -------------------------------------------------------------------------
    # Summary Statistics
    # -------------------------------------------------------------------------

    print()

    print(LOG_SEPARATOR)
    print("SUMMARY STATISTICS")
    print(LOG_SEPARATOR)

    print(
        df.describe(
            include="all"
        )
    )

    # -------------------------------------------------------------------------
    # Pipeline Complete
    # -------------------------------------------------------------------------

    print()

    print(LOG_SEPARATOR)
    print("PIPELINE COMPLETED")
    print(LOG_SEPARATOR)

    print(f"Total Rows      : {len(df):,}")

    print(
        f"Companies       : {df['ticker'].nunique():,}"
    )

    print(
        f"Fiscal Years    : "
        f"{df['fiscal_year'].min()} - "
        f"{df['fiscal_year'].max()}"
    )

    print(
        f"Dataset Saved   : {OUTPUT_DATASET}"
    )


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    main()