# AgentOS Local Governance v0.25.1 — Release Metadata Coherence

Database schema remains **49**. This hardening node repairs release/package
identity drift and makes future release metadata inconsistencies fail closed.

- `VERSION` is the single release-version source of truth.
- `agentos.__version__`, MCP runtime, governance version, manifest, package
  completeness, and current-release identity docs must agree.
- Added read-only `.agents/agentos/release_coherence.py`.
- `tools/validate_release.py` now includes a `release_metadata_coherence` gate.
- `release_integrity.py` no longer hard-codes one historical release literal.
- `tools/build_manifest.py` synchronizes `PACKAGE_COMPLETENESS.json` before hash generation.
- Stale `PACKAGE_COMPLETENESS` release/schema/count metadata is repaired at build time.
- `VALIDATION_REPORT.json` is no longer a required clean-main package file because
  generated validation reports are intentionally excluded from authoritative source packaging.
- Current bilingual README/developer-guide identity is synchronized to v0.25.1.
- v0.25.0 Schema Bootstrap Baseline remains unchanged: schema 46 bootstrap,
  fingerprint verification, coverage 1..46, then migrations 47→49.
- No SOURCE/TARGET, approval, privacy, signed-audit, context, MCP mutation, or DB schema change.
