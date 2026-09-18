# Bengaluru Housing Market — Executive Insight Memo

*Bengaluru House Price Data (Kaggle), 13,320 raw rows -> 12,791 after removing 529 exact-duplicate rows -> 12,742 used for statistical analysis after excluding 49 further Invalid records (missing core fields, or price/sqft values outside the Rs 500-50,000 plausibility band established during data cleaning).*

## Executive Summary

Bengaluru's residential market shows a wide and statistically defensible spread in price per square foot across localities (city median Rs 5,482/sqft), with premium micro-markets commanding multiples of the city median. Price does not scale linearly with BHK size — the jump from 3 BHK to 4 BHK is far steeper than any other step — and a comparable-group methodology (matching on BHK, size band and locality tier) surfaces specific, named localities that price meaningfully below their true peers.

## Finding 1: Premium localities trade at multiples of the city median, not just a modest premium

**HAL 2nd Stage** has the highest verified median price per sqft in the dataset at **Rs 24,167/sqft** (n=11 listings) — **4.4x** the city-wide median of Rs 5,482/sqft. Locality tiers, built from terciles of median Rs/sqft among localities with >= 10 listings, place the Tier 1 (Premium) cutoff at Rs 6,089/sqft and Tier 3 (Value) below Rs 4,991/sqft — a >1.2x spread between tier boundaries.

## Finding 2: The price curve steepens sharply at 4 BHK, and 5+ BHK is not simply "more expensive"

Median price by BHK category: 1 BHK Rs 34.6L, 2 BHK Rs 54.0L, 3 BHK Rs 90.0L, **4 BHK Rs 204.0L**, 5+ BHK Rs 165.0L. The 3->4 BHK step is the largest jump in the series. Notably, 5+ BHK properties carry the **highest** Rs/sqft rate (Rs 11,250/sqft) but a **lower** median absolute price than 4 BHK (Rs 165.0L vs Rs 204.0L) — consistent with 5+ BHK listings in this dataset skewing toward smaller, premium-rate homes rather than larger ones, not a simple "more rooms = more expensive" pattern.

## Finding 3: Comparable-group analysis identifies specific under-priced pockets — not just "cheap" localities

Comparing each locality only against peers with the **same BHK category, size bucket and locality tier** (minimum 5 listings), **Chandapura** (1 BHK, 500-1000 sqft, Tier 3 - Value) prices **40.9% below** its true comparable group (Rs 2,550/sqft vs a group median of Rs 4,314/sqft, n=10). This is a within-tier gap, not an artifact of comparing a Tier 3 locality to Tier 1 pricing. Separately, a listing-level comparable-group check (same locality + BHK + size, n>=5, threshold 30%) flags **513** listings priced >=30% below their local comparable group and **850** priced >=30% above, out of 7,778 listings with a valid comparable group.

## Business Implications

- **Buyers**: The comparable-group gap in Finding 3 is a starting point for site visits, not a purchase signal — it flags where price and local comparables diverge, and the cause could be genuine value, a data-entry error, or a property-specific defect the dataset can't see (condition, legal status, exact micro-location).
- **Sellers/Developers**: The BHK price curve (Finding 2) suggests 4 BHK inventory captures a pricing inflection point in this market snapshot — relevant for unit-mix decisions in new developments, though this is a single historical dataset, not a live market signal.
- **Analysts**: Locality-level medians are only reliable at n >= 10 listings (998 of 1251 localities fall below this and are excluded from tiering) — any locality ranking built on fewer listings should be treated as indicative only.

## Methodology & Limitations

- **Dataset**: Kaggle "Bengaluru House Price Data" (13,320 raw rows, single historical snapshot — no listing date, so results describe the period the data was collected, not the current market). Hyderabad/Chennai data (Kaggle "Housing Prices in Metropolitan Areas of India") was profiled and cleaned in parallel but is schema-incompatible for a row-level merge (no `bath`/`total_sqft` text-parsing needed there; it uses amenity flags instead) — it is used for a separate city-level comparison, not blended into the Bengaluru locality analysis.
- **Cleaning**: 49 rows were excluded as Invalid, most from unit-conversion errors (Acres/Perch/Cents to sqft) producing implausible price/sqft (observed range before the fix: Rs 2.26 to Rs 1.2 crore per sqft). This single fix moved the Pearson correlation between price and sqft from 0.049 (distorted by extreme outliers) to 0.64, consistent with the outlier-robust Spearman correlation of 0.736 both before and after — a reminder that Pearson correlation alone can be actively misleading in the presence of a handful of extreme records.
- **Locality standardization**: Whitespace/case/punctuation variants (e.g. "Whitefield"/"White Field") were auto-merged, collapsing 1,271 raw locality spellings to 1,257 standardized localities. Fuzzy typo-correction was evaluated and deliberately **not** auto-applied — on this dataset, fuzzy string similarity cannot reliably separate real typos from genuinely distinct localities (e.g. "HBR Layout" vs "HSR Layout" score identically to a known typo pair). All 139 fuzzy candidates are logged in `reports/locality_mapping_bengaluru.csv` for manual review rather than silently merged.
- **Correlation is not causation**: relationships reported here (e.g. BHK vs price) describe association in this dataset only.
- **"Potentially mispriced" / "value opportunity" are not investment advice**: both use a comparable-group median as a statistical benchmark; deviation from that benchmark can reflect genuine opportunity, a data-quality issue, or unobserved property characteristics. No claim in this memo should be read as a guaranteed investment outcome.
