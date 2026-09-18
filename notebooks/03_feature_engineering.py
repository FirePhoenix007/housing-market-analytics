"""
Phase 3 - Feature Engineering & Locality Tier Segmentation
Bengaluru / Hyderabad Housing Market Intelligence Dashboard

Builds the analytics-ready `housing_cleaned` table (Bengaluru) with:
  - price_per_sqft (already computed in Phase 2)
  - bhk_category, size_bucket (already computed in Phase 2)
  - locality_tier: statistically-derived segmentation (see methodology below)

Outputs:
  data/cleaned/housing_cleaned.parquet / .csv   <- the "housing_cleaned" analytics table
  reports/locality_tier_table.csv               <- Locality | Listings | Median Price | Median Rs/sqft | Tier
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEANED = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"

MIN_LISTINGS_FOR_TIER = 10  # below this, a locality's median is too noisy to rank


def build_locality_tiers(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[df["quality_flag"] != "Invalid"].copy()

    agg = (
        valid.groupby("locality_standard")
        .agg(
            listings=("price_per_sqft", "count"),
            median_price_lakhs=("price_lakhs", "median"),
            median_price_per_sqft=("price_per_sqft", "median"),
        )
        .reset_index()
    )

    ranked = agg[agg["listings"] >= MIN_LISTINGS_FOR_TIER].copy()
    # Quantile-based tiers on median price_per_sqft among localities with enough data
    # to make the median statistically meaningful (n >= MIN_LISTINGS_FOR_TIER).
    q_high = ranked["median_price_per_sqft"].quantile(2 / 3)
    q_low = ranked["median_price_per_sqft"].quantile(1 / 3)

    def tier_of(v):
        if v >= q_high:
            return "Tier 1 - Premium"
        if v >= q_low:
            return "Tier 2 - Mid-market"
        return "Tier 3 - Value"

    ranked["locality_tier"] = ranked["median_price_per_sqft"].apply(tier_of)

    agg = agg.merge(
        ranked[["locality_standard", "locality_tier"]], on="locality_standard", how="left"
    )
    agg["locality_tier"] = agg["locality_tier"].fillna(
        f"Insufficient data (<{MIN_LISTINGS_FOR_TIER} listings)"
    )

    thresholds = {
        "min_listings_for_tier": MIN_LISTINGS_FOR_TIER,
        "tier_1_threshold_rs_per_sqft": round(float(q_high), 2),
        "tier_2_threshold_rs_per_sqft": round(float(q_low), 2),
        "localities_ranked": int(len(ranked)),
        "localities_insufficient_data": int((agg["locality_tier"].str.startswith("Insufficient")).sum()),
        "methodology": (
            "Localities with >= "
            f"{MIN_LISTINGS_FOR_TIER} valid listings are ranked by median price/sqft. "
            "Tier boundaries are the 33rd and 67th percentiles of that median across ranked "
            "localities (terciles), not arbitrary cutoffs. Localities below the listing "
            "threshold are marked 'Insufficient data' rather than force-tiered, since a "
            "median of <10 listings is not statistically reliable."
        ),
    }
    return agg.sort_values("median_price_per_sqft", ascending=False), thresholds


def main():
    df = pd.read_parquet(CLEANED / "bengaluru_clean.parquet")

    tier_table, thresholds = build_locality_tiers(df)
    tier_table.rename(
        columns={
            "locality_standard": "Locality",
            "listings": "Listings",
            "median_price_lakhs": "Median Price (Lakhs INR)",
            "median_price_per_sqft": "Median Rs per sqft",
            "locality_tier": "Tier",
        }
    ).to_csv(REPORTS / "locality_tier_table.csv", index=False)

    (REPORTS / "locality_tier_methodology.json").write_text(json.dumps(thresholds, indent=2))

    df = df.merge(
        tier_table[["locality_standard", "locality_tier"]], on="locality_standard", how="left"
    )

    df.to_parquet(CLEANED / "housing_cleaned.parquet", index=False)
    df.to_csv(CLEANED / "housing_cleaned.csv", index=False)

    print("housing_cleaned rows:", len(df))
    print("Tier thresholds:", thresholds)
    print(df["locality_tier"].value_counts())


if __name__ == "__main__":
    main()
