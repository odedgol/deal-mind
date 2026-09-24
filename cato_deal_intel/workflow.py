import uuid
from pathlib import Path
from typing import Literal

from .agent_runner import AgentRunner
from .agents import AgentContext
from .artifact_store import ArtifactStore
from .data import SourceData
from .llm import LLMAdapter
from .models import Brief
from .retrieval import EvidenceRetriever
from .services import ApprovalService, DealService, EvidenceService, build_brief
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
    evidence = EvidenceService(source, EvidenceRetriever()).retrieve(opportunity_id, decision)
    run_id = uuid.uuid4().hex
    agent_run = AgentRunner(llm).run(AgentContext(opportunity, evidence), run_id)
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
