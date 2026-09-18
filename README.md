# Bengaluru / Hyderabad Housing Market Intelligence Dashboard

An end-to-end data analytics project: raw Kaggle CSVs -> data-quality audit -> documented cleaning ->
Delta Lake analytics table -> statistical analysis -> executive insight memo -> Tableau dashboard spec.
Every number in `reports/` and `reports/insight_memo.md` is computed from the real datasets — nothing
is estimated or fabricated (see `docs/methodology.md` for the full audit trail).

## 1. Project Overview

Bengaluru's residential real-estate listings are notoriously messy — inconsistent locality spelling,
mixed area-unit formats, and no reliable ground truth for "is this locality expensive." This project
builds a reproducible pipeline that cleans that mess with documented, defensible rules, segments
localities into tiers using actual price distributions (not guesswork), and answers seven concrete
business questions with a comparable-group methodology that avoids the common mistake of calling a
locality "cheap" just because its raw price is low.

## 2. Business Problem

Buyers, sellers and analysts need locality-level price benchmarks, but the raw data can't be queried
directly: `location` has 1,294 raw spellings for far fewer real places, `total_sqft` mixes 5+ formats,
and there is no locality tier or comparable-group framework to judge whether a price is actually high
or low for its context.

## 3. Objectives

1. Quantify and document every data-quality issue before touching the data.
2. Clean without silently deleting — every record keeps a `quality_flag`.
3. Build a statistically-derived locality tier segmentation (not arbitrary).
4. Answer 7 business questions with a comparable-group methodology.
5. Ship a Databricks/Delta pipeline, 10 SQL queries, and a Tableau dashboard spec.
6. Produce a 1-page insight memo where every number traces back to `reports/analysis_results.json`.

## 4. Dataset

- [Bengaluru House Price Data](https://www.kaggle.com/datasets/amitabhajoy/bengaluru-house-price-data) (Kaggle) — 13,320 rows, primary analysis
- [Housing Prices in Metropolitan Areas of India](https://www.kaggle.com/datasets/ruchi798/housing-prices-in-metropolitan-areas-of-india) (Kaggle) — Hyderabad (2,518 rows) and Chennai (5,014 rows) used for metropolitan comparison

See `data/README.md` for exact download commands and file layout.

## 5. Technology Stack

Python (Pandas, NumPy, SciPy, rapidfuzz), SQL (Databricks SQL / Spark SQL), Databricks + Delta Lake,
Tableau Public, Matplotlib/Seaborn, Git.

## 6. Architecture

```
raw (CSV as downloaded)
  -> staging (typed: total_sqft parsed, bhk extracted, price_per_sqft derived)
    -> cleaned (locality standardized, quality_flag assigned — nothing deleted)
      -> analytics: housing_cleaned Delta table (+ bhk_category, size_bucket, locality_tier)
        -> SQL (sql/*.sql) + Tableau (dashboard/tableau/)
```

Implemented twice: locally in pandas (`notebooks/01`-`06`, run and validated against the real data —
every number in this README came from these runs) and as a PySpark/Delta port
(`notebooks/databricks_etl_notebook.py`) for Databricks Community Edition.

## 7. Data-Cleaning Methodology (summary — full detail in `docs/methodology.md`)

- **`total_sqft`**: plain numbers kept; ranges converted to midpoint; Sq.Meter/Sq.Yards/Acres/Cents/
  Guntha/Grounds/Perch converted to sqft via documented factors.
- **Locality standardization**: whitespace/case/punctuation variants auto-merged (1,271 -> 1,257
  standardized localities). Fuzzy typo-correction was tested and **deliberately not auto-applied** —
  on this data, similarity scores can't separate real typos ("whietfield"/"whitefield", ratio 90) from
  genuinely different places ("HBR Layout"/"HSR Layout", also ratio 90). All 139 fuzzy candidates are
  logged in `reports/locality_mapping_bengaluru.csv` for manual review instead.
- **`quality_flag`**: `Invalid` (missing core fields, or price/sqft outside a Rs 500-50,000/sqft
  plausibility band — this band caught 49 unit-conversion errors, e.g. a "2 BHK" parsed to 1.3M sqft
  from a mis-recorded Acres value), `Suspicious` (bath/BHK mismatch, implausible sqft-per-BHK), `Valid`.

## 8. Feature Engineering

`bhk_category` (1/2/3/4/5+ BHK), `size_bucket` (5 bands from <500 to 2500+ sqft), `price_per_sqft`,
`locality_tier` (see below). No `age_bucket` was invented — neither source dataset has a
construction-year field.

## 9. Statistical Methodology

Descriptive stats (mean/median/std/IQR) on price, price/sqft, sqft, BHK, bath. IQR outlier detection
(`Q1 - 1.5*IQR` / `Q3 + 1.5*IQR`) and z-score (|z|>3) computed independently. Pearson **and** Spearman
correlation reported side by side — Pearson between price and sqft was a meaningless 0.049 before the
price/sqft plausibility filter (a few extreme unit-conversion errors dominate a mean-based statistic)
and 0.64 after, consistent with Spearman's outlier-robust 0.736 both times. **Locality tiers** are
built from terciles of median price/sqft among localities with >= 10 listings (see
`reports/locality_tier_methodology.json`). "Value opportunity" and "statistically expensive" localities
are found by comparing each locality only to peers sharing the same BHK category, size bucket **and**
locality tier (min 5 listings) — never by comparing raw prices across different tiers.

## 10. Key Findings (numbers from `reports/insight_memo.md` / `reports/analysis_results.json`)

1. **HAL 2nd Stage** has the highest verified median price/sqft (Rs 24,167, n=11) — 4.4x the city
   median of Rs 5,482/sqft.
2. Price steps up sharply at 4 BHK (median Rs 204.0L vs Rs 90.0L for 3 BHK); 5+ BHK carries the
   *highest* Rs/sqft (Rs 11,250) but a *lower* median price (Rs 165.0L) than 4 BHK — not a simple
   "more rooms = more expensive" curve.
3. Comparable-group analysis (same BHK + size + tier) finds **Chandapura** (1 BHK, 500-1000 sqft,
   Tier 3) priced 40.9% below its true peer group — a specific, named, statistically-grounded
   candidate for further due diligence, not a blanket "cheap locality" claim.
4. 1,191 of 12,742 valid listings (9.35%) are IQR outliers on price/sqft; a separate comparable-group
   check flags 513 listings as potentially under-priced and 850 as potentially over-priced (>=30%
   deviation from their local comparable group).

Full memo with methodology and limitations: [`reports/insight_memo.pdf`](reports/insight_memo.pdf).

## 11. Dashboard Preview

Static chart equivalents in `dashboard/screenshots/` (generated by `notebooks/05_visualizations.py`
from the real cleaned data): price distribution, price/sqft distribution, top-15 localities, price by
BHK, correlation heatmap, listings by tier. Full interactive Tableau dashboard spec (4 pages) and setup
instructions — including a verified explanation of what Tableau Public can and cannot connect to
live — are in [`dashboard/tableau/TABLEAU_SETUP.md`](dashboard/tableau/TABLEAU_SETUP.md).

## 12. How to Reproduce

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pandas numpy matplotlib seaborn scipy rapidfuzz pyarrow reportlab

python notebooks/01_data_profiling.py        # -> reports/data_quality_report.md
python notebooks/02_data_cleaning.py         # -> data/cleaned/*_clean.{csv,parquet}
python notebooks/03_feature_engineering.py   # -> data/cleaned/housing_cleaned.*, locality tiers
python notebooks/04_statistical_analysis.py  # -> reports/analysis_results.json
python notebooks/05_visualizations.py        # -> dashboard/screenshots/*.png
python notebooks/06_generate_insight_memo.py # -> reports/insight_memo.{md,pdf}
```

For the Databricks/Delta/Tableau path, see `notebooks/databricks_etl_notebook.py` and
`dashboard/tableau/TABLEAU_SETUP.md`.

## 13. Repository Structure

```
housing-market-analytics/
├── README.md
├── data/
│   ├── README.md
│   ├── raw/                 (as downloaded from Kaggle)
│   └── cleaned/             (pipeline output, .csv + .parquet)
├── notebooks/
│   ├── 01_data_profiling.py
│   ├── 02_data_cleaning.py
│   ├── 03_feature_engineering.py
│   ├── 04_statistical_analysis.py
│   ├── 05_visualizations.py
│   ├── 06_generate_insight_memo.py
│   └── databricks_etl_notebook.py   (PySpark/Delta port for Databricks CE)
├── sql/
│   ├── 01_data_quality.sql
│   ├── 02_locality_analysis.sql
│   ├── 03_bhk_analysis.sql
│   ├── 04_outlier_analysis.sql
│   └── 05_value_analysis.sql
├── dashboard/
│   ├── tableau/              (Tableau-ready CSV extracts + TABLEAU_SETUP.md)
│   └── screenshots/          (static chart previews)
├── reports/
│   ├── data_quality_report.md
│   ├── locality_mapping_bengaluru.csv
│   ├── locality_tier_table.csv
│   ├── analysis_results.json
│   └── insight_memo.{md,pdf}
└── docs/
    ├── methodology.md
    └── data_dictionary.md
```

## 14. Limitations

See `docs/methodology.md` (§ Limitations) — single historical snapshot per dataset, no age/construction
-year field in either source, Bengaluru and metropolitan datasets are schema-incompatible for a row-level
merge, correlation is not causation, and "potentially mispriced"/"value opportunity" are statistical
flags, not investment advice.

## 15. Future Improvements

- Bring in a real gazetteer of Bangalore localities to safely resolve the 139 flagged fuzzy-match
  candidates instead of leaving them for manual review.
- Add listing-date data (not present in either source) to move from a single snapshot to a trend.
- Automate Tableau extract refresh via Tableau Bridge if this moves beyond a portfolio project.
