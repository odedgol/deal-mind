import json
from pathlib import Path
from typing import Any

from .models import (
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

    def save_run(
        self,
        *,
        run_id: str,
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
            "request.json": {"run_id": run_id, "opportunity_id": opportunity.opportunity_id},
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
        "Executive Summary": [brief.executive_summary],
        "Buyer Goals and Business Drivers": [item.text for item in brief.buyer_goals],
        "Stakeholder Map": [item.text for item in brief.stakeholder_map],
        "Negotiation State": [item.text for item in brief.negotiation_state],
        "Recommended Next Actions": [item.action for item in brief.recommended_next_actions],
        "Missing Information": brief.missing_information,
        "Source Evidence": [
            f"{item.evidence_id}: {item.source_file} ({item.source_id})"
            for item in brief.source_evidence
        ],
        "Confidence and Review Warnings": brief.confidence_and_review_warnings,
    }
    lines = [f"# Strategic Deal Intelligence Brief — {brief.opportunity_id}", ""]
    for title, content in sections.items():
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {item}" for item in content)
        lines.append("")
    return "\n".join(lines)
