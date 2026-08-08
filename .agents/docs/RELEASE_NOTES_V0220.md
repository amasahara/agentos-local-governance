# Release Notes — v0.22.0

- Schema 38 controlled TARGET insert plans/events.
- Fully validated staging batches only; partial batches are blocked.
- Immutable plan hashes and mandatory human review/approval.
- Prepared INSERT-only statements for PostgreSQL, MySQL, SQL Server, and Oracle.
- One external transaction with rollback on pre-commit failure.
- Commit uncertainty produces `in_doubt` and disables automatic retry.
- Generic/raw INSERT and all SOURCE writes remain blocked.
- MCP remains read-only.
