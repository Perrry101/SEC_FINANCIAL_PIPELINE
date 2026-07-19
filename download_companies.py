"""
download_companies.py

Loads, validates and cleans the company universe
for the SEC Financial Pipeline.
"""

from pathlib import Path
import pandas as pd

from config import (
    COMPANIES_FILE,
    LOG_SEPARATOR,
    logger,
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
    Load companies.csv.
    """

    if not file_path.exists():
        raise FileNotFoundError(
            f"\nCompany file not found:\n{file_path}"
        )

    df = pd.read_csv(file_path)

    return df


# =============================================================================
# VALIDATE
# =============================================================================

def validate_companies(df: pd.DataFrame) -> None:
    """
    Validate required columns.
    """

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    if df.empty:
        raise ValueError("companies.csv is empty.")


# =============================================================================
# CLEAN COMPANY LIST
# =============================================================================

def clean_companies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize company information.
    """

    df = df.copy()

    # ---------------------------------------------------------
    # Remove rows with missing required values
    # ---------------------------------------------------------

    df = df.dropna(
        subset=[
            "ticker",
            "cik",
            "company",
        ]
    )

    # ---------------------------------------------------------
    # Remove empty strings
    # ---------------------------------------------------------

    df = df[
        df["ticker"].astype(str).str.strip() != ""
    ]

    df = df[
        df["company"].astype(str).str.strip() != ""
    ]

    # ---------------------------------------------------------
    # Standardize ticker
    # ---------------------------------------------------------

    df["ticker"] = (
        df["ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # ---------------------------------------------------------
    # Standardize company name
    # ---------------------------------------------------------

    df["company"] = (
        df["company"]
        .astype(str)
        .str.strip()
    )

    # ---------------------------------------------------------
    # SEC requires 10-digit CIK
    # Handles float strings like "320193.0" and plain "320193"
    # ---------------------------------------------------------

    df["cik"] = (
        pd.to_numeric(df["cik"], errors="coerce")
        .fillna(0)
        .astype(int)
        .astype(str)
        .str.zfill(10)
    )

    # ---------------------------------------------------------
    # Remove duplicate ticker
    # ---------------------------------------------------------

    df = df.drop_duplicates(
        subset="ticker",
        keep="first",
    )

    # ---------------------------------------------------------
    # Remove duplicate CIK
    # ---------------------------------------------------------

    df = df.drop_duplicates(
        subset="cik",
        keep="first",
    )

    # ---------------------------------------------------------
    # Optional columns
    # ---------------------------------------------------------

    optional_columns = [
        "sic_code",
        "sic_description",
        "target_sector",
    ]

    for column in optional_columns:

        if column not in df.columns:
            df[column] = ""

    # ---------------------------------------------------------
    # Reorder columns
    # ---------------------------------------------------------

    ordered_columns = [
        "ticker",
        "cik",
        "company",
        "sic_code",
        "sic_description",
        "target_sector",
    ]

    df = df[ordered_columns]

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# =============================================================================
# PIPELINE
# =============================================================================

def get_company_list() -> pd.DataFrame:
    """
    Load + validate + clean company list.
    """

    companies = load_companies()

    validate_companies(companies)

    companies = clean_companies(companies)

    return companies


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":

    print(LOG_SEPARATOR)
    print("LOAD COMPANY LIST")
    print(LOG_SEPARATOR)

    companies = get_company_list()

    print(f"\nTotal Companies : {len(companies)}\n")

    print(companies.head(20))

    print("\nData Types\n")

    print(companies.dtypes)

    print("\nMissing Values\n")

    print(companies.isna().sum())

    print("\nDone.")