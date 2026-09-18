-- ============================================================================
-- 05_value_analysis.sql -- Phase 6: Potentially mispriced listing detection
-- ============================================================================

-- Query 10: Potentially mispriced listings. Comparable group = same locality +
-- BHK category + size bucket (min 5 listings). expected_price_per_sqft = group
-- median. Listings deviating >= 30% from their group are flagged as POTENTIALLY
-- mispriced (below = possible bargain/data issue, above = possible premium/data
-- issue) -- never labeled as definitively mispriced.
WITH comparable AS (
    SELECT
        *,
        COUNT(*) OVER (PARTITION BY locality_standard, bhk_category, size_bucket) AS comparable_group_n,
        PERCENTILE(price_per_sqft, 0.5)
            OVER (PARTITION BY locality_standard, bhk_category, size_bucket)      AS expected_price_per_sqft
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid'
),
scored AS (
    SELECT
        locality_standard, bhk_category, size_bucket, total_sqft_clean, price_lakhs,
        ROUND(price_per_sqft, 0)            AS price_per_sqft,
        ROUND(expected_price_per_sqft, 0)   AS expected_price_per_sqft,
        ROUND(100.0 * (price_per_sqft - expected_price_per_sqft) / expected_price_per_sqft, 1) AS pct_deviation,
        comparable_group_n
    FROM comparable
    WHERE comparable_group_n >= 5
)
SELECT *,
    CASE WHEN pct_deviation <= -30 THEN 'Potentially UNDER-priced vs comparables'
         WHEN pct_deviation >= 30  THEN 'Potentially OVER-priced vs comparables'
    END AS pricing_flag
FROM scored
WHERE pct_deviation <= -30 OR pct_deviation >= 30
ORDER BY ABS(pct_deviation) DESC
LIMIT 30;
