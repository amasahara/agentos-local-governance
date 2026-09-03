# AgentOS v0.31.0 — Governed Learning Signal Integration

Database schema: **64**

v0.31.0 adds a thin evidence/linkage layer: `learning_signals`,
`learning_signal_links`, and `knowledge_usage`.

Raw learning signals are telemetry only and are not retrieved into future context.
Existing `skill`, `memory`, and `finding` remain the only knowledge kinds used by
`context_runtime`.

Learning-derived evidence remains `project_evidence`, authority `none`, and
`instruction_authority = false`. Inclusion may change provenance, but cannot raise
Context Authority.

Per-task signal sequence numbers are assigned transactionally. Promotion-oriented
links revalidate source hashes and verified cross-task eligibility.

MCP is read-only. v0.31.0 does not auto-graduate skills, auto-activate policies,
mutate Architecture Authority, or auto-deactivate knowledge.

Learning observation is degraded-safe; governance/security/architecture/write/
Context Authority boundaries retain their existing fail-closed semantics.

Canonical learning signals are not automatically deleted or archived in v0.31.0.

## Context provenance boundary

Raw `learning_signals` are not registered as Context Authority source kinds.
Only existing promoted knowledge objects (`skill`, `memory`, `finding`) use the
existing project-evidence provenance path. This prevents a raw signal from
becoming a context source merely because it resembles an instruction.

## Source ownership

`.agents/config/policy/learning.json` is the single modular source owner for
`governed_learning_policy`. Generated effective policy remains derived output.
