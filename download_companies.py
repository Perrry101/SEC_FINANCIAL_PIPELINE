"""
download_companies.py

Loads and validates the company universe for the SEC Financial Pipeline.
"""

from pathlib import Path
import pandas as pd

from config import (
    COMPANIES_FILE,
    LOG_SEPARATOR,
)

# =============================================================================
# REQUIRED COLUMNS
# =============================================================================

REQUIRED_COLUMNS = [
    "ticker",
    "cik",
    "company",
]


# =============================================================================
# LOAD COMPANY LIST
# =============================================================================

def load_companies(file_path: Path = COMPANIES_FILE) -> pd.DataFrame:
    """
    Load companies.csv into a DataFrame.

    Parameters
    ----------
    file_path : Path

    Returns
    -------
    pandas.DataFrame
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"\nCompany file not found:\n{file_path}"
        )

    df = pd.read_csv(file_path)

    return df


# =============================================================================
# VALIDATE COMPANY LIST
# =============================================================================

def validate_companies(df: pd.DataFrame) -> None:
    """
    Validate the company DataFrame.
    """

    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    if df.empty:
        raise ValueError(
            "companies.csv is empty."
        )


# =============================================================================
# CLEAN DATA
# =============================================================================

def clean_companies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize company information.
    """

    df = df.copy()

    # Remove whitespace
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    df["company"] = (
        df["company"]
        .astype(str)
        .str.strip()
    )

    # SEC requires 10-digit CIK
    df["cik"] = (
        df["cik"]
        .astype(str)
        .str.replace(".0", "", regex=False)
        .str.zfill(10)
    )

    # Remove duplicate tickers
    df = df.drop_duplicates(
        subset="ticker"
    ).reset_index(drop=True)

    return df


# =============================================================================
# PIPELINE FUNCTION
# =============================================================================

def get_company_list() -> pd.DataFrame:
    """
    Complete pipeline.

    Returns
    -------
    Clean company DataFrame
    """

    df = load_companies()

    validate_companies(df)

    df = clean_companies(df)

    return df


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    print(LOG_SEPARATOR)
    print("LOAD COMPANY LIST")
    print(LOG_SEPARATOR)

    companies = get_company_list()

    print(f"\nTotal Companies : {len(companies)}\n")

    print(companies)

    print("\nData Types\n")
    print(companies.dtypes)

    print("\nDone.")