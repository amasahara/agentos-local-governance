# AgentOS Local Governance

**Current release: v0.25.1 — Release Metadata Coherence**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **49**.

v0.25.1 makes release identity fail-closed and self-consistent. `VERSION` is the
single release-version source of truth; runtime/package versions, governance,
`MANIFEST.json`, `PACKAGE_COMPLETENESS.json`, and current-release identity docs
must agree before a release can validate.

The v0.25.0 **Schema Bootstrap Baseline** remains unchanged: a fresh database
materializes schema 46, verifies the release-pinned fingerprint, records
migration coverage 1..46, then applies migrations 47→49. Existing versioned
databases still migrate incrementally from their recorded version.

## Invariants

- Current database schema remains 49; v0.25.1 adds no migration.
- Release validators must not hard-code the current release literal.
- `PACKAGE_COMPLETENESS.json` is synchronized before manifest hashing.
- Generated `VALIDATION_REPORT*.json` artifacts are not required clean-main files.
- Fresh DB does not invoke historical migration functions 1..46.
- SOURCE/TARGET write boundaries, approvals, privacy, signed audit, context
  preservation and MCP mutation authority are unchanged.
- MCP tool surface is unchanged.

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

See [Upgrade v0.25.0 → v0.25.1](UPGRADE_FROM_0.25.0.md). The versioned updater
is a GitHub Release asset and is intentionally absent from clean `main`.

## Current node documentation

- [Release Metadata Coherence](.agents/docs/RELEASE_METADATA_COHERENCE_V0251.md)
- [Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md)
- [MCP Feature Runtime Refactor](.agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)
