# AgentOS v0.32.1 — Runtime Coherence & Provenance Ergonomics

v0.32.1 remains on schema 65.

## Learning degraded-safe hardening

Optional `knowledge_usage` persistence is isolated by a SQLite savepoint. If the
learning-only write fails, AgentOS rolls back only the usage rows, preserves the
context pack and context knowledge event, surfaces degradation, and fabricates
no usage evidence.

## Execution provenance ergonomics

New agent-plane command:

```text
execution-provenance-list
```

Supported filters: task, session, provider, model, verification class, time
range, and bounded result limit.

## MCP

Two read-only tools are registered through the modern feature runtime:

```text
agentos.execution_provenance_get
agentos.execution_provenance_list
```

There is no MCP registration tool.

The MCP-safe projection excludes `execution_ref_id`, provider request hashes,
deployment IDs, recorded-by identity and secret flags. Responses explicitly
carry non-authority and non-attestation markers.

## Surface

```text
schema      = 65
CLI         = 368
agent       = 270
privileged  = 100
MCP         = 134
```

No schema 66, provider/model auto-selection, instruction authority, Context
Authority promotion, remote cryptographic-attestation claim or MCP mutation is
introduced.

## Base governance vs current release overlay

`.agents/config/governance.json` remains the historical base policy and retains
its top-level version `0.26.3`. This is intentional. Historical fixture tests
may copy only this base file and must not accidentally activate successor-only
version-gated policy validators.

The current release identity is owned by the managed release overlay:

```text
governance.json          = historical base version 0.26.3
release_policy.json      = current release version 0.32.1
governance.effective     = current effective release policy
```

v0.32.1 must not rewrite the base-policy version merely to make the generated
effective policy current.
