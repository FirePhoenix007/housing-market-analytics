"""
Phase 4-6 - Statistical Analysis, Outlier Detection, Correlation,
            Business Analysis, and Mispriced-Listing Analysis.

Everything in this script reads the real `housing_cleaned` table produced by
03_feature_engineering.py and writes its findings to reports/analysis_results.json
so the insight memo (06_generate_insight_memo.py) never hand-types a number.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
CLEANED = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"

results = {}


def descriptive_stats(df: pd.DataFrame) -> dict:
    out = {}
    for col in ["price_lakhs", "price_per_sqft", "total_sqft_clean", "bhk", "bath"]:
        s = df[col].dropna()
        out[col] = {
            "mean": round(float(s.mean()), 2),
            "median": round(float(s.median()), 2),
            "std": round(float(s.std()), 2),
            "min": round(float(s.min()), 2),
            "max": round(float(s.max()), 2),
            "q1": round(float(s.quantile(0.25)), 2),
            "q3": round(float(s.quantile(0.75)), 2),
            "iqr": round(float(s.quantile(0.75) - s.quantile(0.25)), 2),
            "n": int(s.count()),
        }
    return out


def iqr_outliers(df: pd.DataFrame, col: str):
    s = df[col].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mask = (df[col] < lower) | (df[col] > upper)
    return {
        "q1": round(float(q1), 2),
        "q3": round(float(q3), 2),
        "iqr": round(float(iqr), 2),
        "lower_bound": round(float(lower), 2),
        "upper_bound": round(float(upper), 2),
        "outlier_count": int(mask.sum()),
        "outlier_pct": round(100 * mask.sum() / len(df), 2),
    }


def zscore_outliers(df: pd.DataFrame, col: str, threshold: float = 3.0):
    s = df[col].dropna()
    z = np.abs(stats.zscore(s))
    return {
        "threshold": threshold,
        "outlier_count": int((z > threshold).sum()),
        "outlier_pct": round(100 * (z > threshold).sum() / len(s), 2),
    }


def correlation_analysis(df: pd.DataFrame) -> dict:
    cols = ["price_lakhs", "price_per_sqft", "total_sqft_clean", "bhk", "bath", "balcony"]
    sub = df[cols].dropna()
    pearson = sub.corr(method="pearson").round(3)
    spearman = sub.corr(method="spearman").round(3)
    return {
        "n_rows_used": int(len(sub)),
        "pearson": pearson.to_dict(),
        "spearman": spearman.to_dict(),
        "note": "Correlation measures association, not causation. price_per_sqft is "
        "derived from price and total_sqft_clean, so its correlation with either is "
        "structural, not an independent finding.",
    }


def business_questions(df: pd.DataFrame, tier_table: pd.DataFrame) -> dict:
    valid = df[df["quality_flag"] != "Invalid"].copy()
    out = {}

    # Q1: highest median Rs/sqft localities (min listing threshold for reliability)
    ranked = tier_table[tier_table["Listings"] >= 10].sort_values(
        "Median Rs per sqft", ascending=False
    )
    out["q1_top_localities_by_median_price_per_sqft"] = ranked.head(10)[
        ["Locality", "Listings", "Median Rs per sqft"]
    ].to_dict("records")

    # Q2: high volume but relatively low Rs/sqft (value-for-volume)
    volume_cutoff = ranked["Listings"].quantile(0.75)
    high_vol = ranked[ranked["Listings"] >= volume_cutoff].sort_values("Median Rs per sqft")
    out["q2_high_volume_low_price_localities"] = {
        "volume_cutoff_listings": round(float(volume_cutoff), 1),
        "localities": high_vol.head(10)[["Locality", "Listings", "Median Rs per sqft"]].to_dict("records"),
    }

    # Q3: price by BHK category
    bhk_stats = (
        valid.groupby("bhk_category")
        .agg(
            listings=("price_lakhs", "count"),
            median_price_lakhs=("price_lakhs", "median"),
            median_price_per_sqft=("price_per_sqft", "median"),
        )
        .reset_index()
    )
    order = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5+ BHK"]
    bhk_stats["_order"] = bhk_stats["bhk_category"].apply(lambda x: order.index(x) if x in order else 99)
    bhk_stats = bhk_stats.sort_values("_order").drop(columns="_order")
    out["q3_price_by_bhk"] = bhk_stats.to_dict("records")

    # Q4: dominant property size per locality tier
    size_by_tier = (
        valid.groupby(["locality_tier", "size_bucket"]).size().reset_index(name="count")
    )
    dominant = size_by_tier.loc[size_by_tier.groupby("locality_tier")["count"].idxmax()]
    out["q4_dominant_size_bucket_per_tier"] = dominant.to_dict("records")

    # Q5: large properties (2500+ sqft) with unusually low Rs/sqft, by locality
    large = valid[valid["size_bucket"] == "2500+ sqft"]
    if len(large):
        large_by_loc = (
            large.groupby("locality_standard")
            .agg(listings=("price_per_sqft", "count"), median_price_per_sqft=("price_per_sqft", "median"))
            .reset_index()
        )
        large_by_loc = large_by_loc[large_by_loc["listings"] >= 3].sort_values("median_price_per_sqft")
        out["q5_large_properties_low_price_per_sqft"] = large_by_loc.head(10).to_dict("records")
    else:
        out["q5_large_properties_low_price_per_sqft"] = []

    # Q6 & Q7: comparable-group relative pricing ("value opportunity" methodology)
    # Comparable group = same bhk_category + size_bucket + locality_tier.
    # For each locality within a group, compare its median Rs/sqft to the
    # GROUP's median (i.e. peers with the same BHK, size band and tier).
    # Only localities with >= 5 listings in a group are considered comparable.
    group_cols = ["bhk_category", "size_bucket", "locality_tier"]
    valid_g = valid.dropna(subset=group_cols + ["price_per_sqft"])
    group_median = valid_g.groupby(group_cols)["price_per_sqft"].transform("median")
    valid_g = valid_g.assign(group_median_price_per_sqft=group_median)

    loc_group = (
        valid_g.groupby(group_cols + ["locality_standard"])
        .agg(
            listings=("price_per_sqft", "count"),
            locality_median=("price_per_sqft", "median"),
            group_median=("group_median_price_per_sqft", "first"),
        )
        .reset_index()
    )
    loc_group = loc_group[loc_group["listings"] >= 5]
    loc_group["pct_diff_vs_comparable_group"] = round(
        100 * (loc_group["locality_median"] - loc_group["group_median"]) / loc_group["group_median"], 1
    )

    expensive = loc_group[loc_group["pct_diff_vs_comparable_group"] >= 15].sort_values(
        "pct_diff_vs_comparable_group", ascending=False
    )
    value_opportunities = loc_group[loc_group["pct_diff_vs_comparable_group"] <= -15].sort_values(
        "pct_diff_vs_comparable_group"
    )

    out["q6_statistically_expensive_localities"] = expensive.head(10)[
        ["locality_standard", "bhk_category", "size_bucket", "locality_tier", "listings",
         "locality_median", "group_median", "pct_diff_vs_comparable_group"]
    ].to_dict("records")

    out["q7_value_opportunity_localities"] = value_opportunities.head(10)[
        ["locality_standard", "bhk_category", "size_bucket", "locality_tier", "listings",
         "locality_median", "group_median", "pct_diff_vs_comparable_group"]
    ].to_dict("records")

    out["q6_q7_methodology"] = (
        "A locality is only compared against peers sharing the same BHK category, "
        "size bucket AND locality tier (min 5 listings per locality within that "
        "comparable group). pct_diff_vs_comparable_group is the locality's median "
        "Rs/sqft vs. the comparable group's median. This avoids the trivial/incorrect "
        "claim that a locality is 'cheap' just because its raw price is low (it may "
        "simply have smaller, lower-tier listings)."
    )

    return out


def mispriced_listings(df: pd.DataFrame) -> dict:
    valid = df[df["quality_flag"] != "Invalid"].dropna(
        subset=["locality_standard", "bhk_category", "size_bucket", "price_per_sqft"]
    ).copy()

    group_cols = ["locality_standard", "bhk_category", "size_bucket"]
    grp = valid.groupby(group_cols)["price_per_sqft"]
    valid["comparable_group_n"] = grp.transform("count")
    valid["expected_price_per_sqft"] = grp.transform("median")

    comparable = valid[valid["comparable_group_n"] >= 5].copy()
    comparable["pricing_gap"] = comparable["price_per_sqft"] - comparable["expected_price_per_sqft"]
    comparable["pct_deviation"] = round(
        100 * comparable["pricing_gap"] / comparable["expected_price_per_sqft"], 1
    )

    THRESHOLD_PCT = 30
    below = comparable[comparable["pct_deviation"] <= -THRESHOLD_PCT]
    above = comparable[comparable["pct_deviation"] >= THRESHOLD_PCT]

    cols = [
        "locality_standard", "bhk_category", "size_bucket", "total_sqft_clean",
        "price_lakhs", "price_per_sqft", "expected_price_per_sqft", "pct_deviation",
        "comparable_group_n",
    ]
    return {
        "methodology": (
            f"Comparable group = same locality + BHK category + size bucket, min 5 "
            f"listings. expected_price_per_sqft = group median. Listings deviating "
            f">= {THRESHOLD_PCT}% from their group's expected price are flagged as "
            "POTENTIALLY mispriced (below = possible bargain/data issue, above = "
            "possible premium/data issue) - not definitively mispriced."
        ),
        "threshold_pct": THRESHOLD_PCT,
        "comparable_universe_n": int(len(comparable)),
        "flagged_below_count": int(len(below)),
        "flagged_above_count": int(len(above)),
        "examples_below_expected": below.sort_values("pct_deviation").head(10)[cols].to_dict("records"),
        "examples_above_expected": above.sort_values("pct_deviation", ascending=False).head(10)[cols].to_dict("records"),
    }


def main():
    df = pd.read_parquet(CLEANED / "housing_cleaned.parquet")
    tier_table = pd.read_csv(REPORTS / "locality_tier_table.csv")

    valid = df[df["quality_flag"] != "Invalid"]

    results["dataset_scope"] = {
        "total_rows": int(len(df)),
        "valid_rows_used_for_stats": int(len(valid)),
        "excluded_invalid_rows": int((df["quality_flag"] == "Invalid").sum()),
        "suspicious_rows_retained": int((df["quality_flag"] == "Suspicious").sum()),
    }
    results["descriptive_stats"] = descriptive_stats(valid)
    results["outliers_iqr"] = {
        "price_lakhs": iqr_outliers(valid, "price_lakhs"),
        "price_per_sqft": iqr_outliers(valid, "price_per_sqft"),
        "total_sqft_clean": iqr_outliers(valid, "total_sqft_clean"),
    }
    results["outliers_zscore"] = {
        "price_lakhs": zscore_outliers(valid, "price_lakhs"),
        "price_per_sqft": zscore_outliers(valid, "price_per_sqft"),
    }
    results["correlation"] = correlation_analysis(valid)
    results["business_questions"] = business_questions(valid, tier_table)
    results["mispriced_listings"] = mispriced_listings(df)

    (REPORTS / "analysis_results.json").write_text(json.dumps(results, indent=2, default=str))
    print("Wrote reports/analysis_results.json")
    print("Valid rows analyzed:", len(valid))
    print("Price/sqft IQR outliers:", results["outliers_iqr"]["price_per_sqft"]["outlier_count"])
    print("Potentially mispriced (below):", results["mispriced_listings"]["flagged_below_count"])
    print("Potentially mispriced (above):", results["mispriced_listings"]["flagged_above_count"])


if __name__ == "__main__":
    main()
