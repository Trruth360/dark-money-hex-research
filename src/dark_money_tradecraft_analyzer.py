"""Dark Money Tradecraft Analyzer.

Public-record-only forensic workflow for dark money investigation.

This module is deliberately conservative:
- all claims require a public anchor (Cal-Access, NetFile, public registry, or captured source)
- blocked telecom / device / tower / subscriber / IP fields remain segregated
- no unverified linkages are promoted into scorecards
- output tables are deterministic, audit-friendly, and Hex-ready
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


class PublicEvidenceGate:
    """Enforce evidence hygiene rules for public-record dark money analysis."""

    BLOCKED_FIELD_NAMES = {
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

    RESERVED_IP_PREFIXES = (
        "192.0.2.",
        "198.51.100.",
        "203.0.113.",
        "127.0.0.",
        "0.0.0.0",
    )

    def __init__(self) -> None:
        self.quarantine_records: List[Dict[str, Any]] = []

    @staticmethod
    def _normalize_name(value: Any) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip().lower()

    def _is_reserved_ip(self, value: Any) -> bool:
        if pd.isna(value):
            return False
        text = str(value).strip()
        return any(text.startswith(prefix) for prefix in self.RESERVED_IP_PREFIXES)

    def audit(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add evidence hygiene and public-anchor metadata to each row."""
        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            record = row.to_dict()
            blocked = []
            for field in self.BLOCKED_FIELD_NAMES:
                if field in row.index and not pd.isna(row[field]):
                    blocked.append(field)

            source_url = row.get("source_url")
            case_id = row.get("case_id")
            approved_date = row.get("approved_date")

            if source_url is not None and str(source_url).strip() != "":
                anchor = "public_registry_or_source"
                evidence_status = "anchored_public"
            elif case_id is not None and str(case_id).strip() != "" and approved_date is not None and str(approved_date).strip() != "":
                anchor = "cal_access_or_public_filing"
                evidence_status = "anchored_public"
            else:
                anchor = "needs_public_anchor"
                evidence_status = "needs_review"

            if blocked:
                evidence_status = "legal_process_dependent"

            if "ip_address" in row.index and self._is_reserved_ip(row.get("ip_address")):
                evidence_status = "quarantined_placeholder"
                self.quarantine_records.append({**record, "quarantine_reason": "reserved_or_example_ip"})

            record["anchor_type"] = anchor
            record["evidence_status"] = evidence_status
            record["blocked_fields"] = ",".join(blocked) if blocked else ""
            rows.append(record)

        return pd.DataFrame(rows)


class CountyRegionJoiner:
    """Join county data to a Census region crosswalk."""

    def __init__(self, region_file: str | Path) -> None:
        self.region_file = Path(region_file)
        self.region_df = pd.read_csv(self.region_file)
        self.region_df.columns = [str(c).strip().lower().replace(" ", "_") for c in self.region_df.columns]

    def normalize_county(self, value: Any) -> str:
        if pd.isna(value):
            return ""
        return str(value).strip()

    def join(self, df: pd.DataFrame) -> pd.DataFrame:
        work = df.copy()
        if "county" not in work.columns:
            raise ValueError("Expected 'county' in the case dataset.")
        work["county"] = work["county"].fillna("Unknown").astype(str).str.strip()
        if "county_name" in self.region_df.columns:
            self.region_df["county_name"] = self.region_df["county_name"].fillna("Unknown").astype(str).str.strip()

        merged = work.merge(
            self.region_df[["region_id", "county_name"]],
            how="left",
            left_on="county",
            right_on="county_name",
        )
        merged["region_id"] = merged["region_id"].fillna("Unknown")
        return merged


class AccountabilityScorecard:
    """Compute deterministic public transparency deficit scores."""

    BASE_PENALTIES = {
        "501(c)(3)": 0.9,
        "501(c)(4)": 0.5,
        "501(c)(5)": 0.5,
        "501(c)(6)": 0.5,
        "independent_expenditure_committee": 0.0,
        "standard_disclosed": 0.0,
        "shell_llc": 0.7,
        "unknown": 0.3,
    }

    JURISDICTION_PENALTIES = {"DE": 0.7, "NV": 0.7, "WY": 0.7, "CA": 0.0}

    def compute(self, row: Dict[str, Any]) -> Dict[str, Any]:
        entity_class = str(row.get("tax_entity_class", "unknown")).lower()
        base_penalty = self.BASE_PENALTIES.get(entity_class, 0.3)

        state = str(row.get("state_registered", "CA")).upper()
        jurisdiction_penalty = self.JURISDICTION_PENALTIES.get(state, 0.0)

        formation_date = pd.to_datetime(row.get("committee_formed_date"), errors="coerce")
        election_date = pd.to_datetime(row.get("election_date"), errors="coerce")

        pop_up_penalty = 0.0
        days_before_election = None
        if pd.notna(formation_date) and pd.notna(election_date):
            days_before_election = (election_date - formation_date).days
            if days_before_election < 90:
                pop_up_penalty = 0.3
            elif days_before_election < 180:
                pop_up_penalty = 0.15

        public_donor_list = bool(row.get("public_donor_list_available", False))
        disclosure_penalty = 0.0 if public_donor_list else 0.2

        total_deficit = min(1.0, base_penalty + jurisdiction_penalty + pop_up_penalty + disclosure_penalty)

        if total_deficit >= 0.7:
            tier = "high_opacity_alarm"
        elif total_deficit >= 0.5:
            tier = "elevated_concern"
        elif total_deficit >= 0.3:
            tier = "monitor"
        else:
            tier = "transparent"

        return {
            "entity_name": row.get("entity_name"),
            "entity_id": row.get("entity_id"),
            "entity_class": entity_class,
            "state_registered": state,
            "base_penalty": base_penalty,
            "jurisdiction_penalty": jurisdiction_penalty,
            "pop_up_penalty": pop_up_penalty,
            "disclosure_penalty": disclosure_penalty,
            "total_accountability_deficit": round(total_deficit, 3),
            "tier": tier,
            "days_before_election": days_before_election,
            "audit_flag": tier in {"high_opacity_alarm", "elevated_concern"},
        }


class DarkMoneyTradecraftAnalyzer:
    """Public-record dark money forensic workflow."""

    def __init__(self, base_dir: str | Path = ".") -> None:
        self.base_dir = Path(base_dir)
        self.case_file = self.base_dir / "data" / "fpcc_cases.csv"
        self.region_file = self.base_dir / "data" / "ca_county_regions.csv"
        self.entity_file = self.base_dir / "data" / "entity_registry.csv"
        self.vendor_file = self.base_dir / "data" / "vendor_registry.csv"
        self.output_dir = self.base_dir / "data" / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cases(self) -> pd.DataFrame:
        if not self.case_file.exists():
            raise FileNotFoundError(f"Missing case file: {self.case_file}")
        df = pd.read_csv(self.case_file)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df

    def load_optional_table(self, path: Path) -> Optional[pd.DataFrame]:
        if not path.exists():
            return None
        df = pd.read_csv(path)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        return df

    def build_region_rollup(self, df: pd.DataFrame) -> pd.DataFrame:
        region_joiner = CountyRegionJoiner(self.region_file)
        merged = region_joiner.join(df)

        if "fine_amount" in merged.columns:
            result = (
                merged.groupby("region_id", as_index=False)
                .agg(
                    case_count=("case_id", "count"),
                    total_fines=("fine_amount", "sum"),
                    avg_fine=("fine_amount", "mean"),
                )
                .sort_values("total_fines", ascending=False)
            )
        else:
            result = (
                merged.groupby("region_id", as_index=False)
                .agg(case_count=("case_id", "count"))
                .sort_values("case_count", ascending=False)
            )
        return result

    def build_monthly_region_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        region_joiner = CountyRegionJoiner(self.region_file)
        merged = region_joiner.join(df)

        if "approved_date" in merged.columns:
            merged["approved_date"] = pd.to_datetime(merged["approved_date"], errors="coerce")
            merged["month"] = merged["approved_date"].dt.to_period("M").astype(str)

            trend = (
                merged.groupby(["month", "region_id"], as_index=False)
                .agg(
                    case_count=("case_id", "count"),
                    total_fines=("fine_amount", "sum") if "fine_amount" in merged.columns else ("case_id", "count"),
                )
                .sort_values(["month", "total_fines"], ascending=[True, False])
            )
            return trend

        return pd.DataFrame()

    def build_public_hygiene_audit(self, df: pd.DataFrame) -> pd.DataFrame:
        gate = PublicEvidenceGate()
        audited = gate.audit(df)
        return audited

    def build_accountability_scorecard(self, entity_df: pd.DataFrame) -> pd.DataFrame:
        scorecard = AccountabilityScorecard()
        scores = [scorecard.compute(row.to_dict()) for _, row in entity_df.iterrows()]
        return pd.DataFrame(scores)

    def run(self) -> Dict[str, pd.DataFrame]:
        cases = self.load_cases()
        cases["county"] = cases["county"].fillna("Unknown").astype(str).str.strip()

        if "fine_amount" in cases.columns:
            cases["fine_amount"] = pd.to_numeric(
                cases["fine_amount"].astype(str).str.replace("$", "", regex=False).str.replace(",", "", regex=False),
                errors="coerce",
            )
        if "approved_date" in cases.columns:
            cases["approved_date"] = pd.to_datetime(cases["approved_date"], errors="coerce")

        hygiene = self.build_public_hygiene_audit(cases)
        regional = self.build_region_rollup(cases)
        monthly = self.build_monthly_region_trend(cases)

        entity_df = self.load_optional_table(self.entity_file)
        accountability = self.build_accountability_scorecard(entity_df) if entity_df is not None else pd.DataFrame()

        self.output_dir.mkdir(parents=True, exist_ok=True)
        hygiene.to_csv(self.output_dir / "hygiene_audit.csv", index=False)
        regional.to_csv(self.output_dir / "regional_summary.csv", index=False)
        monthly.to_csv(self.output_dir / "monthly_region_trend.csv", index=False)
        if not accountability.empty:
            accountability.to_csv(self.output_dir / "accountability_scores.csv", index=False)

        return {
            "hygiene_audit": hygiene,
            "regional_summary": regional,
            "monthly_region_trend": monthly,
            "accountability_scores": accountability,
        }


if __name__ == "__main__":
    analyzer = DarkMoneyTradecraftAnalyzer(base_dir=".")
    results = analyzer.run()
    for name, df in results.items():
        print(f"\n{name} rows={len(df)}")
        print(df.head())
