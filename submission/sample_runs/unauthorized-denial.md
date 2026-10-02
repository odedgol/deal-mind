# Unauthorized request sample

Command:

```bash
uv run deal-intel brief --opportunity OPP-1003 --user USR-5007 --approval pending
```

Output:

```text
Request denied: Requester is not authorized for this request.
```

The authorization gate returns before evidence retrieval or LLM invocation. By design, the
denied request does not persist a run artifact or expose protected account/source details.
