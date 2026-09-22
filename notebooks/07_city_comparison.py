"""
Builds dashboard/tableau/city_comparison.csv: Bengaluru / Hyderabad / Chennai from the
metropolitan-areas dataset only (one schema, so cities are comparable).
Same rules as the main pipeline: exact duplicates dropped, price/sqft outside Rs 500-50,000 excluded.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "metro_india"

frames = []
for fname, city in [("Bangalore.csv", "Bengaluru"), ("Hyderabad.csv", "Hyderabad"), ("Chennai.csv", "Chennai")]:
    d = pd.read_csv(RAW / fname).drop_duplicates()
    out = pd.DataFrame(
        {
            "city": city,
            "locality": d["Location"].astype(str).str.strip(),
            "bhk": pd.to_numeric(d["No. of Bedrooms"], errors="coerce"),
            "total_sqft": pd.to_numeric(d["Area"], errors="coerce"),
            "price_inr": pd.to_numeric(d["Price"], errors="coerce"),
        }
    )
    out["price_per_sqft"] = out.price_inr / out.total_sqft
    ok = (
        (out.total_sqft > 0) & (out.price_inr > 0) & out.bhk.notna()
        & out.price_per_sqft.between(500, 50000)
    )
    out = out[ok].copy()
    out["bhk_category"] = out.bhk.apply(lambda x: "5+ BHK" if x >= 5 else f"{int(x)} BHK")
    frames.append(out)

allc = pd.concat(frames)
allc.to_csv(ROOT / "dashboard" / "tableau" / "city_comparison.csv", index=False)
print(allc.groupby("city").size().to_string())
