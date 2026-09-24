# Production Readiness Notes

## Current MVP behavior

The MVP workflow is read-only with respect to external business systems:

- Qdrant is used for local evidence indexing and retrieval.
- The LLM produces structured recommendations but does not write to a system of record.
- Approval records are saved as local run artifacts.
- Retries are safe for transient read-only calls when they do not repeat an external write.

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
