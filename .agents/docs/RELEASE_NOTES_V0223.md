# Release Notes v0.22.3 — Core Reintegration & Release Integrity

- Reintegrates the historical governance core with the project/database consolidation branch.
- Restores central SQLite persistence and contiguous migrations 1 through 40.
- Restores real v0.19.5 compatibility CLI/MCP backends instead of dead stubs.
- Makes old and new governance policy sections coexist in one validated policy.
- Adds package-integrity, aggregate documentation, and manifest verification gates.
- Makes historical core tests and extension tests jointly release-critical.
- Keeps database schema at 40.
- Defers full database-domain task/session guard and signed-audit unification to v0.22.4.
