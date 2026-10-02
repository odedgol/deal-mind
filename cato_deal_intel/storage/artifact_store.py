import json
from pathlib import Path
from typing import Any

from ..models import (
    AgentOutput,
    AgentTrace,
    ApprovalRecord,
    AuthorizationDecision,
    Brief,
    EvidenceItem,
    Opportunity,
    StrategyOutput,
)


class ArtifactStore:
    """Persists one complete, inspectable run."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def find_brief(self, run_id: str) -> Brief | None:
        path = self.root / run_id / "brief.json"
        if not path.exists():
            return None
        return Brief.model_validate_json(path.read_text(encoding="utf-8"))

    def save_run(
        self,
        *,
        run_id: str,
        requester_user_id: str,
        opportunity: Opportunity,
        decision: AuthorizationDecision,
        evidence: list[EvidenceItem],
        conversation: AgentOutput,
        stakeholders: AgentOutput,
        strategy: StrategyOutput,
        approvals: list[ApprovalRecord],
        brief: Brief,
        traces: list[AgentTrace],
    ) -> None:
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "request.json": {
                "run_id": run_id,
                "opportunity_id": opportunity.opportunity_id,
                "user_id": requester_user_id,
            },
            "authorization.json": decision,
            "retrieved_evidence.json": evidence,
            "agent_outputs.json": {
                "conversation": conversation,
                "stakeholders": stakeholders,
                "strategy": strategy,
            },
            "approval.json": approvals,
            "brief.json": brief,
            "trace.json": traces,
        }
        for filename, value in files.items():
            path = run_dir / filename
            path.write_text(json.dumps(_to_json(value), indent=2) + "\n", encoding="utf-8")
        (run_dir / "brief.md").write_text(_to_markdown(brief), encoding="utf-8")

    def save_failure_trace(
        self,
        *,
        run_id: str,
        opportunity_id: str,
        user_id: str,
        traces: list[AgentTrace],
        error: Exception,
    ) -> None:
        """Persist only safe diagnostics when an agent run fails."""
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        files = {
            "request.json": {
                "run_id": run_id,
                "opportunity_id": opportunity_id,
                "user_id": user_id,
            },
            "trace.json": traces,
            "error.json": {"error_type": type(error).__name__},
        }
        for filename, value in files.items():
            (run_dir / filename).write_text(
                json.dumps(_to_json(value), indent=2) + "\n", encoding="utf-8"
            )


def _to_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    return value


def _to_markdown(brief: Brief) -> str:
    sections = {
        "Deal Snapshot": [brief.deal_snapshot.model_dump_json(indent=2)],
        "Executive Summary": [
            _with_evidence(brief.executive_summary, brief.executive_summary_evidence_ids)
        ],
        "Buyer Goals and Business Drivers": [
            _with_evidence(item.text, item.evidence_ids) for item in brief.buyer_goals
        ],
        "Stakeholder Map": [
            _with_evidence(item.text, item.evidence_ids) for item in brief.stakeholder_map
        ],
        "Negotiation State": [
            _with_evidence(item.text, item.evidence_ids) for item in brief.negotiation_state
        ],
        "Recommended Next Actions": [
            _with_evidence(item.action, item.evidence_ids)
            for item in brief.recommended_next_actions
        ],
        "Missing Information": brief.missing_information,
        "Source Evidence": [
            f"{item.evidence_id}: {item.source_file} ({item.source_id})"
            for item in brief.source_evidence
        ],
        "Confidence and Review Warnings": brief.confidence_and_review_warnings or ["None."],
    }
    lines = [
        f"# Strategic Deal Intelligence Brief — {brief.opportunity_id}",
        "",
        f"**Workflow status:** {brief.run_status}",
        "",
    ]
    for title, content in sections.items():
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {item}" for item in content)
        lines.append("")
    return "\n".join(lines)


def _with_evidence(text: str, evidence_ids: list[str]) -> str:
    if not evidence_ids:
        return text
    citations = ", ".join(evidence_ids)
    return f"{text} [Evidence: {citations}]"
