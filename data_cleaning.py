"""
data_cleaning.py

Production-grade data cleaning module for the SEC Financial Panel.

This module performs:
    1. Schema validation — types, required columns, ranges
    2. Encoding fixes — non-breaking spaces, Unicode normalization
    3. Outlier handling — winsorization at 1st/99th percentile
    4. Imputation — forward-fill within company, cross-sectional median fallback
    5. Consistency checks — accounting identity, logical constraints
    6. Feature engineering — lagged variables, rolling statistics, growth rates
    7. Export — clean CSV + validation report

Design Principles:
    - Every transformation is logged and reversible
    - No silent data loss — rows removed are counted and reported
    - Validation report is generated automatically
    - Pipeline is idempotent — re-running produces identical output

Usage:
    python data_cleaning.py
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config import (
    PROCESSED_DATA_DIR,
    LOG_SEPARATOR,
    logger,
)

# =============================================================================
# CONFIGURATION
# =============================================================================

INPUT_FILE = PROCESSED_DATA_DIR / "sec_financial_panel.csv"
OUTPUT_FILE = PROCESSED_DATA_DIR / "sec_financial_panel_clean.csv"
REPORT_FILE = PROCESSED_DATA_DIR / "cleaning_report.txt"

# Winsorization bounds
WINSORIZE_LOWER = 0.01
WINSORIZE_UPPER = 0.99

# Minimum coverage threshold to keep a column
MIN_COLUMN_COVERAGE = 0.05  # 5%

# Balance sheet tolerance for accounting checks
ACCOUNTING_TOLERANCE_PCT = 0.02  # 2%


# =============================================================================
# 1. LOAD
# =============================================================================

def load_raw_dataset(filepath: Path = INPUT_FILE) -> pd.DataFrame:
    """Load the raw SEC financial panel, preserving CIK as string."""

    if not filepath.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")

    df = pd.read_csv(filepath, encoding="utf-8-sig")

    # Force CIK to string and zero-pad — pandas reads it as int64
    if "cik" in df.columns:
        df["cik"] = (
            pd.to_numeric(df["cik"], errors="coerce")
            .fillna(0)
            .astype(int)
            .astype(str)
            .str.zfill(10)
        )

    logger.info("Loaded raw dataset: %d rows x %d columns", len(df), len(df.columns))

    return df


# =============================================================================
# 2. ENCODING & TEXT CLEANING
# =============================================================================

def clean_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix encoding artifacts in text columns.

    Issues addressed:
    - \\xa0 (non-breaking space) in company names
    - Leading/trailing whitespace
    - Inconsistent casing in tickers
    """

    df = df.copy()

    # ------------------------------------------------------------------
    # Company names: remove non-breaking spaces, strip whitespace
    # ------------------------------------------------------------------

    if "company" in df.columns:
        df["company"] = (
            df["company"]
            .astype(str)
            .str.replace(r"\xa0", " ", regex=False)
            .str.replace(r" ", " ", regex=False)
            .str.strip()
            .str.title()
        )

    # ------------------------------------------------------------------
    # Tickers: uppercase, strip whitespace
    # ------------------------------------------------------------------

    if "ticker" in df.columns:
        df["ticker"] = (
            df["ticker"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

    # ------------------------------------------------------------------
    # Sector descriptions: strip whitespace
    # ------------------------------------------------------------------

    for col in ["sic_description", "target_sector"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    logger.info("Text columns cleaned")

    return df


# =============================================================================
# 3. SCHEMA VALIDATION
# =============================================================================

def validate_schema(df: pd.DataFrame) -> dict:
    """
    Validate dataset schema and return validation results.

    Checks:
    - Required columns exist
    - Data types are correct
    - No duplicate ticker+period combinations
    - Fiscal year is within reasonable range
    - Fiscal quarter is 1-4
    """

    report = {}

    # ------------------------------------------------------------------
    # Required columns
    # ------------------------------------------------------------------

    required = [
        "company", "ticker", "cik", "period_end",
        "fiscal_year", "fiscal_quarter",
        "total_assets", "total_liabilities", "equity",
    ]

    missing = [c for c in required if c not in df.columns]
    report["missing_columns"] = missing

    if missing:
        logger.error("Missing required columns: %s", missing)

    # ------------------------------------------------------------------
    # Duplicate check
    # ------------------------------------------------------------------

    if "ticker" in df.columns and "period_end" in df.columns:
        dupes = df.duplicated(subset=["ticker", "period_end"]).sum()
        report["duplicate_ticker_periods"] = int(dupes)

        if dupes > 0:
            logger.warning("Found %d duplicate ticker+period rows", dupes)

    # ------------------------------------------------------------------
    # Fiscal year range
    # ------------------------------------------------------------------

    if "fiscal_year" in df.columns:
        fy_min = df["fiscal_year"].min()
        fy_max = df["fiscal_year"].max()
        report["fiscal_year_range"] = (int(fy_min), int(fy_max))

        unreasonable = df[
            (df["fiscal_year"] < 1990) | (df["fiscal_year"] > 2030)
        ]
        report["unreasonable_fiscal_years"] = len(unreasonable)

    # ------------------------------------------------------------------
    # Fiscal quarter
    # ------------------------------------------------------------------

    if "fiscal_quarter" in df.columns:
        valid_quarters = df["fiscal_quarter"].isin([1, 2, 3, 4]).all()
        report["valid_quarters"] = bool(valid_quarters)

    # ------------------------------------------------------------------
    # Column coverage report
    # ------------------------------------------------------------------

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    coverage = {}
    for col in numeric_cols:
        pct = df[col].notna().mean()
        coverage[col] = round(pct * 100, 1)
    report["column_coverage"] = coverage

    logger.info("Schema validation complete")

    return report


# =============================================================================
# 4. FIX IMPOSSIBLE VALUES
# =============================================================================

def fix_impossible_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fix values that are logically impossible.

    Rules:
    - Revenue cannot be negative (set to NaN)
    - Total assets cannot be negative (set to NaN)
    - Current assets cannot be negative (set to NaN)
    - Equity CAN be negative (insolvent companies are real)
    - Net income CAN be negative (losses are real)
    - Filing date cannot be before period end (flag but keep)
    """

    df = df.copy()

    fixes = 0

    # ------------------------------------------------------------------
    # Revenue should not be negative
    # ------------------------------------------------------------------

    if "revenue" in df.columns:
        mask = df["revenue"] < 0
        count = mask.sum()
        if count > 0:
            logger.warning("Fixing %d negative revenue values → NaN", count)
            df.loc[mask, "revenue"] = np.nan
            fixes += count

    # ------------------------------------------------------------------
    # Total assets should not be negative
    # ------------------------------------------------------------------

    if "total_assets" in df.columns:
        mask = df["total_assets"] < 0
        count = mask.sum()
        if count > 0:
            logger.warning("Fixing %d negative total_assets → NaN", count)
            df.loc[mask, "total_assets"] = np.nan
            fixes += count

    # ------------------------------------------------------------------
    # Current assets should not be negative
    # ------------------------------------------------------------------

    if "current_assets" in df.columns:
        mask = df["current_assets"] < 0
        count = mask.sum()
        if count > 0:
            logger.warning("Fixing %d negative current_assets → NaN", count)
            df.loc[mask, "current_assets"] = np.nan
            fixes += count

    # ------------------------------------------------------------------
    # Cost of revenue should not be negative
    # ------------------------------------------------------------------

    if "cost_of_revenue" in df.columns:
        mask = df["cost_of_revenue"] < 0
        count = mask.sum()
        if count > 0:
            logger.warning("Fixing %d negative cost_of_revenue → NaN", count)
            df.loc[mask, "cost_of_revenue"] = np.nan
            fixes += count

    logger.info("Fixed %d impossible values", fixes)

    return df


# =============================================================================
# 5. REMOVE SPURIOUS DUPLICATES
# =============================================================================

def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove duplicate ticker+period rows, keeping the most complete record.

    Priority: row with fewer NaN values wins.
    """

    before = len(df)

    if "ticker" in df.columns and "period_end" in df.columns:

        df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")

        # Count NaN per row (lower = more complete)
        df["_completeness"] = df.isna().sum(axis=1)

        df = (
            df
            .sort_values("_completeness")
            .drop_duplicates(subset=["ticker", "period_end"], keep="first")
            .drop(columns=["_completeness"])
            .reset_index(drop=True)
        )

    removed = before - len(df)
    logger.info("Deduplicated: removed %d rows (%d → %d)", removed, before, len(df))

    return df


# =============================================================================
# 6. WINSORIZE OUTLIERS
# =============================================================================

def winsorize_columns(
    df: pd.DataFrame,
    columns: list = None,
    lower: float = WINSORIZE_LOWER,
    upper: float = WINSORIZE_UPPER,
) -> pd.DataFrame:
    """
    Winsorize numeric columns at given percentiles.

    This caps extreme outliers without removing rows.
    """

    df = df.copy()

    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()
        # Exclude identifiers and time columns
        exclude = ["fiscal_year", "fiscal_quarter", "sic_code"]
        columns = [c for c in columns if c not in exclude]

    clipped_total = 0

    for col in columns:
        if col not in df.columns:
            continue

        series = df[col].dropna()
        if len(series) < 100:
            continue

        q_low = series.quantile(lower)
        q_high = series.quantile(upper)

        before_clip = ((df[col] < q_low) | (df[col] > q_high)).sum()

        df[col] = df[col].clip(lower=q_low, upper=q_high)

        clipped_total += before_clip

    logger.info(
        "Winsorized %d outlier values across %d columns (%.1f%%–%.1f%%)",
        clipped_total,
        len(columns),
        lower * 100,
        upper * 100,
    )

    return df


# =============================================================================
# 7. FORWARD-FILL WITHIN COMPANY
# =============================================================================

def forward_fill_within_company(df: pd.DataFrame) -> pd.DataFrame:
    """
    Forward-fill missing values within each company's time series.

    Quarterly data: if Q2 is missing but Q1 exists, carry Q1 forward.
    This is standard practice for financial panel data.

    Only fills balance sheet and cash flow fields — income statement
    fields are more volatile and should not be carried forward.
    """

    df = df.copy()

    if "ticker" not in df.columns:
        return df

    # Sort by company and time
    df = df.sort_values(["ticker", "period_end"]).reset_index(drop=True)

    # Columns safe to forward-fill (stock-type balance sheet items)
    safe_ffill = [
        "cash", "short_term_investments", "receivables", "inventory",
        "current_assets", "ppe", "goodwill", "intangible_assets",
        "total_assets", "accounts_payable", "current_liabilities",
        "long_term_debt", "total_liabilities", "equity",
    ]

    # Only fill columns that exist
    safe_ffill = [c for c in safe_ffill if c in df.columns]

    ffill_count = 0

    for col in safe_ffill:
        before = df[col].isna().sum()
        df[col] = df.groupby("ticker")[col].ffill()
        after = df[col].isna().sum()
        ffill_count += (before - after)

    logger.info(
        "Forward-filled %d values across %d balance sheet columns",
        ffill_count,
        len(safe_ffill),
    )

    return df


# =============================================================================
# 8. CROSS-SECTIONAL MEDIAN IMPUTATION
# =============================================================================

def median_imputation_by_sector(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill remaining NaN values with the cross-sectional median
    for that fiscal year and sector.

    This preserves the company's relative position within its
    industry rather than using a global mean.
    """

    df = df.copy()

    impute_cols = [
        "current_assets", "current_liabilities", "total_assets",
        "total_liabilities", "equity", "cash", "receivables",
        "inventory", "ppe", "accounts_payable",
    ]

    impute_cols = [c for c in impute_cols if c in df.columns]

    impute_count = 0

    for col in impute_cols:
        before = df[col].isna().sum()

        # Group median by year
        df[col] = df.groupby("fiscal_year")[col].transform(
            lambda x: x.fillna(x.median())
        )

        after = df[col].isna().sum()
        impute_count += (before - after)

    logger.info(
        "Median-imputed %d values across %d columns (by fiscal year)",
        impute_count,
        len(impute_cols),
    )

    return df


# =============================================================================
# 9. ACCOUNTING CONSISTENCY CHECK
# =============================================================================

def validate_accounting_equation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Re-validate the accounting equation after all cleaning steps.

    Assets = Liabilities + Equity ± tolerance
    """

    df = df.copy()

    required = ["total_assets", "total_liabilities", "equity"]

    if not all(c in df.columns for c in required):
        logger.warning("Cannot validate accounting equation — missing columns")
        return df

    # Drop rows where any required field is NaN
    valid_mask = df[required].notna().all(axis=1)

    diff = (
        df["total_assets"]
        - (df["total_liabilities"] + df["equity"])
    ).abs()

    # Relative tolerance: 2% of total assets, floor $1M
    assets = df["total_assets"].fillna(0).abs()
    threshold = (
        assets * ACCOUNTING_TOLERANCE_PCT
    ).clip(lower=1_000_000)

    df["balance_sheet_difference"] = diff
    df["balance_sheet_valid"] = (diff <= threshold) & valid_mask

    valid_count = df["balance_sheet_valid"].sum()
    invalid_count = (~df["balance_sheet_valid"]).sum()

    logger.info(
        "Accounting validation: %d valid, %d invalid",
        valid_count,
        invalid_count,
    )

    return df


# =============================================================================
# 10. DROP LOW-COVERAGE COLUMNS
# =============================================================================

def drop_sparse_columns(
    df: pd.DataFrame,
    threshold: float = MIN_COLUMN_COVERAGE,
) -> pd.DataFrame:
    """
    Drop columns where non-null coverage is below threshold.

    These columns are too sparse to be useful for analysis or ML.
    """

    df = df.copy()

    before_cols = len(df.columns)

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    # Never drop identifiers
    keep = ["fiscal_year", "fiscal_quarter", "sic_code"]
    drop_candidates = [c for c in numeric_cols if c not in keep]

    dropped = []
    for col in drop_candidates:
        coverage = df[col].notna().mean()
        if coverage < threshold:
            dropped.append((col, round(coverage * 100, 1)))
            df = df.drop(columns=[col])

    after_cols = len(df.columns)

    if dropped:
        logger.warning(
            "Dropped %d sparse columns (< %.0f%% coverage): %s",
            len(dropped),
            threshold * 100,
            [(name, pct) for name, pct in dropped],
        )
    else:
        logger.info("No columns dropped — all above %.0f%% coverage", threshold * 100)

    return df


# =============================================================================
# 11. ADD LAGGED FEATURES
# =============================================================================

def add_lagged_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add quarter-over-quarter lagged values for key metrics.

    These are essential for time-series ML models.
    """

    df = df.copy()

    lag_columns = [
        "revenue", "net_income", "operating_cash_flow",
        "total_assets", "equity", "current_assets",
    ]

    lag_columns = [c for c in lag_columns if c in df.columns]

    df = df.sort_values(["ticker", "period_end"]).reset_index(drop=True)

    for col in lag_columns:
        lag_col = f"{col}_lag1"
        df[lag_col] = df.groupby("ticker")[col].shift(1)

    logger.info("Added %d lagged features", len(lag_columns))

    return df


# =============================================================================
# 12. ADD GROWTH RATES
# =============================================================================

def add_growth_rates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add quarter-over-quarter growth rates for key metrics.
    """

    df = df.copy()

    growth_columns = [
        "revenue", "net_income", "total_assets", "equity",
    ]

    growth_columns = [c for c in growth_columns if c in df.columns]

    for col in growth_columns:
        lag_col = f"{col}_lag1"
        if lag_col in df.columns:
            growth_col = f"{col}_growth_qoq"
            df[growth_col] = np.divide(
                df[col] - df[lag_col],
                df[lag_col].abs(),
                out=np.full(len(df), np.nan),
                where=df[lag_col].fillna(0).ne(0),
            )
            df[growth_col] = df[growth_col].round(4)

    logger.info("Added %d growth rate features", len(growth_columns))

    return df


# =============================================================================
# 13. GENERATE CLEANING REPORT
# =============================================================================

def generate_report(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    report: dict,
    filepath: Path = REPORT_FILE,
):
    """Generate a human-readable cleaning report."""

    lines = []
    lines.append("=" * 80)
    lines.append("SEC FINANCIAL PANEL — DATA CLEANING REPORT")
    lines.append("=" * 80)
    lines.append("")

    lines.append("BEFORE CLEANING")
    lines.append(f"  Rows:          {len(df_raw):,}")
    lines.append(f"  Columns:       {len(df_raw.columns):,}")
    lines.append(f"  Memory:        {df_raw.memory_usage(deep=True).sum() / 1e6:.1f} MB")
    lines.append("")

    lines.append("AFTER CLEANING")
    lines.append(f"  Rows:          {len(df_clean):,}")
    lines.append(f"  Columns:       {len(df_clean.columns):,}")
    lines.append(f"  Memory:        {df_clean.memory_usage(deep=True).sum() / 1e6:.1f} MB")
    lines.append("")

    lines.append("ROWS REMOVED")
    lines.append(f"  Total removed: {len(df_raw) - len(df_clean):,}")
    lines.append("")

    lines.append("COLUMN COVERAGE (after cleaning)")
    lines.append("-" * 50)
    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()
    for col in sorted(numeric_cols):
        pct = df_clean[col].notna().mean() * 100
        bar = "#" * int(pct / 2)
        lines.append(f"  {col:35s} {pct:5.1f}% {bar}")
    lines.append("")

    lines.append("SCHEMA VALIDATION")
    lines.append("-" * 50)
    lines.append(f"  Missing columns:     {report.get('missing_columns', [])}")
    lines.append(f"  Duplicate periods:   {report.get('duplicate_ticker_periods', 'N/A')}")
    lines.append(f"  Valid quarters:      {report.get('valid_quarters', 'N/A')}")
    fy_range = report.get("fiscal_year_range", ("N/A", "N/A"))
    lines.append(f"  Fiscal year range:   {fy_range[0]} – {fy_range[1]}")
    lines.append("")

    lines.append("OUTPUT")
    lines.append(f"  File: {filepath}")
    lines.append("")
    lines.append("=" * 80)

    report_text = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(report_text)

    logger.info("Cleaning report saved to %s", filepath)


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def clean_pipeline(input_file: Path = INPUT_FILE, output_file: Path = OUTPUT_FILE):
    """
    Execute the full cleaning pipeline.

    Pipeline steps:
        1. Load raw data
        2. Schema validation (before)
        3. Text/encoding cleanup
        4. Fix impossible values
        5. Deduplicate
        6. Forward-fill within company
        7. Median imputation by sector/year
        8. Winsorize outliers
        9. Re-validate accounting equation
       10. Drop sparse columns
       11. Add lagged features
       12. Add growth rates
       13. Final validation
       14. Export
       15. Generate report
    """

    logger.info(LOG_SEPARATOR)
    logger.info("DATA CLEANING PIPELINE")
    logger.info(LOG_SEPARATOR)

    # ------------------------------------------------------------------
    # 1. Load
    # ------------------------------------------------------------------

    logger.info("Step 1: Loading raw dataset...")
    df_raw = load_raw_dataset(input_file)
    df = df_raw.copy()

    # ------------------------------------------------------------------
    # 2. Schema validation (before cleaning)
    # ------------------------------------------------------------------

    logger.info("Step 2: Validating schema...")
    report = validate_schema(df)

    # ------------------------------------------------------------------
    # 3. Text/encoding cleanup
    # ------------------------------------------------------------------

    logger.info("Step 3: Cleaning text/encoding...")
    df = clean_text_columns(df)

    # ------------------------------------------------------------------
    # 4. Fix impossible values
    # ------------------------------------------------------------------

    logger.info("Step 4: Fixing impossible values...")
    df = fix_impossible_values(df)

    # ------------------------------------------------------------------
    # 5. Deduplicate
    # ------------------------------------------------------------------

    logger.info("Step 5: Deduplicating...")
    df = deduplicate(df)

    # ------------------------------------------------------------------
    # 6. Forward-fill within company
    # ------------------------------------------------------------------

    logger.info("Step 6: Forward-filling within company...")
    df = forward_fill_within_company(df)

    # ------------------------------------------------------------------
    # 7. Median imputation
    # ------------------------------------------------------------------

    logger.info("Step 7: Median imputation by fiscal year...")
    df = median_imputation_by_sector(df)

    # ------------------------------------------------------------------
    # 8. Winsorize outliers
    # ------------------------------------------------------------------

    logger.info("Step 8: Winsorizing outliers...")
    df = winsorize_columns(df)

    # ------------------------------------------------------------------
    # 9. Re-validate accounting
    # ------------------------------------------------------------------

    logger.info("Step 9: Re-validating accounting equation...")
    df = validate_accounting_equation(df)

    # ------------------------------------------------------------------
    # 10. Drop sparse columns
    # ------------------------------------------------------------------

    logger.info("Step 10: Dropping sparse columns...")
    df = drop_sparse_columns(df)

    # ------------------------------------------------------------------
    # 11. Add lagged features
    # ------------------------------------------------------------------

    logger.info("Step 11: Adding lagged features...")
    df = add_lagged_features(df)

    # ------------------------------------------------------------------
    # 12. Add growth rates
    # ------------------------------------------------------------------

    logger.info("Step 12: Adding growth rates...")
    df = add_growth_rates(df)

    # ------------------------------------------------------------------
    # 12b. Winsorize engineered features (growth rates can be extreme)
    # ------------------------------------------------------------------

    logger.info("Step 12b: Winsorizing engineered features...")
    engineered_cols = [
        c for c in df.columns
        if c.endswith("_growth_qoq") or c.endswith("_lag1")
    ]
    engineered_cols = [
        c for c in engineered_cols
        if c in df.columns and c not in ("ticker", "company")
    ]
    df = winsorize_columns(df, columns=engineered_cols, lower=0.01, upper=0.99)

    # ------------------------------------------------------------------
    # 13. Final schema validation
    # ------------------------------------------------------------------

    logger.info("Step 13: Final validation...")
    final_report = validate_schema(df)

    # ------------------------------------------------------------------
    # 14. Export — ensure CIK is zero-padded string
    # ------------------------------------------------------------------

    if "cik" in df.columns:
        df["cik"] = (
            pd.to_numeric(df["cik"], errors="coerce")
            .fillna(0)
            .astype(int)
            .astype(str)
            .str.zfill(10)
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    logger.info("Clean dataset saved: %s", output_file)

    # ------------------------------------------------------------------
    # 15. Report
    # ------------------------------------------------------------------

    generate_report(df_raw, df, final_report)

    return df


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    clean_pipeline()
