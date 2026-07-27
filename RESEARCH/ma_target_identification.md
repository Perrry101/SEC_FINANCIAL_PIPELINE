# M&A Target Identification — Research Project Reference

**Project:** Identify the most attractive M&A acquisition targets from the SEC Financial Pipeline dataset  
**Dataset:** `specific_fields_dataset.csv` — 1,433 companies, 5 sectors, 2016–2026  
**Output:** Ranked target list + sector summary + Jupyter notebook with visual analysis  
**Difficulty:** Medium  
**Market audience:** Investment banks, private equity firms, corporate development teams

---

## 1. Concept — What We're Building

A multi-dimensional scoring engine that evaluates each company on **5 dimensions** of "acquirability" and produces a ranked list of the most attractive M&A targets per sector.

The core idea: **Not all companies are equally likely to be acquired.** Private equity firms, strategic buyers, and corporate acquirers all look for similar patterns — small enough to afford, profitable, growing, financially healthy, and with a manageable public float. We quantify each of these dimensions from the 10-K financial data and combine them into a single score.

---

## 2. The 5 Scoring Dimensions

### 2.1 Size Score (25% weight)

| Aspect | Detail |
|--------|--------|
| **Logic** | Smaller companies are easier and cheaper to acquire |
| **Primary input** | `total_assets` (98.3% coverage) |
| **Fallback** | `market_value` when assets are missing |
| **Method** | Inverse percentile rank within sector |
| **Bonus** | Micro-cap bonus for companies with assets < $50M |
| **Why this matters** | Large-cap M&A ($10B+) requires consortium financing, antitrust review, and lengthy negotiations. Micro/small-cap targets ($50M–$2B) are the sweet spot for PE and strategic acquirers. |

### 2.2 Profitability Score (20% weight)

| Aspect | Detail |
|--------|--------|
| **Logic** | Profitable companies contribute accretive earnings immediately |
| **Inputs** | `net_income`, `net_margin` (derived), `gross_profit` |
| **Method** | Percentile rank of net margin within sector + flag for positive net income |
| **Blend** | 60% margin rank, 40% profitability flag |
| **Why this matters** | Acquiring a loss-making company means a dilutive earnings impact and an immediate restructuring need. Strategic acquirers and PE firms pay premiums for high-margin targets. |

### 2.3 Growth Score (20% weight)

| Aspect | Detail |
|--------|--------|
| **Logic** | Growing revenue signals future upside potential |
| **Inputs** | 1-year `revenue_growth`, 3-year avg `revenue_growth_3yr` |
| **Clamping** | Growth rates clamped to [-90%, +200%] to prevent one-off events from dominating |
| **Method** | Percentile rank within sector for both timeframes |
| **Blend** | 60% recent growth, 40% sustained 3-year trend |
| **Why this matters** | Strategic acquirers pay for growth they can't build organically. A company growing 15% YoY in a sector growing 3% is highly attractive. |

### 2.4 Financial Health Score (20% weight)

| Aspect | Detail |
|--------|--------|
| **Logic** | Healthy targets close faster with less financing friction |
| **Inputs** | `debt_to_equity` (inverse), `current_ratio` (direct), retained earnings positivity |
| **Method** | Blend of inverse leverage rank + liquidity rank + profitability flags |
| **Blend** | 30% D/E, 30% current ratio, 20% positive NI, 20% positive retained earnings |
| **Why this matters** | Highly leveraged targets may need debt restructuring. Illiquid targets may have working capital issues post-acquisition. Healthy targets mean cleaner deal execution. |

### 2.5 Public Float Score (15% weight)

| Aspect | Detail |
|--------|--------|
| **Logic** | Smaller public float = fewer shareholders = easier to acquire |
| **Primary input** | `market_value` (EntityPublicFloat, 91.5% coverage) |
| **Method** | Inverse percentile rank within sector |
| **Bonus** | Micro-cap bonus for market cap < $500M |
| **Why this matters** | Large public float means more institutional shareholders to convince, higher chance of activist opposition, and potentially a hostile bid scenario. Small floats make for friendlier, faster processes. |

---

## 3. Weight Configuration

```python
weights = {
    "size":               0.25,   # Smaller = easier
    "profitability":      0.20,   # Profitable = accretive
    "growth":             0.20,   # Growing = upside
    "financial_health":   0.20,   # Healthy = clean deal
    "public_float":       0.15,   # Small float = less friction
}
```

**Total: 1.00.** These weights are a balanced starting point. They can be tuned for different use cases:

| Use Case | Size | Profit | Growth | Health | Float |
|----------|:----:|:------:|:------:|:------:|:-----:|
| **Balanced (default)** | 0.25 | 0.20 | 0.20 | 0.20 | 0.15 |
| **PE Buyout** | 0.30 | 0.25 | 0.10 | 0.25 | 0.10 |
| **Strategic Growth** | 0.15 | 0.15 | 0.35 | 0.20 | 0.15 |
| **Distressed / Turnaround** | 0.20 | 0.05 | 0.10 | 0.05 | 0.60 |
| **Micro-Cap Focus** | 0.35 | 0.20 | 0.20 | 0.15 | 0.10 |

---

## 4. Dataset Profile

### 4.1 Coverage Summary

| Field | Coverage | Use |
|-------|----------|-----|
| `total_assets` | 98.3% | Size (primary) |
| `current_assets` | 97.3% | Health (liquidity) |
| `current_liabilities` | 97.1% | Health (leverage) |
| `net_income` | 96.4% | Profitability |
| `retained_earnings` | 96.2% | Health (earnings quality) |
| `market_value` | 91.5% | Public float |
| `total_revenue` | 79.6% | Growth rate computation |
| `total_liabilities` | 74.0% | Health (debt) |
| `long_term_debt` | 55.6% | Health (secondary) |
| `shares_outstanding` | 82.7% | Float (secondary) |

### 4.2 Sector Breakdown

| Sector | Companies | Notes |
|--------|:---------:|-------|
| Industrials | 467 | Largest sector, diverse subsectors |
| Manufacturing | 372 | Capital-intensive, strong asset base |
| Retail | 227 | Revenue-dependent, margin-focused |
| Energy | 216 | Asset-heavy, cyclical |
| Consumer Goods | 151 | Brand-driven, steady growth |

---

## 5. Implementation Architecture

### 5.1 Pipeline Steps

```
  ┌─────────────────────────────────────────────────────┐
  │ 1. LOAD DATASET                                     │
  │    specific_fields_dataset.csv (12,747 rows)         │
  └────────────────────┬────────────────────────────────┘
                       ▼
  ┌─────────────────────────────────────────────────────┐
  │ 2. FEATURE ENGINEERING                              │
  │    • net_margin = net_income / total_revenue         │
  │    • debt_to_equity = total_liabilities / equity     │
  │    • current_ratio = current_assets / cur_liab       │
  │    • revenue_growth = 1-yr pct change                │
  │    • revenue_growth_3yr = 3-yr avg growth            │
  └────────────────────┬────────────────────────────────┘
                       ▼
  ┌─────────────────────────────────────────────────────┐
  │ 3. LATEST YEAR SNAPSHOT                             │
  │    One row per company (most recent fiscal year)     │
  └────────────────────┬────────────────────────────────┘
                       ▼
  ┌─────────────────────────────────────────────────────┐
  │ 4. SCORE EACH DIMENSION                             │
  │    ┌──────────┐ ┌──────────┐ ┌──────────┐          │
  │    │  Size   │ │  Profit  │ │  Growth  │           │
  │    │ (25%)   │ │  (20%)   │ │  (20%)   │           │
  │    └────┬─────┘ └────┬─────┘ └────┬─────┘          │
  │         │            │            │                  │
  │    ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐          │
  │    │  Health │ │  Float   │ │ Composite│           │
  │    │ (20%)   │ │  (15%)   │ │  Score   │           │
  │    └──────────┘ └──────────┘ └──────────┘          │
  └────────────────────┬────────────────────────────────┘
                       ▼
  ┌─────────────────────────────────────────────────────┐
  │ 5. RANK & EXPORT                                    │
  │    • ma_targets_ranked.csv (full ranked list)        │
  │    • ma_sector_summary.csv (sector aggregates)       │
  │    • Console report + thesis labels                  │
  └─────────────────────────────────────────────────────┘
```

### 5.2 Output Schema — `ma_targets_ranked.csv`

| Column | Type | Description |
|--------|------|-------------|
| `rank` | int | Overall acquirability rank |
| `ticker` | str | Company ticker |
| `company` | str | Company name |
| `target_sector` | str | Sector classification |
| `fiscal_year` | int | Latest reporting year |
| `total_revenue` | float | Latest annual revenue (USD) |
| `net_income` | float | Latest net income (USD) |
| `acquirability_score` | float | Composite score (0–100) |
| `size_score` | float | Size subscore (0–100) |
| `profit_score` | float | Profitability subscore (0–100) |
| `growth_score` | float | Growth subscore (0–100) |
| `health_score` | float | Health subscore (0–100) |
| `mv_score` | float | Public float subscore (0–100) |
| `revenue_growth` | float | YoY revenue growth rate (dec) |
| `net_margin` | float | Net profit margin (dec) |
| `thesis` | str | Natural-language investment thesis |

---

## 6. How to Execute — Jupyter Notebook Guide

### 6.1 Prerequisites

```bash
cd D:\SEC_FINANCIAL_PIPELINE
venv\Scripts\activate
pip install pandas numpy jupyter matplotlib seaborn
```

### 6.2 Notebook Structure (11 cells)

#### Cell 1 — Imports & Setup
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

ROOT = Path.cwd()
DATA_FILE = ROOT / "data" / "processed" / "specific_fields_dataset.csv"
```

#### Cell 2 — Load Dataset
```python
df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")
print(f"Loaded: {len(df):,} rows × {len(df.columns)} cols")
print(f"Companies: {df['ticker'].nunique():,}")
print(f"Years: {df['fiscal_year'].min()}–{df['fiscal_year'].max()}")
```

#### Cell 3 — Feature Engineering
```python
# Compute: net_margin, debt_to_equity, current_ratio, equity
# Compute: revenue_growth (1-yr, 3-yr) with clamping
```

#### Cell 4 — Latest Year Snapshot
```python
# Group by ticker, take last fiscal year
```

#### Cell 5 — Scoring Functions
```python
# score_size(), score_profitability(), score_growth()
# score_health(), score_public_float()
```

#### Cell 6 — Composite Score
```python
# Weight dimensions → acquirability_score
```

#### Cell 7 — Top 50 Results Table
```python
# Display formatted top 50
```

#### Cell 8 — Sector Score Breakdown (Bar Chart)
```python
# Grouped bar chart: 5 sectors × 5 dimensions
```

#### Cell 9 — Score Distribution (Histogram)
```python
# Distribution of acquirability scores
```

#### Cell 10 — Radar / Spider Chart
```python
# Compare top 3 companies across all 5 dimensions
```

#### Cell 11 — Sector Heatmap
```python
# Heatmap of average dimension scores by sector
```

### 6.3 Expected Output

- **12,747 rows** loaded → **~1,433 companies** scored
- **Top 50 targets** printed with scores and thesis labels
- **5 sector summaries** with average dimension scores
- **3 visualizations:** bar chart, histogram, heatmap
- **CSV exports:** ranked list + sector summary

---

## 7. Real-World Use Cases

| Audience | How They Use It |
|----------|-----------------|
| **M&A Advisory** (Goldman Sachs, Morgan Stanley, PJT Partners) | Generate target lists for sell-side mandates. Supplement pitch books with data-driven rankings. |
| **Private Equity** (KKR, Blackstone, Apollo, Carlyle) | Screen platform acquisitions. Identify add-on targets in specific sectors. |
| **Corporate Development** (Apple, Amazon, Johnson & Johnson) | Find strategic bolt-on acquisitions. Monitor competitors' acquisition patterns. |
| **Hedge Funds** (activist, event-driven) | Identify companies likely to be acquired → build long positions before premium is paid. |
| **Investment Banking Analysts** | Quick-start screening for engagement letters. Reduce manual screening time from days to minutes. |

---

## 8. Limitations & Caveats

1. **No deal premium data** — We score fundamental attractiveness, not expected valuation. A cheap company may still have unrealistic price expectations.
2. **No ownership structure** — We can't detect dual-class shares, founder control, or poison pills that block takeovers.
3. **Sector classification is broad** — "Industrials" includes aerospace, logistics, construction. More granular SIC codes exist but aren't used.
4. **Growth from partial data** — Companies with gaps in filing history may have unreliable growth rates.
5. **One-year snapshot** — Using the latest year only. A 3-year trend would be more robust but reduces sample size.
6. **No geographic data** — Cross-border vs domestic acquisitions have different dynamics.

---

## 9. Future Enhancements

- [ ] **3-year trend stability score** — Companies with consistently growing revenue over 3+ years
- [ ] **Moat proxy via gross margin stability** — Low margin volatility suggests competitive advantage
- [ ] **Deal capacity proxy** — Acquirer-side: who has cash and low leverage to make acquisitions?
- [ ] **Stock price integration** — EV/EBITDA, P/E, price-to-book for valuation overlay
- [ ] **Bolt-on vs Platform classifier** — Small companies = bolt-on, medium = platform, large = strategic
- [ ] **Sector-specific weight tuning** — Growth matters more in Tech, assets matter more in Manufacturing
- [ ] **Historical acquisition verification** — Cross-reference with actual M&A databases to validate scoring
- [ ] **Predicted acquisition premium** — Estimate % premium a target might command based on fundamentals

---

## 10. Appendix: Weight Tuning Scenarios

### PE Buyout Weights
```python
weights = {
    "size": 0.30, "profitability": 0.25,
    "growth": 0.10, "financial_health": 0.25, "public_float": 0.10
}
```
Best for: Traditional PE firms seeking stable, profitable, healthy companies with minimal growth premium.

### Strategic Acquisition Weights
```python
weights = {
    "size": 0.15, "profitability": 0.15,
    "growth": 0.35, "financial_health": 0.20, "public_float": 0.15
}
```
Best for: Corporate acquirers buying growth and technology. Willing to pay up for revenue trajectory.

### Distressed / Turnaround Weights
```python
weights = {
    "size": 0.20, "profitability": 0.05,
    "growth": 0.10, "financial_health": 0.05, "public_float": 0.60
}
```
Best for: Turnaround funds targeting public companies with small floats. Willing to ignore current financials.
