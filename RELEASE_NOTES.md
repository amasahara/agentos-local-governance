# AgentOS Local Governance v0.24.2 — DB-Aware Context Projection

- Schema **48 → 49**.
- Added deterministic reversible structural compression for schema, mapping, and manifest JSON evidence.
- Added `db_schema_keydict_v1`, `db_mapping_keydict_v1`, and `db_manifest_keydict_v1`.
- Projection is Evidence-Plane-only; original request, Requirement Ledger, AGENTS authority, approved scope, active plan, and governance authority remain lossless.
- A codec is selected only when it reduces actual serialized size.
- Schema 49 persists only hashes/counters/codec metadata; raw projected DB content is not persisted.
- Existing source hash, context revision, expansion, stale detection, adaptive token budget, and preservation gates remain authoritative.
- Added read-only CLI preview/status and read-only MCP telemetry.
- No DB mutation authority is granted to MCP or the LLM.

## Repository Release Cleanup

- `main` now represents only the latest runnable AgentOS package.
- Historical versioned updater/validator/release packaging files are staged outside the repository for GitHub Release assets.
- Historical regression tests remain on `main` as compatibility contracts.
- Runtime/state/cache and editor/test caches remain local-only.
