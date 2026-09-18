"""
Phase 2 - Data Cleaning & Standardization
Bengaluru / Hyderabad Housing Market Intelligence Dashboard

Produces:
  data/cleaned/bengaluru_clean.parquet   (+ .csv for Databricks/Tableau upload)
  data/cleaned/metro_hyderabad_clean.parquet / .csv
  data/cleaned/metro_chennai_clean.parquet / .csv
  reports/locality_mapping_bengaluru.csv   (raw -> standardized locality, with method + confidence)
  reports/cleaning_log.json                (row counts at every step, for the data-quality narrative)

Nothing is silently dropped: every record that fails a check gets a `quality_flag`
(Valid / Suspicious / Invalid) instead of being deleted. Downstream analysis decides
whether to exclude Invalid rows.
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEANED = ROOT / "data" / "cleaned"
REPORTS = ROOT / "reports"
CLEANED.mkdir(exist_ok=True, parents=True)

cleaning_log = {}

# ---------------------------------------------------------------------------
# total_sqft parsing
# ---------------------------------------------------------------------------

UNIT_TO_SQFT = {
    "sq. meter": 10.7639,
    "sq. yards": 9.0,
    "acres": 43560.0,
    "cents": 435.6,
    "guntha": 1089.0,
    "grounds": 2400.0,
    "perch": 272.25,
}


def parse_total_sqft(raw: str):
    """Returns (value, method) where method documents how the value was derived."""
    if pd.isna(raw):
        return np.nan, "null"
    s = str(raw).strip()

    # Plain number
    if re.match(r"^\d+(\.\d+)?$", s):
        return float(s), "plain"

    # Range "1000 - 1285" -> midpoint
    m = re.match(r"^(\d+(\.\d+)?)\s*-\s*(\d+(\.\d+)?)$", s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(3))
        return (lo + hi) / 2, "range_midpoint"

    # "<n><Unit>" e.g. "1100Sq. Meter", "1.25Acres", "10Cents", "1Perch", "1Guntha", "5Grounds"
    for unit, factor in UNIT_TO_SQFT.items():
        m = re.match(rf"^(\d+(\.\d+)?)\s*{re.escape(unit)}$", s, flags=re.IGNORECASE)
        if m:
            return float(m.group(1)) * factor, f"unit_convert:{unit}"

    return np.nan, "unparseable"


def clean_bengaluru() -> pd.DataFrame:
    df = pd.read_csv(RAW / "bengaluru" / "Bengaluru_House_Data.csv")
    steps = {"raw_rows": len(df)}

    df = df.drop_duplicates().reset_index(drop=True)
    steps["after_dedup"] = len(df)

    # --- BHK ---
    df["bhk"] = df["size"].astype(str).str.extract(r"(\d+)")[0].astype(float)

    # --- total_sqft ---
    parsed = df["total_sqft"].apply(parse_total_sqft)
    df["total_sqft_clean"] = parsed.apply(lambda t: t[0])
    df["sqft_parse_method"] = parsed.apply(lambda t: t[1])

    # --- price: already numeric, in INR Lakhs. Convert to absolute INR for clarity. ---
    df["price_lakhs"] = pd.to_numeric(df["price"], errors="coerce")
    df["price_inr"] = df["price_lakhs"] * 100000

    # --- bath / balcony ---
    df["bath"] = pd.to_numeric(df["bath"], errors="coerce")
    df["balcony"] = pd.to_numeric(df["balcony"], errors="coerce")

    # --- price per sqft ---
    df["price_per_sqft"] = np.where(
        (df["total_sqft_clean"].notna()) & (df["total_sqft_clean"] > 0),
        df["price_inr"] / df["total_sqft_clean"],
        np.nan,
    )

    # --- locality standardization ---
    df["location_raw"] = df["location"].fillna("Unknown").astype(str).str.strip()

    def normalize(s):
        s = s.lower().strip()
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    df["location_norm"] = df["location_raw"].apply(normalize)

    def compact(s):
        return re.sub(r"[^a-z0-9]", "", s)

    def digits_of(s):
        return re.findall(r"\d+", s)

    # ------------------------------------------------------------------
    # Stage A (auto-applied, high confidence): whitespace/punctuation-only
    # variants collapse to the same locality. This alone handles the
    # brief's flagship example: "Whitefield" / "White Field" / "whitefield"
    # all compact to "whitefield".
    # ------------------------------------------------------------------
    norm_counts = df["location_norm"].value_counts()
    uniques = norm_counts.index.tolist()
    compact_of = {v: compact(v) for v in uniques}

    compact_groups = {}
    for v in uniques:
        compact_groups.setdefault(compact_of[v], []).append(v)

    # canonical normalized form per compact-group = most frequent raw variant
    canonical_map = {}
    display_name_by_norm = {}
    for compact_key, variants in compact_groups.items():
        winner = max(variants, key=lambda v: norm_counts[v])
        for v in variants:
            canonical_map[v] = winner

    display_name = (
        df.groupby("location_norm")["location_raw"]
        .agg(lambda x: x.value_counts().idxmax())
        .to_dict()
    )

    df["locality_standard_norm"] = df["location_norm"].map(canonical_map)
    df["locality_standard"] = df["locality_standard_norm"].map(display_name)

    # ------------------------------------------------------------------
    # Stage B (NOT auto-applied): fuzzy typo candidates between remaining
    # distinct canonical localities. Ratio-based fuzzy matching cannot
    # reliably separate real typos ("whietfield") from genuinely distinct
    # localities that happen to look similar ("HBR Layout" vs "HSR Layout"
    # both score ratio=90; "Electronic City Phase 1" vs "Phase 2" scores
    # even higher at 95.7 despite being different phases). No safe global
    # threshold exists, so every candidate is written to the mapping report
    # for manual review instead of being merged automatically. This is a
    # deliberate methodology choice, not a shortcut: incorrectly merging
    # two real localities corrupts every downstream price-per-sqft and
    # locality-tier statistic, which is worse than missing a rare typo.
    # ------------------------------------------------------------------
    canon_norms = sorted(set(canonical_map.values()), key=lambda v: -norm_counts[v])
    mapping_rows = []
    for v in uniques:
        mapping_rows.append(
            {
                "raw_locality_normalized": v,
                "standard_locality_normalized": canonical_map[v],
                "standard_locality_display": display_name[canonical_map[v]],
                "method": "whitespace_normalization" if canonical_map[v] != v else "unique",
                "confidence": 100,
                "n_listings": int(norm_counts[v]),
                "flag_for_manual_review": False,
            }
        )

    FUZZY_THRESHOLD = 90
    seen_pairs = set()
    for i, a in enumerate(canon_norms):
        for b in canon_norms[i + 1:]:
            if abs(len(a) - len(b)) > 4:
                continue
            da, db = digits_of(a), digits_of(b)
            if da or db:
                if da != db:
                    continue  # never suggest merging different phase/block/stage numbers
            score = fuzz.ratio(a, b)
            if score >= FUZZY_THRESHOLD and (a, b) not in seen_pairs:
                seen_pairs.add((a, b))
                mapping_rows.append(
                    {
                        "raw_locality_normalized": a,
                        "standard_locality_normalized": b,
                        "standard_locality_display": display_name[b],
                        "method": "fuzzy_suggestion_NOT_applied",
                        "confidence": round(score, 1),
                        "n_listings": int(norm_counts.get(a, 0)),
                        "flag_for_manual_review": True,
                    }
                )

    mapping_df = pd.DataFrame(mapping_rows).sort_values(
        ["flag_for_manual_review", "standard_locality_display"], ascending=[False, True]
    )
    mapping_df.to_csv(REPORTS / "locality_mapping_bengaluru.csv", index=False)
    steps["raw_localities"] = len(uniques)
    steps["standard_localities"] = df["locality_standard_norm"].nunique()
    steps["low_confidence_matches_flagged"] = int(mapping_df["flag_for_manual_review"].sum())

    # --- quality_flag ---
    # PRICE_PER_SQFT_BOUNDS: discovered empirically, not guessed. Plot-type listings
    # convert total_sqft from Acres/Perch/Cents/Guntha; a handful of these produce
    # nonsensical price_per_sqft (observed range down to Rs 2.26/sqft and up to
    # Rs 1.2 crore/sqft) that are near-certainly unit or entry errors in the source
    # data, not real prices. The bounds below are set outside the IQR-outlier fence
    # for price_per_sqft (Q1=4296, Q3=7401, IQR fence upper=12057 - see
    # reports/analysis_results.json) specifically so this rule only catches values
    # that are implausible on their face, not merely statistically unusual premium
    # or budget listings.
    PRICE_PER_SQFT_MIN, PRICE_PER_SQFT_MAX = 500, 50000

    def classify(row):
        bhk, bath, sqft, price = row["bhk"], row["bath"], row["total_sqft_clean"], row["price_lakhs"]
        ppsf = row["price_per_sqft"]
        if pd.isna(bhk) or pd.isna(sqft) or pd.isna(price) or sqft <= 0 or price <= 0:
            return "Invalid"
        if pd.notna(ppsf) and (ppsf < PRICE_PER_SQFT_MIN or ppsf > PRICE_PER_SQFT_MAX):
            return "Invalid:implausible_price_per_sqft"
        reasons = []
        if not pd.isna(bath) and bath > bhk + 2:
            reasons.append("bath_exceeds_bhk+2")
        if sqft < 100:
            reasons.append("implausibly_small_sqft")
        if bhk >= 1 and (sqft / bhk) < 150:
            reasons.append("sqft_per_bhk_below_150")
        if row["sqft_parse_method"] == "unparseable":
            reasons.append("sqft_unparseable")
        return "Suspicious:" + ",".join(reasons) if reasons else "Valid"

    df["quality_flag_detail"] = df.apply(classify, axis=1)

    def bucket(v):
        if v == "Valid":
            return "Valid"
        if v.startswith("Invalid"):
            return "Invalid"
        return "Suspicious"

    df["quality_flag"] = df["quality_flag_detail"].apply(bucket)
    steps["quality_flag_counts"] = df["quality_flag"].value_counts().to_dict()

    # --- BHK category & size bucket ---
    df["bhk_category"] = df["bhk"].apply(
        lambda x: "5+ BHK" if pd.notna(x) and x >= 5 else (f"{int(x)} BHK" if pd.notna(x) else "Unknown")
    )

    def size_bucket(sqft):
        if pd.isna(sqft):
            return "Unknown"
        if sqft < 500:
            return "<500 sqft"
        if sqft < 1000:
            return "500-1000 sqft"
        if sqft < 1500:
            return "1000-1500 sqft"
        if sqft < 2500:
            return "1500-2500 sqft"
        return "2500+ sqft"

    df["size_bucket"] = df["total_sqft_clean"].apply(size_bucket)

    # --- availability bucket ---
    df["availability_bucket"] = np.where(
        df["availability"].astype(str).str.strip().str.lower() == "ready to move",
        "Ready to move",
        "Under construction",
    )

    df["age_bucket"] = "Not available in source data"  # explicit, not invented

    df["city"] = "Bengaluru"
    return df, steps


def clean_metro_city(filename: str, city: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / "metro_india" / filename)
    df = df.drop_duplicates().reset_index(drop=True)

    df["price_inr"] = pd.to_numeric(df["Price"], errors="coerce")
    df["total_sqft_clean"] = pd.to_numeric(df["Area"], errors="coerce")
    df["bhk"] = pd.to_numeric(df["No. of Bedrooms"], errors="coerce")
    df["price_per_sqft"] = np.where(
        (df["total_sqft_clean"] > 0) & df["total_sqft_clean"].notna(),
        df["price_inr"] / df["total_sqft_clean"],
        np.nan,
    )
    df["locality_standard"] = df["Location"].astype(str).str.strip()
    df["bhk_category"] = df["bhk"].apply(
        lambda x: "5+ BHK" if pd.notna(x) and x >= 5 else (f"{int(x)} BHK" if pd.notna(x) else "Unknown")
    )

    def size_bucket(sqft):
        if pd.isna(sqft):
            return "Unknown"
        if sqft < 500:
            return "<500 sqft"
        if sqft < 1000:
            return "500-1000 sqft"
        if sqft < 1500:
            return "1000-1500 sqft"
        if sqft < 2500:
            return "1500-2500 sqft"
        return "2500+ sqft"

    df["size_bucket"] = df["total_sqft_clean"].apply(size_bucket)
    df["quality_flag"] = np.where(
        (df["price_inr"] > 0) & (df["total_sqft_clean"] > 0) & df["bhk"].notna(), "Valid", "Invalid"
    )
    df["city"] = city
    df["age_bucket"] = "Not available in source data"
    amenity_cols = [c for c in df.columns if c not in [
        "Price", "Area", "Location", "No. of Bedrooms", "Resale", "price_inr",
        "total_sqft_clean", "bhk", "price_per_sqft", "locality_standard",
        "bhk_category", "size_bucket", "quality_flag", "city", "age_bucket",
    ]]
    df["amenity_score"] = df[amenity_cols].sum(axis=1)
    df["amenity_count_total"] = len(amenity_cols)
    return df


def main():
    beng, steps = clean_bengaluru()
    cleaning_log["bengaluru"] = steps
    keep_cols = [
        "city", "locality_standard", "location_raw", "bhk", "bhk_category",
        "total_sqft_clean", "sqft_parse_method", "size_bucket", "bath", "balcony",
        "price_lakhs", "price_inr", "price_per_sqft", "area_type", "availability_bucket",
        "age_bucket", "quality_flag", "quality_flag_detail",
    ]
    beng_out = beng[keep_cols]
    beng_out.to_parquet(CLEANED / "bengaluru_clean.parquet", index=False)
    beng_out.to_csv(CLEANED / "bengaluru_clean.csv", index=False)

    hyd = clean_metro_city("Hyderabad.csv", "Hyderabad")
    chen = clean_metro_city("Chennai.csv", "Chennai")
    for name, d in [("metro_hyderabad_clean", hyd), ("metro_chennai_clean", chen)]:
        d.to_parquet(CLEANED / f"{name}.parquet", index=False)
        d.to_csv(CLEANED / f"{name}.csv", index=False)

    cleaning_log["hyderabad_rows"] = len(hyd)
    cleaning_log["chennai_rows"] = len(chen)
    (REPORTS / "cleaning_log.json").write_text(json.dumps(cleaning_log, indent=2, default=str))

    print("Bengaluru cleaned rows:", len(beng_out), "| quality_flag counts:", steps["quality_flag_counts"])
    print("Hyderabad cleaned rows:", len(hyd), "| Chennai cleaned rows:", len(chen))
    print("Locality collapse: raw", steps["raw_localities"], "-> standard", steps["standard_localities"])


if __name__ == "__main__":
    main()
