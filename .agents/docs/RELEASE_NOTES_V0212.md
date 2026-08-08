# Release Notes — v0.21.2

- Schema 37: extraction batches, batch-mapping pins, validation findings, extraction events.
- First controlled business-record read from SOURCE databases.
- Generated SELECT-only queries from confirmed mapped columns; no SELECT *, raw SQL, DML/DDL.
- Revalidation of source snapshot, target contract, mapping set, and plan hashes before extraction.
- Allowlisted deterministic transforms and target-contract validation.
- Local chmod-0600 staging artifacts with SHA-256 manifest.
- Quarantine stores hashes/issues only; no raw invalid values in SQLite/audit.
- MCP remains read-only and cannot run extraction or read staging data.
- TARGET INSERT remains disabled until v0.22.0.
