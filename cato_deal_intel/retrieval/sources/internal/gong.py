from datetime import date
from pathlib import Path

from ....models import EvidenceItem
from ..reader import TsvReader


class GongEvidenceLoader:
    """Load Gong call summaries and transcript files as evidence."""

    def __init__(
        self,
        root: Path,
        reader: TsvReader,
        account_by_opportunity: dict[str, str],
    ) -> None:
        self.root = root
        self.reader = reader
        self.account_by_opportunity = account_by_opportunity

    def load(self) -> list[EvidenceItem]:
        return self._summary_evidence() + self._transcript_evidence()

    def _summary_evidence(self) -> list[EvidenceItem]:
        rows = self.reader.read("gong/gong_call_summaries.tsv")
        return [
            EvidenceItem(
                evidence_id=f"gong:summary:{row['call_id']}",
                opportunity_id=row["opportunity_id"],
                account_id=row["account_id"],
                source_type="gong",
                source_file="synthetic_data/gong/gong_call_summaries.tsv",
                source_id=row["call_id"],
                access_level=row["source_access_level"],
                event_date=date.fromisoformat(row["call_date"]),
                text=f"{row['summary']} {row['key_points']} Risks: {row['risks']}",
                metadata={"title": row["title"], "participants": row["participants"]},
            )
            for row in rows
        ]

    def _transcript_evidence(self) -> list[EvidenceItem]:
        transcripts = sorted((self.root / "gong/transcripts").glob("*.md"))
        return [self._transcript_to_evidence(transcript) for transcript in transcripts]

    def _transcript_to_evidence(self, transcript: Path) -> EvidenceItem:
        opportunity_id, call_id = transcript.stem.split("_", maxsplit=1)
        return EvidenceItem(
            evidence_id=f"gong:transcript:{call_id}",
            opportunity_id=opportunity_id,
            account_id=self.account_by_opportunity[opportunity_id],
            source_type="gong",
            source_file=f"synthetic_data/gong/transcripts/{transcript.name}",
            source_id=call_id,
            access_level="standard",
            text=transcript.read_text(encoding="utf-8"),
        )
