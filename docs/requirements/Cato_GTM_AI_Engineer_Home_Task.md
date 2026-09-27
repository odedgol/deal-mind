# Agentic AI Engineer - Home Task

_Strategic Deal Intelligence Assistant - Cato Networks Candidate Assignment Brief_

> Up-to-date versions of this document and the synthetic data files are available at [danaabramov/Cato-IS-AI-Engineer-Exam](https://github.com/danaabramov/Cato-IS-AI-Engineer-Exam).

## 1. Business Story

Cato wants to build a set of agents that support the Sales team during strategic customer negotiations. The assistant will help the account owner understand the current state of the deal before a negotiation meeting.

Important context is fragmented across systems such as Salesforce, Gong calls, Slack discussions, pricing notes, Deal Desk policy, and the account team's memory.

Your task is to build an agentic deal intelligence assistant for negotiation preparation. Humans remain in the loop: Sales leaders, Deal Desk, and the account owner must approve sensitive recommendations before they are used in any customer-facing action.

The goal is not to automatically win a deal or replace sellers. The goal is to demonstrate that an agentic AI system can turn messy GTM data into a grounded, observable, and auditable Strategic Deal Intelligence Brief, supported by production-minded engineering.

## 2. Assignment Objective

Build a multi-agent system that creates a Strategic Deal Intelligence Brief for a strategic sales opportunity.

The system should accept an opportunity ID and a requesting user identity or role, retrieve the relevant allowed evidence, and generate a brief that helps the account owner prepare for a negotiation meeting.

The goal is to demonstrate strong engineering judgment for agentic AI systems: grounding, permissions, human approval, observability, state management, cost awareness, and production-readiness thinking.

## 3. Provided Data

Use the provided synthetic dataset as the base source material:

- `synthetic_data/salesforce/accounts.tsv`
- `synthetic_data/salesforce/opportunities.tsv`
- `synthetic_data/salesforce/contacts.tsv`
- `synthetic_data/gong/gong_call_summaries.tsv`
- `synthetic_data/gong/transcripts/*.md`
- `synthetic_data/pricing/pricing_notes.tsv`
- `synthetic_data/policies/access_permissions.tsv`
- `synthetic_data/policies/deal_desk_policy.md`

The synthetic dates are scenario dates in the recent past. Preserve their chronology when generating additional data or demo artifacts.

The dataset includes three canonical opportunities:

- `OPP-1001`: standard but complex late-stage enterprise renewal.
- `OPP-1002`: technical proof and expansion opportunity with product validation friction.
- `OPP-1003`: restricted high-risk negotiation with approval-sensitive commercial and legal constraints.

### Mandatory Data-Generation Subtask

Generate a small synthetic Slack-style account-team update dataset for the provided opportunities, and ingest it as an additional evidence source.

The generated updates must:

- Be clearly synthetic.
- Avoid real names, real customer names, real emails, real phone numbers, or any sensitive information.
- Add useful account-team context that is not fully duplicated from the provided Salesforce, Gong, pricing, or policy files.
- Include at least two generated updates per opportunity.
- Across the generated updates, include at least one update that reinforces a known fact, one that adds missing context, and one that introduces ambiguity or a possible conflict the system must handle.
- Be stored in a simple, documented format that your prototype can ingest.
- Be permissioned as source type `slack`. The provided `access_permissions.tsv` includes `slack` in `allowed_source_types` for users who may retrieve generated account-team updates.

## 4. System Requirements

The prototype must:

- Support all three provided opportunities.
- Use the provided Salesforce opportunity, account, and contact data.
- Use the provided Gong call summaries and transcript snippets.
- Use the provided pricing notes, access permissions, and Deal Desk policy.
- Use the candidate-generated Slack-style updates as an additional source.
- Use a multi-agent design with at least three specialized agents. See section 5 below.
- Use actual LLM-backed agents for synthesis, extraction, and generation work. An offline-only deterministic implementation is not sufficient for this exam.
- Run the system with live LLM calls to generate the briefs, approval outputs, traces, and other generated artifacts included in the submission.
- Include a deterministic harness around the LLM agents: typed contracts, deterministic parsing and tool execution where appropriate, validation rules, permission and guardrail checks, replayable traces, and enough tests or fixtures to evaluate behavior consistently across runs.
- Ground important claims in retrieved evidence and include source citations. Do not hallucinate numbers, dates, customers, competitors, stakeholders, discounts, or quotes.
- Use a consistent citation format that identifies the source file and stable source ID when available, such as `source=synthetic_data/gong/gong_call_summaries.tsv, call_id=CALL-008`.
- Enforce permissions before retrieval and before generation. A user must not receive a summary, citation, inferred fact, or metadata from sources they are not allowed to access.
- Internal authorization lookups needed to map an opportunity to its account, requester, and permission profile do not count as evidence retrieval. These lookups may happen before retrieval so the system can decide whether to proceed, but denied outputs and traces must still avoid revealing unauthorized account/source details.
- Treat source access and sensitivity as intentionally distributed across the dataset. Gong and generated Slack rows include `source_access_level`, while pricing notes must be evaluated together with opportunity restrictions and Deal Desk policy. Do not assume every sensitive pricing signal is contained in a single column.
- Route high-impact recommendations through a human-in-the-loop approval flow. Examples include pricing, concessions, legal terms, customer-facing language, and low-confidence strategic recommendations.
- Be observable: every agent invocation, retrieval, tool call, approval, and generated recommendation should leave a trace.
- Persist state across runs, including enough information to recover or inspect generated briefs, approvals, and traces.

The generated brief must include these sections:

- Deal Snapshot
- Executive Summary
- Buyer Goals and Business Drivers
- Stakeholder Map
- Negotiation State
- Recommended Next Actions
- Missing Information
- Source Evidence
- Confidence and Review Warnings

## 5. Suggested Agent Design

How you address the business need is your call. You may choose a different agent design if you can defend it. One reasonable design is:

| Agent | Core responsibility | Example inputs | Example outputs |
| --- | --- | --- | --- |
| Negotiation Strategy Agent | Main agent. Synthesizes facts and signals into recommended internal next actions. | Outputs from other agents. | Prioritized next actions with owners and rationale. |
| Deal Context Agent | Subagent. Loads deterministic CRM and account data. | Opportunity, account, stage, amount, close date, owner. | Canonical deal snapshot with source IDs. |
| Conversation Intelligence Agent | Subagent. Extracts buyer interests, objections, urgency, competitors, and action items from calls and generated account-team updates. | Gong call summaries, Gong transcripts, generated Slack-style updates. | Evidence-backed findings and uncertainty labels. |
| Stakeholder Map Agent | Subagent. Builds a buying committee view and identifies missing stakeholders. | Contacts, call speakers, notes. | Economic buyer, champion, blockers, procurement, unknowns. |

Each agent must have a clear contract: typed inputs, typed outputs, defined tools, expected failure modes, and validation rules. Choose and justify an orchestration pattern, such as a graph workflow, durable workflow engine, state machine, or managed agent runtime. Be explicit about how state flows between agents and how the system behaves under partial failure.

For the purpose of this exam, "agent" means an LLM-backed component with a defined role, prompt/context contract, tool access, validation rules, and observable invocation trace. The surrounding harness should make agent inputs, outputs, retrieval results, approvals, and safety decisions inspectable and reproducible enough for review. You may use the same underlying model for multiple agents if their responsibilities and contracts are distinct.

## 6. Implementation Scope

Build a runnable prototype. It may be a CLI, API service, lightweight web app, or Slack-style simulator. Real Cato integrations are not required, but the design must show a clear path to production.

You do not need to build real integrations with Salesforce, Gong, Slack, or Cato systems. Use local files, mocked tools, or lightweight services as needed, but make the production path clear.

You do not need to provide Cato with your personal or company LLM API key. Document how reviewers can configure and run the system themselves, including supported model providers or models, required environment variables, API-key configuration, and any relevant inference parameters. Ability to run the whole system without LLM access is a non-goal.

For the submitted artifacts, run the prototype against a real LLM provider and include outputs produced by that run. For the interview, be prepared to run a live demo that also makes live LLM calls rather than replaying only precomputed or mocked responses.

## 7. Engineering Expectations

Your prototype should include a practical, lightweight implementation for each area below, and your documentation should explain what would need to change for a production deployment.

- A real functioning RAG or retrieval layer over the provided and generated data. The dataset is small, so this can be a lightweight local implementation or open-source component, but it should perform actual indexing/retrieval with metadata filtering and return evidence used by the agents.
- Permission checks before retrieval and generation.
- Human-in-the-loop approval simulation for sensitive recommendations.
- Logs or traces for agent invocations, retrievals, approvals, and generated recommendations.
- Guardrails for restricted data, unsupported claims, and unsafe customer-facing language.
- Cost and token management strategy.
- Basic failure handling for missing data, denied access, malformed inputs, and partial agent failure.
- Clear contracts for agents, tools, state, and output format.

In your technical overview, briefly explain the additional work required for production deployment, including scalability, high availability, monitoring, secrets management, and operational support.

## 8. Required Demo Scenarios

- Generate a brief for `OPP-1001` or `OPP-1002` as an authorized user. For example, `USR-5001` owns `OPP-1001`, and `USR-5002` owns `OPP-1002`.
- Generate a brief for `OPP-1003` as an authorized user and show approval routing for sensitive pricing, legal terms, or customer-facing recommendation language.
- Attempt to access `OPP-1003` as an unauthorized or insufficiently privileged user and show that restricted sources are not retrieved, summarized, cited, or leaked.
- Show how the generated Slack-style updates affect the brief, including at least one cited generated update.

## 9. Deliverables

A. Runnable prototype: CLI, API service, lightweight web app, or Slack-style simulator.

B. Architecture diagrams: logical view showing agents, orchestration, RAG, state, human-in-the-loop approval, guardrails, observability, and output channels; deployment view showing services, storage, secrets, model gateway, and monitoring. Diagram format is not important.

C. Documentation: README, technical overview, and security notes. Include a short explanation of permission enforcement, state persistence, and how the generated Slack-style updates are produced and ingested.

D. Sample run artifacts: generated briefs, generated Slack-style update data, approval-flow output, and trace or log examples.

E. Interview presentation: 15-minute walkthrough that explains the business value, design choices, live demo, evaluation results, and what would break in production.

## 10. Bonus

- Advanced RAG with hybrid search, metadata filtering, recency weighting, source reliability scoring, and citation validation.
- Cost-aware model routing and token budgeting.
- Documented prompt-injection test cases and defenses.
- Synthetic evaluation data generation with golden labels and regression tests.

---

_Cato Networks - Candidate Assignment - Internal use_
