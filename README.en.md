[🇻🇳 Vietnamese](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.4

## Unified Governance Enforcement & Signed Audit

v0.22.4 places the v0.20–v0.22 project/database branch inside the same enforcement boundary as the governance core restored in v0.22.3.

### Required privileged-mutation lifecycle

```text
approved task + owner session
        ↓
workflow approve_task done
        ↓
initialized baseline + no drift
        ↓
approved sensitive override only
        ↓
one-time guard token
        ↓
domain transaction
        ↓
privacy-safe signed domain events
        ↓
guarded completion + signed completion
```

### Guarantees

- Privileged database-domain mutations on a valid AgentOS project require `task_id` and `session_id`.
- The task must be approved and the caller session must currently own it.
- An uninitialized baseline or unacknowledged governance drift blocks mutation.
- One business operation consumes one guard token; SQL statements do not receive separate tokens.
- Six database-pipeline event tables persist `governed_operation_id` and `external_event_hash`.
- Signed-audit failure blocks the operation before the local domain event is persisted.
- All six database modules use the shared `agentos.db.connect()` path, giving consistent SQLite foreign-key and busy-timeout enforcement.
- SOURCE write, raw TARGET write, automatic identity decisions, and automatic in-doubt recovery remain fail-closed non-overridable invariants.
- MCP remains read-only for privileged database mutations.

### CLI

Privileged commands accept governance context before the command:

```bash
.agents/bin/agentos \
  --task-id TASK-001 \
  --session-id AGENT-1 \
  db-connection-register ...
```

`AGENTOS_TASK_ID` and `AGENTOS_SESSION_ID` may be used instead of prefix flags.

### Schema

Database schema: **41**

Schema 41 adds `governed_operations` plus correlation columns to the six domain event tables.

### Next roadmap node

v0.22.5 will flatten CLI/MCP routing and complete the cross-platform runtime. That refactor is deliberately outside v0.22.4.
