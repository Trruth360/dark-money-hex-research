import pandas as pd
import numpy as np
from pathlib import Path

# ---- 1) load public case data ----
cases = pd.read_csv("fpcc_cases.csv")  # your FPPC case dataset

# ---- 2) load county-to-region crosswalk ----
regions = pd.read_csv("data/ca_county_regions.csv")

# ---- 3) normalize column names ----
cases.columns = [c.strip().lower().replace(" ", "_") for c in cases.columns]
regions.columns = [c.strip().lower().replace(" ", "_") for c in regions.columns]

# standardize county names
cases["county"] = cases["county"].fillna("Unknown").astype(str).str.strip()
regions["county_name"] = regions["county_name"].fillna("Unknown").astype(str).str.strip()

# coerce money fields
for col in ["fine_amount", "amount_usd"]:
    if col in cases.columns:
        cases[col] = pd.to_numeric(cases[col].astype(str).str.replace("$","",regex=False)
                                   .str.replace(",","",regex=False)
                                   .str.replace(" ","",regex=False), errors="coerce")

# date fields
if "approved_date" in cases.columns:
    cases["approved_date"] = pd.to_datetime(cases["approved_date"], errors="coerce")

# ---- 4) merge county to region ----
merged = cases.merge(
    regions[["region_id", "county_name"]],
    how="left",
    left_on="county",
    right_on="county_name"
)

# optional cleanup
merged = merged.rename(columns={"region_id": "region_id"})
merged["region_id"] = merged["region_id"].fillna("Unknown")

# ---- 5) build regional summaries ----
if "fine_amount" in merged.columns:
    regional_summary = (
        merged.groupby(["region_id"], as_index=False)
        .agg(
            case_count=("case_id", "count"),
            total_fines=("fine_amount", "sum"),
            avg_fine=("fine_amount", "mean")
        )
        .sort_values("total_fines", ascending=False)
    )
else:
    regional_summary = (
        merged.groupby(["region_id"], as_index=False)
        .agg(
            case_count=("case_id", "count")
        )
        .sort_values("case_count", ascending=False)
    )

# ---- 6) monthly regional trend ----
if "approved_date" in merged.columns:
    merged["month"] = merged["approved_date"].dt.to_period("M").astype(str)
    monthly_region_trend = (
        merged.groupby(["month", "region_id"], as_index=False)
        .agg(
            case_count=("case_id", "count"),
            total_fines=("fine_amount", "sum")
        )
        .sort_values(["month", "total_fines"], ascending=[True, False])
    )
else:
    monthly_region_trend = pd.DataFrame()

# ---- 7) save outputs for Hex tables ----
regional_summary.to_csv("regional_summary.csv", index=False)
if not monthly_region_trend.empty:
    monthly_region_trend.to_csv("monthly_region_trend.csv", index=False)

# ---- 8) display ----
display(regional_summary.head(20))
if not monthly_region_trend.empty:
    display(monthly_region_trend.head(20))
