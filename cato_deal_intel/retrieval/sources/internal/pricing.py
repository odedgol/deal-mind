from ....models import EvidenceItem
from ..reader import TsvReader


class PricingEvidenceLoader:
    """Load pricing notes and apply their sensitivity classification."""

    def __init__(self, reader: TsvReader) -> None:
        self.reader = reader

    def load(self) -> list[EvidenceItem]:
        return [
            self._to_evidence(row)
            for row in self.reader.read("pricing/pricing_notes.tsv")
        ]

    def _to_evidence(self, row: dict[str, str]) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=f"pricing:{row['pricing_note_id']}",
            opportunity_id=row["opportunity_id"],
            source_type="pricing",
            source_file="synthetic_data/pricing/pricing_notes.tsv",
            source_id=row["pricing_note_id"],
            access_level="sensitive" if row["commercial_risk"] == "high" else "standard",
            text=row["pricing_notes"],
            metadata={"approval_status": row["approval_status"]},
        )
