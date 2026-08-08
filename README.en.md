[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.2

## Reconciliation & Recovery

v0.22.2 is the final consolidation-roadmap node. It does not widen database write permissions. It adds **read-only reconciliation and fail-closed recovery** after Controlled Target Insert and Identity Resolution.

```text
SOURCE SELECT-only
      ↓
validated + identity-resolved staging
      ↓
Controlled Target Insert
      ↓
TARGET
      ↓ SELECT-only reconciliation
expected whole-row fingerprints ↔ observed TARGET fingerprints
      ↓
matched / observed_none / observed_partial / mismatch
      ↓
Human recovery decision when commit outcome is uncertain
```

### Mandatory invariants

- Reconciliation reads TARGET only and scopes queries to business keys already approved in the identity policy/TARGET contract.
- No business-key value, query parameter, record value, PHI/PII, or credential is persisted in SQLite/audit/recovery checkpoints.
- Reconciliation compares keyed **whole-row fingerprints** for every inserted column, not counts alone.
- `in_doubt`/`committing` never auto-transition to committed or failed.
- `committed_verified` requires a `matched` reconciliation and explicit human confirmation.
- `not_committed_verified` requires `observed_none` plus human confirmation; only manual retry becomes eligible afterward.
- `observed_partial`/`mismatch` never trigger automatic UPDATE/DELETE/UPSERT/MERGE repair. They require manual intervention.
- SOURCE remains read-only throughout recovery.
- Pending local lineage can be rebuilt idempotently after a known commit; INSERT must not be retried just to repair lineage.
- Every recovery stage records a privacy-safe checkpoint hash for resume/audit.

### Schema 40

Adds `db_reconciliation_runs`, `db_reconciliation_findings`, `db_recovery_cases`, `db_recovery_checkpoints`, and `db_recovery_events`.

### Recovery semantics

```text
committed insert
    ↓ reconciliation
matched       → reconciliation complete
mismatch      → discrepancy / manual investigation

in_doubt | committing
    ↓ reconciliation
matched       → HUMAN may choose committed_verified
observed_none → HUMAN may choose not_committed_verified
                → manual retry only
partial       → manual_intervention only
mismatch      → manual_intervention only
```

### Read-only MCP additions

- `agentos.db_reconciliation_get`
- `agentos.db_reconciliation_summary_get`
- `agentos.db_reconciliation_spec_get`
- `agentos.db_recovery_cases_get`
- `agentos.db_recovery_readiness_get`
- `agentos.db_recovery_checkpoints_get`

MCP exposes no reconciliation execution, recovery decision, lineage finalization, TARGET mutation, raw values, or credentials.

See [.agents/docs/RECONCILIATION_AND_RECOVERY.md](.agents/docs/RECONCILIATION_AND_RECOVERY.md).

## Completed roadmap

```text
v0.20.0 Project Identity & Purpose Model
→ v0.20.1 Primary Project Selection & Domain Compatibility
→ v0.20.2 Primary-Project Consolidation
→ v0.21.0 Source/Target Database Boundary
→ v0.21.1 Target Schema Contract & Cross-DB Field Mapping
→ v0.21.2 Read-Only Extraction & Data Validation
→ v0.22.0 Controlled Target Insert
→ v0.22.1 Identity Resolution, Deduplication & Lineage
→ v0.22.2 Reconciliation & Recovery                     ← current
```

## Release validation

```text
v0.22.2 node tests:              18 passed
available full regression:       159 passed
schema:                          40
MCP read-only catalog:            37 tools
SOURCE write:                    forbidden
in_doubt automatic retry:        forbidden
partial TARGET automatic repair: forbidden
raw values in recovery state:    forbidden
```
