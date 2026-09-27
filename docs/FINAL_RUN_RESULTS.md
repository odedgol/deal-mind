# Final Run Results

## Run metadata

| Field | Value |
|---|---|
| Project | `cato-deal-intel` |
| Project version | `0.1.0` |
| Run date | `2026-09-27` |
| Evaluation mode | Deterministic fake LLM |
| Command | `CATO_FAKE_LLM=1 uv run deal-intel evaluate --mode fake` |
| Test command | `UV_CACHE_DIR=/tmp/cato-uv-cache uv run pytest -q` |

## Results

| Metric | Result | Meaning |
|---|---:|---|
| Golden Tests | **10/10 passed** | 4 workflow cases and 6 quality cases passed. |
| Unauthorized Leakage | **0 restricted evidence leaked** | The unauthorized restricted request was denied before retrieval and generation. |
| Citation Validation | **10/10 passed** | Citations were grounded in the evidence available to each run. |
| Required Slack Evidence | **7 updates indexed** | Synthetic Slack updates were loaded for all three opportunities and Slack citations were verified where required. |

## Golden workflow coverage

- Authorized standard opportunity: `OPP-1001` / `USR-5001`
- Authorized restricted opportunity with approval routing: `OPP-1003` / `USR-5003`
- Unauthorized restricted opportunity: `OPP-1003` / `USR-5007`
- Authorized expansion opportunity: `OPP-1002` / `USR-5002`

## Slack evidence coverage

The synthetic Slack dataset contains seven updates:

- `OPP-1001`: 3 updates
- `OPP-1002`: 2 updates
- `OPP-1003`: 2 restricted updates

The evaluation verifies that Slack is retrieved as a required source and that
Slack evidence is cited in the applicable authorized scenarios.

## Verification status

- Full test suite: **53 passed**
- Ruff: **clean**
- Mypy: **clean**

## Scope note

The submission includes live-provider artifacts in `submission/sample_runs/`:

- `openai-slack-opp-1001`: live `gpt-4o-mini` run with generated Slack citation
  `slack:SLACK-1001-03`.
- `openai-approved-opp-1003`: live `gpt-4o-mini` restricted-opportunity run with approval.

The deterministic evaluation path remains the repeatable regression baseline; live-provider
artifacts are evidence of real execution and are not used as deterministic test fixtures.
