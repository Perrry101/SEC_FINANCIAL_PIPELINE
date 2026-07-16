"""
download_filings.py

Downloads SEC Company Facts JSON files for every company in companies.csv.

Output:
data/raw/company_facts/{ticker}.json
"""

import json
import time
from pathlib import Path

import requests
from tqdm import tqdm

from config import (
    COMPANY_FACTS_API,
    COMPANY_FACTS_DIR,
    SEC_HEADERS,
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    MAX_RETRIES,
    LOG_SEPARATOR,
)

from download_companies import get_company_list


# ==============================================================================
# DOWNLOAD SINGLE COMPANY
# ==============================================================================

def download_company_facts(cik: str, ticker: str) -> bool:
    """
    Download Company Facts JSON for one company.

    Parameters
    ----------
    cik : str
        10-digit SEC CIK

    ticker : str
        Stock ticker

    Returns
    -------
    bool
        True if download succeeded
    """

    url = COMPANY_FACTS_API.format(cik=cik)

    output_file = COMPANY_FACTS_DIR / f"{ticker}.json"

    # Skip already downloaded files
    if output_file.exists():
        print(f"Skipping {ticker} (already exists)")
        return True

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = requests.get(
                url,
                headers=SEC_HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:

                data = response.json()

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)

                time.sleep(REQUEST_DELAY)

                return True

            print(
                f"{ticker}: HTTP {response.status_code}"
            )

        except Exception as e:

            print(
                f"{ticker}: Attempt {attempt} failed"
            )

            print(e)

            time.sleep(2)

    return False


# ==============================================================================
# DOWNLOAD ALL COMPANIES
# ==============================================================================

def download_all_company_facts():

    companies = get_company_list()

    success = 0
    failed = 0

    print(LOG_SEPARATOR)
    print("DOWNLOADING COMPANY FACTS")
    print(LOG_SEPARATOR)

    for _, row in tqdm(
        companies.iterrows(),
        total=len(companies)
    ):

        ok = download_company_facts(
            cik=row["cik"],
            ticker=row["ticker"]
        )

        if ok:
            success += 1
        else:
            failed += 1

    print()

    print(LOG_SEPARATOR)

    print(f"Downloaded : {success}")

    print(f"Failed     : {failed}")

    print(LOG_SEPARATOR)


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":

    download_all_company_facts()