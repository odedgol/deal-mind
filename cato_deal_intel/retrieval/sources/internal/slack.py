from datetime import date

from ....models import EvidenceItem
from ..reader import TsvReader


class SlackEvidenceLoader:
    """Load synthetic account-team updates as permissioned evidence."""

    def __init__(self, reader: TsvReader) -> None:
        self.reader = reader

    def load(self) -> list[EvidenceItem]:
        rows = self.reader.read("slack/account_team_updates.tsv")
        return [self._to_evidence(row) for row in rows]

    def _to_evidence(self, row: dict[str, str]) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=f"slack:{row['update_id']}",
            opportunity_id=row["opportunity_id"],
            account_id=row["account_id"],
            source_type="slack",
            source_file="synthetic_data/slack/account_team_updates.tsv",
            source_id=row["update_id"],
            access_level=row["source_access_level"],
            event_date=date.fromisoformat(row["update_date"]),
            text=row["update_text"],
            metadata={
                "synthetic_notice": row["synthetic_notice"],
                "channel": row["channel"],
            },
        )
