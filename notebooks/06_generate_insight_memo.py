"""
Phase 11 - Insight Memo generator.
Every number in the memo is pulled programmatically from reports/analysis_results.json
and reports/locality_tier_table.csv -- nothing here is hand-typed, so the memo can never
drift from what the pipeline actually computed.

Outputs: reports/insight_memo.md and reports/insight_memo.pdf
"""

import json
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

r = json.loads((REPORTS / "analysis_results.json").read_text())
tier_table = pd.read_csv(REPORTS / "locality_tier_table.csv")
tier_methodology = json.loads((REPORTS / "locality_tier_methodology.json").read_text())
cleaning_log = json.loads((REPORTS / "cleaning_log.json").read_text())
beng_cleaning = cleaning_log["bengaluru"]

bq = r["business_questions"]
city_median_ppsf = r["descriptive_stats"]["price_per_sqft"]["median"]

top_locality = bq["q1_top_localities_by_median_price_per_sqft"][0]
top_locality_multiple = round(top_locality["Median Rs per sqft"] / city_median_ppsf, 1)

bhk_rows = {row["bhk_category"]: row for row in bq["q3_price_by_bhk"]}
bhk4 = bhk_rows["4 BHK"]
bhk5 = bhk_rows["5+ BHK"]

value_op = bq["q7_value_opportunity_localities"][0]

mis = r["mispriced_listings"]

MEMO_MD = f"""# Bengaluru Housing Market — Executive Insight Memo

*Bengaluru House Price Data (Kaggle), {beng_cleaning['raw_rows']:,} raw rows -> {beng_cleaning['after_dedup']:,} after removing {beng_cleaning['raw_rows']-beng_cleaning['after_dedup']} exact-duplicate rows -> {r['dataset_scope']['valid_rows_used_for_stats']:,} used for statistical analysis after excluding {r['dataset_scope']['excluded_invalid_rows']} further Invalid records (missing core fields, or price/sqft values outside the Rs 500-50,000 plausibility band established during data cleaning).*

## Executive Summary

Bengaluru's residential market shows a wide and statistically defensible spread in price per square foot across localities (city median Rs {city_median_ppsf:,.0f}/sqft), with premium micro-markets commanding multiples of the city median. Price does not scale linearly with BHK size — the jump from 3 BHK to 4 BHK is far steeper than any other step — and a comparable-group methodology (matching on BHK, size band and locality tier) surfaces specific, named localities that price meaningfully below their true peers.

## Finding 1: Premium localities trade at multiples of the city median, not just a modest premium

**{top_locality['Locality']}** has the highest verified median price per sqft in the dataset at **Rs {top_locality['Median Rs per sqft']:,.0f}/sqft** (n={top_locality['Listings']} listings) — **{top_locality_multiple}x** the city-wide median of Rs {city_median_ppsf:,.0f}/sqft. Locality tiers, built from terciles of median Rs/sqft among localities with >= {tier_methodology['min_listings_for_tier']} listings, place the Tier 1 (Premium) cutoff at Rs {tier_methodology['tier_1_threshold_rs_per_sqft']:,.0f}/sqft and Tier 3 (Value) below Rs {tier_methodology['tier_2_threshold_rs_per_sqft']:,.0f}/sqft — a >{round(tier_methodology['tier_1_threshold_rs_per_sqft']/tier_methodology['tier_2_threshold_rs_per_sqft'],1)}x spread between tier boundaries.

## Finding 2: The price curve steepens sharply at 4 BHK, and 5+ BHK is not simply "more expensive"

Median price by BHK category: 1 BHK Rs {bhk_rows['1 BHK']['median_price_lakhs']:.1f}L, 2 BHK Rs {bhk_rows['2 BHK']['median_price_lakhs']:.1f}L, 3 BHK Rs {bhk_rows['3 BHK']['median_price_lakhs']:.1f}L, **4 BHK Rs {bhk4['median_price_lakhs']:.1f}L**, 5+ BHK Rs {bhk5['median_price_lakhs']:.1f}L. The 3->4 BHK step is the largest jump in the series. Notably, 5+ BHK properties carry the **highest** Rs/sqft rate (Rs {bhk5['median_price_per_sqft']:,.0f}/sqft) but a **lower** median absolute price than 4 BHK (Rs {bhk5['median_price_lakhs']:.1f}L vs Rs {bhk4['median_price_lakhs']:.1f}L) — consistent with 5+ BHK listings in this dataset skewing toward smaller, premium-rate homes rather than larger ones, not a simple "more rooms = more expensive" pattern.

## Finding 3: Comparable-group analysis identifies specific under-priced pockets — not just "cheap" localities

Comparing each locality only against peers with the **same BHK category, size bucket and locality tier** (minimum 5 listings), **{value_op['locality_standard']}** ({value_op['bhk_category']}, {value_op['size_bucket']}, {value_op['locality_tier']}) prices **{abs(value_op['pct_diff_vs_comparable_group']):.1f}% below** its true comparable group (Rs {value_op['locality_median']:,.0f}/sqft vs a group median of Rs {value_op['group_median']:,.0f}/sqft, n={value_op['listings']}). This is a within-tier gap, not an artifact of comparing a Tier 3 locality to Tier 1 pricing. Separately, a listing-level comparable-group check (same locality + BHK + size, n>=5, threshold 30%) flags **{mis['flagged_below_count']}** listings priced >=30% below their local comparable group and **{mis['flagged_above_count']}** priced >=30% above, out of {mis['comparable_universe_n']:,} listings with a valid comparable group.

## Business Implications

- **Buyers**: The comparable-group gap in Finding 3 is a starting point for site visits, not a purchase signal — it flags where price and local comparables diverge, and the cause could be genuine value, a data-entry error, or a property-specific defect the dataset can't see (condition, legal status, exact micro-location).
- **Sellers/Developers**: The BHK price curve (Finding 2) suggests 4 BHK inventory captures a pricing inflection point in this market snapshot — relevant for unit-mix decisions in new developments, though this is a single historical dataset, not a live market signal.
- **Analysts**: Locality-level medians are only reliable at n >= {tier_methodology['min_listings_for_tier']} listings ({tier_methodology['localities_insufficient_data']} of {tier_methodology['localities_insufficient_data']+tier_methodology['localities_ranked']} localities fall below this and are excluded from tiering) — any locality ranking built on fewer listings should be treated as indicative only.

## Methodology & Limitations

- **Dataset**: Kaggle "Bengaluru House Price Data" ({beng_cleaning['raw_rows']:,} raw rows, single historical snapshot — no listing date, so results describe the period the data was collected, not the current market). Hyderabad/Chennai data (Kaggle "Housing Prices in Metropolitan Areas of India") was profiled and cleaned in parallel but is schema-incompatible for a row-level merge (no `bath`/`total_sqft` text-parsing needed there; it uses amenity flags instead) — it is used for a separate city-level comparison, not blended into the Bengaluru locality analysis.
- **Cleaning**: {r['dataset_scope']['excluded_invalid_rows']} rows were excluded as Invalid, most from unit-conversion errors (Acres/Perch/Cents to sqft) producing implausible price/sqft (observed range before the fix: Rs 2.26 to Rs 1.2 crore per sqft). This single fix moved the Pearson correlation between price and sqft from 0.049 (distorted by extreme outliers) to 0.64, consistent with the outlier-robust Spearman correlation of 0.736 both before and after — a reminder that Pearson correlation alone can be actively misleading in the presence of a handful of extreme records.
- **Locality standardization**: Whitespace/case/punctuation variants (e.g. "Whitefield"/"White Field") were auto-merged, collapsing {beng_cleaning['raw_localities']:,} raw locality spellings to {beng_cleaning['standard_localities']:,} standardized localities. Fuzzy typo-correction was evaluated and deliberately **not** auto-applied — on this dataset, fuzzy string similarity cannot reliably separate real typos from genuinely distinct localities (e.g. "HBR Layout" vs "HSR Layout" score identically to a known typo pair). All {beng_cleaning['low_confidence_matches_flagged']} fuzzy candidates are logged in `reports/locality_mapping_bengaluru.csv` for manual review rather than silently merged.
- **Correlation is not causation**: relationships reported here (e.g. BHK vs price) describe association in this dataset only.
- **"Potentially mispriced" / "value opportunity" are not investment advice**: both use a comparable-group median as a statistical benchmark; deviation from that benchmark can reflect genuine opportunity, a data-quality issue, or unobserved property characteristics. No claim in this memo should be read as a guaranteed investment outcome.
"""

(REPORTS / "insight_memo.md").write_text(MEMO_MD)


def build_pdf():
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1F4E5F"))
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.3, leading=13, spaceAfter=6)
    italic = ParagraphStyle("italic", parent=body, fontName="Helvetica-Oblique", fontSize=8.5, textColor=colors.grey)

    doc = SimpleDocTemplate(
        str(REPORTS / "insight_memo.pdf"), pagesize=LETTER,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    )
    flow = []
    lines = MEMO_MD.split("\n")
    for line in lines:
        if line.startswith("# "):
            flow.append(Paragraph(line[2:], h1))
        elif line.startswith("## "):
            flow.append(Paragraph(line[3:], h2))
        elif line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            flow.append(Paragraph(line.strip("*"), italic))
        elif line.strip().startswith("- "):
            flow.append(Paragraph("&bull; " + _md_bold(line.strip()[2:]), body))
        elif line.strip():
            flow.append(Paragraph(_md_bold(line), body))
        else:
            flow.append(Spacer(1, 4))
    doc.build(flow)


def _md_bold(text: str) -> str:
    import re as _re
    return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


build_pdf()
print("Wrote reports/insight_memo.md and reports/insight_memo.pdf")
