# SEC Financial Pipeline

A Python data pipeline that pulls financial data directly from the U.S. Securities and Exchange Commission (SEC) EDGAR system, extracts balance sheet statements for ~500 manufacturing companies, and produces a single clean CSV dataset with computed financial ratios.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Directory Structure](#directory-structure)
4. [Pipeline Flow](#pipeline-flow)
5. [Module Breakdown](#module-breakdown)
   - [config.py](#configpy)
   - [test.py](#testpy)
   - [test2.py / test3.py / test4.py](#test2py--test3py--test4py)
   - [download_companies.py](#download_companiespy)
   - [download_filings.py](#download_filingspy)
   - [extract_balance_sheet.py](#extract_balance_sheetpy)
   - [create_dataset.py](#create_datasetpy)
6. [SEC API Endpoints Used](#sec-api-endpoints-used)
7. [Data Schema](#data-schema)
8. [Financial Tags Extracted](#financial-tags-extracted)
9. [How to Run](#how-to-run)
10. [Key Design Decisions](#key-design-decisions)

---

## Project Overview

This pipeline answers a simple question: **"What do the balance sheets of 500+ U.S. manufacturing companies look like over time?"**

It connects to the SEC's public EDGAR API, downloads XBRL-tagged financial facts in JSON format, parses every quarterly (10-Q) and annual (10-K) filing, and produces a panel dataset with:

- Raw balance sheet line items (cash, assets, liabilities, equity, etc.)
- Income statement line items (revenue, net income, EPS)
- Cash flow line items (operating cash flow, capex, depreciation)
- Computed financial ratios (current ratio, cash ratio, debt-to-equity, debt-to-assets)
- Accounting validation (does Assets = Liabilities + Equity?)
- Company metadata (SIC code, industry sector, ticker, CIK)

The dataset covers fiscal years **1998–2026** and is structured as one row per company per fiscal quarter.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SEC EDGAR (Public API)                    │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
           ▼                              ▼
   ┌───────────────┐            ┌────────────────────┐
   │   test.py     │            │  download_filings.py│
   │ (fetch all    │            │  (fetch company     │
   │  SEC companies│            │   facts JSON for    │
   │  + SIC codes) │            │   each company)     │
   └───────┬───────┘            └─────────┬──────────┘
           │                              │
           ▼                              ▼
   ┌───────────────┐            ┌────────────────────────┐
   │ all_sec_      │            │ data/raw/company_facts/ │
   │ companies.csv │            │   {TICKER}.json         │
   │ (10,409 rows) │            │   (one per company)     │
   └───────┬───────┘            └─────────┬──────────────┘
           │                              │
     Filter by                         Processed by
     SIC code                          extract_balance_sheet.py
           │                              │
           ▼                              ▼
   ┌───────────────┐            ┌────────────────────────┐
   │ companies.csv │            │ extract_balance_sheet.py│
   │ (525 mfg      │            │ (parse XBRL tags,      │
   │  companies)   │            │  validate accounting   │
   └───────┬───────┘            │  equation)             │
           │                    └─────────┬──────────────┘
           │                              │
           └──────────┬───────────────────┘
                      ▼
           ┌────────────────────┐
           │  create_dataset.py │
           │  (clean, compute   │
           │   ratios, save)    │
           └─────────┬──────────┘
                     ▼
           ┌─────────────────────────────────────┐
           │  data/processed/financial_dataset.csv│
           │  (final output — ready for analysis) │
           └─────────────────────────────────────┘
```

---

## Directory Structure

```
SEC_FINANCIAL_PIPELINE/
│
├── config.py                       # Central configuration (paths, API settings, XBRL tags)
├── test.py                         # Fetch all SEC companies (ticker, CIK, name)
├── test2.py                        # Fetch SIC codes via individual API calls (slow, small-batch)
├── test3.py                        # Fetch SIC codes via bulk ZIP download (fast, full dataset)
├── test4.py                        # Refined bulk SIC extraction with CIK format cleanup
│
├── download_companies.py           # Load, validate, clean companies.csv
├── download_filings.py             # Download Company Facts JSON for each company
├── extract_balance_sheet.py        # Parse balance sheets from JSON, validate accounting equation
├── create_dataset.py               # Final extraction, cleaning, ratio computation, export
│
├── companies.csv                   # Target company list (525 manufacturing companies)
├── all_sec_companies.csv           # Full SEC company index (10,409 companies)
├── all_sec_companies_categorized.csv # Full index + SIC codes + sector labels
├── sec_sector_classified.csv       # Sample SIC classification output
│
├── requirements.txt                # (empty — dependencies listed below)
├── .gitignore                      # Excludes __pycache__, *.csv, data/
├── README.md                       # (original placeholder)
│
├── data/
│   ├── raw/
│   │   └── company_facts/          # Downloaded SEC Company Facts JSON files
│   │       ├── AAPL.json
│   │       ├── MSFT.json
│   │       └── ... (one per company)
│   └── processed/
│       └── financial_dataset.csv   # Final output dataset
│
└── venv/                           # Python virtual environment
```

---

## Pipeline Flow

### Stage 1 — Seed the Company Universe (`test.py`)

Fetches the complete list of SEC-reporting companies from:
`https://www.sec.gov/files/company_tickers.json`

Output: `all_sec_companies.csv` — ~10,409 companies with ticker, CIK, and name.

### Stage 2 — Classify Companies by Sector (`test3.py` / `test4.py`)

Downloads the SEC bulk submissions archive (a ~100MB ZIP containing one JSON file per company), reads each company's SIC code, and maps it to a target sector:

| SIC Range | Sector |
|-----------|--------|
| 7370–7379, 3570–3577 | Technology |
| 2833–2836, 3840–3849 | Healthcare |
| 1311–1389, 2911–2999 | Energy |
| 5200–5999 | Retail |
| 3500–3599, 3600–3699, 3711–3799 | Industrials |
| 2000–2399, 2500–2599 | Consumer Goods |
| 2000–3999 (catch-all) | Manufacturing |

Output: `all_sec_companies_categorized.csv` — full index with SIC codes and sector labels.

### Stage 3 — Curate Target Companies (`companies.csv`)

A filtered subset of ~525 manufacturing companies pulled from the categorized index. This is the pipeline's working universe.

### Stage 4 — Download Financial Data (`download_filings.py`)

For each of the 525 companies, calls the SEC Company Facts API:

```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```

Each response is a massive JSON blob containing **every XBRL-tagged financial fact** the company has ever filed — balance sheet, income statement, cash flow, everything.

Output: one `{TICKER}.json` file per company in `data/raw/company_facts/`.

**Resilience features:**
- Skips already-downloaded files (safe to re-run)
- Exponential backoff on retries (2s → 4s → 8s)
- HTTP 429 rate limit detection (extra-long cooldown)
- Validates JSON structure before saving

### Stage 5 — Extract Balance Sheet (`extract_balance_sheet.py`)

Reads every JSON file and extracts balance sheet data using a generic XBRL tag extraction engine.

**How it works:**

1. For each financial concept (e.g., "cash"), tries multiple XBRL tag alternatives in priority order until one matches
2. Keeps only 10-Q (quarterly) and 10-K (annual) filing types
3. For duplicate periods, keeps the latest filing
4. Merges company metadata (SIC code, sector) from `companies.csv`
5. Validates the accounting equation: **Assets ≈ Liabilities + Equity**

**Validation tolerance:** A row is valid if the absolute difference is within **$1M** OR within **1% of total assets**, whichever is more lenient.

### Stage 6 — Build Final Dataset (`create_dataset.py`)

Calls `extract_all_balance_sheets()`, then:

1. **Cleans** — converts dates, removes duplicate company-quarter rows
2. **Computes ratios:**
   - `working_capital` = current_assets − current_liabilities
   - `current_ratio` = current_assets / current_liabilities
   - `cash_ratio` = cash / current_liabilities
   - `debt_to_equity` = total_liabilities / equity
   - `debt_to_assets` = total_liabilities / total_assets
3. **Saves** to `data/processed/financial_dataset.csv`
4. **Prints** summary stats, validation counts, and missing value report

---

## Module Breakdown

### `config.py`

Central hub. Every other module imports from here.

**Contains:**
- Project directory paths (`PROJECT_ROOT`, `DATA_DIR`, `COMPANY_FACTS_DIR`, etc.)
- SEC API endpoints and HTTP settings (User-Agent, timeout, delay, retries)
- Balance sheet validation tolerances (`VALIDATION_ABS_TOLERANCE`, `VALIDATION_PCT_TOLERANCE`)
- **XBRL tag dictionaries** — maps each financial concept to one or more SEC tag names:
  - `BALANCE_SHEET_TAGS` — 14 concepts (cash, receivables, inventory, assets, liabilities, equity, etc.)
  - `INCOME_STATEMENT_TAGS` — 10 concepts (revenue, COGS, gross profit, operating income, EPS, etc.)
  - `CASH_FLOW_TAGS` — 6 concepts (operating/investing/financing cash flow, capex, depreciation, amortization)
- Dataset column definitions
- Logging configuration (INFO level, timestamped format)

### `test.py`

One-shot script that fetches all SEC companies. Only needs to be run once to generate `all_sec_companies.csv`.

### `test2.py` / `test3.py` / `test4.py`

Iterative experiments for fetching SIC codes:
- `test2.py` — calls the submissions API one company at a time (slow, rate-limited)
- `test3.py` — downloads the bulk submissions ZIP and processes in memory (fast, full dataset)
- `test4.py` — refined version of test3 with CIK format cleanup and Excel-safe output

### `download_companies.py`

Loads `companies.csv`, validates required columns (`ticker`, `cik`, `company`), and cleans the data:
- Drops rows with missing values
- Standardizes tickers (uppercase, trimmed)
- Pads CIKs to 10 digits
- Removes duplicate tickers/CIKs
- Fills in optional columns (`sic_code`, `sic_description`, `target_sector`)

Exposes `get_company_list()` — called by other modules to load the company universe.

### `download_filings.py`

Downloads Company Facts JSON for every company in `companies.csv`. One HTTP request per company.

**Key functions:**
- `download_company_facts(cik, ticker)` — downloads a single company, handles retries/rate limits
- `download_all_company_facts()` — iterates over all companies with a progress bar (tqdm)

### `extract_balance_sheet.py`

The core extraction engine. Generic enough to be reused for income statements and cash flows later.

**Key functions:**
- `load_company_json(path)` — safe JSON loading with error handling
- `extract_tag(company_data, tag_name)` — extracts one XBRL tag, returns `{period: {value, filing_date, year, quarter}}`
- `extract_statement(company_json, tag_dictionary)` — iterates all concepts in a tag dictionary, builds a DataFrame
- `extract_balance_sheet(company_json)` — wrapper using `BALANCE_SHEET_TAGS`
- `merge_company_metadata(dataset)` — joins SIC codes and sector labels from `companies.csv`
- `validate_balance_sheet(df)` — checks Assets ≈ Liabilities + Equity with configurable tolerance
- `extract_all_balance_sheets()` — master function: iterates all JSON files, extracts, merges, validates, deduplicates

### `create_dataset.py`

Final stage. Calls `extract_all_balance_sheets()`, then cleans, computes ratios, and saves.

**Key functions:**
- `clean_dataset(df)` — date conversion, deduplication, sorting
- `calculate_financial_ratios(df)` — safe division using `np.divide(where=...)` to handle zero denominators
- `save_dataset(df)` — writes to CSV with UTF-8 BOM encoding

---

## SEC API Endpoints Used

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `https://www.sec.gov/files/company_tickers.json` | Full company index | 10 req/s |
| `https://data.sec.gov/submissions/CIK{cik}.json` | Company metadata (SIC codes) | 10 req/s |
| `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | All XBRL financial facts | 10 req/s |
| `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` | Bulk submissions archive | Single download |

**All requests require a `User-Agent` header** with a real name and email address. SEC will reject anonymous requests with HTTP 403.

---

## Data Schema

### Input: `companies.csv`

| Column | Type | Description |
|--------|------|-------------|
| ticker | str | Stock ticker (e.g., AAPL) |
| cik | str | 10-digit SEC CIK |
| company | str | Company name |
| sic_code | str | Standard Industrial Classification code |
| sic_description | str | Human-readable SIC description |
| target_sector | str | Mapped sector (Manufacturing, Technology, etc.) |

### Output: `financial_dataset.csv`

| Column | Type | Description |
|--------|------|-------------|
| company | str | Company name |
| ticker | str | Stock ticker |
| cik | str | 10-digit CIK |
| sic_code | float | SIC code |
| sic_description | str | SIC description |
| target_sector | str | Mapped sector |
| filing_date | datetime | Date the filing was submitted to SEC |
| period_end | datetime | End date of the reporting period |
| fiscal_year | int | Fiscal year |
| fiscal_quarter | int | Fiscal quarter (1–4) |
| cash | float | Cash and cash equivalents |
| short_term_investments | float | Available-for-sale securities / short-term investments |
| receivables | float | Accounts receivable (net) |
| inventory | float | Inventory (net) |
| current_assets | float | Total current assets |
| ppe | float | Property, plant & equipment (net) |
| goodwill | float | Goodwill |
| intangible_assets | float | Finite-lived intangible assets (net) |
| total_assets | float | Total assets |
| accounts_payable | float | Accounts payable (current) |
| current_liabilities | float | Total current liabilities |
| long_term_debt | float | Long-term debt (non-current) |
| total_liabilities | float | Total liabilities |
| equity | float | Stockholders' equity |
| balance_sheet_difference | float | Absolute difference: Assets − (Liabilities + Equity) |
| balance_sheet_valid | bool | Whether accounting equation holds within tolerance |
| working_capital | float | current_assets − current_liabilities |
| current_ratio | float | current_assets / current_liabilities |
| cash_ratio | float | cash / current_liabilities |
| debt_to_equity | float | total_liabilities / equity |
| debt_to_assets | float | total_liabilities / total_assets |

---

## Financial Tags Extracted

### Balance Sheet (`BALANCE_SHEET_TAGS`)

| Concept | XBRL Tags (priority order) |
|---------|---------------------------|
| cash | CashAndCashEquivalentsAtCarryingValue, Cash, CashCashEquivalentsRestrictedCash |
| short_term_investments | AvailableForSaleSecuritiesCurrent, ShortTermInvestments, MarketableSecuritiesCurrent |
| receivables | AccountsReceivableNetCurrent, ReceivablesNetCurrent |
| inventory | InventoryNet, InventoryCurrent, InventoryFinishedGoods, InventoryGross |
| current_assets | AssetsCurrent |
| ppe | PropertyPlantAndEquipmentNet, PropertyPlantAndEquipmentGross |
| goodwill | Goodwill |
| intangible_assets | FiniteLivedIntangibleAssetsNet, IntangibleAssetsNetExcludingGoodwill |
| total_assets | Assets |
| accounts_payable | AccountsPayableCurrent |
| current_liabilities | LiabilitiesCurrent |
| long_term_debt | LongTermDebtNoncurrent, LongTermDebt, LongTermBorrowings |
| total_liabilities | Liabilities |
| equity | StockholdersEquity, StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest |

### Income Statement (`INCOME_STATEMENT_TAGS`)

| Concept | XBRL Tags (priority order) |
|---------|---------------------------|
| revenue | RevenueFromContractWithCustomerExcludingAssessedTax, SalesRevenueNet, Revenues |
| cost_of_revenue | CostOfGoodsSold, CostOfRevenue |
| gross_profit | GrossProfit |
| operating_income | OperatingIncomeLoss |
| pretax_income | IncomeBeforeTaxExpenseBenefit |
| income_tax | IncomeTaxExpenseBenefit |
| net_income | NetIncomeLoss |
| interest_expense | InterestExpense |
| basic_eps | EarningsPerShareBasic |
| diluted_eps | EarningsPerShareDiluted |

### Cash Flow (`CASH_FLOW_TAGS`)

| Concept | XBRL Tags (priority order) |
|---------|---------------------------|
| operating_cash_flow | NetCashProvidedByUsedInOperatingActivities, NetCashProvidedByOperatingActivities |
| investing_cash_flow | NetCashProvidedByUsedInInvestingActivities |
| financing_cash_flow | NetCashProvidedByUsedInFinancingActivities |
| capital_expenditure | PaymentsToAcquirePropertyPlantAndEquipment, CapitalExpendituresIncurredButNotYetPaid |
| depreciation | Depreciation, DepreciationAndAmortization |
| amortization | AmortizationOfIntangibleAssets |

---

## How to Run

```bash
# Activate virtual environment
cd D:\SEC_FINANCIAL_PIPELINE
venv\Scripts\activate

# Install dependencies (when requirements.txt is populated)
pip install pandas numpy requests tqdm

# Step 1 — Fetch all SEC companies (run once)
python test.py

# Step 2 — Classify companies by sector (run once)
python test3.py

# Step 3 — Filter to your target companies → companies.csv (manual or scripted)

# Step 4 — Download Company Facts JSON for your companies
python download_filings.py

# Step 5 — Build the final dataset
python create_dataset.py
```

**Output:** `data/processed/financial_dataset.csv`

Steps 1–3 only need to run once. On subsequent runs, you only need Steps 4–5. Step 4 skips already-downloaded files automatically, so it's safe to re-run if interrupted.

---

## Key Design Decisions

### Why XBRL tag fallbacks?

Different companies use different tag names for the same concept. For example, "cash" is tagged as `CashAndCashEquivalentsAtCarryingValue` by some companies and plain `Cash` by others. The pipeline tries each tag in priority order — first successful match wins.

### Why relative + absolute validation tolerance?

The old pipeline used a hardcoded absolute tolerance of 1.0, which meant large companies with billions in assets would always "fail" validation. The new system uses whichever is more lenient: a $1M floor or 1% of total assets. A $500B company is allowed a $5B difference; a $50M company is allowed a $1M difference.

### Why safe division?

The old code used `replace(0, pd.NA)` to avoid divide-by-zero, which silently dropped valid rows where a company genuinely had zero liabilities (rare but real). The new code uses `np.divide(where=...)` which returns NaN for zero denominators without destroying the row.

### Why exponential backoff?

SEC rate-limits at 10 requests per second. A flat 2-second sleep is wasteful for successful requests and insufficient after a 429. Exponential backoff (2s → 4s → 8s) with a 5x multiplier for HTTP 429 handles both cases.

### Why keep the extraction engine generic?

`extract_statement()` accepts any tag dictionary, not just balance sheets. Income statement and cash flow extraction can be added with a one-line wrapper function — no code duplication needed.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| pandas | Data manipulation and CSV I/O |
| numpy | Safe division in ratio calculations |
| requests | HTTP requests to SEC API |
| tqdm | Progress bars for download loop |

---

## Sample Output

```
2026-07-19 16:14:36 | INFO     | CREATE FINANCIAL DATASET
2026-07-19 16:14:36 | INFO     | Extracting financial statements...
2026-07-19 16:14:36 | INFO     | Processing 483 Company Facts files...
2026-07-19 16:19:51 | INFO     | Rows extracted: 22327
2026-07-19 16:19:51 | INFO     | Rows after cleaning: 22327
2026-07-19 16:19:52 | INFO     | PIPELINE COMPLETE
2026-07-19 16:19:52 | INFO     | Total Rows: 22327
2026-07-19 16:19:52 | INFO     | Companies: 398
2026-07-19 16:19:52 | INFO     | Fiscal Years: 1998 - 2026
2026-07-19 16:19:52 | INFO     | Dataset Saved: data/processed/financial_dataset.csv
```


