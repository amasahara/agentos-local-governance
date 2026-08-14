# AgentOS Local Governance

**Current release: v0.24.2 — Risk-Tiered Batch Review**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.23.3 adds a **read-only consolidation cockpit** spanning project selection through database reconciliation and a **non-destructive performance baseline** for fresh migrations, the current full-rebuild symbol index, and cockpit latency. It does not change consolidation authority, SOURCE/TARGET write boundaries, privacy rules, or the lossless Context Control Plane.

Database schema: **49**. v0.24.2 adds deterministic mapping risk tiers and Ed25519-signed LOW-risk review bundles. MEDIUM/HIGH mappings remain individual human review; whole-plan approval and execution authority are unchanged.

## GitHub-ready full release

The public v0.23.2 tree remains the materialized baseline. Apply the v0.23.3 upgrader, capture `PERFORMANCE_BASELINE_V0233.json` on the materialized repository, then run release-integrity/docs/tests before publishing a v0.23.3 full tree.

## Upgrade
See [UPGRADE_FROM_0.23.4.md](UPGRADE_FROM_0.23.4.md).

## Node documentation
- [Risk-Tiered Batch Review](.agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md)
- [Incremental Symbol Index](.agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md)
- [Consolidation Cockpit & Performance Baseline](.agents/docs/CONSOLIDATION_COCKPIT_PERFORMANCE_BASELINE_V0233.md)
- [Context Expansion & Compression Evaluation](.agents/docs/CONTEXT_EXPANSION_COMPRESSION_EVALUATION_V0232.md)
- [Adaptive Token Budget & Model Profiles](.agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md)
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)


## v0.24.2 — DB-Aware Context Projection

Deterministic reversible schema/mapping/manifest projection is limited to the Context Evidence Plane. Control Plane authority remains lossless.

## Repository release policy

`main` contains the latest runnable source, regression tests and current docs. Versioned updater/recovery artifacts belong to Git tags/GitHub Releases. See `.agents/docs/REPOSITORY_RELEASE_POLICY.md`.
