# AgentOS Local Governance v0.20.2

## Primary-Project Consolidation

This release converts the v0.20.1 human-selected Primary Project into the only consolidation write target.

### Added

- Schema 34 consolidation state.
- Explicit component mapping actions.
- Human review and plan-hash-bound approval.
- Source manifest/file hash re-verification.
- Target expected-hash/expected-absence concurrency guard.
- Atomic Primary-only materialization.
- Per-component provenance.
- Rollback backup and fail-closed rollback.
- Read-only consolidation MCP tools.
- GitHub-friendly Vietnamese/English docs.

### Security boundary

Secondary Projects remain immutable. Primary authority files (`AGENTS.md`, `VERSION`, `.agents/`, `.git/`) are excluded from consolidation writes/imports.

### Compatibility

Baseline: **v0.20.1**  
Target schema: **34**
