# AgentOS Local Governance v0.25.0 — Schema Bootstrap Baseline

Database schema remains **49**; this node changes fresh initialization mechanics,
not business-state schema.

- Added deterministic schema-46 bootstrap SQL + metadata/fingerprint artifacts.
- Fresh DB records migration coverage 1..46 without invoking those migration functions.
- Fresh DB then runs only migrations 47, 48 and 49.
- Existing databases preserve ordinary incremental migration behavior.
- Bootstrap schema is verified against the release-pinned fingerprint before use.
- Added fail-closed handling for unversioned non-empty databases.
- Generic release validation now proves the fresh bootstrap execution path.
- Added bootstrap-vs-full-replay schema equivalence regression coverage.
- No SOURCE/TARGET, approval, privacy, signed-audit or MCP mutation boundary changes.

## R2 compatibility hardening

- Route project selection/consolidation DB access through central `db.connect()`.
- Reconcile exact legacy module-local schema 32/33/34 once while preserving rows.
- Unknown unversioned schema remains fail-closed.
- Fresh DB still skips migration functions 1..46 and runs only 47..49.
