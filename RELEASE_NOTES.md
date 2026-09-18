# AgentOS Local Governance v0.32.4 — Windows Trusted Gateway IPC & Capability Completion Stabilization

Database schema: **65**

v0.32.4 is a cumulative bounded patch over formal release v0.32.2.
It incorporates the operational v0.32.3 capability-session/completion
stabilization and the Windows trusted gateway IPC fix.

## Changes

- Preserve v0.32.3 capability-session bootstrap on the privileged control plane.
- Preserve stable workflow completion subjects independent of task ownership/liveness state.
- Use project-scoped Windows Named Pipes (AF_PIPE) for the trusted gateway.
- Preserve POSIX AF_UNIX gateway behavior.
- Protect the Windows gateway auth-key file with a protected DACL granting full access only to the current execution identity, SYSTEM, and Administrators.
- Keep the gateway free of TCP listeners.
- Remove direct subprocess/process-creation primitives from gateway ACL setup; use direct Win32 security APIs instead.
- Add focused Windows IPC, ACL, cleanup, and attestation regression coverage.

## Compatibility

VERSION = 0.32.4
schema = 65
previous formal release = 0.32.2
operational predecessor = 0.32.3

No database migration is introduced.

## Authority and security

This release does not widen approved scope, create filesystem/process/network authority, add MCP mutation authority, replace Human approval, weaken context authority, or claim general host containment.

Windows gateway transport is local-only AF_PIPE. No TCP listener is added.

---

# AgentOS Local Governance v0.32.2 — Project Artifact Placement & Path Safety

Database schema: **65**

v0.32.2 is a bounded patch release for explicit project-relative
CREATE placement and path-safety regression coverage.

## Changes

- Preserve explicit project-relative CREATE targets instead of reducing
  them to their basename.
- Preserve configured `source_root` placement for basename-only CREATE
  targets.
- Reject absolute paths, drive-qualified paths, and parent traversal
  before normal write authorization.
- Preserve approved-scope and existing write-authorization semantics.
- Add regression coverage for project-owned artifacts outside `src/`.
- Add regression coverage for the hospital Baseline review-artifact path.

## Compatibility

VERSION = 0.32.2
schema = 65
previous release = 0.32.1

No database migration is introduced.

## Authority and security

Explicit placement is not write authorization.

This release does not widen approved scope, create a new internal-write
capability, alter Human approval authority, or weaken sandbox, credential,
context-authority, or project-preservation boundaries.

---

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
