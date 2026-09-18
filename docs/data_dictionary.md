# Data Dictionary — `housing_cleaned` (Bengaluru analytics table)

Source: Kaggle `amitabhajoy/bengaluru-house-price-data`, cleaned by `notebooks/02_data_cleaning.py`
and `notebooks/03_feature_engineering.py`. Row grain: one listing.

| Column | Description | Data Type | Example | Transformation |
|---|---|---|---|---|
| `city` | City name | string | `Bengaluru` | Constant, added for future multi-city union |
| `locality_standard` | Standardized locality name | string | `Whitefield` | Whitespace/case/punctuation-normalized; see `reports/locality_mapping_bengaluru.csv` for the full raw->standard mapping |
| `location_raw` | Original locality text as scraped | string | `Whitefield ` | Kept for traceability/audit |
| `bhk` | Number of bedrooms | double | `2.0` | Regex-extracted leading integer from `size` (e.g. "2 BHK", "4 Bedroom") |
| `bhk_category` | Bucketed BHK | string | `2 BHK` | `bhk` capped at "5+ BHK" |
| `total_sqft_clean` | Property area in sqft | double | `1056.0` | Parsed from `total_sqft`: plain numbers kept as-is; ranges ("1000 - 1285") converted to midpoint; unit suffixes (Sq. Meter, Sq. Yards, Acres, Cents, Guntha, Grounds, Perch) converted to sqft |
| `sqft_parse_method` | How `total_sqft_clean` was derived | string | `range_midpoint` | One of: `plain`, `range_midpoint`, `unit_convert:<unit>`, `unparseable`, `null` |
| `size_bucket` | Property size band | string | `1000-1500 sqft` | Derived from `total_sqft_clean`: <500, 500-1000, 1000-1500, 1500-2500, 2500+ |
| `bath` | Number of bathrooms | double | `2.0` | Cast to numeric |
| `balcony` | Number of balconies | double | `1.0` | Cast to numeric |
| `price_lakhs` | Listed price in INR Lakhs (source unit) | double | `39.07` | Cast to numeric |
| `price_inr` | Listed price in absolute INR | double | `3907000.0` | `price_lakhs * 100000` |
| `price_per_sqft` | Price per sqft in INR | double | `3699.24` | `price_inr / total_sqft_clean` |
| `area_type` | Listing area type (source field) | string | `Super built-up  Area` | Unmodified |
| `availability_bucket` | Ready-to-move vs under-construction | string | `Ready to move` | `availability == "Ready To Move"` -> "Ready to move", else "Under construction" (source encodes construction-completion month as a date string) |
| `age_bucket` | Property age band | string | `Not available in source data` | **Not computed** — source data has no construction-year/age field; inventing one would violate the no-fabrication requirement |
| `quality_flag` | Overall record quality | string | `Valid` | One of `Valid`, `Suspicious`, `Invalid` — see `docs/methodology.md` for thresholds |
| `quality_flag_detail` | Specific quality issue(s) | string | `Suspicious:bath_exceeds_bhk+2` | Comma-joined reason codes when not Valid/Invalid |
| `locality_tier` | Statistically-derived locality segment | string | `Tier 1 - Premium` | Tercile of median `price_per_sqft` among localities with >= 10 valid listings; see `reports/locality_tier_methodology.json` for exact thresholds |

## Metropolitan comparison tables (`metro_hyderabad_clean`, `metro_chennai_clean`)

Source: Kaggle `ruchi798/housing-prices-in-metropolitan-areas-of-india` (`Hyderabad.csv`, `Chennai.csv`).
Different schema from Bengaluru — no `bath`/`balcony`/`total_sqft` text parsing needed (`Area` is
already numeric); instead each row carries ~37 binary amenity flags (Gymnasium, SwimmingPool, etc.).

| Column | Description | Data Type | Transformation |
|---|---|---|---|
| `price_inr` | Listed price in INR | double | Cast from source `Price` |
| `total_sqft_clean` | Property area in sqft | double | Cast from source `Area` (already numeric, no parsing needed) |
| `bhk` | Number of bedrooms | double | Cast from source `No. of Bedrooms` |
| `bhk_category`, `size_bucket` | Same definitions as Bengaluru table | string | Same bucketing logic |
| `price_per_sqft` | Price per sqft | double | `price_inr / total_sqft_clean` |
| `locality_standard` | Locality name | string | Source `Location`, trimmed only (not fuzzy-standardized — smaller, cleaner locality set than Bengaluru) |
| `amenity_score` | Count of amenities present | int | Row-sum of the ~37 binary amenity columns |
| `amenity_count_total` | Total amenity columns available | int | Constant per file |
| `quality_flag` | `Valid`/`Invalid` | string | `Invalid` if price, area, or bedroom count is missing/non-positive |
