# AgentOS Local Governance v0.25.1 — Release Metadata Coherence

[README landing](README.md) | [Tiếng Việt](README.vi.md)

## Current release: v0.25.1 — Release Metadata Coherence

Database schema: **49**.

v0.25.1 establishes one fail-closed release identity for the package. `VERSION`
is the release-version source of truth; `agentos.__version__`, the MCP runtime,
governance policy, `MANIFEST.json`, `PACKAGE_COMPLETENESS.json`, and current
release identity documents must agree.

This node does **not** change the database schema or authority model. The v0.25.0
Schema Bootstrap Baseline remains intact: fresh databases materialize schema 46,
verify its fingerprint, record coverage 1..46, and then apply migrations 47→49;
existing databases continue incremental migration from their recorded version.

## Validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

## Upgrade

See [Upgrade v0.25.0 → v0.25.1](UPGRADE_FROM_0.25.0.md).

## Node documentation

- [Release Metadata Coherence](.agents/docs/RELEASE_METADATA_COHERENCE_V0251.md)
- [Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md)
