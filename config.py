"""
config.py

Central configuration file for the SEC Financial Pipeline.

This module contains:
- SEC API configuration
- Project directory paths
- HTTP settings
- Dataset configuration
"""

from pathlib import Path

# =============================================================================
# PROJECT DIRECTORIES
# =============================================================================

# Root directory of the project
# Root directory of the project
PROJECT_ROOT = Path(__file__).resolve().parent

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Raw SEC JSON storage
COMPANY_FACTS_DIR = RAW_DATA_DIR / "company_facts"

# Output dataset
OUTPUT_DATASET = PROCESSED_DATA_DIR / "financial_dataset.csv"

# Company list
COMPANIES_FILE = PROJECT_ROOT / "companies.csv"

# =============================================================================
# CREATE DIRECTORIES IF THEY DON'T EXIST
# =============================================================================

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
COMPANY_FACTS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# SEC API CONFIGURATION
# =============================================================================

SEC_BASE_URL = "https://data.sec.gov"

COMPANY_FACTS_API = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)

SUBMISSIONS_API = (
    "https://data.sec.gov/submissions/CIK{cik}.json"
)

# =============================================================================
# HTTP REQUEST SETTINGS
# =============================================================================

# Replace with your own details before running
SEC_HEADERS = {
    "User-Agent": "Your Name your_email@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

REQUEST_TIMEOUT = 30          # seconds
REQUEST_DELAY = 0.25          # seconds between SEC requests
MAX_RETRIES = 3

# =============================================================================
# BALANCE SHEET TAGS
# =============================================================================

BALANCE_SHEET_TAGS = {

    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashCashEquivalentsRestrictedCash",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],

    "short_term_investments": [
        "AvailableForSaleSecuritiesCurrent",
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
    ],

    "receivables": [
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
    ],

    "inventory": [
        "InventoryNet",
        "InventoryCurrent",
        "InventoryFinishedGoods",
        "InventoryGross",
    ],

    "current_assets": [
        "AssetsCurrent",
    ],

    "ppe": [
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentGross",
    ],

    "goodwill": [
        "Goodwill",
    ],

    "intangible_assets": [
        "FiniteLivedIntangibleAssetsNet",
        "IntangibleAssetsNetExcludingGoodwill",
    ],

    "total_assets": [
        "Assets",
    ],

    "accounts_payable": [
        "AccountsPayableCurrent",
    ],

    "current_liabilities": [
        "LiabilitiesCurrent",
    ],

    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermBorrowings",
    ],

    "total_liabilities": [
        "Liabilities",
    ],

    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
}
# Some companies use alternate tag names.
# These can be added later if required.

# =============================================================================
# INCOME STATEMENT TAGS
# =============================================================================

INCOME_STATEMENT_TAGS = {

    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ],

    "cost_of_revenue": [
        "CostOfGoodsSold",
        "CostOfRevenue",
    ],

    "gross_profit": [
        "GrossProfit",
    ],

    "operating_income": [
        "OperatingIncomeLoss",
    ],

    "pretax_income": [
        "IncomeBeforeTaxExpenseBenefit",
    ],

    "income_tax": [
        "IncomeTaxExpenseBenefit",
    ],

    "net_income": [
        "NetIncomeLoss",
    ],

    "interest_expense": [
        "InterestExpense",
    ],

    "basic_eps": [
        "EarningsPerShareBasic",
    ],

    "diluted_eps": [
        "EarningsPerShareDiluted",
    ],
}

# =============================================================================
# CASH FLOW TAGS
# =============================================================================

CASH_FLOW_TAGS = {

    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByOperatingActivities",
    ],

    "investing_cash_flow": [
        "NetCashProvidedByUsedInInvestingActivities",
    ],

    "financing_cash_flow": [
        "NetCashProvidedByUsedInFinancingActivities",
    ],

    "capital_expenditure": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],

    "depreciation": [
        "Depreciation",
        "DepreciationAndAmortization",
    ],

    "amortization": [
        "AmortizationOfIntangibleAssets",
    ],
}

# =============================================================================
# DATASET COLUMNS
# =============================================================================

DATASET_COLUMNS = [
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

# =============================================================================
# LOGGING
# =============================================================================

LOG_SEPARATOR = "=" * 80

# =============================================================================
# MAIN (FOR QUICK TESTING)
# =============================================================================

if __name__ == "__main__":
    print(LOG_SEPARATOR)
    print("SEC Financial Pipeline Configuration")
    print(LOG_SEPARATOR)

    print(f"Project Root       : {PROJECT_ROOT}")
    print(f"Raw Data Directory : {RAW_DATA_DIR}")
    print(f"Processed Data Dir : {PROCESSED_DATA_DIR}")
    print(f"Company Facts Dir  : {COMPANY_FACTS_DIR}")
    print(f"Companies File     : {COMPANIES_FILE}")
    print(f"Output Dataset     : {OUTPUT_DATASET}")

    print("\nConfiguration loaded successfully.")

