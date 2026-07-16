"""
extract_balance_sheet.py

Extract quarterly balance sheet information from
SEC Company Facts JSON files.
"""

import json
from pathlib import Path

import pandas as pd

from config import (
    COMPANY_FACTS_DIR,
    BALANCE_SHEET_TAGS,
    LOG_SEPARATOR,
)


# ==============================================================================
# LOAD JSON
# ==============================================================================

def load_company_json(file_path: Path) -> dict:

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# EXTRACT A SINGLE US-GAAP TAG
# ==============================================================================

def extract_tag(company_data: dict, tag_name: str):
    """
    Returns

    {
        period_end : value
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

    # Most companies report in USD
    if "USD" not in units:
        return {}

    values = {}

    for item in units["USD"]:

        # Keep only quarterly filings
        if item.get("form") != "10-Q":
            continue

        period = item.get("end")

        value = item.get("val")

        if period and value is not None:
            values[period] = value

    return values


# ==============================================================================
# EXTRACT BALANCE SHEET
# ==============================================================================

def extract_balance_sheet(company_json: dict) -> pd.DataFrame:

    entity_name = company_json.get("entityName", "")

    cik = str(company_json.get("cik", "")).zfill(10)

    periods = {}

    # --------------------------------------------
    # Extract every configured balance sheet tag
    # --------------------------------------------

    for column, us_gaap_tag in BALANCE_SHEET_TAGS.items():

        tag_values = extract_tag(
            company_json,
            us_gaap_tag
        )

        for period, value in tag_values.items():

            if period not in periods:

                periods[period] = {
                    "company": entity_name,
                    "cik": cik,
                    "period_end": period
                }

            periods[period][column] = value

    if not periods:
        return pd.DataFrame()

    df = pd.DataFrame(periods.values())

    df = df.sort_values(
        "period_end"
    ).reset_index(drop=True)

    return df


# ==============================================================================
# EXTRACT ALL COMPANIES
# ==============================================================================

def extract_all_balance_sheets():

    all_frames = []

    files = sorted(
        COMPANY_FACTS_DIR.glob("*.json")
    )

    for file in files:

        company_json = load_company_json(file)

        df = extract_balance_sheet(company_json)

        if df.empty:
            continue

        df.insert(
            1,
            "ticker",
            file.stem
        )

        all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    return pd.concat(
        all_frames,
        ignore_index=True
    )


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":

    print(LOG_SEPARATOR)
    print("EXTRACT BALANCE SHEETS")
    print(LOG_SEPARATOR)

    dataset = extract_all_balance_sheets()

    print()

    print(dataset.head())

    print()

    print(dataset.info())

    print()

    print(f"Rows : {len(dataset)}")

    print(f"Companies : {dataset['ticker'].nunique()}")