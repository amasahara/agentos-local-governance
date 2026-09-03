# AgentOS Local Governance v0.30.1 — Release & Schema Metadata Coherence

v0.30.1 is the mandatory coherence prerequisite before v0.31.0. Database
schema remains **63**; no migration is added.

## What changed

- Aligns current release documentation identity with v0.30.1 / schema 63.
- Repairs `schema_bootstrap_policy.current_database_schema` to 63.
- Requires the exact contiguous post-bootstrap sequence **47..63** for bootstrap
  schema 46; missing, duplicate, out-of-order, or above-current migrations fail.
- Adds a reusable schema-bootstrap coherence validator to release coherence.
- Keeps the generic historical release-coherence API backward-compatible when a
  fixture/repository does not declare the schema-bootstrap contract.
- Makes `tools/build_manifest.py` validate generated-policy coherence before
  package/manifest/checksum generation.
- Adds a dedicated `schema_bootstrap_coherence` result to `validate_release.py`.
- Preserves historical subsystem `database_schema` metadata when it describes
  feature-introduction schema rather than current release schema.

## Authority and behavior boundaries

This release does **not** add learning signals, does not grant new MCP mutation
authority, and does not change Architecture or human-approval authority.
Generated governance, `MANIFEST.json`, `CHECKSUMS.sha256`, and
`PACKAGE_COMPLETENESS.json` must be regenerated from authoritative sources and
are never hand-edited.

## Schema

Database schema remains **63**. The bootstrap baseline remains schema 46.
The post-baseline migration contract is exactly 47 through 63.

## Inherited predecessor contract — v0.30.0 — Context Authority & Untrusted Provenance

v0.30.1 preserves the v0.30.0 context-authority boundary. Source-origin
classification, hash-only provenance persistence, Context Transport provenance
pinning, and the rule that evidence-derived content cannot promote itself into
AgentOS instruction authority remain unchanged.

The predecessor non-claims also remain unchanged: this release does **not** claim
that prompt injection is eliminated, semantic correctness is guaranteed, model
manipulation is impossible, all input channels are secured, or human review is
replaced.

## Inherited v0.29.4/v0.29.5 Windows execution contract

The bounded Windows execution claims remain preserved:

```text
v0.29.4 Restricted Token
restricted_token_attested = true
v0.29.5 — Native Physical Isolation Extensions
low_integrity_attested = true
host_filesystem_isolation_attested = false
```

These claims remain scoped to `agentos_mediated_process_execution`; they do not
imply general host-filesystem isolation, general OS write confinement, desktop
isolation, credential isolation, or same-user host-bypass resistance.

## Next node

Only after all v0.30.1 release gates pass may development begin on
**v0.31.0 — Governed Learning Signal Integration / schema 64**.
