# SEC Financial Pipeline

A Python data pipeline that pulls financial data directly from the U.S. Securities and Exchange Commission (SEC) EDGAR system and extracts standardized financial fields from SEC Company Facts JSON into a clean, analysis-ready CSV.

**Latest update:** The pipeline now has two tracks — the original full-extraction pipeline (`create_dataset.py`) and a new focused extractor (`extract_specific_fields.py`, ~1,400 companies, 2016+, 16 selected fields with robust NaN minimization).

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Directory Structure](#directory-structure)
4. [Pipeline Flow](#pipeline-flow)
5. [Module Breakdown](#module-breakdown)
6. [SEC API Endpoints Used](#sec-api-endpoints-used)
7. [Field Mapping & XBRL Tags](#field-mapping--xbrl-tags)
8. [Output Schema](#output-schema)
9. [Dataset Coverage & Quality](#dataset-coverage--quality)
10. [How to Run](#how-to-run)
11. [What You Can Do With This Dataset](#what-you-can-do-with-this-dataset)
12. [Key Design Decisions](#key-design-decisions)

---

## Project Overview

This pipeline answers a simple question: **"What do the financial statements of 1,400+ U.S. companies look like over time?"**

It connects to the SEC's public EDGAR API, downloads XBRL-tagged financial facts in JSON format, extracts only annual (10-K) filings, and produces a clean panel dataset with **16 key financial fields** plus company metadata.

**Dataset at a glance:**
- **12,747 rows** across **1,433 companies**
- **Fiscal years 2016–2026** (filtered for better data density)
- **27 columns** including 16 financial fields + 2 bonus DEI fields
- **10-K annual filings only** (one row per company per year)
- **~92–98% coverage** on core fields (assets, income, equity, market value)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SEC EDGAR (Public API)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
               ┌───────────────────┐
               │ download_filings  │
               │ .py               │
               │ (fetch Company    │
               │  Facts JSON for   │
               │  each company)    │
               └────────┬──────────┘
                        │
                        ▼
               ┌────────────────────────┐
               │ data/raw/company_facts/ │
               │   {TICKER}.json         │
               │   (1,455 files)         │
               └────────┬───────────────┘
                        │
                ┌───────┴────────┐
                │                │
                ▼                ▼
    ┌──────────────────┐  ┌────────────────────────┐
    │  RECOMMENDED     │  │  Legacy Pipeline       │
    │                  │  │                        │
    │ extract_specific_│  │ extract_balance_sheet  │
    │ fields.py        │  │ .py                    │
    │                  │  │                        │
    │ • 16 targeted    │  │ • Full XBRL extraction │
    │   fields         │  │ • 70+ fields           │
    │ • Groups by      │  │ • Quarterly + annual   │
    │   fiscal year    │  │                        │
    │ • 2016+ filter   │  └──────────┬─────────────┘
    │ • NaN-minimized  │             │
    │   logic          │             ▼
    └────────┬─────────┘  ┌──────────────────────┐
             │            │  create_dataset.py   │
             ▼            │  (ratios, save)      │
    ┌──────────────────┐  └──────────┬───────────┘
    │ specific_fields_ │             │
    │ dataset.csv      │             ▼
    │                  │  ┌──────────────────────┐
    │ (12,747 rows)    │  │ financial_dataset    │
    └──────────────────┘  │ .csv                 │
                          └──────────────────────┘
```

---

## Directory Structure

```
SEC_FINANCIAL_PIPELINE/
│
├── config.py                          # Central configuration (paths, API, XBRL tags)
├── test.py                            # Fetch all SEC companies (ticker, CIK, name)
├── test3.py / test4.py                # Fetch SIC codes via bulk ZIP download
├── test45.py / test54.py              # Refined bulk extraction scripts
│
├── download_companies.py              # Load, validate, clean companies.csv
├── download_filings.py                # Download Company Facts JSON for each company
├── extract_specific_fields.py         # ⭐ New — focused extractor (16 fields, 2016+)
├── extract_balance_sheet.py           # Legacy — generic XBRL extraction engine
├── create_dataset.py                  # Legacy — build full dataset with ratios
│
├── companies.csv                      # Target company list (1,476 companies)
├── all_sec_companies.csv              # Full SEC company index (10,409 companies)
├── all_sec_companies_categorized.csv  # Full index + SIC codes + sector labels
├── new_companies.csv                  # Original new company list (before cleanup)
├── research_universe.csv              # Extended research universe
│
├── requirements.txt
├── .gitignore                         # Excludes __pycache__, *.csv, data/
├── README.md
│
├── data/
│   ├── raw/
│   │   └── company_facts/             # Downloaded SEC Company Facts JSON files
│   │       ├── AAPL.json
│   │       ├── MSFT.json
│   │       └── ... (1,455 files)
│   └── processed/
│       ├── specific_fields_dataset.csv  # ⭐ New output (recommended)
│       └── sec_financial_panel.csv      # Legacy output
│
└── venv/                              # Python virtual environment
```

---

## Pipeline Flow

### Stage 1 — Download Financial Data (`download_filings.py`)

For each company in `companies.csv`, calls the SEC Company Facts API:

```
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
```

Each response is a massive JSON blob containing every XBRL-tagged financial fact the company has ever filed.

Output: one `{TICKER}.json` file per company in `data/raw/company_facts/`.

### Stage 2 (RECOMMENDED) — Extract 16 Specific Fields (`extract_specific_fields.py`)

Reads every JSON file and extracts only the fields you care about. This is the recommended pipeline stage.

**How it differs from the legacy extractor:**

| Feature | Legacy (`create_dataset.py`) | New (`extract_specific_fields.py`) |
|---------|-----------------------------|-------------------------------------|
| Companies | ~474 manufacturing | ~1,433 diversified |
| Fields | 70+ financial fields | 16 targeted fields |
| Filing types | 10-Q + 10-K | 10-K annual only |
| Row structure | One row per quarter | One row per fiscal year |
| Year range | 1998–2026 | 2016–2026 |
| Merge key | period_end | fiscal_year |
| NaN handling | None | Drops rows < 3 fields with data |
| DEI fields | No | Yes (market_value, shares_outstanding) |
| Tag fallbacks | Basic | Frequency-ranked from 200+ file analysis |

**Key innovation — fiscal year grouping:**

Different XBRL fields for the same fiscal year often have different `period_end` dates. For example:

| Field | period_end | Fiscal Year |
|-------|-----------|-------------|
| total_assets | 2016-10-31 | 2016 |
| net_income | 2016-10-31 | 2016 |
| market_value | 2016-04-30 | 2016 |
| shares_outstanding | 2016-12-01 | 2016 |

The legacy pipeline merged on `period_end`, causing fields with the same fiscal year but different calendar dates to land on separate rows. The new pipeline groups by `fiscal_year`, keeping all data for one company-year together.

### Stage 2 (Legacy) — Extract All Fields (`create_dataset.py`)

For the original ~474 manufacturing companies, extracts all balance sheet, income statement, and cash flow fields, computes financial ratios, and saves.

---

## Module Breakdown

### `config.py`

Central hub. Every other module imports from here.

**Contains:**
- Project directory paths
- SEC API endpoints and HTTP settings (User-Agent, timeout, delay, retries)
- XBRL tag dictionaries for balance sheet, income statement, and cash flow
- Dataset column definitions and logging configuration

### `download_companies.py`

Loads `companies.csv`, validates required columns (`ticker`, `cik`, `company`), and standardizes:
- Zero-pads CIKs to 10 digits
- Uppercases tickers
- Removes duplicate tickers/CIKs

### `download_filings.py`

Downloads Company Facts JSON for every company in `companies.csv`.

**Key features:**
- Skips already-downloaded files (safe to re-run)
- Exponential backoff on retries (2s → 4s → 8s)
- HTTP 429 rate limit detection (extra-long cooldown)
- Validates JSON structure before saving

### `extract_specific_fields.py` (New — Recommended)

Focused extractor that minimizes NaN values and produces a clean dataset.

**Key design decisions:**

1. **Groups by fiscal year**, not period_end — aligns balance sheet, income statement, and DEI fields
2. **Filters to 2016+** from the start — eliminates sparse early XBRL years
3. **First-match-wins tag fallbacks** — ranked by real tag frequency from 200+ JSON files
4. **Latest filing wins** for duplicate periods
5. **Drops rows** where fewer than 3 financial fields have data
6. **Smart field combination** — fills `net_sales` from `total_revenue` (and vice versa) when one is missing, since SEC filers use different tag names for the same revenue figure

**Functions:**
- `extract_tag_values(facts_section, tag_name)` — extract raw values for one XBRL tag
- `extract_company(file_path)` — extract all 16 fields for one company, collapse to one row per fiscal year
- `merge_metadata(dataset)` — join SIC codes and sector labels from `companies.csv`
- `clean_sparse_rows(df)` — drop rows with < 3 populated fields
- `extract_all()` — iterate all JSON files, merge, clean
- `main()` — entry point with logging and summary

### `extract_balance_sheet.py` / `create_dataset.py` (Legacy)

The original extraction engine — generic enough to handle balance sheet, income statement, and cash flow via tag dictionaries.

---

## SEC API Endpoints Used

| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` | All XBRL financial facts | 10 req/s |
| `https://www.sec.gov/files/company_tickers.json` | Full company index | 10 req/s |
| `https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip` | Bulk submissions archive | Single download |

**All requests require a `User-Agent` header** with a real name and email address. SEC rejects anonymous requests with HTTP 403. Update `SEC_HEADERS` in `config.py`.

---

## Field Mapping & XBRL Tags

### 16 Target Fields

| # | Field | XBRL Tags (priority order) | SEC Section |
|---|-------|---------------------------|-------------|
| 1 | current_assets | `AssetsCurrent` | us-gaap |
| 2 | cost_of_goods_sold | `CostOfGoodsAndServicesSold`, `CostOfGoodsSold`, `CostOfRevenue` | us-gaap |
| 3 | depreciation_amortization | `DepreciationDepletionAndAmortization`, `DepreciationAndAmortization`, `Depreciation`, `AmortizationOfIntangibleAssets` | us-gaap |
| 4 | inventory | `InventoryNet`, `InventoryCurrent`, `InventoryFinishedGoods`, `InventoryGross` | us-gaap |
| 5 | net_income | `NetIncomeLoss`, `NetIncomeLossAvailableToCommonStockholdersBasic` | us-gaap |
| 6 | total_receivables | `AccountsReceivableNetCurrent`, `ReceivablesNetCurrent`, `AccountsReceivableNet` | us-gaap |
| 7 | market_value | `EntityPublicFloat` | **dei** |
| 8 | net_sales | `SalesRevenueNet`, `SalesRevenueGoodsNet`, `RevenueFromContractWithCustomerExcludingAssessedTax` | us-gaap |
| 9 | total_assets | `Assets` | us-gaap |
| 10 | long_term_debt | `LongTermDebtNoncurrent`, `LongTermDebt`, `LongTermBorrowings` | us-gaap |
| 11 | gross_profit | `GrossProfit` | us-gaap |
| 12 | current_liabilities | `LiabilitiesCurrent` | us-gaap |
| 13 | retained_earnings | `RetainedEarningsAccumulatedDeficit`, `RetainedEarnings` | us-gaap |
| 14 | total_revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`, `Revenues` | us-gaap |
| 15 | total_liabilities | `Liabilities` | us-gaap |
| 16 | total_operating_expenses | `OperatingExpenses`, `OperatingCostsAndExpenses`, `CostsAndExpenses` | us-gaap |

### Bonus DEI Fields

| Field | XBRL Tag | Availability |
|-------|----------|--------------|
| market_value | `EntityPublicFloat` | 91.5% coverage |
| shares_outstanding | `EntityCommonStockSharesOutstanding` | 82.7% coverage |

### Tag Fallback Strategy

XBRL tags were ranked by real frequency, checked across 200+ random JSON files. The first tag in each list is the most commonly used. If it's not available for a given company, the next tag is tried, and so on. This maximizes extraction success.

---

## Output Schema

### `specific_fields_dataset.csv`

| Column | Type | Description |
|--------|------|-------------|
| **Metadata** | | |
| company | str | Company name |
| ticker | str | Stock ticker |
| cik | str | 10-digit SEC CIK |
| sic_code | float | Standard Industrial Classification code |
| sic_description | str | Human-readable SIC description |
| target_sector | str | Mapped sector (Manufacturing, Technology, Retail, etc.) |
| filing_date | datetime | Date the filing was submitted to SEC |
| period_end | datetime | End date of the reporting period |
| fiscal_year | int | Fiscal year |
| fiscal_quarter | int | Always 4 (10-K annual) |
| **16 Financial Fields** | | |
| current_assets | float | Total current assets |
| cost_of_goods_sold | float | Cost of goods sold |
| depreciation_amortization | float | Depreciation, depletion & amortization |
| inventory | float | Inventory (net) |
| net_income | float | Net income (loss) |
| total_receivables | float | Accounts receivable (net current) |
| net_sales | float | Net sales revenue (filled from total_revenue if missing) |
| total_assets | float | Total assets |
| long_term_debt | float | Long-term debt (non-current) |
| gross_profit | float | Gross profit |
| current_liabilities | float | Total current liabilities |
| retained_earnings | float | Retained earnings (accumulated deficit) |
| total_revenue | float | Total revenue (filled from net_sales if missing) |
| total_liabilities | float | Total liabilities |
| total_operating_expenses | float | Total operating costs and expenses |
| **Bonus DEI Fields** | | |
| market_value | float | Entity public float (USD) |
| shares_outstanding | float | Common stock shares outstanding |

---

## Dataset Coverage & Quality

### Data Density (Fiscal Year ≥ 2016)

| Field | Coverage | Status |
|-------|----------|--------|
| total_assets | 98.3% | ✅ Excellent |
| current_assets | 97.3% | ✅ Excellent |
| current_liabilities | 97.1% | ✅ Excellent |
| net_income | 96.4% | ✅ Excellent |
| retained_earnings | 96.2% | ✅ Excellent |
| market_value | 91.5% | ✅ Excellent |
| depreciation_amortization | 85.1% | ✅ Great |
| shares_outstanding | 82.7% | ✅ Great |
| inventory | 81.8% | ✅ Great |
| total_receivables | 81.9% | ✅ Great |
| net_sales / total_revenue | 79.6% | ✅ Good |
| total_liabilities | 74.0% | ✅ Good |
| cost_of_goods_sold | 69.6% | ✅ Decent |
| gross_profit | 67.2% | ✅ Decent |
| total_operating_expenses | 56.8% | ⚠ Moderate |
| long_term_debt | 55.6% | ⚠ Moderate |

### What Affects Coverage

- **XBRL adoption:** Fields like `total_assets` (`Assets`) are near-universal because they're required for balance sheet reporting. Others like `total_operating_expenses` are less standardized — some companies break them into components (SG&A, R&D, etc.) rather than reporting a single total.
- **Company size:** Smaller companies may not report `EntityPublicFloat` or `LongTermDebt` if they don't have public float or long-term borrowings.
- **Industry variation:** Manufacturing companies tend to report `inventory` and `cost_of_goods_sold`, while service companies may not.

---

## How to Run

### Quick Start (Recommended Pipeline)

```bash
cd D:\SEC_FINANCIAL_PIPELINE
venv\Scripts\activate

# Step 1 — Download Company Facts JSON (skip if already done)
python download_filings.py

# Step 2 — Extract 16 specific fields
python extract_specific_fields.py
```

**Output:** `data/processed/specific_fields_dataset.csv`

### Full Pipeline (Legacy)

```bash
cd D:\SEC_FINANCIAL_PIPELINE
venv\Scripts\activate

# Step 1 — Fetch all SEC companies (run once)
python test.py

# Step 2 — Classify companies by sector (run once)
python test3.py

# Step 3 — Download Company Facts JSON
python download_filings.py

# Step 4 — Build full dataset with ratios
python create_dataset.py
```

**Output:** `data/processed/sec_financial_panel.csv`

### Dependencies

Install with:
```bash
pip install pandas numpy requests tqdm
```

| Package | Purpose |
|---------|---------|
| pandas | Data manipulation and CSV I/O |
| numpy | Safe division in ratio calculations |
| requests | HTTP requests to SEC API |
| tqdm | Progress bars for download loop |

---

## What You Can Do With This Dataset

### 1. Compute Financial Ratios

Derive standard financial ratios from the raw fields:

| Category | Ratio | Formula |
|----------|-------|--------|
| **Profitability** | Gross Margin | `gross_profit / total_revenue` |
| | Operating Margin | `(total_revenue - total_operating_expenses) / total_revenue` |
| | Net Margin | `net_income / total_revenue` |
| | Return on Assets (ROA) | `net_income / total_assets` |
| | Return on Equity (ROE) | `net_income / (total_assets - total_liabilities)` |
| **Liquidity** | Current Ratio | `current_assets / current_liabilities` |
| | Working Capital | `current_assets - current_liabilities` |
| **Leverage** | Debt-to-Equity | `total_liabilities / (total_assets - total_liabilities)` |
| | Debt-to-Assets | `total_liabilities / total_assets` |
| | Long-Term Debt Ratio | `long_term_debt / total_assets` |
| **Efficiency** | Asset Turnover | `total_revenue / total_assets` |
| | Inventory Turnover | `cost_of_goods_sold / inventory` |
| | Receivables Turnover | `total_revenue / total_receivables` |
| **Market** | Market Cap | `shares_outstanding × stock_price` (need price data) |
| | Enterprise Value | market cap + long_term_debt - cash (need price data) |

### 2. Sector & Industry Analysis

```python
import pandas as pd

df = pd.read_csv("data/processed/specific_fields_dataset.csv")

# Net margin by sector over time
df["net_margin"] = df["net_income"] / df["total_revenue"]
sector_trend = df.groupby(["target_sector", "fiscal_year"])["net_margin"].mean()

# Rank companies by ROA within each sector
df["roa"] = df["net_income"] / df["total_assets"]
top = df.loc[df.groupby(["target_sector", "fiscal_year"])["roa"].idxmax()]

# Spot sectors with deteriorating margins
volatility = df.groupby(["target_sector", "fiscal_year"]).agg(
    {"net_margin": "std"}
).reset_index()
```

### 3. Financial Health Screening

Screen for companies meeting specific criteria:

- **Liquidity risk:** `current_assets / current_liabilities < 1.0` (potential short-term distress)
- **Over-leveraged:** `total_liabilities / total_assets > 0.8` (high debt levels)
- **Profitability stall:** `net_income < 0` for 2+ consecutive years
- **Cash-burning:** consistent negative earnings with declining working capital
- **Growth screen:** year-over-year revenue growth > 20% with positive net income

### 4. Time-Series & Event Studies

Analyze how financial metrics responded to major economic events:

- **COVID-19 (2020):** Which sectors saw the sharpest revenue drops? How fast did they recover?
- **Interest rate hikes (2022–2023):** Did long-term debt levels change? Interest expense patterns?
- **Inflation period (2021–2023):** How did COGS as a % of revenue shift?
- **Post-pandemic (2024–2026):** Which sectors structurally changed their cost structure?

### 5. Cross-Sectional Comparisons

- **Size effects:** Split companies into market-cap quintiles (using `market_value`) and compare ratios
- **Sector benchmarks:** Build sector-specific benchmarks for each financial ratio
- **Outlier detection:** Flag companies with ratios > 3 standard deviations from their sector mean
- **Peer analysis:** Pick a company and find its closest peers by profitability and leverage profile

### 6. Merger & Screening Inputs

- **Valuation work:** Merge with stock price data to compute P/E, EV/EBITDA, P/B, dividend yields
- **Risk modeling:** Use leverage and liquidity ratios as inputs for credit scoring or distress prediction
- **Portfolio construction:** Filter for companies meeting specific financial criteria for quantitative strategies
- **Fundamental signals:** Create multi-factor signals combining profitability, leverage, and efficiency

### 7. Merge With External Data

This dataset is designed to be merged with other data sources:

- **Stock prices** (from Yahoo Finance, Alpha Vantage, etc.) — merge on `ticker` and `fiscal_year` for market-capitalization-weighted analysis
- **Macroeconomic data** (GDP growth, interest rates, inflation) — merge on `fiscal_year` for macro-financial studies
- **ESG scores** — merge on `ticker` to analyze how sustainability metrics correlate with financial performance
- **Credit ratings** — merge on `ticker` to build rating-prediction models from financial ratios

### Example: Build a Complete Analysis DataFrame

```python
import pandas as pd
import numpy as np

df = pd.read_csv("data/processed/specific_fields_dataset.csv")

# Calculate key ratios
df["net_margin"] = np.where(df["total_revenue"] > 0,
    df["net_income"] / df["total_revenue"], np.nan)
df["current_ratio"] = np.where(df["current_liabilities"] > 0,
    df["current_assets"] / df["current_liabilities"], np.nan)
df["debt_to_equity"] = np.where(
    (df["total_assets"] - df["total_liabilities"]) > 0,
    df["total_liabilities"] / (df["total_assets"] - df["total_liabilities"]),
    np.nan)

# Flag healthy vs risky companies
df["healthy"] = (
    (df["current_ratio"] > 1.5) &
    (df["debt_to_equity"] < 1.0) &
    (df["net_margin"] > 0.05)
)

# Group by sector and year
summary = df[df["fiscal_year"] == 2025].groupby("target_sector").agg({
    "net_margin": "mean",
    "current_ratio": "mean",
    "debt_to_equity": "mean",
    "healthy": "mean",
}).round(4)
```

---

## Key Design Decisions

### Why group by fiscal year instead of period_end?

Different XBRL fields for the same fiscal year can have different `period_end` dates. Balance sheet fields report as of a single date, while income statement fields cover a period ending on that date. DEI fields like `EntityPublicFloat` are reported mid-year. By grouping on `fiscal_year`, all data for one company-year stays in one row instead of fragmenting across multiple rows.

### Why filter to 2016+?

XBRL tagging was phased in gradually. Before ~2008, almost no data is tagged. Between 2008–2015, adoption was inconsistent — some companies tagged all fields, others only a few. By 2016, XBRL reporting was standard for most U.S. public companies. Filtering to 2016+ eliminates the sparse early years while keeping 10 years of quality data.

### Why multiple XBRL tag fallbacks ranked by frequency?

Different companies and different SEC filers use different XBRL tag names for the same financial concept. For example, "cash" could be `CashAndCashEquivalentsAtCarryingValue`, `Cash`, or `CashCashEquivalentsRestrictedCash`. The fallback order was determined by scanning 200+ random JSON files and ranking tags by actual usage frequency.

### Why only 10-K (annual) filings?

10-K filings are audited and standardized. 10-Q filings are unaudited and may contain revisions. By using only 10-K data, the dataset has one row per company per year — cleaner for panel analysis, no need to average quarterly data.

### Why keep both net_sales and total_revenue?

SEC filers tag revenue inconsistently — some use `SalesRevenueNet`, others use `RevenueFromContractWithCustomerExcludingAssessedTax`. The smart fill logic copies whichever value is available into both columns, so you always have revenue data to work with. The values are identical when filled from the other.

### Why drop sparse rows?

If a company's JSON file has < 3 extracted financial fields, it likely has too little data for any meaningful analysis. Dropping these rows (959 out of 13,706 extracted) keeps the dataset clean without losing useful data.
