-- ============================================================================
-- 04_outlier_analysis.sql -- Phase 4/5: IQR outlier detection + large-property anomalies
-- ============================================================================

-- Query 8: IQR-based outlier detection on price_per_sqft, computed in-SQL
-- (Q1/Q3 via PERCENTILE, matching the Python IQR methodology 1:1).
WITH bounds AS (
    SELECT
        PERCENTILE(price_per_sqft, 0.25) AS q1,
        PERCENTILE(price_per_sqft, 0.75) AS q3
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid'
),
flagged AS (
    SELECT
        h.*,
        b.q1, b.q3, (b.q3 - b.q1) AS iqr,
        b.q1 - 1.5 * (b.q3 - b.q1) AS lower_bound,
        b.q3 + 1.5 * (b.q3 - b.q1) AS upper_bound
    FROM housing_cleaned h CROSS JOIN bounds b
    WHERE h.quality_flag != 'Invalid'
)
SELECT
    locality_standard, bhk_category, size_bucket, total_sqft_clean, price_lakhs,
    ROUND(price_per_sqft, 0) AS price_per_sqft,
    ROUND(upper_bound, 0)    AS iqr_upper_bound,
    CASE WHEN price_per_sqft > upper_bound THEN 'Above upper fence'
         WHEN price_per_sqft < lower_bound THEN 'Below lower fence'
    END AS outlier_direction
FROM flagged
WHERE price_per_sqft > upper_bound OR price_per_sqft < lower_bound
ORDER BY price_per_sqft DESC
LIMIT 25;

-- Query 9: Large properties (2500+ sqft) with unusually low Rs/sqft, by locality
-- (Business Question 5) -- min 3 listings so a single record can't drive the ranking.
SELECT
    locality_standard,
    COUNT(*)                        AS listings,
    ROUND(PERCENTILE(price_per_sqft, 0.5), 0) AS median_price_per_sqft
FROM housing_cleaned
WHERE quality_flag != 'Invalid' AND size_bucket = '2500+ sqft'
GROUP BY locality_standard
HAVING COUNT(*) >= 3
ORDER BY median_price_per_sqft ASC
LIMIT 10;
