# AgentOS v0.23.2 — Full GitHub-Ready Materialization

## Purpose

This package is a **full materialized repository**, not an upgrade overlay. It is intended for the workflow:

```text
extract ZIP
→ replace/upload repository contents
→ commit/push to GitHub
→ GitHub Actions validates the release
```

No `apply_v0232.py` command is required when using the full package.

## Authoritative release state

- `VERSION`: `0.23.2`
- runtime `__version__`: `0.23.2`
- unified CLI/MCP runtime version: `0.23.2`
- AgentOS database schema: `46`
- migrations: contiguous `1 → 46`
- SQLite `foreign_keys=ON`
- SQLite `secure_delete=ON`

## Materialization repairs

The full-tree validation discovered historical state that an overlay-only workflow could not safely repair by file replacement alone. This release materializes the fixes into the authoritative repository:

1. Restores legacy governance sections from the exact v0.22.5 Git history so v0.23.x retains language, installation, security, execution-platform, evolution, multi-agent, evaluation, storage, and knowledge-runtime compatibility policy.
2. Restores historical upgrade guides from Git history instead of synthesizing replacement documentation.
3. Makes historical regression tests release-agnostic where their original assertions were about invariants rather than a permanently frozen current release number/schema.
4. Completes the declared v0.22.7 privacy hardening: one-way erasure locators, immutable request/plan triggers, bounded reason codes, canonical UUID tombstoning, active/in-doubt operation blocking, and staging-only deletion.
5. Repairs existing schema-45 databases during migration 46, so privacy hardening applies to already-upgraded installations as well as fresh databases.
6. Synchronizes unified MCP runtime version with v0.23.2 and preserves a unique flat MCP catalog.

## GitHub validation

`.github/workflows/agentos-release-validation.yml` runs on pushes to `main`, pull requests, and manual dispatch. It checks:

- Python compilation;
- v0.23.2 node validator;
- release-integrity and manifest/checksum validation;
- runtime-health, docs-check and instruction-check;
- the complete shipped pytest regression suite.

The workflow restores executable bits inside CI before invoking POSIX wrappers. This matters when files were uploaded through interfaces that do not preserve Unix executable mode.

## Local generated data

The full package deliberately excludes Git metadata and generated AgentOS state. `.gitignore` prevents runtime/state/cache, SQLite databases, lineage key material, Python caches, and environment-secret files from becoming release authority.

## Upgrade overlay

`tools/apply_v0232.py` is retained for developer/operator upgrade workflows. It is **not required** when the full GitHub-ready package is used.
