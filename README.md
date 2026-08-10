# AgentOS Local Governance

**Current release: v0.23.4 — Incremental Symbol Index**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.23.3 adds a **read-only consolidation cockpit** spanning project selection through database reconciliation and a **non-destructive performance baseline** for fresh migrations, the current full-rebuild symbol index, and cockpit latency. It does not change consolidation authority, SOURCE/TARGET write boundaries, privacy rules, or the lossless Context Control Plane.

Database schema: **47**. v0.23.4 adds deterministic per-file content-hash state for the local Python symbol index. MCP authority is unchanged; index mutation/benchmark execution remain local CLI/operator functions.

## GitHub-ready full release

The public v0.23.2 tree remains the materialized baseline. Apply the v0.23.3 upgrader, capture `PERFORMANCE_BASELINE_V0233.json` on the materialized repository, then run release-integrity/docs/tests before publishing a v0.23.3 full tree.

## Upgrade
See [UPGRADE_FROM_0.23.3.md](UPGRADE_FROM_0.23.3.md).

## Node documentation
- [Incremental Symbol Index](.agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md)
- [Consolidation Cockpit & Performance Baseline](.agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md)
- [Context Expansion & Compression Evaluation](.agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md)
- [Adaptive Token Budget & Model Profiles](.agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md)
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)
