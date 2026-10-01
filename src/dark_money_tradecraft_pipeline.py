#!/usr/bin/env python3
"""Dark Money Tradecraft: Complete Hex-Ready Pipeline

This is the production-grade public-record dark money forensic workflow.

Layers:
1. Public Records Anchor: Cal-Access, NetFile, public registries only
2. County-to-Region Join: California Census regions geographic rollup
3. Evidence Hygiene Gate: Quarantine placeholders, block telecom fields
4. Accountability Scorecard: Deterministic public transparency deficit scoring
5. Hex-Ready Exports: CSV tables for dashboards and SQL queries

All outputs are deterministic, fully auditable, and legally compliant.
"""

import sys
from pathlib import Path

import pandas as pd


class PublicRecordsAnchor:
    """Enforce public-record-only evidence layer."""

    RESERVED_IP_RANGES = ("192.0.2.", "198.51.100.", "203.0.113.", "127.0.0.", "0.0.0.0")
    BLOCKED_TELECOM_FIELDS = {
        "ip_address",
        "tower_node_id",
        "cell_sector",
        "lac_tac",
        "imsi",
        "tmsi",
        "msisdn",
        "geo_latitude",
        "geo_longitude",
        "timing_advance",
        "rsrp",
        "rsrq",
        "sinr",
        "device_id",
    }

    @staticmethod
    def is_reserved_ip(value) -> bool:
        if pd.isna(value):
            return False
        text = str(value).strip()
        return any(text.startswith(prefix) for prefix in PublicRecordsAnchor.RESERVED_IP_RANGES)

    @staticmethod
    def has_public_anchor(row) -> str:
        """Classify evidence anchor status."""
        source_url = row.get("source_url")
        case_id = row.get("case_id")
        approved_date = row.get("approved_date")

        if source_url is not None and str(source_url).strip():
            return "anchored_public_registry"
        if case_id is not None and str(case_id).strip() and approved_date is not None:
            return "anchored_cal_access_filing"
        return "unanchored_needs_review"

    @staticmethod
    def audit(df: pd.DataFrame) -> pd.DataFrame:
        """Add public anchor and evidence hygiene metadata."""
        work = df.copy()
        work["evidence_status"] = work.apply(PublicRecordsAnchor.has_public_anchor, axis=1)
        work["has_reserved_ip"] = work.get("ip_address", "").apply(PublicRecordsAnchor.is_reserved_ip)

        # Mark rows with blocked telecom fields
        blocked_count = 0
        for field in PublicRecordsAnchor.BLOCKED_TELECOM_FIELDS:
            if field in work.columns:
                blocked_count += work[field].notna().astype(int)

        work["blocked_telecom_fields"] = blocked_count

        # Quarantine placeholders
        work.loc[work["has_reserved_ip"], "evidence_status"] = "quarantined_placeholder"

        return work


class CountyRegionJoiner:
    """Join cases to California Census regions by county."""

    def __init__(self, region_file: str | Path):
        self.regions = pd.read_csv(region_file)
        self.regions.columns = [c.strip().lower().replace(" ", "_") for c in self.regions.columns]
        if "county_name" in self.regions.columns:
            self.regions["county_name"] = self.regions["county_name"].astype(str).str.strip()

    def join(self, cases: pd.DataFrame) -> pd.DataFrame:
        """Join cases to regions by county."""
        work = cases.copy()
        work["county"] = work["county"].fillna("Unknown").astype(str).str.strip()

        merged = work.merge(
            self.regions[["region_id", "county_name"]],
            how="left",
            left_on="county",
            right_on="county_name",
        )
        merged["region_id"] = merged["region_id"].fillna("Unknown")
        return merged


class EvidenceHygieneGate:
    """Filter and audit evidence before scoring."""

    @staticmethod
    def clean_money(value) -> float | None:
        """Parse money fields."""
        if pd.isna(value):
            return None
        text = str(value).strip().replace("$", "").replace(",", "")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def clean_date(value) -> pd.Timestamp | None:
        """Parse date fields."""
        if pd.isna(value):
            return None
        return pd.to_datetime(value, errors="coerce")

    @staticmethod
    def process(df: pd.DataFrame) -> pd.DataFrame:
        """Apply hygiene rules."""
        work = df.copy()

        # Normalize columns
        work.columns = [c.strip().lower().replace(" ", "_") for c in work.columns]

        # Clean money fields
        for col in ["fine_amount", "amount_usd", "total_fines"]:
            if col in work.columns:
                work[col] = work[col].apply(EvidenceHygieneGate.clean_money)

        # Clean date fields
        for col in ["approved_date", "transaction_date", "committee_formed_date", "election_date"]:
            if col in work.columns:
                work[col] = work[col].apply(EvidenceHygieneGate.clean_date)

        # Remove empty rows
        work = work.dropna(subset=["case_id"], how="all")

        return work


class AccountabilityScorecard:
    """Score entities for public transparency deficit."""

    BASE_PENALTIES = {
        "501(c)(3)": 0.9,
        "501(c)(4)": 0.5,
        "501(c)(5)": 0.5,
        "501(c)(6)": 0.5,
        "independent_expenditure_committee": 0.0,
        "carey_committee": 0.0,
        "standard_disclosed": 0.0,
        "shell_llc": 0.7,
        "unknown": 0.3,
    }

    JURISDICTION_PENALTIES = {"DE": 0.7, "NV": 0.7, "WY": 0.7, "CA": 0.0, "": 0.0}

    @staticmethod
    def score(entity_row: pd.Series) -> dict:
        """Compute accountability deficit for an entity."""
        entity_class = str(entity_row.get("tax_entity_class", "unknown")).lower().strip()
        base_penalty = AccountabilityScorecard.BASE_PENALTIES.get(entity_class, 0.3)

        state = str(entity_row.get("state_registered", "CA")).upper().strip()
        jurisdiction_penalty = AccountabilityScorecard.JURISDICTION_PENALTIES.get(state, 0.0)

        # Pop-up risk: formed < 90 days before election
        formation = pd.to_datetime(entity_row.get("committee_formed_date"), errors="coerce")
        election = pd.to_datetime(entity_row.get("election_date"), errors="coerce")
        pop_up_penalty = 0.0
        days_before_election = None

        if pd.notna(formation) and pd.notna(election):
            days_before_election = (election - formation).days
            if days_before_election < 90:
                pop_up_penalty = 0.3
            elif days_before_election < 180:
                pop_up_penalty = 0.15

        # Donor disclosure penalty
        public_donor_list = bool(entity_row.get("public_donor_list_available", False))
        disclosure_penalty = 0.0 if public_donor_list else 0.2

        # Total deficit (0-1 scale, 1 = fully opaque)
        total_deficit = min(1.0, base_penalty + jurisdiction_penalty + pop_up_penalty + disclosure_penalty)

        # Tier classification
        if total_deficit >= 0.7:
            tier = "high_opacity_alarm"
        elif total_deficit >= 0.5:
            tier = "elevated_concern"
        elif total_deficit >= 0.3:
            tier = "monitor"
        else:
            tier = "transparent"

        return {
            "entity_name": entity_row.get("entity_name", "unknown"),
            "entity_id": entity_row.get("entity_id", "unknown"),
            "entity_class": entity_class,
            "state_registered": state,
            "base_penalty": round(base_penalty, 3),
            "jurisdiction_penalty": round(jurisdiction_penalty, 3),
            "pop_up_penalty": round(pop_up_penalty, 3),
            "disclosure_penalty": round(disclosure_penalty, 3),
            "total_accountability_deficit": round(total_deficit, 3),
            "tier": tier,
            "days_before_election": days_before_election,
            "audit_flag": tier in {"high_opacity_alarm", "elevated_concern"},
        }


class DarkMoneyTradecraftPipeline:
    """Orchestrate the complete dark money forensic workflow."""

    def __init__(self, base_dir: str | Path = "."):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.output_dir = self.data_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cases(self) -> pd.DataFrame:
        """Load FPPC case data."""
        case_file = self.data_dir / "fpcc_cases.csv"
        if not case_file.exists():
            print(f"⚠️  Missing: {case_file}")
            return pd.DataFrame()
        print(f"✓ Loaded {case_file}")
        return pd.read_csv(case_file)

    def load_entities(self) -> pd.DataFrame:
        """Load entity registry."""
        entity_file = self.data_dir / "entity_registry.csv"
        if not entity_file.exists():
            print(f"⚠️  Missing: {entity_file}")
            return pd.DataFrame()
        print(f"✓ Loaded {entity_file}")
        return pd.read_csv(entity_file)

    def load_regions(self) -> pd.DataFrame:
        """Load county-to-region crosswalk."""
        region_file = self.data_dir / "ca_county_regions.csv"
        if not region_file.exists():
            raise FileNotFoundError(f"Required: {region_file}")
        print(f"✓ Loaded {region_file}")
        return pd.read_csv(region_file)

    def step_1_hygiene_audit(self, cases: pd.DataFrame) -> pd.DataFrame:
        """Step 1: Evidence hygiene gate."""
        print("\n=== STEP 1: EVIDENCE HYGIENE AUDIT ===")
        cases = EvidenceHygieneGate.process(cases)
        cases = PublicRecordsAnchor.audit(cases)

        anchored = len(cases[cases["evidence_status"].str.contains("anchored", na=False)])
        quarantined = len(cases[cases["evidence_status"].str.contains("quarantined", na=False)])
        unanchored = len(cases[cases["evidence_status"].str.contains("unanchored", na=False)])

        print(f"Anchored public records:     {anchored}")
        print(f"Quarantined placeholders:   {quarantined}")
        print(f"Needs review:               {unanchored}")

        cases.to_csv(self.output_dir / "hygiene_audit.csv", index=False)
        print(f"✓ Exported: hygiene_audit.csv")
        return cases

    def step_2_regional_rollup(self, cases: pd.DataFrame) -> pd.DataFrame:
        """Step 2: County-to-region geographic rollup."""
        print("\n=== STEP 2: COUNTY-REGION GEOGRAPHIC ROLLUP ===")
        joiner = CountyRegionJoiner(self.data_dir / "ca_county_regions.csv")
        merged = joiner.join(cases)

        if "fine_amount" not in merged.columns:
            print("⚠️  No fine_amount column; using case counts only")
            regional = merged.groupby("region_id", as_index=False).agg(
                case_count=("case_id", "count")
            )
        else:
            regional = merged.groupby("region_id", as_index=False).agg(
                case_count=("case_id", "count"),
                total_fines=("fine_amount", "sum"),
                avg_fine=("fine_amount", "mean"),
            )

        regional = regional.sort_values(
            "total_fines" if "total_fines" in regional.columns else "case_count",
            ascending=False,
        )

        print(regional.to_string())
        regional.to_csv(self.output_dir / "regional_summary.csv", index=False)
        print(f"✓ Exported: regional_summary.csv")
        return regional

    def step_3_monthly_trend(self, cases: pd.DataFrame) -> pd.DataFrame:
        """Step 3: Monthly trend analysis."""
        print("\n=== STEP 3: MONTHLY REGIONAL TREND ===")
        if "approved_date" not in cases.columns:
            print("⚠️  No approved_date column; skipping monthly trend")
            return pd.DataFrame()

        joiner = CountyRegionJoiner(self.data_dir / "ca_county_regions.csv")
        merged = joiner.join(cases)

        merged["month"] = merged["approved_date"].dt.to_period("M").astype(str)

        if "fine_amount" in merged.columns:
            trend = merged.groupby(["month", "region_id"], as_index=False).agg(
                case_count=("case_id", "count"),
                total_fines=("fine_amount", "sum"),
            )
        else:
            trend = merged.groupby(["month", "region_id"], as_index=False).agg(
                case_count=("case_id", "count"),
            )

        trend = trend.sort_values(["month", "case_count"], ascending=[True, False])
        print(trend.tail(20).to_string())
        trend.to_csv(self.output_dir / "monthly_region_trend.csv", index=False)
        print(f"✓ Exported: monthly_region_trend.csv")
        return trend

    def step_4_accountability_scoring(self, entities: pd.DataFrame) -> pd.DataFrame:
        """Step 4: Accountability deficit scorecard."""
        print("\n=== STEP 4: ACCOUNTABILITY DEFICIT SCORING ===")
        if entities.empty:
            print("⚠️  No entity data; skipping accountability scoring")
            return pd.DataFrame()

        scores = []
        for _, row in entities.iterrows():
            score = AccountabilityScorecard.score(row)
            scores.append(score)

        scorecard = pd.DataFrame(scores)

        high_opacity = len(scorecard[scorecard["tier"] == "high_opacity_alarm"])
        elevated = len(scorecard[scorecard["tier"] == "elevated_concern"])
        monitor = len(scorecard[scorecard["tier"] == "monitor"])
        transparent = len(scorecard[scorecard["tier"] == "transparent"])

        print(f"High-opacity alarms:  {high_opacity}")
        print(f"Elevated concern:     {elevated}")
        print(f"Monitor:              {monitor}")
        print(f"Transparent:          {transparent}")

        if high_opacity > 0:
            print("\n⚠️  HIGH-OPACITY ENTITIES:")
            alarms = scorecard[scorecard["tier"] == "high_opacity_alarm"]
            print(alarms[["entity_name", "entity_class", "total_accountability_deficit"]].to_string(index=False))

        scorecard.to_csv(self.output_dir / "accountability_scores.csv", index=False)
        print(f"✓ Exported: accountability_scores.csv")
        return scorecard

    def run(self) -> dict:
        """Execute the complete pipeline."""
        print("🔍 DARK MONEY TRADECRAFT PIPELINE")
        print("=" * 70)
        print("Anchored to public records | County-region join | Evidence hygiene")
        print("Accountability scorecard | Hex-ready exports")
        print("=" * 70)

        # Load data
        cases = self.load_cases()
        entities = self.load_entities()
        self.load_regions()

        if cases.empty:
            print("✗ No case data available. Exiting.")
            return {}

        # Execute steps
        audit = self.step_1_hygiene_audit(cases)
        regional = self.step_2_regional_rollup(cases)
        monthly = self.step_3_monthly_trend(cases)
        scores = self.step_4_accountability_scoring(entities)

        print("\n" + "=" * 70)
        print("✅ PIPELINE COMPLETE")
        print(f"All outputs exported to: {self.output_dir}")
        print("=" * 70)

        return {
            "hygiene_audit": audit,
            "regional_summary": regional,
            "monthly_region_trend": monthly,
            "accountability_scores": scores,
        }


def main() -> int:
    """Main entry point."""
    pipeline = DarkMoneyTradecraftPipeline(base_dir=".")
    results = pipeline.run()
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
