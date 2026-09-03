# AgentOS Local Governance v0.30.0 — Context Authority & Untrusted Provenance

v0.30.0 adds an explicit **context authority boundary** to AgentOS context assembly.

The release separates verified provenance from instruction authority. Content is classified by source origin, and evidence does not gain authority merely because it contains instruction-like text or is transformed, summarized, retrieved, or projected into a Context Transport pack.

## Activated guarantees

- deterministic source-origin context classification;
- explicit authority classes for governance, human request, approved task state, and human decisions;
- explicit evidence/untrusted classes for project evidence, tool evidence, external content, generated evidence, and unknown sources;
- unknown provenance fails to `unknown_untrusted`;
- evidence-derived content cannot promote itself into instruction authority;
- exact authority copies may preserve only the same explicit authority class;
- Context Transport pins `provenance_manifest_hash` and `context_authority_hash`;
- transport read paths revalidate stored hash-only provenance and detect provenance/authority drift;
- provenance persistence stores hashes, labels, producer/transform metadata, and parent IDs rather than raw context content;
- four agent-plane read-only CLI inspection commands;
- four read-only MCP inspection tools;
- structural enforcement attestation for the bounded context-authority contract.

## Read-only operator surfaces

CLI:

```text
context-authority-status
context-provenance-show
context-authority-explain
context-authority-findings
```

MCP:

```text
agentos.context_authority_status_get
agentos.context_provenance_get
agentos.context_authority_explain
agentos.context_authority_findings_get
```

No MCP authority-grant, trust-promotion, provenance-override, approval, or finding-waiver surface is added.

## Database

Database schema: **63**.

## Bounded claim

**AgentOS v0.30.0 deterministically distinguishes explicit AgentOS context authority from evidence-derived and untrusted provenance, preserves provenance across the governed Context Transport path, and prevents evidence-derived context from being promoted into AgentOS instruction authority by that path.**

## Explicit non-claims

This release does **not** claim that prompt injection is eliminated, semantic correctness is guaranteed, a model cannot be manipulated, every possible input channel is secured, or human review/approval is replaced.

Existing Windows Restricted Token + Low Integrity and other v0.29.x claims remain separately bounded to their previously attested scopes.

## Inherited predecessor contract — v0.29.5 — Native Physical Isolation Extensions

v0.30.0 preserves the bounded v0.29.5 Native Physical Isolation Extensions
contract. Restricted Token + Low Integrity remains scoped to
`agentos_mediated_process_execution`; broader host-filesystem isolation,
general OS write confinement, desktop isolation, credential isolation, and
same-user host-bypass resistance remain unclaimed.

## Inherited v0.29.4/v0.29.5 Windows execution contract

The v0.30.0 release preserves the predecessor Windows execution claims:

```text
v0.29.4 Restricted Token
restricted_token_attested = true
v0.29.5 — Native Physical Isolation Extensions
low_integrity_attested = true
host_filesystem_isolation_attested = false
```

These predecessor claims remain bounded to `agentos_mediated_process_execution`.
They do not imply general host-filesystem isolation, general OS write
confinement, desktop isolation, credential isolation, or same-user host
bypass resistance.
