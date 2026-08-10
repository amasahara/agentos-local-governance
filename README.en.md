# AgentOS Local Governance v0.23.4 — Incremental Symbol Index

[README landing](README.md) | [Tiếng Việt](README.vi.md)

v0.23.4 adds a deterministic content-hash incremental Python symbol index. Unchanged files are not AST-parsed; changed/new files replace only their own rows and deleted files remove stale rows. Schema is **47**.

## v0.23.3 foundation

v0.23.3 adds a read-only end-to-end consolidation cockpit and non-destructive performance baselines for fresh schema migration, the current full-rebuild symbol index, and cockpit latency. Schema remains **46**. MCP can read status/baseline artifacts but cannot execute benchmarks or mutate consolidation state.

## v0.23.2 foundation
v0.23.2 adds a bounded, hash-pinned expansion loop and deterministic Compression Evaluation v2 on top of v0.23.0/0.23.1. The Control Plane remains fully lossless. Expansion verifies the transport hash, canonical revision, and source hash, supports line/token bounds and Requirement Ledger bindings, and never persists expanded content. Evaluation hard-fails on any protected-requirement loss, unaccounted canonical candidate, broken omission handle, budget overflow, stale source, or transport-integrity failure. The 2–4x compression band remains an advisory stability target.

Schema: **46**. New read-only MCP operations expose expansion metadata/batch reads and evaluation/compare reads; persistence and mutation remain outside MCP authority.

## Full GitHub-ready release

The complete v0.23.2 package is materialized from the full repository rather than delivered as an overlay. Extract it, replace/upload the repository contents, and commit/push; `apply_v0232.py` is not required for the full package. The included GitHub Actions workflow runs compilation, validators, release-integrity, manifest/checksum, docs/instruction checks, and the complete test suite.

See [Full GitHub-Ready Materialization](.agents/docs/GITHUB_READY_FULL_RELEASE_V0232.md).
