-- ============================================================================
-- 00_data_cleaning.sql
-- Cleans the raw Bengaluru listings CSV in SQL only -- no pandas.
-- Mirrors notebooks/02_data_cleaning.py step for step (sqft parsing, quality_flag
-- rules, bhk/size buckets) so the two pipelines can be checked against each other.
-- Written for DuckDB; the string/regex functions used here also exist in
-- Spark SQL (Databricks), so this ports over with minor syntax changes.
--
-- What this script does NOT do: the fuzzy locality-typo pass (comparing every
-- pair of locality names for near-duplicates) stays in Python. That needs a
-- string-similarity score across ~1,200 x 1,200 pairs, which plain SQL isn't
-- built for -- and even in Python it's deliberately NOT auto-applied (see
-- docs/methodology.md). This script only does the safe, automatic part:
-- collapsing whitespace/punctuation variants of the same name.
--
-- Checked against notebooks/02_data_cleaning.py's output on the same file: row
-- count, quality_flag counts, bhk_category counts, size_bucket counts, and the
-- sum of total_sqft_clean and price_per_sqft all match exactly. Locality name
-- grouping also matches (1,257 standardized localities both ways); in ~8 of
-- those groups the two pick a different capitalization as the display name
-- when two raw spellings occur with equal frequency (a tie-break order
-- difference, not a different grouping) -- cosmetic only, doesn't change any
-- count or statistic.
-- ============================================================================

WITH raw AS (
    -- society is kept here only so DISTINCT dedupes on the same columns pandas
    -- does (df.drop_duplicates() uses every column); it's dropped after dedup.
    SELECT area_type, availability, location, size, society, total_sqft, bath, balcony, price
    FROM read_csv_auto('data/raw/bengaluru/Bengaluru_House_Data.csv')
),

deduped AS (
    SELECT area_type, availability, location, size, total_sqft, bath, balcony, price
    FROM (SELECT DISTINCT * FROM raw)
),

-- Parse total_sqft: plain numbers, "1000 - 1200" ranges (midpoint), and
-- Sq.Meter / Sq.Yards / Acres / Cents / Guntha / Grounds / Perch conversions.
sqft_parsed AS (
    SELECT *,
        CASE
            WHEN total_sqft SIMILAR TO '[0-9]+(\.[0-9]+)?' THEN CAST(total_sqft AS DOUBLE)
            WHEN total_sqft SIMILAR TO '[0-9]+(\.[0-9]+)?\s*-\s*[0-9]+(\.[0-9]+)?' THEN
                (CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE)
                 + CAST(regexp_extract(total_sqft, '-\s*([0-9]+(\.[0-9]+)?)$', 1) AS DOUBLE)) / 2
            WHEN total_sqft ILIKE '%Sq. Meter%' THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 10.7639
            WHEN total_sqft ILIKE '%Sq. Yards%' THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 9.0
            WHEN total_sqft ILIKE '%Acres%'     THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 43560.0
            WHEN total_sqft ILIKE '%Cents%'     THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 435.6
            WHEN total_sqft ILIKE '%Guntha%'    THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 1089.0
            WHEN total_sqft ILIKE '%Grounds%'   THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 2400.0
            WHEN total_sqft ILIKE '%Perch%'     THEN CAST(regexp_extract(total_sqft, '^([0-9]+(\.[0-9]+)?)', 1) AS DOUBLE) * 272.25
            ELSE NULL
        END AS total_sqft_clean,
        CASE
            WHEN total_sqft SIMILAR TO '[0-9]+(\.[0-9]+)?' THEN 'plain'
            WHEN total_sqft SIMILAR TO '[0-9]+(\.[0-9]+)?\s*-\s*[0-9]+(\.[0-9]+)?' THEN 'range_midpoint'
            WHEN total_sqft ILIKE '%Sq. Meter%' THEN 'unit_convert:sq. meter'
            WHEN total_sqft ILIKE '%Sq. Yards%' THEN 'unit_convert:sq. yards'
            WHEN total_sqft ILIKE '%Acres%'     THEN 'unit_convert:acres'
            WHEN total_sqft ILIKE '%Cents%'     THEN 'unit_convert:cents'
            WHEN total_sqft ILIKE '%Guntha%'    THEN 'unit_convert:guntha'
            WHEN total_sqft ILIKE '%Grounds%'   THEN 'unit_convert:grounds'
            WHEN total_sqft ILIKE '%Perch%'     THEN 'unit_convert:perch'
            ELSE 'unparseable'
        END AS sqft_parse_method,
        CAST(regexp_extract(size, '([0-9]+)', 1) AS DOUBLE) AS bhk,
        CAST(price AS DOUBLE) AS price_lakhs,
        CAST(price AS DOUBLE) * 100000 AS price_inr,
        CAST(bath AS DOUBLE) AS bath_clean,
        CAST(balcony AS DOUBLE) AS balcony_clean,
        trim(coalesce(location, 'Unknown')) AS location_raw
    FROM deduped
),

with_ppsf AS (
    SELECT *,
        CASE WHEN total_sqft_clean > 0 THEN price_inr / total_sqft_clean END AS price_per_sqft
    FROM sqft_parsed
),

-- Normalize locality text: lowercase, strip punctuation, collapse whitespace.
normalized AS (
    SELECT *,
        trim(regexp_replace(regexp_replace(lower(location_raw), '[^a-z0-9 ]', ' ', 'g'), '\s+', ' ', 'g')) AS location_norm
    FROM with_ppsf
),

-- Compact form (letters/digits only) groups "White Field" / "Whitefield" / "whitefield" together.
with_compact AS (
    SELECT *, regexp_replace(location_norm, '[^a-z0-9]', '', 'g') AS location_compact
    FROM normalized
),

-- Canonical display name per compact group = the most common raw spelling.
locality_counts AS (
    SELECT location_compact, location_raw, COUNT(*) AS n
    FROM with_compact
    GROUP BY location_compact, location_raw
),
canonical AS (
    SELECT location_compact, location_raw AS locality_standard
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY location_compact ORDER BY n DESC, location_raw) AS rn
        FROM locality_counts
    )
    WHERE rn = 1
),

joined AS (
    SELECT w.*, c.locality_standard
    FROM with_compact w
    JOIN canonical c USING (location_compact)
),

-- quality_flag: same three rules as the Python pipeline (see docs/methodology.md
-- for why 500-50000 Rs/sqft is the implausibility bound, not a round guess).
classified AS (
    SELECT *,
        CASE
            WHEN bhk IS NULL OR total_sqft_clean IS NULL OR price_lakhs IS NULL
                 OR total_sqft_clean <= 0 OR price_lakhs <= 0 THEN 'Invalid'
            WHEN price_per_sqft IS NOT NULL AND (price_per_sqft < 500 OR price_per_sqft > 50000)
                 THEN 'Invalid'
            WHEN (bath_clean IS NOT NULL AND bath_clean > bhk + 2)
                 OR total_sqft_clean < 100
                 OR (bhk >= 1 AND total_sqft_clean / bhk < 150)
                 OR sqft_parse_method = 'unparseable'
                THEN 'Suspicious'
            ELSE 'Valid'
        END AS quality_flag
    FROM joined
)

SELECT
    'Bengaluru' AS city,
    locality_standard,
    location_raw,
    bhk,
    CASE WHEN bhk >= 5 THEN '5+ BHK'
         WHEN bhk IS NOT NULL THEN CAST(CAST(bhk AS INT) AS VARCHAR) || ' BHK'
         ELSE 'Unknown' END AS bhk_category,
    total_sqft_clean,
    sqft_parse_method,
    CASE
        WHEN total_sqft_clean IS NULL THEN 'Unknown'
        WHEN total_sqft_clean < 500 THEN '<500 sqft'
        WHEN total_sqft_clean < 1000 THEN '500-1000 sqft'
        WHEN total_sqft_clean < 1500 THEN '1000-1500 sqft'
        WHEN total_sqft_clean < 2500 THEN '1500-2500 sqft'
        ELSE '2500+ sqft'
    END AS size_bucket,
    bath_clean AS bath,
    balcony_clean AS balcony,
    price_lakhs,
    price_inr,
    price_per_sqft,
    area_type,
    CASE WHEN lower(trim(availability)) = 'ready to move' THEN 'Ready to move'
         ELSE 'Under construction' END AS availability_bucket,
    quality_flag
FROM classified;
