# Data

## Raw (`data/raw/`)

Downloaded directly from Kaggle's public dataset-download API (no authentication required for
these two public datasets):

- `raw/bengaluru/Bengaluru_House_Data.csv` — [amitabhajoy/bengaluru-house-price-data](https://www.kaggle.com/datasets/amitabhajoy/bengaluru-house-price-data) (13,320 rows)
- `raw/metro_india/{Bangalore,Chennai,Delhi,Hyderabad,Kolkata,Mumbai}.csv` — [ruchi798/housing-prices-in-metropolitan-areas-of-india](https://www.kaggle.com/datasets/ruchi798/housing-prices-in-metropolitan-areas-of-india); this project uses `Hyderabad.csv` (2,518 rows) and `Chennai.csv` (5,014 rows) for the metropolitan comparison.

To re-download: `curl -L "https://www.kaggle.com/api/v1/datasets/download/<owner>/<dataset-slug>" -o data.zip`

## Cleaned (`data/cleaned/`)

Produced by `notebooks/02_data_cleaning.py` and `notebooks/03_feature_engineering.py`. Both
`.parquet` (for Python/Spark) and `.csv` (for Tableau/Excel/manual inspection) are provided:

- `bengaluru_clean.{parquet,csv}` — Bengaluru, cleaned but pre-tier (12,791 rows, all quality flags retained)
- `housing_cleaned.{parquet,csv}` — Bengaluru, cleaned + locality-tiered (the main analytics table)
- `metro_hyderabad_clean.{parquet,csv}`, `metro_chennai_clean.{parquet,csv}` — metropolitan comparison cities

Regenerate everything with: `source .venv/bin/activate && python notebooks/0{1,2,3,4,5,6}_*.py` (run
in numeric order — each stage reads the previous stage's output).
