# Cato GTM AI Engineer Home Task

This repository contains the assignment brief and synthetic source data for the Cato Networks GTM AI Engineer home task: building a Strategic Deal Intelligence Assistant for sales negotiation preparation.

The task asks candidates to build a runnable, LLM-backed multi-agent prototype that retrieves evidence from local GTM-style data, enforces permissions, generates grounded deal briefs, routes sensitive recommendations through human approval, and leaves observable traces.

## Contents

- [Assignment brief](Cato_GTM_AI_Engineer_Home_Task.md)
- [Synthetic data overview](synthetic_data/README.md)
- [Salesforce-style fixtures](synthetic_data/salesforce/)
- [Gong-style call summaries and transcripts](synthetic_data/gong/)
- [Pricing notes](synthetic_data/pricing/pricing_notes.tsv)
- [Access permissions](synthetic_data/policies/access_permissions.tsv)
- [Deal Desk policy](synthetic_data/policies/deal_desk_policy.md)

## Notes

The included data is fully synthetic and covers three fictional opportunities: `OPP-1001`, `OPP-1002`, and `OPP-1003`.

This branch intentionally excludes the generated Slack-style update dataset. Candidates should create and ingest their own synthetic Slack-style updates as described in the assignment brief.

## Prototype implementation

This workspace contains a Typer CLI with typed Pydantic contracts, local Qdrant retrieval, deterministic authorization, three LLM-backed synthesis roles, citation validation, approval records, and inspectable run artifacts.

## Local interfaces

The CLI is the primary runnable prototype. A lightweight HTTP adapter exposes the same workflow without duplicating orchestration logic:

```bash
uv run deal-intel-api
```

Then call `GET http://127.0.0.1:8000/health` or send a request to `POST /brief`:

```json
{
  "opportunity_id": "OPP-1001",
  "user_id": "USR-5001",
  "approval_decision": "pending"
}
```

The CLI defaults to an interactive approval question. The API uses an explicit approval value because HTTP requests cannot pause and ask a terminal question. Slack Socket Mode can be added later as another adapter over the same workflow.

### React demo

The local web UI lives in `frontend/` and uses React, Vite, and Tailwind:

```bash
cd frontend
npm install
npm run dev
```

Run `uv run deal-intel-api` in another terminal, then open `http://127.0.0.1:5173`.

The local Qdrant client is shared and requests are serialized inside the API process because file-backed Qdrant storage allows only one active local client. For multi-process or production deployment, use a Qdrant server instead of local storage.

The generated synthetic Slack updates are stored at `synthetic_data/slack/account_team_updates.tsv`.

Architecture and deployment diagrams are documented in [ARCHITECTURE.md](ARCHITECTURE.md).
Production idempotency and deployment notes are documented in
[PRODUCTION_READINESS.md](PRODUCTION_READINESS.md).

Setup and tests:

```bash
uv sync
uv run pytest -q
uv run ruff check .
```

Offline demo using the deterministic adapter:

```bash
CATO_FAKE_LLM=1 uv run deal-intel demo
```

Live run using OpenAI structured outputs:

```bash
cp .env.example .env
# Edit .env and replace the placeholder API key.
# Set CATO_OBSERVABILITY=false in .env to disable logs and trace entries.
# Use CATO_OBSERVABILITY_IO=full only for local debugging; metadata is safer.
uv run deal-intel ingest
uv run deal-intel brief --opportunity OPP-1001 --user USR-5001
uv run deal-intel brief --opportunity OPP-1003 --user USR-5003 --approval pending
```

Each run is saved under `artifacts/runs/<run_id>/`. Unauthorized requests fail before retrieval and do not create an artifact.
