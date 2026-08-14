# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.24.2**. Database schema: **49**. Use `consolidation-status` for a read-only end-to-end pipeline view, capture `PERFORMANCE_BASELINE_V0233.json` with `performance-baseline-run`, and keep the v0.23.2 lossless Context Control Plane and all SOURCE/TARGET/privacy/approval boundaries unchanged.


## v0.24.2 Risk-Tiered Batch Review
Use `project-consolidation-risk-assess` first. Batch only deterministic LOW mappings into a signed bundle; review MEDIUM/HIGH individually; then use the existing whole-plan approval gate.


## v0.24.2 — DB-Aware Context Projection

Deterministic reversible schema/mapping/manifest projection is limited to the Context Evidence Plane. Control Plane authority remains lossless.
