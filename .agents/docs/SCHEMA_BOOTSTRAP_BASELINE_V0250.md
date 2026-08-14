# v0.25.0 — Schema Bootstrap Baseline

## Mục tiêu

Fresh AgentOS state database không còn replay lịch sử migrations 1→46.

## Runtime path

```text
fresh DB
  ↓
create schema_migrations metadata table
  ↓
verify database is truly pristine
  ↓
apply release-pinned schema-46 baseline DDL
  ↓
verify schema fingerprint
  ↓
record migration coverage 1..46
  ↓
run migrations 47→49
  ↓
current schema 49
```

Existing databases do **not** use the bootstrap shortcut. A database at schema 45
still runs 46→49, schema 46 runs 47→49, and current schema 49 is a no-op.

## Safety properties

- The baseline is generated from the v0.24.3 migration chain during upgrade.
- Release artifacts include deterministic SQL plus metadata/fingerprint.
- Bootstrap application is transactionally guarded by a SQLite SAVEPOINT.
- The materialized schema is fingerprint-verified before post-baseline migration.
- An unversioned database containing unknown schema objects fails closed.
- `schema_migrations` still contains 1..49 after fresh initialization, preserving
  compatibility with historical checks and migration continuity.
- No SOURCE/TARGET authority, MCP mutation authority, privacy, approval, or audit
  boundary is changed.

## Baseline choice

Schema **46** is the first bootstrap baseline. Current schema remains **49**.
Therefore fresh initialization invokes only migrations **47, 48, 49** rather than
executing migration functions 1..49.

This is a structural reduction from 49 migration function invocations to 3
post-baseline migrations; it is not presented as a wall-clock performance claim.

## Future migrations

The baseline remains at 46 until a later explicit baseline-rotation release.
Future schema 50+ migrations continue incrementally after the same bootstrap.

## R2 legacy module-local reconciliation

Historical schema-32/33/34 module-local SQLite state may exist without `schema_migrations` markers. R2 accepts it only when every user schema object name and normalized SQL exactly matches the reference generated from migrations 32, 33 and 34. Existing rows are preserved and the full historical chain is reconciled once. Unknown or drifted schema remains fail-closed. This path is not the fresh bootstrap path.
