# AgentOS Local Governance v0.32.1 — Runtime Coherence & Provenance Ergonomics

Database schema: **65**

v0.32.1 hardens optional learning telemetry and adds privacy-minimal execution
provenance inspection without changing registration authority.

## Changes

- `knowledge_usage` writes are isolated by a SQLite savepoint and degrade safely.
- New agent-plane `execution-provenance-list` command.
- New read-only MCP tools:
  - `agentos.execution_provenance_get`
  - `agentos.execution_provenance_list`
- MCP provenance uses a sanitized projection.
- Provenance registration remains privileged and is not exposed over MCP.
- Historical MCP feature-runtime counters are explicitly marked as activation
  snapshots; live counts come from runtime catalog validation.

## Expected surface

```text
VERSION       = 0.32.1
schema        = 65
CLI           = 368
agent         = 270
privileged    = 100
MCP           = 134
```

## Non-claims

v0.32.1 does not claim remote-provider cryptographic attestation, causal model
effectiveness, automatic provider/model selection, instruction authority from
execution provenance, MCP mutation authority, semantic correctness,
prompt-injection elimination or general host isolation.

## Predecessor contracts preserved

v0.32.1 preserves the bounded predecessor contracts and attestations carried
forward by v0.32.0:

- v0.32.0 — Execution Identity & Model Provenance
- v0.31.3 — Learning Effectiveness & Drift
- v0.31.2 — Closed-Loop Skill & Policy Improvement
- v0.31.1 — Governed Memory Promotion & Context Binding
- v0.31.0 — Governed Learning Signal Integration
- v0.30.1 — Release & Schema Metadata Coherence
- v0.30.0 — Context Authority & Untrusted Provenance
- v0.29.5 — Native Physical Isolation Extensions
- v0.29.4 Restricted Token

```text
restricted_token_attested = true
low_integrity_attested = true
host_filesystem_isolation_attested = false
```

These are bounded AgentOS-mediated enforcement claims, not general host
containment claims.

The release continues to make no causal model-effectiveness claim and does not
claim remote-provider cryptographic attestation, semantic correctness, prompt injection elimination, replacement of human review, automatic provider/model
selection, or general host isolation.
