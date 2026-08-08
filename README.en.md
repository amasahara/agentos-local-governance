[🇻🇳 Vietnamese](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.3

## Core Reintegration & Release Integrity

This release repairs the v0.22.2 integrity break: the GitHub tree still contains the historical core, but v0.22.2 replaced `db.py` with only migrations 32–40 and replaced `governance.json` with only the extension-policy branch. v0.22.3 restores one coherent runtime.

### Invariants

- The v0.19.5 governance core and v0.20-v0.22 extension branch must ship together.
- `db.py` restores `connect()` and migrations 1→31, then appends migrations 32→40.
- `CURRENT_SCHEMA_VERSION = 40` is the single schema-version authority.
- `governance.json` is the union of core policy and project/database extension policy.
- `agentos.v0195` and `agentos-mcp.v0195` invoke real core runtime paths; silent-success/echo stubs are forbidden.
- Historical core tests and current feature tests are both release gates.
- `MANIFEST.json`/`CHECKSUMS.sha256` are verified by a first-party tool.

### Deliberate non-goal

v0.22.3 does not claim that every database-domain mutation is already routed through `guard_tool`/signed audit. That remains v0.22.4 Unified Governance Enforcement & Signed Audit.

Database schema: **40**
