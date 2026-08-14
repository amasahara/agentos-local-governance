# AgentOS Local Governance

**Current release: v0.24.2 — DB-Aware Context Projection**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **49**.

v0.24.2 adds deterministic, reversible structural projection for DB schema,
field-mapping, and manifest evidence. Projection is limited to the Context
**Evidence Plane**; the original request, Requirement Ledger, `AGENTS.md`,
approved scope, active plan, and governance authority remain lossless.

## Security and governance invariants

- SOURCE projects/databases remain read-only.
- TARGET mutation authority is unchanged and remains approval/governance gated.
- DB-aware projection is used only when it reduces serialized size.
- Raw projected DB content is not persisted in projection telemetry.
- MCP exposes projection telemetry as read-only inspection only.
- Risk-Tiered Batch Review from v0.24.1 remains active; whole-plan approval is still required.

## Validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
```

Full regression:

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

On PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

## Upgrade

See [Upgrade v0.24.1 → v0.24.2](UPGRADE_FROM_0.24.1.md).
The versioned updater is distributed as a GitHub Release asset and is not
committed to clean `main`.

## Current node documentation

- [DB-Aware Context Projection](.agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md)
- [Risk-Tiered Batch Review](.agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md)
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)

## Repository release model

`main` contains the latest runnable source, regression tests, current docs, and
generic validation tools. Versioned updater/recovery assets belong to Git tags
and GitHub Releases rather than accumulating on `main`.
