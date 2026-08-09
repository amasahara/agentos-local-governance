# AgentOS Local Governance v0.22.7

**Data Subject Rights & Privacy Lifecycle — schema 43**

This node adds an immutable data-subject erasure request/plan lifecycle followed by human review, human approval, local execution, canonical tombstoning, and signed audit evidence.

Key invariants:
- SOURCE remains SELECT-only.
- TARGET writes remain limited to Controlled Target Insert; v0.22.7 adds no UPDATE/DELETE/UPSERT/MERGE path.
- When committed TARGET lineage exists outside AgentOS authority, the result explicitly reports `external_target_erasure_required=true` while local erasure can complete.
- Relinkable local identity bindings/candidates/lineage are removed and the canonical entity becomes a non-relinkable tombstone.
- Related staging/cache/memory/index material is purged by policy; retained evidence is hashes/counts/status only.
- Active or `in_doubt` identity/extraction/TARGET/reconciliation/recovery work blocks erasure planning/execution.
- MCP exposes read-only status only; request/review/approval/execution stay outside LLM mutation authority.

See [`DATA_SUBJECT_RIGHTS.md`](DATA_SUBJECT_RIGHTS.md) and [`.agents/docs/PRIVACY_BOUNDARY_V0227.md`](.agents/docs/PRIVACY_BOUNDARY_V0227.md).
