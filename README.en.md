# AgentOS Local Governance v0.25.0 — Schema Bootstrap Baseline

[README landing](README.md) | [Tiếng Việt](README.vi.md)

**Current release: v0.25.0 — Schema Bootstrap Baseline**  
Database schema: **49**.

A brand-new AgentOS state database no longer invokes migration functions 1→46.
It materializes the release-pinned schema-46 baseline, verifies its fingerprint,
records migration coverage 1..46, then runs migrations 47→49.

Existing databases remain on the ordinary incremental migration path. Governance
and mutation boundaries are unchanged.

See [Upgrade v0.24.3 → v0.25.0](UPGRADE_FROM_0.24.3.md) and
[Schema Bootstrap Baseline](.agents/docs/SCHEMA_BOOTSTRAP_BASELINE_V0250.md).
