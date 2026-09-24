import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .agents import (
    AgentContext,
    run_conversation_intelligence,
    run_deal_context,
    run_stakeholder_map,
    run_strategy,
)
from .authorization import authorize
from .data import SourceData
from .llm import LLMAdapter
from .models import (
    AgentOutput,
    AgentTrace,
    ApprovalRecord,
    AuthorizationDecision,
    Brief,
    EvidenceItem,
    Opportunity,
    PermissionProfile,
    RecommendedAction,
    StrategyOutput,
)
from .retrieval import EvidenceRetriever, RetrievalRequest
from .validation import validate_citations


def create_brief(
    *,
    root: Path,
    artifacts_root: Path,
    opportunity_id: str,
    user_id: str,
    llm: LLMAdapter,
    approval_decision: Literal["approved", "rejected", "pending"] = "pending",
) -> Brief:
    source = SourceData(root)
    opportunity = _find_opportunity(source.opportunities(), opportunity_id)
    requester = _find_requester(source.permissions(), user_id)
    decision = authorize(opportunity, requester)
    if not decision.allowed:
        raise PermissionError(decision.reason)
    retriever = EvidenceRetriever()
    retriever.index(source.evidence())
    evidence = retriever.retrieve(
        RetrievalRequest(
            query="buyer goals objections urgency stakeholders negotiation risks pricing legal",
            opportunity_id=opportunity_id,
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
        ),
        decision,
    )
    evidence = _include_generated_context(evidence, retriever, decision, opportunity_id)
    run_id = uuid.uuid4().hex
    context = AgentContext(opportunity=opportunity, evidence=evidence)
    traces: list[AgentTrace] = []
    deal_snapshot = run_deal_context(context)
    conversation = _traced_specialist(
        run_id,
        "Conversation Intelligence Agent",
        lambda: run_conversation_intelligence(context, llm),
        traces,
    )
    stakeholders = _traced_specialist(
        run_id, "Stakeholder Map Agent", lambda: run_stakeholder_map(context, llm), traces
    )
    strategy = _traced_strategy(run_id, context, [conversation, stakeholders], llm, traces)
    validate_citations([conversation, stakeholders, strategy], evidence)
    actions = _route_approval(opportunity, strategy.actions)
    approvals = _build_approvals(actions, approval_decision)
    brief = Brief(
        run_id=run_id,
        opportunity_id=opportunity_id,
        deal_snapshot=deal_snapshot,
        executive_summary=strategy.summary,
        buyer_goals=conversation.findings,
        stakeholder_map=stakeholders.findings,
        negotiation_state=conversation.findings,
        recommended_next_actions=actions,
        missing_information=conversation.missing_information + stakeholders.missing_information,
        source_evidence=evidence,
        confidence_and_review_warnings=strategy.warnings + _approval_warnings(approvals),
    )
    _save_run(
        artifacts_root,
        run_id,
        opportunity,
        decision,
        evidence,
        conversation,
        stakeholders,
        strategy,
        approvals,
        brief,
        traces,
    )
    return brief


def _find_opportunity(opportunities: list[Opportunity], opportunity_id: str) -> Opportunity:
    match = next((item for item in opportunities if item.opportunity_id == opportunity_id), None)
    if match is None:
        raise ValueError("Opportunity was not found.")
    return match


def _find_requester(requesters: list[PermissionProfile], user_id: str) -> PermissionProfile | None:
    return next((item for item in requesters if item.user_id == user_id), None)


def _include_generated_context(
    evidence: list[EvidenceItem],
    retriever: EvidenceRetriever,
    decision: AuthorizationDecision,
    opportunity_id: str,
) -> list[EvidenceItem]:
    if any(item.source_type == "slack" for item in evidence):
        return evidence
    updates = retriever.retrieve(
        RetrievalRequest(
            query="synthetic account team dashboard escalation conflict",
            opportunity_id=opportunity_id,
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
            limit=2,
        ),
        decision,
    )
    return evidence + [item for item in updates if item.source_type == "slack"]


def _traced_specialist(
    run_id: str,
    name: str,
    call: Callable[[], AgentOutput],
    traces: list[AgentTrace],
) -> AgentOutput:
    started = datetime.now(UTC)
    try:
        output = call()
    except Exception as error:
        traces.append(
            AgentTrace(
                run_id=run_id,
                agent_name=name,
                prompt_version="v1",
                status="failed",
                started_at=started,
                completed_at=datetime.now(UTC),
                error=str(error),
            )
        )
        raise
    traces.append(
        AgentTrace(
            run_id=run_id,
            agent_name=name,
            prompt_version="v1",
            status="completed",
            started_at=started,
            completed_at=datetime.now(UTC),
        )
    )
    return output


def _traced_strategy(
    run_id: str,
    context: AgentContext,
    outputs: list[AgentOutput],
    llm: LLMAdapter,
    traces: list[AgentTrace],
) -> StrategyOutput:
    started = datetime.now(UTC)
    try:
        output = run_strategy(context, outputs, llm)
    except Exception as error:
        traces.append(
            AgentTrace(
                run_id=run_id,
                agent_name="Negotiation Strategy Agent",
                prompt_version="v1",
                status="failed",
                started_at=started,
                completed_at=datetime.now(UTC),
                error=str(error),
            )
        )
        raise
    traces.append(
        AgentTrace(
            run_id=run_id,
            agent_name="Negotiation Strategy Agent",
            prompt_version="v1",
            status="completed",
            started_at=started,
            completed_at=datetime.now(UTC),
        )
    )
    return output


def _route_approval(
    opportunity: Opportunity, actions: list[RecommendedAction]
) -> list[RecommendedAction]:
    if not opportunity.approval_required:
        return actions
    return [action.model_copy(update={"requires_approval": True}) for action in actions]


def _build_approvals(
    actions: list[RecommendedAction],
    decision: Literal["approved", "rejected", "pending"],
) -> list[ApprovalRecord]:
    now = datetime.now(UTC)
    return [
        ApprovalRecord(
            recommendation=action.action,
            reason="Sensitive opportunity recommendation requires human review.",
            decision=decision if action.requires_approval else "approved",
            timestamp=now,
        )
        for action in actions
        if action.requires_approval
    ]


def _approval_warnings(approvals: list[ApprovalRecord]) -> list[str]:
    return [
        f"Approval required: {approval.recommendation}"
        for approval in approvals
        if approval.decision == "pending"
    ]


def _save_run(
    root: Path,
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
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    values = {
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
    for filename, value in values.items():
        (run_dir / filename).write_text(json.dumps(_json(value), indent=2) + "\n", encoding="utf-8")
    (run_dir / "brief.md").write_text(_markdown(brief), encoding="utf-8")


def _json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    return value


def _markdown(brief: Brief) -> str:
    lines = [f"# Strategic Deal Intelligence Brief — {brief.opportunity_id}", ""]
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
    for title, content in sections.items():
        lines.extend([f"## {title}", ""])
        lines.extend(f"- {item}" for item in content)
        lines.append("")
    return "\n".join(lines)
