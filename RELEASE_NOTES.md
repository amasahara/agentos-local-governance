# AgentOS Local Governance v0.22.2 — Reconciliation & Recovery

v0.22.2 completes the v0.20.0→v0.22.2 consolidation roadmap with read-only TARGET reconciliation and fail-closed recovery.

Key changes:

- schema 40 reconciliation/recovery state;
- generated SELECT-only TARGET verification scoped to approved business keys;
- HMAC whole-row fingerprint comparison, not count-only verification;
- end-to-end extraction/validation/identity/insert/lineage accounting;
- `in_doubt` recovery requires read-only evidence plus explicit human decision;
- `observed_none` can enable manual retry, never automatic retry;
- partial/mismatched TARGET state requires manual intervention and never automatic data repair;
- known committed lineage can be rebuilt locally/idempotently;
- six additional read-only MCP tools;
- README and developer guide remain split into linked Vietnamese/English pages.

Validation: 18 v0.22.2 node tests and 159 available regression tests passed before packaging.
