from pathlib import Path

from ....models import EvidenceItem


class PolicyEvidenceLoader:
    """Load the shared Deal Desk policy as standard evidence."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> list[EvidenceItem]:
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
