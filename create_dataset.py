"""
create_dataset.py

Creates the final financial dataset from the extracted
SEC Company Facts data.
"""

import numpy as np
import pandas as pd

from extract_balance_sheet import extract_all_balance_sheets

from config import (
    OUTPUT_DATASET,
    LOG_SEPARATOR,
    logger,
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
        df["current_assets"] - df["current_liabilities"]
    )

    # -------------------------------------------------------------------------
    # Liquidity Ratios
    # Safe division: np.divide with where avoids replacing
    # zero with NA (which would silently drop valid companies
    # that genuinely have zero liabilities).
    # -------------------------------------------------------------------------

    df["current_ratio"] = np.divide(
        df["current_assets"],
        df["current_liabilities"],
        out=np.full(len(df), np.nan),
        where=df["current_liabilities"].fillna(0).ne(0),
    )

    df["cash_ratio"] = np.divide(
        df["cash"],
        df["current_liabilities"],
        out=np.full(len(df), np.nan),
        where=df["current_liabilities"].fillna(0).ne(0),
    )

    # -------------------------------------------------------------------------
    # Leverage Ratios
    # -------------------------------------------------------------------------

    df["debt_to_equity"] = np.divide(
        df["total_liabilities"],
        df["equity"],
        out=np.full(len(df), np.nan),
        where=df["equity"].fillna(0).ne(0),
    )

    df["debt_to_assets"] = np.divide(
        df["total_liabilities"],
        df["total_assets"],
        out=np.full(len(df), np.nan),
        where=df["total_assets"].fillna(0).ne(0),
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

    logger.info("CREATE FINANCIAL DATASET")

    # -------------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------------

    logger.info("Extracting financial statements...")

    df = extract_all_balance_sheets()

    logger.info("Rows extracted: %d", len(df))

    # -------------------------------------------------------------------------
    # Cleaning
    # -------------------------------------------------------------------------

    logger.info("Cleaning dataset...")

    df = clean_dataset(df)

    logger.info("Rows after cleaning: %d", len(df))

    # -------------------------------------------------------------------------
    # Feature Engineering
    # -------------------------------------------------------------------------

    logger.info("Calculating financial ratios...")

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

    logger.info("ACCOUNTING VALIDATION")

    print(
        df["balance_sheet_valid"]
        .value_counts(dropna=False)
    )

    # -------------------------------------------------------------------------
    # Missing Values
    # -------------------------------------------------------------------------

    print()

    logger.info("MISSING VALUES")

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

    logger.info("SUMMARY STATISTICS")

    print(
        df.describe(
            include="all"
        )
    )

    # -------------------------------------------------------------------------
    # Pipeline Complete
    # -------------------------------------------------------------------------

    print()

    logger.info("PIPELINE COMPLETE")
    logger.info("Total Rows: %d", len(df))
    logger.info("Companies: %d", df["ticker"].nunique())
    logger.info(
        "Fiscal Years: %s - %s",
        df["fiscal_year"].min(),
        df["fiscal_year"].max(),
    )
    logger.info("Dataset Saved: %s", OUTPUT_DATASET)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    main()