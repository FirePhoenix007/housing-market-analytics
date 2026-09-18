-- ============================================================================
-- 03_bhk_analysis.sql -- Business Question 3 & 4 (BHK and size-bucket patterns)
-- ============================================================================

-- Query 6: Median price and Rs/sqft by BHK category, with rank and lag-over-BHK
-- step-up (how much more the next BHK size costs, in %).
WITH bhk_stats AS (
    SELECT
        bhk_category,
        COUNT(*)                        AS listings,
        PERCENTILE(price_lakhs, 0.5)    AS median_price_lakhs,
        PERCENTILE(price_per_sqft, 0.5) AS median_price_per_sqft
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid' AND bhk_category != 'Unknown'
    GROUP BY bhk_category
)
SELECT
    bhk_category,
    listings,
    ROUND(median_price_lakhs, 1)    AS median_price_lakhs,
    ROUND(median_price_per_sqft, 0) AS median_price_per_sqft,
    ROUND(
        100.0 * (median_price_lakhs - LAG(median_price_lakhs) OVER (ORDER BY
            CASE bhk_category WHEN '1 BHK' THEN 1 WHEN '2 BHK' THEN 2 WHEN '3 BHK' THEN 3
                               WHEN '4 BHK' THEN 4 WHEN '5+ BHK' THEN 5 ELSE 99 END))
        / NULLIF(LAG(median_price_lakhs) OVER (ORDER BY
            CASE bhk_category WHEN '1 BHK' THEN 1 WHEN '2 BHK' THEN 2 WHEN '3 BHK' THEN 3
                               WHEN '4 BHK' THEN 4 WHEN '5+ BHK' THEN 5 ELSE 99 END), 0)
    , 1) AS pct_price_stepup_vs_prior_bhk
FROM bhk_stats
ORDER BY CASE bhk_category WHEN '1 BHK' THEN 1 WHEN '2 BHK' THEN 2 WHEN '3 BHK' THEN 3
                            WHEN '4 BHK' THEN 4 WHEN '5+ BHK' THEN 5 ELSE 99 END;

-- Query 7: Dominant property-size bucket within each locality tier
WITH tier_size_counts AS (
    SELECT
        locality_tier, size_bucket, COUNT(*) AS n,
        DENSE_RANK() OVER (PARTITION BY locality_tier ORDER BY COUNT(*) DESC) AS rnk
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid' AND locality_tier NOT LIKE 'Insufficient%'
    GROUP BY locality_tier, size_bucket
)
SELECT locality_tier, size_bucket AS dominant_size_bucket, n AS listings
FROM tier_size_counts
WHERE rnk = 1
ORDER BY locality_tier;
