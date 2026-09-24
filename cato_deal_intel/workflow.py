import uuid
from pathlib import Path
from typing import Literal

from .agent_runner import AgentRunner
from .agents import AgentContext
from .artifact_store import ArtifactStore
from .data import SourceData
from .llm import LLMAdapter
from .models import Brief, EvidenceItem
from .retrieval import EvidenceRetriever
from .services import ApprovalService, DealService, EvidenceService, build_brief
from .tools import (
    ApprovalRequestTool,
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    DealDeskPolicyTool,
    RecommendationValidationTool,
)
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
    """Run the application flow from authorization to persisted brief."""
    source = SourceData(root)
    opportunity, decision = DealService(source).authorize(opportunity_id, user_id)
    evidence_service = EvidenceService(source, EvidenceRetriever())
    evidence = evidence_service.retrieve(opportunity_id, decision)
    run_id = uuid.uuid4().hex
    conversation_search_tool = AuthorizedEvidenceSearchTool(evidence_service, decision)
    stakeholder_search_tool = AuthorizedEvidenceSearchTool(evidence_service, decision)
    policy_tool = DealDeskPolicyTool(evidence_service, decision)
    agent_run = AgentRunner(
        llm,
        deal_context_tool=DealContextTool(opportunity),
        conversation_search_tool=conversation_search_tool,
        stakeholder_search_tool=stakeholder_search_tool,
        recommendation_validator=RecommendationValidationTool(),
        policy_tool=policy_tool,
        approval_tool=ApprovalRequestTool(ApprovalService()),
    ).run(AgentContext(opportunity, evidence), run_id)
    evidence = _merge_evidence(
        evidence,
        [
            *conversation_search_tool.retrieved_evidence,
            *stakeholder_search_tool.retrieved_evidence,
            *policy_tool.retrieved_evidence,
        ],
    )
    validate_citations(
        [agent_run.conversation, agent_run.stakeholders, agent_run.strategy],
        evidence,
    )
    actions, approvals = ApprovalService().prepare(
        opportunity,
        agent_run.strategy.actions,
        approval_decision,
    )
    brief = build_brief(
        run_id=run_id,
        opportunity=opportunity,
        evidence=evidence,
        deal_snapshot=agent_run.deal_snapshot,
        conversation=agent_run.conversation,
        stakeholders=agent_run.stakeholders,
        strategy=agent_run.strategy,
        actions=actions,
        approvals=approvals,
    )
    ArtifactStore(artifacts_root).save_run(
        run_id=run_id,
        opportunity=opportunity,
        decision=decision,
        evidence=evidence,
        conversation=agent_run.conversation,
        stakeholders=agent_run.stakeholders,
        strategy=agent_run.strategy,
        approvals=approvals,
        brief=brief,
        traces=agent_run.traces,
    )
    return brief


def _merge_evidence(
    primary: list[EvidenceItem], additional: list[EvidenceItem]
) -> list[EvidenceItem]:
    merged = {item.evidence_id: item for item in primary}
    merged.update({item.evidence_id: item for item in additional})
    return list(merged.values())
