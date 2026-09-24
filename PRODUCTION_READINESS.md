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

The local defaults live in `.env.example`; pricing values must be reviewed whenever the provider
pricing changes. A production model gateway should own the authoritative price table, quotas,
budgets, fallback policy, and cross-worker accounting.

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
