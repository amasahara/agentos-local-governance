# AgentOS Local Governance

**Current release: v0.25.0 — Schema Bootstrap Baseline**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **49**.

v0.25.0 optimizes fresh AgentOS state initialization. A brand-new database
materializes a release-pinned **schema-46 bootstrap baseline**, verifies its
schema fingerprint, records migration coverage 1..46, and then runs only
migrations 47→49.

Existing/versioned databases continue to migrate incrementally from their actual
recorded schema version.

## Invariants

- Current database schema remains 49.
- Fresh DB does not invoke historical migration functions 1..46.
- Bootstrap schema must fingerprint-match the schema produced by historical replay.
- Unversioned non-empty databases fail closed.
- SOURCE/TARGET write boundaries, approvals, privacy, signed audit, context
  preservation and MCP mutation authority are unchanged.
- v0.24.3 MCP Feature Runtime separation remains active.

## Validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

## Upgrade

See [Upgrade v0.24.3 → v0.25.0](UPGRADE_FROM_0.24.3.md). The versioned updater
is a GitHub Release asset and is intentionally absent from clean `main`.

## Current node documentation

- [Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md)
- [MCP Feature Runtime Refactor](.agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)
