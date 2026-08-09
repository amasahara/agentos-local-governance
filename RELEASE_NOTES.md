# AgentOS Local Governance v0.23.2 — Release Notes

v0.23.2 upgrades schema **45 → 46** and adds Context Expansion v2 plus Compression Evaluation v2.

Key changes:

- bounded single/batch expansion with source/transport hash pins;
- stable Requirement Ledger bindings and allowlisted expansion reason codes;
- no expanded-content persistence;
- canonical-candidate accountability and expansion-handle integrity hard gates;
- deterministic PASS/WARN/FAIL compression evaluation;
- advisory 2–4x compression stability band;
- shadow comparison between current and historical superseded transport revisions;
- five new read-only MCP operations;
- schema 46 expansion/evaluation metadata tables;
- migration continuity and `foreign_keys=ON` retained.

No permission was added to paraphrase/truncate Control Plane content, mutate SOURCE/TARGET data, resolve credentials through MCP, or let the LLM persist evaluation decisions.

## Full-tree materialization hardening

The GitHub-ready package also repairs issues found only after validating the complete repository: historical governance sections lost by overlay replacement are restored from Git history; historical upgrade guides are restored; v0.22.7 privacy implementation is aligned with its hardening tests; schema 46 repairs pre-existing schema-45 privacy state; MCP runtime version metadata is synchronized; and GitHub Actions provides automatic post-push validation.
