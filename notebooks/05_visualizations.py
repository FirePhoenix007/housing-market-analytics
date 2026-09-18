"""
Phase 4/10 support - Visualizations for the notebook + dashboard screenshots.
Reads the real housing_cleaned table and reports/analysis_results.json.
Outputs PNGs into dashboard/screenshots/ (used as static previews for the README
until the live Tableau Public dashboard is published).
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
CLEANED = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"
FIG_DIR = ROOT / "dashboard" / "screenshots"
FIG_DIR.mkdir(exist_ok=True, parents=True)

sns.set_theme(style="whitegrid")


def main():
    df = pd.read_parquet(CLEANED / "housing_cleaned.parquet")
    valid = df[df["quality_flag"] != "Invalid"].copy()

    # 1. Price distribution
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.histplot(valid["price_lakhs"].clip(upper=valid["price_lakhs"].quantile(0.99)), bins=50, ax=ax, color="#2E5A88")
    ax.set_title("Price Distribution (Bengaluru, clipped at 99th percentile)")
    ax.set_xlabel("Price (Lakhs INR)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "01_price_distribution.png", dpi=130)
    plt.close(fig)

    # 2. Price per sqft distribution
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.histplot(valid["price_per_sqft"], bins=50, ax=ax, color="#8E44AD")
    ax.set_title("Price per Sqft Distribution (post-cleaning, Rs 500-50,000 band)")
    ax.set_xlabel("Rs / sqft")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "02_price_per_sqft_distribution.png", dpi=130)
    plt.close(fig)

    # 3. Top 15 localities by median Rs/sqft (min 10 listings)
    tier_table = pd.read_csv(REPORTS / "locality_tier_table.csv")
    top15 = tier_table[tier_table["Listings"] >= 10].sort_values(
        "Median Rs per sqft", ascending=False
    ).head(15)
    fig, ax = plt.subplots(figsize=(8, 6))
    sns.barplot(data=top15, y="Locality", x="Median Rs per sqft", ax=ax, color="#2E8B57")
    ax.set_title("Top 15 Localities by Median Rs/sqft (min 10 listings)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "03_top_localities_price_per_sqft.png", dpi=130)
    plt.close(fig)

    # 4. BHK vs price boxplot
    order = ["1 BHK", "2 BHK", "3 BHK", "4 BHK", "5+ BHK"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    sns.boxplot(
        data=valid[valid["bhk_category"].isin(order)],
        x="bhk_category", y="price_lakhs", order=order, ax=ax, showfliers=False,
        color="#D68910",
    )
    ax.set_title("Price by BHK Category (outlier points hidden for readability)")
    ax.set_ylabel("Price (Lakhs INR)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "04_price_by_bhk.png", dpi=130)
    plt.close(fig)

    # 5. Correlation heatmap
    results = json.load(open(REPORTS / "analysis_results.json"))
    pearson = pd.DataFrame(results["correlation"]["pearson"])
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(pearson, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
    ax.set_title("Pearson Correlation Matrix (post-cleaning)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "05_correlation_heatmap.png", dpi=130)
    plt.close(fig)

    # 6. Locality tier distribution
    fig, ax = plt.subplots(figsize=(7, 4.5))
    tier_order = ["Tier 1 - Premium", "Tier 2 - Mid-market", "Tier 3 - Value"]
    counts = valid[valid["locality_tier"].isin(tier_order)]["locality_tier"].value_counts().reindex(tier_order)
    sns.barplot(x=counts.index, y=counts.values, ax=ax, palette=["#B03A2E", "#D4AC0D", "#2471A3"])
    ax.set_title("Listing Volume by Locality Tier")
    ax.set_ylabel("Listings")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "06_listings_by_tier.png", dpi=130)
    plt.close(fig)

    print("Saved 6 figures to", FIG_DIR)


if __name__ == "__main__":
    main()
