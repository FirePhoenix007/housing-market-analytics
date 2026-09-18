# Data Quality Report

Generated from the ACTUAL raw CSVs — every number below is computed, not estimated.

## 1. Bengaluru_House_Data.csv

- Rows: **13,320**  Columns: **11**
- Fully duplicate rows: **529**
- `price` values that are <= 0: **0**
- `bath` > `bhk`+2 (suspicious bath/BHK combo): **16** rows

| Field | Type | Null % | Unique | Problems | Treatment |
|---|---|---:|---:|---|---|
| area_type | str | 0.0% | 4 | 4 categories, clean | Keep as categorical |
| availability | str | 0.0% | 81 | Mix of dates ('19-Dec') and 'Ready To Move' | Bucket into Ready-to-move vs Under-construction(date) |
| location | str | 0.01% | 1,305 | 1294 raw values -> 1271 after normalization (1.78% collapse); free text, trailing city suffixes, case/whitespace variants | Normalize (lower/strip/whitespace) then fuzzy-match to canonical locality list; low-confidence matches flagged |
| size | str | 0.12% | 31 | Text field ('2 BHK'/'4 Bedroom'); 0 unparseable, 0.12% null | Regex-extract leading integer -> bhk |
| society | str | 41.31% | 2,688 | 41.31% null, high cardinality | Drop from analytical model (too sparse to use) |
| total_sqft | str | 0.0% | 2,117 | 247 non-plain-numeric values: ranges ('1000 - 1285'), units ('1100Sq. Meter', '1.25Acres') | Parse ranges to midpoint, convert Sq.Meter/Sq.Yards/Acres/Perch/Guntha to sqft, else NaN |
| bath | float64 | 0.55% | 19 | 0.55% null, max=40.0 | Flag bath/bhk mismatches, do not delete |
| balcony | float64 | 4.57% | 4 | 4.57% null, max=3.0 | Impute-flag only, not used in core price model |
| price | float64 | 0.0% | 1,994 | 0 non-numeric, 0 <=0 | Cast to float; price is in INR Lakhs |

## 2. Metropolitan Areas dataset (Housing Prices in Metropolitan Areas of India)

### Hyderabad.csv

- Rows: **2,518**  Columns: **42**
- Fully duplicate rows: **520**
- `Price` <= 0: **0**, `Area` <= 0: **0**
- `Location` raw unique: 243, after normalization: 243

### Chennai.csv

- Rows: **5,014**  Columns: **42**
- Fully duplicate rows: **707**
- `Price` <= 0: **0**, `Area` <= 0: **0**
- `Location` raw unique: 185, after normalization: 185

## 3. Cross-cutting issues discovered while parsing

- `location` in the Bengaluru file contains free-text with embedded commas — a naive comma-split (e.g. shell/awk) misaligns columns; a proper quoted-CSV parser (pandas) is required. Documented here because it caused visibly wrong field values during a raw `awk` sanity check before pandas was used.
- `total_sqft` mixes at least 5 distinct formats: plain number, `min - max` range, `<n>Sq. Meter`, `<n>Sq. Yards`, `<n>Acres`, `<n>Perch`, `<n>Guntha`, `<n>Cents`, `<n>Grounds`. All are handled explicitly in `02_data_cleaning.py`; anything else is left as null and flagged rather than guessed.
- The metropolitan dataset has no `total_sqft`-style messiness — `Area` is already numeric — but has no `bath`/`balcony` fields at all, only amenity flags (0/1) and `No. of Bedrooms`. Cross-city comparison is therefore limited to price, area, bedrooms and price-per-sqft; amenity scoring is dataset-specific and not merged into the Bengaluru feature set.
- No `age`/`year_built` column exists in either dataset. Per the project brief, no age bucket is invented.
