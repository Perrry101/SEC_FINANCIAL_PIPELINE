"""
create_dataset.py

Creates the final financial dataset from the extracted
SEC Company Facts data.
"""

import numpy as np
import pandas as pd

from extract_balance_sheet import extract_all_statements

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
    # Helper: safe divide — NaN where denominator is zero
    # -------------------------------------------------------------------------

    def safe_div(num, den):
        return np.divide(
            num,
            den,
            out=np.full(len(df), np.nan),
            where=den.fillna(0).ne(0),
        )

    # -------------------------------------------------------------------------
    # Liquidity Ratios
    # -------------------------------------------------------------------------

    df["working_capital"] = (
        df["current_assets"] - df["current_liabilities"]
    )

    df["current_ratio"] = safe_div(
        df["current_assets"], df["current_liabilities"]
    )

    df["cash_ratio"] = safe_div(
        df["cash"], df["current_liabilities"]
    )

    # -------------------------------------------------------------------------
    # Leverage Ratios
    # -------------------------------------------------------------------------

    df["debt_to_equity"] = safe_div(
        df["total_liabilities"], df["equity"]
    )

    df["debt_to_assets"] = safe_div(
        df["total_liabilities"], df["total_assets"]
    )

    df["interest_coverage"] = safe_div(
        df["operating_income"], df["interest_expense"]
    )

    # -------------------------------------------------------------------------
    # Profitability Ratios
    # -------------------------------------------------------------------------

    df["gross_margin"] = safe_div(
        df["gross_profit"], df["revenue"]
    )

    df["operating_margin"] = safe_div(
        df["operating_income"], df["revenue"]
    )

    df["net_margin"] = safe_div(
        df["net_income"], df["revenue"]
    )

    df["roa"] = safe_div(
        df["net_income"], df["total_assets"]
    )

    df["roe"] = safe_div(
        df["net_income"], df["equity"]
    )

    # -------------------------------------------------------------------------
    # Efficiency Ratios
    # -------------------------------------------------------------------------

    df["asset_turnover"] = safe_div(
        df["revenue"], df["total_assets"]
    )

    df["receivables_turnover"] = safe_div(
        df["revenue"], df["receivables"]
    )

    df["inventory_turnover"] = safe_div(
        df["cost_of_revenue"], df["inventory"]
    )

    # -------------------------------------------------------------------------
    # Cash Flow / Earnings Quality Ratios
    # -------------------------------------------------------------------------

    df["ocf_to_net_income"] = safe_div(
        df["operating_cash_flow"], df["net_income"]
    )

    df["free_cash_flow"] = (
        df["operating_cash_flow"] - df["capital_expenditure"]
    )

    df["accruals_ratio"] = safe_div(
        df["net_income"] - df["operating_cash_flow"],
        df["total_assets"],
    )

    # -------------------------------------------------------------------------
    # Investment Ratios
    # -------------------------------------------------------------------------

    df["capex_to_revenue"] = safe_div(
        df["capital_expenditure"], df["revenue"]
    )

    df["depreciation_to_revenue"] = safe_div(
        df["depreciation"], df["revenue"]
    )

    # -------------------------------------------------------------------------
    # Round all ratio columns
    # -------------------------------------------------------------------------

    ratio_columns = [
        "working_capital",
        "current_ratio",
        "cash_ratio",
        "debt_to_equity",
        "debt_to_assets",
        "interest_coverage",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roa",
        "roe",
        "asset_turnover",
        "receivables_turnover",
        "inventory_turnover",
        "ocf_to_net_income",
        "free_cash_flow",
        "accruals_ratio",
        "capex_to_revenue",
        "depreciation_to_revenue",
    ]

    # Only round columns that exist
    ratio_columns = [c for c in ratio_columns if c in df.columns]
    df[ratio_columns] = df[ratio_columns].round(4)

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

    logger.info("Extracting all financial statements...")

    df = extract_all_statements()

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
    logger.info("Total Columns: %d", len(df.columns))
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