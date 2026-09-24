# Production Readiness Notes

## Current MVP behavior

The MVP workflow is read-only with respect to external business systems:

- Qdrant is used for local evidence indexing and retrieval.
- The LLM produces structured recommendations but does not write to a system of record.
- Approval records are saved as local run artifacts.
- Retries are safe for transient read-only calls when they do not repeat an external write.

The local Qdrant client is shared and requests are serialized inside the API process. This is
required because Qdrant's file-backed local mode locks its storage directory. It is not a
production scaling strategy: multiple API workers must use a Qdrant server or managed Qdrant
instance instead.

## Implemented issue and solution register

This register records the implementation problems found during the MVP and the decision made
for each one. It is the handoff checklist for the manual rewrite.

| Problem or symptom | Root cause | Implemented solution | Verification |
| --- | --- | --- | --- |
| A second request could fail with “storage folder is already accessed” | Each process or flow opened a file-backed Qdrant client independently | `QdrantClientFactory` owns one client per application component; the API reuses it and serializes requests | `tests/test_client_factory.py`, API reuse test |
| Restricted Slack evidence was missing for an authorized restricted deal | Authorization allowed `standard` and `sensitive`, but omitted `restricted` | `can_view_restricted_account` now adds the `restricted` metadata filter | Retrieval test and authorized `OPP-1003` golden case |
| Unauthorized requests appeared to have no run artifact | Authorization correctly stops the graph before retrieval | Denial is returned safely and no run is persisted because no process started | Unauthorized golden case and workflow tests |
| Failed runs had no useful trace | Exceptions could bypass normal completion persistence | The traced operation records `status=failed`; the workflow persists the failure trace with the error type | `test_failed_agent_persists_failed_trace` |
| Logs could expose prompts or business data | Full input/output logging is useful for debugging but unsafe by default | Annotation-based observability is controlled by `CATO_OBSERVABILITY`; metadata is the default and full I/O is opt-in with `CATO_OBSERVABILITY_IO=full` | Observability tests and `.env.example` |
| Prompt injection could be mistaken for business instructions | Retrieved evidence is untrusted content | Prompts use `<untrusted_data>` boundaries, explicit system instructions, typed output validation, and citation validation | `tests/test_prompt_injection.py` |
| Same request can use different token counts | Live model calls are not deterministic at the token level, even with `temperature=0`; no response cache is part of the MVP | Cost is measured from provider usage per call; exact replay requires a future response cache or recorded replay fixture | LLM cost tests and persisted usage summaries |
| Budget reset after a server restart | In-memory usage is process-local | A file-backed `BudgetLedger` persists period spend; production must replace it with shared durable accounting | `test_budget_ledger_survives_new_controller` |
| Human approval could be unclear in CLI, API, and React | Interfaces have different interaction models | CLI asks interactively, API accepts an explicit decision, and React displays a pending approval panel; production needs durable pause/resume state | Workflow, API, and frontend tests |
| Retrieval could miss exact terms or paraphrases | BM25 and dense search each have blind spots | Hybrid BM25 + dense retrieval with RRF, metadata filters, recency weighting, and source reliability scoring | Retrieval tests and documented retrieval approach |
| Improvements could regress behavior silently | No deterministic acceptance set existed | Four synthetic golden cases check status, approval routing, source coverage, and grounded citations | `evals/golden_set.json`, `uv run deal-intel evaluate` returns `4/4` |
| Local MVP assumptions do not survive deployment | Filesystem, process-local state, and caller-supplied identity are not shared or trusted at scale | Production replacements are documented in the migration table below: authenticated identity, managed Qdrant, durable artifacts/state, centralized observability, secret manager, and model gateway | Architecture review and production checklist |

The register distinguishes implemented MVP behavior from production work that is intentionally not
hidden: the local solution is testable and runnable, while the production replacement is named
explicitly wherever the local assumption would break.

## Retrieval approach

There are three practical retrieval approaches:

1. Lexical retrieval, such as BM25, which is strong for exact terms, IDs, numbers, names,
   and legal or pricing language.
2. Dense semantic retrieval, which is strong for paraphrases and natural-language intent.
3. Hybrid retrieval, which runs both channels and combines their rankings.

This prototype chooses hybrid retrieval. Metadata authorization filters are applied before
ranking, BM25 provides the lexical ranking, dense embeddings provide the semantic ranking,
and Reciprocal Rank Fusion (RRF) combines both rankings. The final score applies exponential
recency decay with a 180-day half-life and a source reliability policy: policies 0.98,
Salesforce 0.95, pricing 0.92, Gong 0.85, and Slack 0.72. A valid `source_reliability` metadata
value can override the default for a source. The agents receive only the final authorized
results; they do not choose which security filter to apply.

## Cost-aware model routing

OpenAI calls use separate configuration points for specialist and strategy work. The specialist
default can remain inexpensive while the strategy model can be upgraded independently. Each
response's prompt and completion token counts are converted to cost using configurable per-million
token rates, accumulated for the adapter's run, and rejected after the configured budget is
exceeded. Usage is written to structured logs without logging prompts or completions.

The MVP also persists the current period's spend in `CATO_LLM_BUDGET_LEDGER_PATH` (monthly by
default), so a server restart does not reset the remaining budget. The summary distinguishes
the current run's spend from the period spend. In production this JSON ledger must be replaced
with an atomic, shared usage database or provider billing service.

The local defaults live in `.env.example`; pricing values must be reviewed whenever the provider
pricing changes. A production model gateway should own the authoritative price table, quotas,
budgets, fallback policy, and cross-worker accounting.

## Prompt-injection defense

Retrieved evidence and specialist outputs are untrusted business data. The prompt boundary marks
them with `<untrusted_data>` delimiters and the system instruction explicitly says never to follow
instructions found inside that content. Structured output validation and citation validation remain
independent guardrails: a model cannot authorize itself, cite an unavailable evidence ID, or turn
source text into a tool instruction.

The regression fixture in `tests/test_prompt_injection.py` covers a malicious evidence sentence
that asks the model to reveal system instructions. Production should extend this fixture set with
tool-use requests, permission-bypass attempts, secret extraction, indirect instructions in Slack
messages, and multilingual variants.

This is a meaningful defense layer, but it is not a complete security boundary. Production must
also add tool sandboxing, authorization enforced in application code, secret filtering, and
additional red-team tests. The system prompt must never be treated as a replacement for these
controls.

## Idempotency preparation

An idempotency key is not required for the current MVP because the workflow does not perform
external writes. The existing `run_id` should be preserved as the root correlation identifier.

Before production writes are added, every write-capable tool must define an idempotency contract.
This applies to actions such as:

- Creating or updating a CRM record.
- Creating an approval request in an external service.
- Sending a customer or internal message.
- Creating a ticket or task.

The recommended key format is:

```text
<run_id>:<agent_name>:<action_name>
```

The receiving service must persist the key and return the original result when the same key is
retried. A retry must not create a second business side effect.

## Production checklist

- Add an idempotency key to every write-capable tool input.
- Persist idempotency results in the receiving service or a durable store.
- Include the key and attempt number in the trace.
- Retry only transient failures such as timeouts, connection errors, rate limits, and temporary
  server errors.
- Do not retry authorization failures, validation failures, or confirmed business rejections.
- Replace file-backed Qdrant with a server or managed deployment before running multiple workers.
- Move run artifacts from the local filesystem to durable shared storage.

## What changes at production scale

The prototype is intentionally runnable on one laptop. The following boundaries are explicit so
that the local implementation is not mistaken for a production deployment:

| MVP behavior | What breaks in production | Production replacement |
| --- | --- | --- |
| User sends `user_id` in the request | A caller can impersonate another user | Authenticate at the API edge and derive identity from a verified session or token; keep authorization in the workflow |
| Local permission files | Permissions become stale or differ between workers | Use a governed CRM/authorization service or replicated policy store with cache invalidation |
| One local Qdrant client and file storage | Multiple workers cannot share the folder | Managed/clustered Qdrant or OpenSearch behind a service URL |
| `ingest` deletes and rebuilds one collection | Reads can see a missing or partial index during rebuild | Build a versioned collection, validate it, then atomically switch an alias |
| Local `artifacts/runs` directory | Containers are ephemeral; artifacts are not shared or durable | Object storage plus a metadata database, with retention, encryption, and access control |
| Synchronous workflow inside a FastAPI route | Long LLM calls consume worker capacity and requests can time out | Async provider clients or a durable job queue with status polling and cancellation |
| Process-local approval lock/callback | Approval is lost if a process restarts and cannot cross workers | Persist approval state and resume the workflow from a durable state store |
| Local JSON traces and stdout | No central search, alerting, or cross-service correlation | Central logs, metrics, distributed traces, redaction, retention, and a `run_id` propagated everywhere |
| `.env` for `OPENAI_API_KEY` | Secrets leak through files, logs, images, or developer machines | Secret manager, key rotation, least privilege, and secret scanning in CI |
| One model provider and one model configuration | Provider outage, model drift, runaway cost, or rate limits affect all runs | Model gateway with budgets, quotas, fallback policy, model pinning, and evaluation gates |
| Local CORS and no API authentication | The endpoint is publicly callable if deployed as-is | SSO/OIDC, API scopes, CSRF strategy where applicable, rate limiting, and network policy |
| React dev server | No hardened static delivery or browser security policy | Build once and serve through a CDN/reverse proxy with CSP, TLS, security headers, and frontend auth |
| Basic `/health` response | Process can be healthy while Qdrant, model gateway, or source data is unavailable | Separate liveness/readiness checks and dependency-aware monitoring |
| Read-only tools with retries | Future writes may be duplicated by retries or replay | Idempotency keys, durable operation records, and retry classification for every write tool |

### Recommended production migration order

1. Add real authentication and derive the requester identity server-side.
2. Move Qdrant and run artifacts to managed, durable services.
3. Make approval state durable and expose asynchronous job status.
4. Add centralized observability, rate limits, budgets, and dependency health checks.
5. Add deployment controls: containers, autoscaling, secrets management, backups, retention,
   disaster recovery, and CI/CD security checks.

This is the intended production path; implementing all of it is outside the runnable MVP scope.
