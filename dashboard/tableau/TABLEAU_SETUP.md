# Tableau Dashboard — Setup & Specification

## Verified limitation: Tableau Public cannot hold a live database connection

Per Tableau's own documentation, **Tableau Public only supports extracts (`.hyper` files)** — when
you publish any workbook to Tableau Public, Desktop converts every data source (including a live
database connection) into a static extract at publish time. This is true for every connector,
including Databricks; there is no way to keep a genuinely live, auto-refreshing connection to a
Databricks SQL warehouse on Tableau Public specifically (Tableau Server/Cloud + Tableau Bridge can do
scheduled live refreshes, but that's a paid/enterprise capability, not Tableau Public).

**What this means practically:** the brief's target architecture (Databricks Delta table -> SQL
warehouse -> Tableau Public "live") is only ever a live *connection at build time* in Tableau Desktop;
once published to Tableau Public it becomes a snapshot that you refresh by republishing. This is not a
shortcut — it's how Tableau Public works for every user, not a limitation of this project's setup.

## Two ways to get the dashboard live, in order of fidelity

### Option A (matches the brief's intended architecture)
1. Import `notebooks/databricks_etl_notebook.py` into Databricks Community Edition (Workspace > Import),
   after uploading the 3 raw CSVs to DBFS (see the notebook's first cell for the exact path).
2. Run it top to bottom — creates the `housing_cleaned` Delta table.
3. In **Tableau Desktop** (not the Tableau Public app, which has no connector picker): Connect > More...
   > Databricks. Enter your Community Edition workspace's server hostname and HTTP path (Databricks:
   Compute > your cluster/warehouse > Advanced Options > JDBC/ODBC tab) and a personal access token
   (User Settings > Developer > Access Tokens).
4. Build the 4 dashboards below against `housing_cleaned`.
5. File > Save to Tableau Public As... — this creates the extract automatically. Repeat step 5 whenever
   you want to refresh the published data.

### Option B (fastest to a working, portfolio-ready public link)
1. Open Tableau Public / Desktop.
2. Connect > Text File > `dashboard/tableau/housing_cleaned.csv` (already cleaned, tiered, and
   feature-engineered — no further transformation needed).
3. Build the dashboards, then publish directly.

Either way, the **data and its lineage are identical** — Option A just proves out the Databricks/Delta
architecture end-to-end; Option B ships the same numbers faster.

## Manual steps only you can do
- Log into Tableau (your account) and Databricks (your workspace) — Claude cannot authenticate as you.
- Upload the CSVs to DBFS if using Option A.
- Click Publish in Tableau.

---

## Dashboard 1 — Market Overview

**KPIs** (single-value tiles, computed on `housing_cleaned` filtered to `quality_flag != 'Invalid'`):
Total Listings, Median Property Price (Lakhs), Median Rs/sqft, Median Property Size (sqft), Number of
Localities (distinct `locality_standard`).

**Charts**: Price distribution (histogram, `price_lakhs`, clip/bin at 99th pct to avoid a few extreme
values crushing the axis — see `dashboard/screenshots/01_price_distribution.png` for the equivalent
static chart); Rs/sqft distribution (histogram); Locality ranking (bar, top 15 by median Rs/sqft, min
10 listings — `dashboard/screenshots/03_top_localities_price_per_sqft.png`); BHK distribution (bar,
count by `bhk_category`).

## Dashboard 2 — Locality Intelligence

Locality ranking table (Locality, Listings, Median Price, Median Rs/sqft, Tier — this is exactly
`dashboard/tableau/locality_tier_table.csv`), a map or bar of Rs/sqft by tier, and a listings-by-tier
bar (`dashboard/screenshots/06_listings_by_tier.png`). **Filters**: Locality (search), BHK category,
Locality Tier, Size Bucket.

## Dashboard 3 — Property & BHK Analysis

BHK vs price (box plot, outliers hidden — `dashboard/screenshots/04_price_by_bhk.png`), BHK vs Rs/sqft
(box plot), property size vs price (scatter, colored by BHK), bathrooms vs price (box plot), size-bucket
distribution (bar).

## Dashboard 4 — Value & Outlier Analysis

IQR outlier table (from `sql/04_outlier_analysis.sql` Query 8, or `reports/analysis_results.json ->
outliers_iqr`), potentially-mispriced listings table (`sql/05_value_analysis.sql` Query 10 — include
the `pricing_flag` column so viewers see "Potentially UNDER/OVER-priced", never an unqualified
"mispriced"), price-deviation-vs-comparable-group chart (bar, from `sql/02_locality_analysis.sql`
Query 5), locality comparison (side-by-side of 2-3 selected localities' price distributions).

Keep each dashboard to 4-5 charts max; every chart should answer one of the 7 business questions in
`docs/methodology.md` / `reports/analysis_results.json -> business_questions`, not just showcase a chart type.
