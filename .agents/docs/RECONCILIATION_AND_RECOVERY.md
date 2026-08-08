# Reconciliation & Recovery — v0.22.2

## Goal

Prove that Controlled Target Insert produced the expected TARGET state and recover safely from local/external uncertainty without adding generic write capability.

## Reconciliation evidence

A reconciliation plan binds to the original insert plan, target contract/snapshot, mapping set, identity manifest, TARGET connection, table, column order, and exact approved business-key fields. The runtime loads the deduplicated staging locally, computes HMAC whole-row fingerprints, then performs generated SELECT-only TARGET reads scoped to those business keys. Raw parameters and result values are transient and are never persisted.

Outcomes:

- `matched`: expected and observed whole-row multisets are identical.
- `observed_none`: none of the expected target rows is observed.
- `observed_partial`: at least one expected row matches but the set is incomplete/different.
- `mismatch`: TARGET rows are present for the scoped keys but none matches the expected whole-row fingerprints.

## Recovery

`committing/in_doubt` remains uncertain after reconciliation. The runtime does not mutate insert status automatically.

- `matched` + explicit human confirmation → `committed_verified`; a recovery receipt hash is created, the run becomes committed, and lineage is finalized locally.
- `observed_none` + explicit human confirmation → `not_committed_verified`; the run becomes failed with stage `reconciled_not_committed`, which is eligible for **manual** retry of the same approved plan.
- `observed_partial/mismatch` → manual intervention only. AgentOS does not issue UPDATE/DELETE/UPSERT/MERGE compensation.

Known-committed inserts whose local lineage is pending may run idempotent lineage recovery. This does not touch TARGET.

## Privacy

SQLite/audit/checkpoints may contain only IDs, hashes, counts, statuses, pseudonymous fingerprints, and error types. Business values, credentials, query parameters, and raw rows are forbidden.

## MCP boundary

MCP exposes only read-only run/summary/spec/case/readiness/checkpoint views. Human/operator CLI retains reconciliation execution and all recovery decisions.
