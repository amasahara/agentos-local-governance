# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.24.2**. Database schema: **49**.

## v0.24.2 — DB-Aware Context Projection

Use DB-aware projection only for structured schema/mapping/manifest evidence.
The codec must be deterministic, reversible, source-hash pinned, and smaller
than the source representation. Never project Control Plane authority.

Read-only inspection:

```text
context-db-projection-preview
context-db-projection-status
agentos.context_db_projection_get
```

The MCP GET path is strict read-only state access: it must not create or migrate
the AgentOS SQLite database.

## v0.24.1 — Risk-Tiered Batch Review

Assess mapping risk deterministically. Batch only LOW mappings into a signed
bundle, review MEDIUM/HIGH individually, resolve BLOCKED mappings, and retain
the exact-plan whole-plan approval gate.

## Release workflow

```text
build manifest → verify manifest → validate release → full regression → tag/release
```

Versioned updater/recovery files belong to GitHub Releases, not clean `main`.
