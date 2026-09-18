-- ============================================================================
-- 02_locality_analysis.sql  -- Business Questions 1, 2 & 6/7 (comparable-group pricing)
-- ============================================================================

-- Query 3: Top localities by median Rs/sqft (min 10 valid listings for reliability)
WITH locality_stats AS (
    SELECT
        locality_standard,
        COUNT(*)                                   AS listings,
        PERCENTILE(price_per_sqft, 0.5)             AS median_price_per_sqft,
        PERCENTILE(price_lakhs, 0.5)                AS median_price_lakhs
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid'
    GROUP BY locality_standard
    HAVING COUNT(*) >= 10
)
SELECT
    locality_standard,
    listings,
    ROUND(median_price_per_sqft, 0) AS median_price_per_sqft,
    ROUND(median_price_lakhs, 1)    AS median_price_lakhs,
    RANK() OVER (ORDER BY median_price_per_sqft DESC) AS price_rank
FROM locality_stats
ORDER BY median_price_per_sqft DESC
LIMIT 15;

-- Query 4: High listing volume but relatively low Rs/sqft (value-for-volume localities)
WITH locality_stats AS (
    SELECT
        locality_standard,
        COUNT(*)                        AS listings,
        PERCENTILE(price_per_sqft, 0.5) AS median_price_per_sqft
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid'
    GROUP BY locality_standard
    HAVING COUNT(*) >= 10
),
volume_cutoff AS (
    SELECT PERCENTILE(listings, 0.75) AS p75_listings FROM locality_stats
)
SELECT s.locality_standard, s.listings, ROUND(s.median_price_per_sqft, 0) AS median_price_per_sqft
FROM locality_stats s CROSS JOIN volume_cutoff v
WHERE s.listings >= v.p75_listings
ORDER BY s.median_price_per_sqft ASC
LIMIT 15;

-- Query 5: Comparable-group relative pricing -- "statistically expensive" and
-- "value opportunity" localities. A locality is only compared to peers sharing
-- the same BHK category, size bucket AND locality tier (>= 5 listings), so a
-- low price is never mistaken for "cheap" when it's actually just smaller/lower-tier stock.
WITH comparable_groups AS (
    SELECT
        bhk_category, size_bucket, locality_tier,
        PERCENTILE(price_per_sqft, 0.5) AS group_median_price_per_sqft
    FROM housing_cleaned
    WHERE quality_flag != 'Invalid' AND locality_tier NOT LIKE 'Insufficient%'
    GROUP BY bhk_category, size_bucket, locality_tier
),
locality_in_group AS (
    SELECT
        h.locality_standard, h.bhk_category, h.size_bucket, h.locality_tier,
        COUNT(*)                                   AS listings,
        PERCENTILE(h.price_per_sqft, 0.5)           AS locality_median_price_per_sqft
    FROM housing_cleaned h
    WHERE h.quality_flag != 'Invalid' AND h.locality_tier NOT LIKE 'Insufficient%'
    GROUP BY h.locality_standard, h.bhk_category, h.size_bucket, h.locality_tier
    HAVING COUNT(*) >= 5
)
SELECT
    l.locality_standard, l.bhk_category, l.size_bucket, l.locality_tier, l.listings,
    ROUND(l.locality_median_price_per_sqft, 0) AS locality_median_price_per_sqft,
    ROUND(g.group_median_price_per_sqft, 0)    AS comparable_group_median_price_per_sqft,
    ROUND(100.0 * (l.locality_median_price_per_sqft - g.group_median_price_per_sqft)
          / g.group_median_price_per_sqft, 1)  AS pct_diff_vs_comparable_group
FROM locality_in_group l
JOIN comparable_groups g
  ON l.bhk_category = g.bhk_category AND l.size_bucket = g.size_bucket AND l.locality_tier = g.locality_tier
ORDER BY pct_diff_vs_comparable_group ASC   -- ascending = value-opportunity candidates first
LIMIT 20;
