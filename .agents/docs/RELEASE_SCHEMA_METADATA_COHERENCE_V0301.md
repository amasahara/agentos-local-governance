# AgentOS v0.30.1 — Release & Schema Metadata Coherence

## Scope

This node repairs release/schema metadata coherence only. Database schema remains
**63** and no v0.31 learning feature is implemented here.

## Required invariant

```text
runtime CURRENT_SCHEMA_VERSION
= documentation current schema
= schema_bootstrap_policy.current_database_schema
= generated effective policy schema_version
= 63
```

For bootstrap schema 46:

```text
post_baseline_migrations_at_release = [47, 48, ..., 63]
```

The list must be complete, ordered, unique, and contain no migration above the
current schema. Historical subsystem `database_schema` fields are not current
schema claims and are intentionally left unchanged.

## Source-of-truth boundary

`governance.effective.json`, `MANIFEST.json`, `CHECKSUMS.sha256`, and
`PACKAGE_COMPLETENESS.json` are generated artifacts. Fix modular/current policy
sources first, then regenerate them with the normal build path.

## Release gate

Before v0.31.0 begins: focused tests, full regression, docs-check,
release-integrity, release validation, manifest verification, `git diff --check`,
and release-clutter checks must all pass.
