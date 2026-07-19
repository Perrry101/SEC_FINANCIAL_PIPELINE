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
    logger,
)

from download_companies import get_company_list


# ==============================================================================
# DOWNLOAD SINGLE COMPANY
# ==============================================================================

def download_company_facts(cik: str, ticker: str) -> bool:
    """
    Download Company Facts JSON for one company.

    Uses exponential backoff on retries and handles HTTP 429
    (rate limit) responses with a longer cooldown.

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
        logger.info("Skipping %s (already exists)", ticker)
        return True

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = requests.get(
                url,
                headers=SEC_HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            # ---------------------------------------------------------
            # Rate limited — back off longer
            # ---------------------------------------------------------
            if response.status_code == 429:
                wait = 2 ** attempt * 5
                logger.warning(
                    "%s: Rate limited (429). Waiting %ds",
                    ticker, wait,
                )
                time.sleep(wait)
                continue

            if response.status_code == 200:

                data = response.json()

                # -----------------------------------------------------
                # Validate expected SEC JSON structure
                # -----------------------------------------------------
                if "facts" not in data:
                    logger.warning(
                        "%s: Response missing 'facts' key, skipping",
                        ticker,
                    )
                    return False

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)

                time.sleep(REQUEST_DELAY)

                return True

            logger.warning(
                "%s: HTTP %d", ticker, response.status_code
            )

        except json.JSONDecodeError:
            logger.error(
                "%s: Response was not valid JSON (attempt %d)",
                ticker, attempt,
            )

        except requests.exceptions.RequestException as e:
            logger.error(
                "%s: Request failed (attempt %d): %s",
                ticker, attempt, e,
            )

        # Exponential backoff: 2s, 4s, 8s, ...
        wait = 2 ** attempt
        time.sleep(wait)

    return False


# ==============================================================================
# DOWNLOAD ALL COMPANIES
# ==============================================================================

def download_all_company_facts():

    companies = get_company_list()

    success = 0
    failed = 0

    logger.info("DOWNLOADING COMPANY FACTS")
    logger.info("Total companies: %d", len(companies))

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

    logger.info(
        "Download complete — Downloaded: %d | Failed: %d",
        success, failed,
    )


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":

    download_all_company_facts()