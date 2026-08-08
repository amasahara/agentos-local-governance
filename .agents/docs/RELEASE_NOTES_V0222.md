# Release Notes — v0.22.2

- Schema 40 reconciliation/recovery state.
- Generated business-key-scoped TARGET SELECT reconciliation.
- HMAC whole-row fingerprint comparison for exact expected/observed row sets.
- End-to-end extraction → identity → insert → lineage accounting.
- Recovery cases and immutable privacy-safe checkpoints.
- Human-only resolution for `committing/in_doubt`.
- Safe manual retry eligibility only after `observed_none` + human confirmation.
- `observed_partial/mismatch` fail closed to manual intervention; no automatic TARGET repair.
- Idempotent local lineage recovery for known committed inserts.
- Six new read-only MCP tools; no reconciliation execution or recovery mutations over MCP.
