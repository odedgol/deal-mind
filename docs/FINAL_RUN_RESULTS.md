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

- Full test suite: **50 passed**
- Ruff: **clean**
- Mypy: **clean**

## Scope note

These results are from the deterministic offline evaluation path. A live LLM
run must be recorded separately with its model, date, configuration, and run
artifact IDs before claiming live-provider performance.
