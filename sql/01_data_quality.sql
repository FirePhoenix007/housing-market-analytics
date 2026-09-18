-- ============================================================================
-- 01_data_quality.sql
-- Run against the `housing_cleaned` Delta table (see docs/methodology.md for
-- the raw -> staging -> cleaned -> analytics architecture).
-- Assumes catalog/schema context has been set, e.g.:
--   USE CATALOG hive_metastore; USE SCHEMA housing_analytics;
-- ============================================================================

-- Query 1: Row counts and quality_flag distribution (Valid / Suspicious / Invalid)
SELECT
    quality_flag,
    COUNT(*)                                   AS n_listings,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total
FROM housing_cleaned
GROUP BY quality_flag
ORDER BY n_listings DESC;

-- Query 2: Null / completeness audit per key analytical column
SELECT
    'bhk'              AS column_name, COUNT(*) FILTER (WHERE bhk IS NULL)               AS null_count FROM housing_cleaned
UNION ALL
SELECT 'total_sqft_clean', COUNT(*) FILTER (WHERE total_sqft_clean IS NULL) FROM housing_cleaned
UNION ALL
SELECT 'price_lakhs',      COUNT(*) FILTER (WHERE price_lakhs IS NULL)      FROM housing_cleaned
UNION ALL
SELECT 'locality_standard', COUNT(*) FILTER (WHERE locality_standard IS NULL) FROM housing_cleaned
UNION ALL
SELECT 'locality_tier',    COUNT(*) FILTER (WHERE locality_tier IS NULL)    FROM housing_cleaned;
