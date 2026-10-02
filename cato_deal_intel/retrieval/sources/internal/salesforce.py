from datetime import date

from ....models import EvidenceItem
from ..reader import TsvReader


class SalesforceEvidenceLoader:
    """Load account, opportunity, and contact rows as evidence."""

    FILES = {
        "accounts.tsv": "accounts",
        "opportunities.tsv": "opportunities",
        "contacts.tsv": "contacts",
    }

    def __init__(self, reader: TsvReader, opportunity_by_account: dict[str, str]) -> None:
        self.reader = reader
        self.opportunity_by_account = opportunity_by_account

    def load(self) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for filename, source_id_field in self.FILES.items():
            evidence.extend(self._load_file(filename, source_id_field))
        return evidence

    def _load_file(self, filename: str, source_id_field: str) -> list[EvidenceItem]:
        rows = self.reader.read(f"salesforce/{filename}")
        return [self._to_evidence(row, filename, source_id_field) for row in rows]

    def _to_evidence(
        self,
        row: dict[str, str],
        filename: str,
        source_id_field: str,
    ) -> EvidenceItem:
        source_id = self._source_id(row, source_id_field)
        return EvidenceItem(
            evidence_id=f"salesforce:{filename}:{source_id}",
            opportunity_id=self._opportunity_for_row(row),
            account_id=row.get("account_id"),
            source_type="salesforce",
            source_file=f"synthetic_data/salesforce/{filename}",
            source_id=source_id,
            access_level="standard",
            event_date=self._event_date(row),
            text="; ".join(f"{key}={value}" for key, value in row.items()),
        )

    def _opportunity_for_row(self, row: dict[str, str]) -> str:
        if "opportunity_id" in row:
            return row["opportunity_id"]
        return self.opportunity_by_account.get(row.get("account_id", ""), "*")

    @staticmethod
    def _source_id(row: dict[str, str], source_id_field: str) -> str:
        if source_id_field == "opportunities":
            return row["opportunity_id"]
        return row[f"{source_id_field[:-1]}_id"]

    @staticmethod
    def _event_date(row: dict[str, str]) -> date | None:
        value = row.get("close_date") or row.get("last_interaction_date")
        return date.fromisoformat(value) if value else None
