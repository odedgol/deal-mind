# Architecture Overview

## Logical view

The workflow is a LangGraph state machine. Authorization is the first gate, the two
evidence-driven specialist agents run in parallel, and the Negotiation Strategy Agent waits
for both specialist outputs.

```mermaid
flowchart TD
    CLI[Typer CLI request]
    AUTH[Authorization node<br/>deterministic permission decision]
    DENY[Safe denial<br/>generic response and END]
    RETRIEVE[Retrieval node<br/>Qdrant metadata filters]
    RAG[RAG layer<br/>BM25 + dense embeddings + RRF]
    CONTEXT[Deal Context Agent<br/>deterministic CRM snapshot]
    CONVERSATION[Conversation Intelligence Agent<br/>Gong + Slack findings]
    STAKEHOLDERS[Stakeholder Map Agent<br/>contacts + stakeholder signals]
    STRATEGY[Negotiation Strategy Agent<br/>synthesis and recommendations]
    VALIDATE[Citation and permission validation]
    APPROVAL[Human-in-the-loop approval node<br/>pending / approved / rejected]
    BRIEF[Brief builder<br/>nine required sections]
    PERSIST[Artifact persistence]
    OUTPUT[JSON + Markdown brief<br/>approval + trace artifacts]
    STATE[(DealState<br/>evidence, agent outputs,<br/>approvals, traces, run_id)]
    OBS[Structured logs and trace events]

    CLI --> AUTH
    AUTH -->|denied| DENY
    AUTH -->|authorized| RETRIEVE
    RETRIEVE --> RAG
    RAG --> CONTEXT
    CONTEXT --> CONVERSATION
    CONTEXT --> STAKEHOLDERS
    CONVERSATION --> STRATEGY
    STAKEHOLDERS --> STRATEGY
    STRATEGY --> VALIDATE
    VALIDATE --> APPROVAL
    APPROVAL --> BRIEF
    BRIEF --> PERSIST
    PERSIST --> OUTPUT

    STATE -. shared LangGraph state .-> RETRIEVE
    STATE -. shared LangGraph state .-> CONVERSATION
    STATE -. shared LangGraph state .-> STAKEHOLDERS
    STATE -. shared LangGraph state .-> STRATEGY
    STATE -. shared LangGraph state .-> APPROVAL
    STATE -. shared LangGraph state .-> PERSIST

    AUTH -. guardrail .-> DENY
    RETRIEVE -. permission filters .-> RAG
    VALIDATE -. unsupported citation guardrail .-> STRATEGY
    APPROVAL -. sensitive recommendation guardrail .-> BRIEF
    CLI -. annotated lifecycle events .-> OBS
    RETRIEVE -. retrieval events .-> OBS
    APPROVAL -. approval events .-> OBS
    STRATEGY -. recommendation events .-> OBS
```

### Logical responsibilities

- `authorize` decides access deterministically. An unauthorized request does not reach RAG or
  any agent.
- `retrieve` applies opportunity, source type, and access level filters before ranking.
- The RAG layer combines BM25 lexical ranking and dense semantic ranking with Reciprocal Rank
  Fusion (RRF).
- `Deal Context Agent` creates a deterministic canonical snapshot. The Conversation and
  Stakeholder agents run concurrently.
- `Negotiation Strategy Agent` synthesizes specialist outputs and policy evidence.
- Citation validation rejects evidence IDs outside the authorized evidence context.
- Approval routing marks pricing, legal, customer-facing, and low-confidence recommendations
  for human review.
- Every agent, retrieval, tool, approval, and recommendation event is written to the trace
  collector and persisted with the run.

## Deployment view

The MVP runs locally through the CLI or the FastAPI service, with the React UI as a thin
presentation layer. Qdrant runs in local persistent mode on disk; it is not a separate service.
The API reuses one local client and serializes requests because file-backed Qdrant storage does
not support multiple clients or processes opening the same folder concurrently. OpenAI is the
external model gateway for chat completions and embeddings.

```mermaid
flowchart LR
    USER[Sales user / reviewer]
    CLI[Terminal<br/>deal-intel CLI]
    WEB[React UI<br/>Vite + Tailwind]
    ENV[.env<br/>API key + model + paths]
    APP[Python application process<br/>Typer + LangGraph + agents + tools]
    MODEL[OpenAI model gateway<br/>chat completions + embeddings]
    QDRANT[(Local persistent Qdrant<br/>artifacts/qdrant)]
    SOURCES[(Synthetic source files<br/>synthetic_data/)]
    RUNS[(Run artifacts<br/>artifacts/runs/<run_id>)]
    LOGS[Structured logs<br/>stdout / log collector]
    MONITOR[Monitoring target<br/>MVP logs and traces<br/>production: Langfuse/OTel]

    USER --> CLI
    USER --> WEB
    ENV -. loaded at startup .-> APP
    CLI --> APP
    WEB -->|HTTP /brief| APP
    SOURCES -->|ingest once or after source changes| QDRANT
    APP -->|authorized retrieval| QDRANT
    APP -->|LLM and embedding requests| MODEL
    APP -->|JSON, Markdown, approval, trace| RUNS
    APP --> LOGS
    LOGS --> MONITOR
```

### Deployment responsibilities

- `uv run deal-intel ingest` reads source files and rebuilds the persistent local Qdrant index.
- `brief` and `search` read the existing index; they do not index source files.
- `.env` holds local configuration and secrets. It is ignored by Git; `.env.example` documents
  the required variables.
- LLM and embedding calls use configured timeout and targeted transient-error retries.
- The MVP monitoring surface is structured logs and persisted `trace.json`. A production
  deployment would add centralized metrics, alerting, distributed tracing, secret management,
  high availability, and durable external storage.
- Real Salesforce, Gong, Slack, or CRM writes are outside the MVP. Any future write-capable tool
  must add an idempotency contract before production use.

### Production scaling boundary

The local file-backed Qdrant client is intentionally an MVP choice. It is suitable for one local
API process, but it must not be shared by multiple API workers, containers, or a CLI and API at
the same time. Production replaces it with a managed or clustered Qdrant deployment (or
OpenSearch), configured through a service URL. Each stateless API worker can then use its own
client connection while the database service coordinates concurrent access.

Other production boundaries are documented in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md),
including API authentication, durable approval state, asynchronous job execution, atomic index
replacement, artifact storage, secrets management, model budgets, and centralized observability.
