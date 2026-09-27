# Security Notes

## Data and identity

- All records in `synthetic_data/` are fictional. Generated account-team updates are marked
  `SYNTHETIC` and carry an explicit source access level.
- The graph authorizes the requester against the opportunity and permission profile before it
  retrieves evidence or invokes an LLM. Denials return a generic message and do not expose
  account details, source names, or a run artifact.
- Retrieval filters by opportunity, allowed source type, and access level. Each evidence tool is
  bound to the authorization decision created by the graph; agents cannot select their own
  permission filters.
- The CLI/API accept a `user_id` for this local prototype. The API does not authenticate that ID.
  A deployed service must derive identity from a verified session or token and enforce access at
  the service boundary as well as in the workflow.

## Model and retrieval safeguards

- Retrieved text is untrusted. Prompts isolate it inside `<untrusted_data>` and explicitly reject
  instructions embedded in source material.
- Pydantic contracts reject malformed structured output. Runtime citation validation rejects
  IDs outside the authorized evidence set, and approval routing flags sensitive recommendations.
- Human approval in the CLI/API/UI records a demo decision only. It does not send messages or write
  to Salesforce, Slack, or another system of record.
- Observability defaults to metadata-only input/output logging. Full I/O logging is opt-in through
  `CATO_OBSERVABILITY_IO=full` and can expose business data if connected to real sources.

## Secrets and deployment limits

- Keep `.env` local. It is ignored by Git; configure reviewers with `.env.example` and their own
  `OPENAI_API_KEY`. Never place keys in source data, traces, screenshots, or sample artifacts.
- The local API has no authentication, uses permissive localhost CORS, and trusts caller-supplied
  identity. Local Qdrant and run files do not provide shared production storage or access control.
- The system prompt and citation checks are useful layers, not a complete security boundary.
  Production needs application-enforced authorization, secret filtering, tool sandboxing, red-team
  testing, authenticated API access, encrypted durable storage, and centralized redacted logging.

See [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the migration checklist and known
operational failure boundaries.
