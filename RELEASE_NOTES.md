# AgentOS Local Governance v0.31.0 — Governed Learning Signal Integration

Database schema: **64**

v0.31.0 adds schema-64 `learning_signals`, `learning_signal_links`, and
`knowledge_usage` as a thin linkage layer across existing verification, outcome,
finding, memory/skill, and context systems.

Raw learning signals are not injected into context. Existing skill/memory/finding
remain project evidence with no instruction authority. MCP is read-only.

Learning observation is degraded-safe; existing governance/security/architecture/
write/Context Authority boundaries remain fail-closed under their own contracts.

No automatic skill graduation, policy activation, Architecture mutation, or
knowledge deactivation is introduced. Canonical signals are not automatically
archived/deleted in this node.

Predecessors preserved:
- v0.30.1 — Release & Schema Metadata Coherence
- v0.30.0 — Context Authority & Untrusted Provenance. Its bounded non-claims remain explicit: this release does not claim prompt injection elimination, semantic correctness, model-manipulation prevention, or human-review replacement.
- v0.29.5 — Native Physical Isolation Extensions

Next node: v0.31.1 — Governed Memory Promotion & Context Binding.

## Raw-signal context boundary

Raw `learning_signals` are not registered as a Context Authority source kind and
are never retrieved by `context_runtime`. Existing promoted `skill`, `memory`,
and `finding` objects continue to use the existing project-evidence provenance
path.

The v0.29.5 predecessor chain remains explicit:

- v0.29.4 Restricted Token
- restricted_token_attested = true
- low_integrity_attested = true
- host_filesystem_isolation_attested = false
