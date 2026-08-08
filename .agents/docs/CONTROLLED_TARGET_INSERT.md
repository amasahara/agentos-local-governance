# Controlled Target Insert — v0.22.0

## Goal

Allow the first governed external data write in the database-consolidation roadmap without weakening SOURCE immutability or exposing arbitrary SQL.

## Authority chain

A write is eligible only when all of these remain current:

`validated extraction batch → staging hash → extraction plan hash → confirmed mapping-set hash → approved target contract hash → active target snapshot hash → immutable insert plan hash → human review → human approval`.

## Write boundary

The generic database boundary continues to deny `insert`. v0.22.0 does **not** set a broad connection-level write flag. `controlled_target_insert.py` is the sole INSERT execution boundary and only accepts a pre-approved run.

Supported write class: `INSERT_ONLY`.

Forbidden: UPDATE, UPSERT, MERGE, DELETE, DDL, stored-procedure side effects, raw SQL, user-provided SQL fragments.

## Staging eligibility

Only extraction batches with `status=validated`, `valid_rows>0`, and zero rejections are accepted. Partial successful subsets from `completed_with_rejections` are intentionally blocked in v0.22.0.

## External transaction safety

AgentOS executes parameterized rows in chunks within one external transaction. Any failure before commit triggers rollback. Before invoking external `commit()`, local state becomes `committing`. If commit raises or the process is interrupted in that interval, the run is treated as uncertain and must not be automatically replayed.

`in_doubt` is intentionally fail-closed; v0.22.2 will provide reconciliation/recovery workflows.

## Privacy

AgentOS state stores only row counts, plan/artifact hashes, status, timestamps, and receipt hash. Inserted business values and resolved credentials are not written to SQLite/audit/MCP.

## MCP

MCP is read-only: plan, readiness, prepared statement shape, receipt. No create/review/approve/execute methods are exposed.
