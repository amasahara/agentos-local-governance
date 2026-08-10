# AgentOS Local Governance v0.23.4 — Incremental Symbol Index

v0.23.4 converts the historical full-rebuild Python symbol index into a deterministic content-hash incremental index.

## Changes

- Schema 46 → 47 with persistent per-file index state.
- `index-build` is incremental by default; `--full` forces rebuild.
- First post-upgrade build bootstraps metadata with one full rebuild.
- Unchanged files are hashed but not AST-parsed.
- Changed/new files replace only their own symbol rows; deleted files remove stale rows.
- Parse failures are transaction-atomic and preserve the previously valid index.
- New `index-status`, `index-benchmark-run`, and `index-benchmark-check` commands.
- Benchmark compares no-change incremental behavior to v0.23.3 full-rebuild baseline without introducing environment-specific hard timing thresholds.
- SOURCE/TARGET, human approval, signed-audit, privacy/secret/key and lossless Context Control Plane invariants are unchanged.
