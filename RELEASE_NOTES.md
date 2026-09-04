# AgentOS Local Governance v0.31.1 — Governed Memory Promotion & Context Binding

Database schema: **64**

v0.31.1 turns repeated, verified project findings into reusable project-memory
candidates through the existing `project_memory`, learning-link, Human Decision,
and context retrieval paths.

No migration 65 and no parallel lesson or feedback subsystem are introduced.

## Governed promotion

Default eligibility requires:

- at least 3 occurrences;
- at least 2 distinct verified tasks;
- evidence within a 30-day working window;
- current source-hash revalidation;
- active Architecture Authority baseline match;
- 7-day promotion cooldown after rejected/stale candidates.

Automatic behavior may flag/create only `project_memory(status='candidate')`.
Existing retrieval selects active memory, so candidates are not injected into
future context.

Activation requires an explicit resolved Human Decision and the privileged
`memory-promotion-finalize` command. Approval revalidates source hashes,
distinct-task eligibility, occurrence threshold, candidate/link identity, and
the active architecture baseline. Rejection produces `status='rejected'`.

## Context Authority

Activated promoted memory continues to use existing `knowledge_memory`
provenance:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

Human approval authorizes only the lifecycle state transition. It does not turn
memory content into human-request or governance authority. Learning-derived
evidence may change `provenance_manifest_hash` when included, but cannot by
itself change `context_authority_hash`.

## MCP and automation boundary

v0.31.1 adds no MCP tool. The validated MCP surface remains 132 tools and the
v0.31.0 learning MCP surface remains read-only.

There is no automatic memory activation, skill graduation, policy activation, or
Architecture Authority mutation.

Candidate observation/flagging is degraded-safe. Activation remains fail-closed
for missing human approval, stale evidence, eligibility regression, architecture
drift, or candidate identity mismatch.

## Predecessor contracts

v0.31.1 preserves:
- v0.31.0 — Governed Learning Signal Integration
- v0.30.1 — Release & Schema Metadata Coherence
- v0.30.0 — Context Authority & Untrusted Provenance
- v0.29.5 — Native Physical Isolation Extensions
- v0.29.4 Restricted Token

### Preserved Windows predecessor attestation markers

The bounded predecessor contracts remain unchanged:

```text
v0.29.4 Restricted Token
restricted_token_attested = true
v0.29.5 — Native Physical Isolation Extensions
low_integrity_attested = true
host_filesystem_isolation_attested = false
```

These markers are scoped release attestations and are not a claim of general
host filesystem isolation.

This release does not claim prompt injection elimination, semantic correctness,
causal learning effectiveness, human-review replacement, or general host
containment.

Next node: **v0.31.2 — Closed-Loop Skill & Policy Improvement**.
