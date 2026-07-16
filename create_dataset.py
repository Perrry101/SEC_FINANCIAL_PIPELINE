"""
create_dataset.py

Creates the final balance sheet dataset from the extracted
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

    # Convert date
    df["period_end"] = pd.to_datetime(df["period_end"])

    # Sort
    df = df.sort_values(
        ["ticker", "period_end"]
    )

    # Remove duplicate company-quarter observations
    df = df.drop_duplicates(
        subset=["ticker", "period_end"]
    )

    df.reset_index(
        drop=True,
        inplace=True
    )

    return df


# ==============================================================================
# FEATURE ENGINEERING
# ==============================================================================

def calculate_financial_ratios(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    # Working Capital
    df["working_capital"] = (
        df["current_assets"] -
        df["current_liabilities"]
    )

    # Current Ratio
    df["current_ratio"] = (
        df["current_assets"] /
        df["current_liabilities"]
    )

    # Debt to Equity
    df["debt_to_equity"] = (
        df["total_liabilities"] /
        df["equity"]
    )

    # Debt to Assets
    df["debt_to_assets"] = (
        df["total_liabilities"] /
        df["total_assets"]
    )

    # Cash Ratio
    df["cash_ratio"] = (
        df["cash"] /
        df["current_liabilities"]
    )

    return df


# ==============================================================================
# SAVE DATASET
# ==============================================================================

def save_dataset(df: pd.DataFrame):

    OUTPUT_DATASET.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_csv(
        OUTPUT_DATASET,
        index=False
    )

    print()
    print(f"Dataset saved to:\n{OUTPUT_DATASET}")


# ==============================================================================
# MAIN PIPELINE
# ==============================================================================

def main():

    print(LOG_SEPARATOR)
    print("CREATE BALANCE SHEET DATASET")
    print(LOG_SEPARATOR)

    print("\nExtracting balance sheets...")

    df = extract_all_balance_sheets()

    print(f"Rows extracted : {len(df)}")

    print("\nCleaning dataset...")

    df = clean_dataset(df)

    print(f"Rows after cleaning : {len(df)}")

    print("\nCalculating financial ratios...")

    df = calculate_financial_ratios(df)

    print("\nDataset Preview\n")

    print(df.head())

    save_dataset(df)

    print()

    print(df.info())

    print()

    print(df.describe(include="all"))

    print()

    print(LOG_SEPARATOR)
    print("PIPELINE COMPLETED")
    print(LOG_SEPARATOR)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    main()