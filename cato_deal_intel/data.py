import csv
from datetime import date
from pathlib import Path
from typing import Any

from .models import EvidenceItem, Opportunity, PermissionProfile


class SourceData:
    def __init__(self, root: Path) -> None:
        self.root = root

    def opportunities(self) -> list[Opportunity]:
        rows = self._read_tsv("salesforce/opportunities.tsv")
        return [Opportunity.model_validate(_coerce_opportunity(row)) for row in rows]

    def permissions(self) -> list[PermissionProfile]:
        rows = self._read_tsv("policies/access_permissions.tsv")
        return [PermissionProfile.model_validate(_coerce_permissions(row)) for row in rows]

    def evidence(self) -> list[EvidenceItem]:
        items = self._salesforce_evidence()
        items.extend(self._gong_evidence())
        items.extend(self._pricing_evidence())
        items.extend(self._policy_evidence())
        items.extend(self._slack_evidence())
        return items

    def _salesforce_evidence(self) -> list[EvidenceItem]:
        files = {
            "accounts.tsv": "accounts",
            "opportunities.tsv": "opportunities",
            "contacts.tsv": "contacts",
        }
        items: list[EvidenceItem] = []
        for filename, source_id_field in files.items():
            for row in self._read_tsv(f"salesforce/{filename}"):
                opportunity_id = self._opportunity_for_row(row)
                account_id = row.get("account_id")
                source_id = _source_id(row, source_id_field)
                text = "; ".join(f"{key}={value}" for key, value in row.items())
                items.append(
                    EvidenceItem(
                        evidence_id=f"salesforce:{filename}:{source_id}",
                        opportunity_id=opportunity_id,
                        account_id=account_id,
                        source_type="salesforce",
                        source_file=f"synthetic_data/salesforce/{filename}",
                        source_id=source_id,
                        access_level="standard",
                        event_date=_date(row.get("close_date") or row.get("last_interaction_date")),
                        text=text,
                    )
                )
        return items

    def _gong_evidence(self) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for row in self._read_tsv("gong/gong_call_summaries.tsv"):
            items.append(
                EvidenceItem(
                    evidence_id=f"gong:summary:{row['call_id']}",
                    opportunity_id=row["opportunity_id"],
                    account_id=row["account_id"],
                    source_type="gong",
                    source_file="synthetic_data/gong/gong_call_summaries.tsv",
                    source_id=row["call_id"],
                    access_level=row["source_access_level"],
                    event_date=_date(row["call_date"]),
                    text=row["summary"] + " " + row["key_points"] + " Risks: " + row["risks"],
                    metadata={"title": row["title"], "participants": row["participants"]},
                )
            )
        for transcript in sorted((self.root / "gong/transcripts").glob("*.md")):
            opportunity_id, call_id = transcript.stem.split("_", maxsplit=1)
            items.append(
                EvidenceItem(
                    evidence_id=f"gong:transcript:{call_id}",
                    opportunity_id=opportunity_id,
                    source_type="gong",
                    source_file=f"synthetic_data/gong/transcripts/{transcript.name}",
                    source_id=call_id,
                    access_level="standard",
                    text=transcript.read_text(encoding="utf-8"),
                )
            )
        return items

    def _pricing_evidence(self) -> list[EvidenceItem]:
        return [
            EvidenceItem(
                evidence_id=f"pricing:{row['pricing_note_id']}",
                opportunity_id=row["opportunity_id"],
                source_type="pricing",
                source_file="synthetic_data/pricing/pricing_notes.tsv",
                source_id=row["pricing_note_id"],
                access_level="sensitive" if row["commercial_risk"] == "high" else "standard",
                text=row["pricing_notes"],
                metadata={"approval_status": row["approval_status"]},
            )
            for row in self._read_tsv("pricing/pricing_notes.tsv")
        ]

    def _policy_evidence(self) -> list[EvidenceItem]:
        path = self.root / "policies/deal_desk_policy.md"
        return [
            EvidenceItem(
                evidence_id="policy:deal-desk",
                opportunity_id="*",
                source_type="policies",
                source_file="synthetic_data/policies/deal_desk_policy.md",
                source_id="deal-desk-policy",
                access_level="standard",
                text=path.read_text(encoding="utf-8"),
            )
        ]

    def _slack_evidence(self) -> list[EvidenceItem]:
        rows = self._read_tsv("slack/account_team_updates.tsv")
        return [
            EvidenceItem(
                evidence_id=f"slack:{row['update_id']}",
                opportunity_id=row["opportunity_id"],
                account_id=row["account_id"],
                source_type="slack",
                source_file="synthetic_data/slack/account_team_updates.tsv",
                source_id=row["update_id"],
                access_level=row["source_access_level"],
                event_date=_date(row["update_date"]),
                text=row["update_text"],
                metadata={"synthetic_notice": row["synthetic_notice"], "channel": row["channel"]},
            )
            for row in rows
        ]

    def _opportunity_for_row(self, row: dict[str, str]) -> str:
        if "opportunity_id" in row:
            return row["opportunity_id"]
        account_id = row.get("account_id", "")
        match = next((item for item in self.opportunities() if item.account_id == account_id), None)
        return match.opportunity_id if match else "*"

    def _read_tsv(self, relative_path: str) -> list[dict[str, str]]:
        path = self.root / relative_path
        if not path.exists():
            return []
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))


def _coerce_opportunity(row: dict[str, str]) -> dict[str, Any]:
    integer_fields = {"acv", "tcv", "renewal_term_months", "probability"}
    boolean_fields = {"approval_required", "restricted_access"}
    return {
        key: _coerce_value(key, value, integer_fields, boolean_fields) for key, value in row.items()
    }


def _coerce_permissions(row: dict[str, str]) -> dict[str, Any]:
    list_fields = {"allowed_account_ids", "allowed_source_types"}
    return {key: _permission_value(key, value, list_fields) for key, value in row.items()}


def _permission_value(key: str, value: str, list_fields: set[str]) -> Any:
    if key in list_fields:
        return value.split(",")
    if key.startswith("can_"):
        return _coerce_bool(value)
    return value


def _source_id(row: dict[str, str], source_id_field: str) -> str:
    if source_id_field == "opportunities":
        return row["opportunity_id"]
    return row[f"{source_id_field[:-1]}_id"]


def _coerce_value(key: str, value: str, integer_fields: set[str], boolean_fields: set[str]) -> Any:
    if key in integer_fields:
        return int(value)
    if key in boolean_fields:
        return _coerce_bool(value)
    if key == "close_date":
        return date.fromisoformat(value)
    return value


def _coerce_bool(value: str) -> bool:
    return value.lower() == "true"


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None
