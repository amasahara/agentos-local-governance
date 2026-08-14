# AgentOS v0.24.2 Developer Guide

## v0.24.2 — Risk-Tiered Batch Review

Assess deterministic mapping tiers first. Batch only LOW mappings into a signed bundle, review MEDIUM/HIGH individually, resolve BLOCKED mappings, and keep the existing exact-plan whole-plan approval gate.


Inspect the complete consolidation pipeline with `consolidation-status` and capture/validate `PERFORMANCE_BASELINE_V0233.json` first. Build a fresh canonical Context Pack and v0.23.1-compatible transport next. Inspect omissions, expand only through bounded hash-pinned handles, and run Compression Evaluation v2. Shadow comparison is read-only and does not activate revisions. Expanded content is ephemeral; the 2–4x ratio is advisory and never permits loss of the protected Control Plane.


## v0.24.2 — DB-Aware Context Projection

Deterministic reversible schema/mapping/manifest projection is limited to the Context Evidence Plane. Control Plane authority remains lossless.
