# AgentOS Local Governance

**Current release: v0.23.2 — Context Expansion & Compression Evaluation**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.23.2 extends the v0.23.0/0.23.1 requirement-preserving transport pipeline with **bounded, hash-pinned context expansion** and **deterministic compression evaluation**. The Control Plane remains 100% lossless. Expansion can reveal omitted evidence only through verified read-only handles, while evaluation checks candidate accountability, handle integrity, token-budget compliance, exact requirement preservation, compression stability, and shadow revision regressions.

Database schema: **46**. Expanded source content is never persisted in expansion telemetry. MCP exposes inspection/expansion/evaluation reads only; evaluation persistence and transport mutation remain operator/CLI-only.

## GitHub-ready full release

This repository is materialized so it can be uploaded/replaced as a complete v0.23.2 tree without running an upgrader first. GitHub Actions validates the pushed tree automatically. See [Full GitHub-Ready Materialization](.agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md).

## Upgrade
See [UPGRADE_FROM_0.23.1.md](UPGRADE_FROM_0.23.1.md).

## Node documentation
- [Context Expansion & Compression Evaluation](.agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md)
- [Adaptive Token Budget & Model Profiles](.agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md)
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)
