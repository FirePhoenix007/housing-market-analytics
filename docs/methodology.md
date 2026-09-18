# Methodology

## Architecture: raw -> staging -> cleaned -> analytics

- **raw**: CSVs exactly as downloaded from Kaggle (`data/raw/`, or `*_raw` tables in Databricks).
- **staging**: typed and parsed — `total_sqft` text parsed to `total_sqft_clean` + `sqft_parse_method`,
  `size` text parsed to `bhk`, price cast to numeric, `price_per_sqft` derived.
- **cleaned**: locality standardized, `quality_flag`/`quality_flag_detail` assigned. Nothing is deleted
  here — every row survives with a flag.
- **analytics** (`housing_cleaned`): staging + cleaned + engineered features (`bhk_category`,
  `size_bucket`, `locality_tier`). This is the table SQL/Tableau/BI tools should query.

Locally this is implemented in pandas (`notebooks/01`-`04`, run and validated against the real data).
`notebooks/databricks_etl_notebook.py` is a PySpark port of the same logic for Databricks Community
Edition / Delta Lake, written to produce the same columns and thresholds.

## `total_sqft` parsing

The source field mixes at least 5 formats. Each is handled explicitly; anything else becomes `NaN`
with `sqft_parse_method = "unparseable"` rather than being guessed:

| Raw format | Example | Handling |
|---|---|---|
| Plain number | `1056` | Used as-is |
| Range | `1000 - 1285` | Midpoint: `(1000+1285)/2 = 1142.5` |
| Sq. Meter | `1100Sq. Meter` | `* 10.7639` |
| Sq. Yards | `1100Sq. Yards` | `* 9.0` |
| Acres | `1.25Acres` | `* 43560` |
| Cents | `10Cents` | `* 435.6` |
| Guntha | `1Guntha` | `* 1089` |
| Grounds | `5Grounds` | `* 2400` |
| Perch | `4Perch` | `* 272.25` |

## Locality standardization — why fuzzy matching was *not* auto-applied

**Stage A (auto-applied):** raw locality strings are lowercased, punctuation-stripped and
whitespace-collapsed, then compacted (spaces removed) to group pure formatting variants — e.g.
`"Whitefield"`, `"White Field"`, `"WHITEFIELD"` all compact to `whitefield` and are merged with full
confidence. This alone collapsed 1,271 normalized locality strings to 1,257 standardized localities
(the raw `location` field itself had 1,294 distinct raw strings before even that normalization).

**Stage B (evaluated, not applied):** typo correction via fuzzy string matching (Levenshtein-based
ratio) was tested and rejected as an automatic step. On this dataset, similarity scores cannot
separate genuine typos from genuinely distinct localities:

| Pair | Relationship | `fuzz.ratio` |
|---|---|---:|
| `whietfield` / `whitefield` | Typo (same place) | 90.0 |
| `hbr layout` / `hsr layout` | **Different places** (HBR Layout and HSR Layout are both real, distinct Bangalore localities) | 90.0 |
| `8th block jayanagar` / `4th t block jayanagar` | **Different places** (different numbered blocks) | 90.0 |
| `electronic city phase 1` / `electronic city phase 2` | **Different places** (different phases) | 95.7 |

The typo and the false-positive pairs score identically or worse than the false positives — there is
no threshold that keeps the first row and drops the rest. Auto-merging on fuzzy score would have
silently collapsed distinct localities (this was caught during development: an earlier version of this
pipeline did exactly that and was corrected before being used for any statistic). Instead:

- Digit tokens are compared first — if either string contains digits and they differ, no merge is
  ever suggested (rules out phase/block/stage numbers automatically).
- All remaining fuzzy candidates (ratio >= 90, length difference <= 4 chars) are written to
  `reports/locality_mapping_bengaluru.csv` with `method = "fuzzy_suggestion_NOT_applied"` and
  `flag_for_manual_review = True` — 139 candidates in this run — for a human to confirm before
  merging, rather than being applied automatically.

## `quality_flag` thresholds

| Flag | Condition |
|---|---|
| `Invalid` | Missing `bhk`, `total_sqft_clean`, or `price_lakhs`; or `total_sqft_clean <= 0`; or `price_lakhs <= 0`; **or** `price_per_sqft` outside Rs 500-50,000 |
| `Suspicious` | `bath > bhk + 2`; or `total_sqft_clean < 100`; or `total_sqft_clean / bhk < 150`; or `sqft_parse_method == "unparseable"` |
| `Valid` | None of the above |

The Rs 500-50,000/sqft band was set **after** discovering that a small number of Plot-type listings
convert Acres/Perch/Cents into enormous or tiny `total_sqft_clean` values relative to their price,
producing price/sqft as low as Rs 2.26 or as high as ~Rs 1.2 crore per sqft — both near-certainly
unit/entry errors, not real prices. Including them moved Pearson correlation between price and sqft to
a meaningless 0.049; excluding the 49 affected rows restored it to 0.64 (consistent with the
outlier-robust Spearman correlation of 0.736, which was stable before and after). The bound is set
outside the IQR outlier fence for `price_per_sqft` (upper fence ~Rs 12,057) specifically so it only
catches implausible-on-their-face values, not merely statistically unusual (but real) premium/budget
listings — genuine outliers stay in the data with a `Suspicious`/`Valid` flag and are analyzed, not removed.

## Locality tier segmentation

1. Restrict to localities with >= 10 valid listings (below this, a median is not statistically reliable).
2. Rank by median `price_per_sqft`.
3. Tier boundaries are the 33rd and 67th percentiles of that median **across the ranked localities**
   (terciles) — not arbitrary round-number cutoffs.
4. Localities below the listing threshold get `locality_tier = "Insufficient data (<10 listings)"`
   rather than being force-assigned a tier.

Exact thresholds for the current run are in `reports/locality_tier_methodology.json` (regenerated
every time `03_feature_engineering.py` runs, so it never drifts from the code).

## Outlier detection

Both IQR (`Q1 - 1.5*IQR`, `Q3 + 1.5*IQR`) and z-score (|z| > 3) are computed
(`reports/analysis_results.json -> outliers_iqr` / `outliers_zscore`). A statistical outlier is not
automatically a data error — see `quality_flag` above for the separate, explicit rule that removes
implausible unit-conversion errors. Genuine outliers (e.g. a legitimately expensive villa) remain in
the analysis.

## "Value opportunity" / "statistically expensive" methodology

A locality is never called cheap or expensive from its raw price alone. It is compared only to peers
sharing the same **BHK category + size bucket + locality tier** (minimum 5 listings per locality in
that comparable group). `pct_diff_vs_comparable_group` is the locality's median `price_per_sqft` minus
the comparable group's median, as a percentage. See `sql/02_locality_analysis.sql` (Query 5) and
`notebooks/04_statistical_analysis.py::business_questions` for the identical implementation in SQL and
Python.

## Mispriced-listing methodology

Comparable group = same `locality_standard` + `bhk_category` + `size_bucket`, minimum 5 listings.
`expected_price_per_sqft` = the group's median. A listing deviating >= 30% from that expectation is
flagged **potentially** mispriced (below = possible bargain or data issue; above = possible premium or
data issue) — never definitively mispriced, since the comparable group cannot see property condition,
exact micro-location, or legal status.

## Limitations

- Single historical snapshot per dataset — no listing date, so trends over time cannot be measured.
- No construction-year/age field exists in either source dataset; no age bucket was invented.
- Hyderabad/Chennai (metropolitan dataset) and Bengaluru (primary dataset) use different schemas
  (amenity flags vs. bath/balcony/area-type) and are profiled/cleaned in parallel, not merged into one
  cross-city table — combining them at the row level would require assumptions the data doesn't support.
- Correlation results describe association only; no causal claim is made anywhere in this project.
- "Potentially mispriced" and "value opportunity" labels are statistical flags relative to a comparable
  group, not investment advice or a guarantee of an actual pricing error.
