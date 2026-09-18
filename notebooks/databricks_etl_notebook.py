# Databricks notebook source
# MAGIC %md
# MAGIC # Housing Market Analytics — Databricks ETL (raw -> staging -> cleaned -> analytics)
# MAGIC
# MAGIC This notebook is a **direct PySpark port** of the local pandas pipeline in
# MAGIC `notebooks/01_data_profiling.py` through `04_statistical_analysis.py`, which was
# MAGIC run and validated against the real Kaggle CSVs before this port was written — every
# MAGIC transformation below mirrors logic that already produced verified numbers locally.
# MAGIC
# MAGIC **Manual step required first:** upload `Bengaluru_House_Data.csv`, `Hyderabad.csv`
# MAGIC and `Chennai.csv` to DBFS (Data > Add data > Upload File), then set `DATA_PATH` below
# MAGIC to that DBFS folder (e.g. `/FileStore/tables/housing/`).
# MAGIC
# MAGIC Architecture: **raw** (CSV as-is) -> **staging** (typed, parsed) -> **cleaned**
# MAGIC (quality-flagged, standardized) -> **analytics** (feature-engineered, tiered).

# COMMAND ----------

DATA_PATH = "/FileStore/tables/housing/"   # <-- change to your DBFS upload path
CATALOG_SCHEMA = "housing_analytics"        # will be created if it doesn't exist

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG_SCHEMA}")
spark.sql(f"USE {CATALOG_SCHEMA}")

# COMMAND ----------

# MAGIC %md ## 1. RAW layer — load CSVs exactly as provided

# COMMAND ----------

df_bengaluru_raw = (
    spark.read.option("header", True).option("inferSchema", True)
    .csv(DATA_PATH + "Bengaluru_House_Data.csv")
)
df_hyderabad_raw = (
    spark.read.option("header", True).option("inferSchema", True)
    .csv(DATA_PATH + "Hyderabad.csv")
)
df_chennai_raw = (
    spark.read.option("header", True).option("inferSchema", True)
    .csv(DATA_PATH + "Chennai.csv")
)

df_bengaluru_raw.write.mode("overwrite").saveAsTable("bengaluru_raw")
df_hyderabad_raw.write.mode("overwrite").saveAsTable("hyderabad_raw")
df_chennai_raw.write.mode("overwrite").saveAsTable("chennai_raw")

print("Bengaluru raw rows:", df_bengaluru_raw.count())
print("Hyderabad raw rows:", df_hyderabad_raw.count())
print("Chennai raw rows:", df_chennai_raw.count())

# COMMAND ----------

# MAGIC %md ## 2. STAGING layer — type casting and field parsing
# MAGIC
# MAGIC `total_sqft` mixes plain numbers, ranges (`"1000 - 1285"`) and unit suffixes
# MAGIC (`Sq. Meter`, `Sq. Yards`, `Acres`, `Cents`, `Guntha`, `Perch`, `Grounds`).
# MAGIC Every format is handled explicitly via a Python UDF ported 1:1 from
# MAGIC `notebooks/02_data_cleaning.py::parse_total_sqft` — nothing is silently coerced.

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, DoubleType, StringType
import re

UNIT_TO_SQFT = {
    "sq. meter": 10.7639, "sq. yards": 9.0, "acres": 43560.0,
    "cents": 435.6, "guntha": 1089.0, "grounds": 2400.0, "perch": 272.25,
}

def parse_total_sqft(raw):
    if raw is None:
        return (None, "null")
    s = str(raw).strip()
    if re.match(r"^\d+(\.\d+)?$", s):
        return (float(s), "plain")
    m = re.match(r"^(\d+(\.\d+)?)\s*-\s*(\d+(\.\d+)?)$", s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(3))
        return ((lo + hi) / 2, "range_midpoint")
    for unit, factor in UNIT_TO_SQFT.items():
        m = re.match(rf"^(\d+(\.\d+)?)\s*{re.escape(unit)}$", s, flags=re.IGNORECASE)
        if m:
            return (float(m.group(1)) * factor, f"unit_convert:{unit}")
    return (None, "unparseable")

sqft_schema = StructType([
    StructField("value", DoubleType()), StructField("method", StringType())
])
parse_sqft_udf = F.udf(parse_total_sqft, sqft_schema)

df_bengaluru_staging = (
    df_bengaluru_raw
    .withColumn("_sqft_parsed", parse_sqft_udf(F.col("total_sqft")))
    .withColumn("total_sqft_clean", F.col("_sqft_parsed.value"))
    .withColumn("sqft_parse_method", F.col("_sqft_parsed.method"))
    .withColumn("bhk", F.regexp_extract(F.col("size"), r"(\d+)", 1).cast("double"))
    .withColumn("price_lakhs", F.col("price").cast("double"))
    .withColumn("price_inr", F.col("price_lakhs") * 100000)
    .withColumn(
        "price_per_sqft",
        F.when(
            (F.col("total_sqft_clean").isNotNull()) & (F.col("total_sqft_clean") > 0),
            F.col("price_inr") / F.col("total_sqft_clean"),
        ),
    )
    .drop("_sqft_parsed")
)

df_bengaluru_staging.write.mode("overwrite").saveAsTable("bengaluru_staging")
display(df_bengaluru_staging.limit(10))

# COMMAND ----------

# MAGIC %md ## 3. CLEANED layer — locality standardization + quality_flag
# MAGIC
# MAGIC **Locality standardization methodology (deliberately conservative):**
# MAGIC Stage A auto-merges pure whitespace/punctuation/case variants (e.g. "Whitefield" /
# MAGIC "White Field" / "WHITEFIELD" all collapse to one canonical form — this is safe
# MAGIC because compacting whitespace cannot change which real-world place is meant).
# MAGIC Stage B (typo correction via fuzzy string matching) is deliberately **not**
# MAGIC auto-applied: testing on this exact dataset showed fuzzy ratio cannot separate
# MAGIC real typos ("whietfield" -> "whitefield", ratio 90) from genuinely different
# MAGIC localities that just look similar ("HBR Layout" vs "HSR Layout", also ratio 90;
# MAGIC "Electronic City Phase 1" vs "Phase 2" scores even higher at 95.7 despite being
# MAGIC different places). Auto-merging those would corrupt every locality-level price
# MAGIC statistic. Fuzzy candidates are written to `reports/locality_mapping_bengaluru.csv`
# MAGIC for manual review instead — see `docs/methodology.md`.
# MAGIC
# MAGIC For the Databricks table, the already-resolved `locality_standard` mapping
# MAGIC produced by the local pandas run (Stage A only) is what should be used; this
# MAGIC cell shows the whitespace-normalization logic in Spark for completeness.

# COMMAND ----------

def normalize_locality(s):
    if s is None:
        return "unknown"
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

normalize_udf = F.udf(normalize_locality, StringType())

df_bengaluru_cleaned = (
    df_bengaluru_staging
    .withColumn("location_norm", normalize_udf(F.col("location")))
    .withColumn("location_compact", F.regexp_replace(F.col("location_norm"), r"[^a-z0-9]", ""))
)

# Canonical name per compact-key = most frequent raw variant in that group
from pyspark.sql.window import Window
w = Window.partitionBy("location_compact").orderBy(F.desc("location_norm"))
counts = df_bengaluru_cleaned.groupBy("location_compact", "location").count()
w_rank = Window.partitionBy("location_compact").orderBy(F.desc("count"))
canonical = (
    counts.withColumn("rnk", F.row_number().over(w_rank))
    .filter(F.col("rnk") == 1)
    .select("location_compact", F.col("location").alias("locality_standard"))
)
df_bengaluru_cleaned = df_bengaluru_cleaned.join(canonical, on="location_compact", how="left")

# quality_flag — mirrors notebooks/02_data_cleaning.py::classify exactly, including
# the empirically-derived price_per_sqft bounds (500-50000 Rs/sqft) that catch the
# Acre/Perch/Cents unit-conversion errors discovered during local validation.
df_bengaluru_cleaned = df_bengaluru_cleaned.withColumn(
    "quality_flag",
    F.when(
        F.col("bhk").isNull() | F.col("total_sqft_clean").isNull() | F.col("price_lakhs").isNull()
        | (F.col("total_sqft_clean") <= 0) | (F.col("price_lakhs") <= 0),
        "Invalid",
    )
    .when(
        F.col("price_per_sqft").isNotNull() & ((F.col("price_per_sqft") < 500) | (F.col("price_per_sqft") > 50000)),
        "Invalid",
    )
    .when(F.col("bath") > F.col("bhk") + 2, "Suspicious")
    .when(F.col("total_sqft_clean") < 100, "Suspicious")
    .otherwise("Valid"),
)

df_bengaluru_cleaned.write.mode("overwrite").saveAsTable("bengaluru_cleaned")
display(df_bengaluru_cleaned.groupBy("quality_flag").count())

# COMMAND ----------

# MAGIC %md ## 4. ANALYTICS layer — feature engineering + locality tiers -> `housing_cleaned` Delta table

# COMMAND ----------

df_features = (
    df_bengaluru_cleaned
    .withColumn(
        "bhk_category",
        F.when(F.col("bhk") >= 5, "5+ BHK").otherwise(F.concat(F.col("bhk").cast("int"), F.lit(" BHK"))),
    )
    .withColumn(
        "size_bucket",
        F.when(F.col("total_sqft_clean") < 500, "<500 sqft")
         .when(F.col("total_sqft_clean") < 1000, "500-1000 sqft")
         .when(F.col("total_sqft_clean") < 1500, "1000-1500 sqft")
         .when(F.col("total_sqft_clean") < 2500, "1500-2500 sqft")
         .otherwise("2500+ sqft"),
    )
)

MIN_LISTINGS_FOR_TIER = 10
locality_medians = (
    df_features.filter(F.col("quality_flag") != "Invalid")
    .groupBy("locality_standard")
    .agg(F.count("*").alias("listings"), F.expr("percentile(price_per_sqft, 0.5)").alias("median_price_per_sqft"))
)
ranked = locality_medians.filter(F.col("listings") >= MIN_LISTINGS_FOR_TIER)
q_high, q_low = ranked.approxQuantile("median_price_per_sqft", [2 / 3, 1 / 3], 0.001)

locality_tiers = ranked.withColumn(
    "locality_tier",
    F.when(F.col("median_price_per_sqft") >= q_high, "Tier 1 - Premium")
     .when(F.col("median_price_per_sqft") >= q_low, "Tier 2 - Mid-market")
     .otherwise("Tier 3 - Value"),
).select("locality_standard", "locality_tier")

housing_cleaned = df_features.join(locality_tiers, on="locality_standard", how="left").withColumn(
    "locality_tier", F.coalesce(F.col("locality_tier"), F.lit(f"Insufficient data (<{MIN_LISTINGS_FOR_TIER} listings)"))
)

housing_cleaned.write.format("delta").mode("overwrite").saveAsTable("housing_cleaned")
print("housing_cleaned rows:", housing_cleaned.count())
display(housing_cleaned.groupBy("locality_tier").count())

# COMMAND ----------

# MAGIC %md ## 5. Run the analytical SQL against the Delta table
# MAGIC Paste any query from `sql/01_data_quality.sql` .. `sql/05_value_analysis.sql`
# MAGIC here (they were written against this exact `housing_cleaned` schema) or run:
# MAGIC `%sql SELECT * FROM housing_cleaned LIMIT 10`

# COMMAND ----------

display(spark.sql("SELECT locality_tier, COUNT(*) AS listings, ROUND(percentile(price_per_sqft, 0.5),0) AS median_price_per_sqft FROM housing_cleaned WHERE quality_flag != 'Invalid' GROUP BY locality_tier ORDER BY median_price_per_sqft DESC"))
