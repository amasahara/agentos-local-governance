# v0.22.4 — Unified Governance Enforcement & Signed Audit

Privileged database-domain mutations now execute inside one governed business-operation lifecycle:

`task/session → approved workflow → baseline/drift gate → one-time guard token → domain transaction → signed domain events → guarded completion`.

## Guarantees

- Valid AgentOS project roots require `task_id` and `session_id` for privileged mutations.
- The task must be approved and owned by the caller session.
- The `approve_task` workflow step must be complete.
- Governance baseline must be initialized and free of unacknowledged drift.
- Sensitive local overrides must already be approved.
- Each operation uses a single-use guarded execution token.
- Domain events receive `governed_operation_id` and `external_event_hash`.
- Signed-audit failure blocks the mutation before the local domain event is persisted.
- SOURCE write, raw TARGET INSERT, automatic identity decisions, and automatic in-doubt recovery remain non-overridable safety invariants.
- MCP continues to expose read-only inspection only for these privileged domains.

Schema 41 adds `governed_operations` and correlation columns to the six domain event tables.
