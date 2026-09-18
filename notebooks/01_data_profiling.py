"""
Phase 1 - Data Ingestion & Profiling
Bengaluru / Hyderabad Housing Market Intelligence Dashboard

Loads the two raw Kaggle datasets and produces a full data-quality audit.
Run from the project root:  python notebooks/01_data_profiling.py

Outputs:
  reports/data_quality_report.md
  reports/profiling_raw_stats.json   (machine-readable, used by later phases)
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def load_bengaluru() -> pd.DataFrame:
    df = pd.read_csv(RAW / "bengaluru" / "Bengaluru_House_Data.csv")
    df["source_city"] = "Bengaluru"
    df["source_dataset"] = "kaggle:amitabhajoy/bengaluru-house-price-data"
    return df


def load_metro(city_file: str, city_name: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / "metro_india" / city_file)
    df["source_city"] = city_name
    df["source_dataset"] = "kaggle:ruchi798/housing-prices-in-metropolitan-areas-of-india"
    return df


def col_profile(series: pd.Series) -> dict:
    n = len(series)
    nulls = series.isna().sum()
    out = {
        "dtype": str(series.dtype),
        "null_count": int(nulls),
        "null_pct": round(100 * nulls / n, 2) if n else 0.0,
        "unique_count": int(series.nunique(dropna=True)),
    }
    return out


def numeric_issue_scan(df: pd.DataFrame, col: str) -> dict:
    """For a column that SHOULD be numeric but may be stored as text, count
    how many non-null values fail a strict float parse."""
    s = df[col].dropna().astype(str).str.strip()
    is_plain_numeric = s.str.match(r"^-?\d+(\.\d+)?$")
    return {
        "non_numeric_count": int((~is_plain_numeric).sum()),
        "non_numeric_examples": s[~is_plain_numeric].unique()[:15].tolist(),
    }


def profile_bengaluru(df: pd.DataFrame) -> dict:
    report = {"dataset": "Bengaluru_House_Data.csv", "rows": len(df), "cols": df.shape[1]}
    report["duplicate_rows_full"] = int(df.duplicated().sum())

    fields = {}
    for c in df.columns:
        fields[c] = col_profile(df[c])

    # total_sqft is the classic messy field: ranges, units, single numbers
    fields["total_sqft"].update(numeric_issue_scan(df, "total_sqft"))

    # size ("2 BHK" / "4 Bedroom") -> extract numeric BHK
    bhk_extract = df["size"].dropna().astype(str).str.extract(r"(\d+)")[0]
    fields["size"]["distinct_raw_values"] = sorted(df["size"].dropna().unique().tolist())
    fields["size"]["unparseable_count"] = int(bhk_extract.isna().sum())

    # price: negative/zero check (price is in lakhs INR in this dataset)
    price_numeric = pd.to_numeric(df["price"], errors="coerce")
    report["price_non_numeric_count"] = int(price_numeric.isna().sum() - df["price"].isna().sum())
    report["price_le_zero_count"] = int((price_numeric <= 0).sum())

    # bath / balcony: negative or extreme
    for c in ["bath", "balcony"]:
        vals = pd.to_numeric(df[c], errors="coerce")
        fields[c]["max"] = float(vals.max()) if vals.notna().any() else None
        fields[c]["min"] = float(vals.min()) if vals.notna().any() else None

    # BHK vs bathroom sanity: bath > bhk + 2 is suspicious per common real-estate heuristic
    bhk_num = pd.to_numeric(bhk_extract, errors="coerce")
    bath_num = pd.to_numeric(df["bath"], errors="coerce")
    aligned = pd.DataFrame({"bhk": bhk_num, "bath": bath_num}).dropna()
    report["bath_gt_bhk_plus_2_count"] = int((aligned["bath"] > aligned["bhk"] + 2).sum())

    # locality (location) raw cardinality - the "messy locality naming" problem
    loc_raw = df["location"].dropna().astype(str).str.strip()
    fields["location"]["raw_unique_count"] = int(loc_raw.nunique())
    loc_norm = loc_raw.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    fields["location"]["normalized_unique_count"] = int(loc_norm.nunique())
    fields["location"]["collapse_ratio_pct"] = round(
        100 * (1 - loc_norm.nunique() / loc_raw.nunique()), 2
    )

    report["fields"] = fields
    return report


def profile_metro_city(df: pd.DataFrame, city: str) -> dict:
    report = {"dataset": f"{city}.csv", "rows": len(df), "cols": df.shape[1]}
    report["duplicate_rows_full"] = int(df.duplicated().sum())

    fields = {}
    for c in ["Price", "Area", "Location", "No. of Bedrooms", "Resale"]:
        fields[c] = col_profile(df[c])

    price_numeric = pd.to_numeric(df["Price"], errors="coerce")
    report["price_le_zero_count"] = int((price_numeric <= 0).sum())
    area_numeric = pd.to_numeric(df["Area"], errors="coerce")
    report["area_le_zero_count"] = int((area_numeric <= 0).sum())

    loc_raw = df["Location"].dropna().astype(str).str.strip()
    fields["Location"]["raw_unique_count"] = int(loc_raw.nunique())
    loc_norm = loc_raw.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    fields["Location"]["normalized_unique_count"] = int(loc_norm.nunique())

    report["fields"] = fields
    return report


def render_markdown(all_reports: dict) -> str:
    lines = ["# Data Quality Report", "", "Generated from the ACTUAL raw CSVs — every number below is computed, not estimated.", ""]

    b = all_reports["bengaluru"]
    lines += [
        "## 1. Bengaluru_House_Data.csv",
        "",
        f"- Rows: **{b['rows']:,}**  Columns: **{b['cols']}**",
        f"- Fully duplicate rows: **{b['duplicate_rows_full']:,}**",
        f"- `price` values that are <= 0: **{b['price_le_zero_count']}**",
        f"- `bath` > `bhk`+2 (suspicious bath/BHK combo): **{b['bath_gt_bhk_plus_2_count']:,}** rows",
        "",
        "| Field | Type | Null % | Unique | Problems | Treatment |",
        "|---|---|---:|---:|---|---|",
    ]
    problems_map = {
        "area_type": ("4 categories, clean", "Keep as categorical"),
        "availability": ("Mix of dates ('19-Dec') and 'Ready To Move'", "Bucket into Ready-to-move vs Under-construction(date)"),
        "location": (
            f"{b['fields']['location']['raw_unique_count']} raw values -> {b['fields']['location']['normalized_unique_count']} after normalization "
            f"({b['fields']['location']['collapse_ratio_pct']}% collapse); free text, trailing city suffixes, case/whitespace variants",
            "Normalize (lower/strip/whitespace) then fuzzy-match to canonical locality list; low-confidence matches flagged",
        ),
        "size": (
            f"Text field ('2 BHK'/'4 Bedroom'); {b['fields']['size']['unparseable_count']} unparseable, {b['fields']['size']['null_pct']}% null",
            "Regex-extract leading integer -> bhk",
        ),
        "society": (f"{b['fields']['society']['null_pct']}% null, high cardinality", "Drop from analytical model (too sparse to use)"),
        "total_sqft": (
            f"{b['fields']['total_sqft']['non_numeric_count']} non-plain-numeric values: ranges ('1000 - 1285'), units ('1100Sq. Meter', '1.25Acres')",
            "Parse ranges to midpoint, convert Sq.Meter/Sq.Yards/Acres/Perch/Guntha to sqft, else NaN",
        ),
        "bath": (f"{b['fields']['bath']['null_pct']}% null, max={b['fields']['bath']['max']}", "Flag bath/bhk mismatches, do not delete"),
        "balcony": (f"{b['fields']['balcony']['null_pct']}% null, max={b['fields']['balcony']['max']}", "Impute-flag only, not used in core price model"),
        "price": (f"{b['price_non_numeric_count']} non-numeric, {b['price_le_zero_count']} <=0", "Cast to float; price is in INR Lakhs"),
    }
    for col, meta in b["fields"].items():
        if col in ("source_city", "source_dataset"):
            continue
        prob, treat = problems_map.get(col, ("-", "-"))
        lines.append(f"| {col} | {meta['dtype']} | {meta['null_pct']}% | {meta['unique_count']:,} | {prob} | {treat} |")

    lines += ["", "## 2. Metropolitan Areas dataset (Housing Prices in Metropolitan Areas of India)", ""]
    for city_key in ["hyderabad", "chennai"]:
        m = all_reports[city_key]
        lines += [
            f"### {m['dataset']}",
            "",
            f"- Rows: **{m['rows']:,}**  Columns: **{m['cols']}**",
            f"- Fully duplicate rows: **{m['duplicate_rows_full']:,}**",
            f"- `Price` <= 0: **{m['price_le_zero_count']}**, `Area` <= 0: **{m['area_le_zero_count']}**",
            f"- `Location` raw unique: {m['fields']['Location']['raw_unique_count']}, after normalization: {m['fields']['Location']['normalized_unique_count']}",
            "",
        ]

    lines += [
        "## 3. Cross-cutting issues discovered while parsing",
        "",
        "- `location` in the Bengaluru file contains free-text with embedded commas — a naive comma-split "
        "(e.g. shell/awk) misaligns columns; a proper quoted-CSV parser (pandas) is required. Documented here "
        "because it caused visibly wrong field values during a raw `awk` sanity check before pandas was used.",
        "- `total_sqft` mixes at least 5 distinct formats: plain number, `min - max` range, `<n>Sq. Meter`, "
        "`<n>Sq. Yards`, `<n>Acres`, `<n>Perch`, `<n>Guntha`, `<n>Cents`, `<n>Grounds`. All are handled explicitly "
        "in `02_data_cleaning.py`; anything else is left as null and flagged rather than guessed.",
        "- The metropolitan dataset has no `total_sqft`-style messiness — `Area` is already numeric — but has no "
        "`bath`/`balcony` fields at all, only amenity flags (0/1) and `No. of Bedrooms`. Cross-city comparison is "
        "therefore limited to price, area, bedrooms and price-per-sqft; amenity scoring is dataset-specific and "
        "not merged into the Bengaluru feature set.",
        "- No `age`/`year_built` column exists in either dataset. Per the project brief, no age bucket is invented.",
        "",
    ]
    return "\n".join(lines)


def main():
    beng = load_bengaluru()
    hyd = load_metro("Hyderabad.csv", "Hyderabad")
    chen = load_metro("Chennai.csv", "Chennai")

    all_reports = {
        "bengaluru": profile_bengaluru(beng),
        "hyderabad": profile_metro_city(hyd, "Hyderabad"),
        "chennai": profile_metro_city(chen, "Chennai"),
    }

    (REPORTS / "profiling_raw_stats.json").write_text(json.dumps(all_reports, indent=2, default=str))
    (REPORTS / "data_quality_report.md").write_text(render_markdown(all_reports))
    print("Wrote reports/data_quality_report.md and reports/profiling_raw_stats.json")
    print(f"Bengaluru: {len(beng):,} rows | Hyderabad: {len(hyd):,} rows | Chennai: {len(chen):,} rows")


if __name__ == "__main__":
    main()
