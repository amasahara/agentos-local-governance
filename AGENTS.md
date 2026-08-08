# AGENTS

<!-- AGENTOS_V0200_PROJECT_IDENTITY_BEGIN -->
identity

<!-- AGENTOS_V0201_PRIMARY_SELECTION_BEGIN -->
## AgentOS v0.20.1 — Primary Project Selection & Domain Compatibility

- Multi-project consolidation must have exactly one Primary Project.
- The LLM may analyze candidates and recommend a primary, but only a human may commit the selection.
- A committed Primary Project must be the currently active AgentOS root. If another project should be primary, re-run the workflow from that project; do not write selection state into a future secondary project.
- Candidate/source projects are read-only during discovery and compatibility analysis.
- `domain.id` mismatch is an absolute consolidation blocker in v0.20.1 and cannot be overridden by capability overlap or technical similarity.
- Same domain + same `purpose.id` is compatible.
- Same domain + different `purpose.id` is only conditionally compatible and requires explicit human confirmation with a business reason.
- Compatibility for consolidation is evaluated from the selected primary to every source; sources do not need to be mutually dependent or directly compatible with each other.
- v0.20.1 does not copy, move, merge, or rewrite project source code. Physical consolidation begins only in v0.20.2.
<!-- AGENTOS_V0201_PRIMARY_SELECTION_END -->

<!-- AGENTOS_V0202_PRIMARY_CONSOLIDATION_BEGIN -->
## AgentOS v0.20.2 — Primary-Project Consolidation

- Consolidation MUST have exactly one Primary Project previously selected by a human through v0.20.1.
- Every Secondary Project MUST remain read-only. Never create, update, delete, rename, chmod, migrate, or persist AgentOS state in a Secondary Project.
- Only the active Primary Project may receive consolidation writes.
- The Primary Project's `AGENTS.md` and governance policy remain authoritative; Secondary governance files MUST NOT be imported or overwrite Primary governance.
- Every source component MUST have an explicit action: `REUSE`, `MOVE`, `ADAPT`, `REIMPLEMENT`, `IGNORE`, or `CONFLICT`.
- `MOVE` means copy exact source bytes into Primary; it MUST NOT delete or modify the source.
- `CONFLICT` MUST block plan review/approval until resolved in a revised plan.
- Human review and human approval are mandatory. Approval MUST bind to the exact `plan_hash`.
- Before each write, re-verify source identity/manifest/file hash and target expected hash or expected absence.
- Writes MUST be atomic and constrained to approved non-governance paths under the Primary root.
- Every executed component MUST record provenance. Replacing an existing target MUST create a rollback backup inside Primary runtime.
- MCP may expose read-only consolidation state but MUST NOT expose approval, execution, or rollback mutations to LLMs.

<!-- AGENTOS_V0210_DATABASE_BOUNDARY_BEGIN -->
## AgentOS v0.21.0 — Source/Target Database Boundary

Database consolidation is directional and fail-closed.

- Every database consolidation has exactly one TARGET and one or more SOURCE connections.
- SOURCE connections are immutable inputs: catalog/metadata and SELECT-style reads only.
- INSERT, UPDATE, DELETE, MERGE/UPSERT, DDL, and side-effect stored procedures are forbidden on SOURCE.
- Read-only verification must use grants/account/session policy or external attestation; never probe production by attempting a write.
- Raw DB credentials/DSNs must not be stored in the repository, AgentOS SQLite, audit logs, or LLM context. Store only credential references.
- SOURCE and TARGET must share the same business domain for one consolidation plan.
- One connection cannot act as both SOURCE and TARGET in the same consolidation.
- v0.21.0 does not enable data writes to TARGET. Target schema contract arrives in v0.21.1 and controlled INSERT in v0.22.0.
- LLM/MCP may inspect redacted boundary state and ask for authorization decisions, but may not register endpoints, attest read-only status, or mutate consolidation membership.
<!-- AGENTOS_V0210_DATABASE_BOUNDARY_END -->

<!-- AGENTOS_V0211_SCHEMA_MAPPING_BEGIN -->
## AgentOS v0.21.1 — Target Schema Contract & Cross-DB Field Mapping

- Target schema is authoritative. AgentOS MUST NOT infer or create TARGET structure from SOURCE schemas.
- Every TARGET contract MUST be backed by an active TARGET schema snapshot and validated table-by-table, column-by-column against that snapshot.
- v0.21.1 handles catalog/schema metadata only. Business record extraction remains disabled until v0.21.2 and TARGET writes remain disabled until v0.22.0.
- SOURCE schema snapshots may only be registered after v0.21.0 read-only verification and only as metadata manifests; no record values may be stored in schema snapshots.
- Mapping direction is always `registered SOURCE -> approved TARGET contract`; SOURCE-to-SOURCE mapping is forbidden.
- A field mapping MUST reference a SOURCE snapshot from a SOURCE already registered in the same database consolidation.
- A field mapping MUST reference an approved TARGET contract from the same database consolidation.
- Mapping evidence and canonical type compatibility are mandatory. Coercible types require an explicit transform rule; incompatible types require an explicit transform rule whose declared output type equals the TARGET canonical type.
- Human confirmation is mandatory before a proposed mapping becomes `confirmed`. LLM suggestions are advisory only and MUST NOT persist or confirm mappings through MCP.
- Every mapping is bound to both `source_snapshot_hash` and `target_contract_hash`. New SOURCE snapshots or TARGET schema drift MUST stale dependent mappings.
- A new TARGET snapshot supersedes contracts tied to the old snapshot. Approval MUST be re-established against the new structure.
- MCP may expose read-only snapshot/contract/mapping state and advisory suggestions, but MUST NOT expose snapshot registration, contract approval, mapping confirmation/rejection, data extraction, arbitrary SQL, or TARGET writes.
<!-- AGENTOS_V0211_SCHEMA_MAPPING_END -->

<!-- AGENTOS_V0212_READ_ONLY_EXTRACTION_BEGIN -->
## AgentOS v0.21.2 — Read-Only Extraction & Data Validation

- SOURCE extraction is allowed only from a SOURCE that remains `readonly_verified`, active, and registered in the same database consolidation.
- Extraction MUST use an immutable batch built only from confirmed/current v0.21.1 mappings and an approved/current TARGET contract.
- Re-verify `source_snapshot_hash`, `target_contract_hash`, `mapping_hash`, and extraction-plan hash immediately before SOURCE access.
- SQL is generated by AgentOS from validated identifiers and confirmed mapped columns only. `SELECT *`, arbitrary SQL, user-supplied WHERE/DDL/DML, and side-effect procedures are forbidden.
- v0.21.2 may read business rows from SOURCE but MUST NOT write to SOURCE or TARGET. TARGET INSERT remains disabled until v0.22.0.
- Transformation execution is allowlist-only and deterministic. Never `eval`/`exec` transform rules or dynamically load unapproved transformation code.
- Every row must be transformed into TARGET-contract shape and validated before staging. Invalid rows are rejected/quarantined and are never silently coerced into acceptable output.
- SQLite/audit MUST NOT store raw business record values. Validation findings store value hashes only; raw quarantine values are disabled by default.
- Valid transformed rows may exist only in local `.agents/runtime/data-staging/` artifacts with owner-only permissions, content hashes, and a manifest; this path MUST be Git-ignored.
- MCP may expose batch metadata, validation summaries, value-hash findings, and artifact-integrity status only. MCP MUST NOT run extraction, resolve credentials, expose staged record contents, accept raw SQL, or write TARGET data.
<!-- AGENTOS_V0212_READ_ONLY_EXTRACTION_END -->

<!-- AGENTOS_V0221_IDENTITY_RESOLUTION_BEGIN -->
## AgentOS v0.22.1 — Identity Resolution, Deduplication & Lineage

- New TARGET INSERT plans require a resolved v0.22.1 identity-resolution run.
- Identity policy must use a TARGET-contract business key and requires explicit human review + approval.
- Exact business-key matching may auto-bind only under that approved deterministic policy.
- Strong multi-field matches are candidates only and require explicit human confirm/reject; LLM/MCP must never decide identity.
- Fuzzy/embedding similarity may not auto-merge canonical entities.
- Persist only pseudonymous HMAC tokens/hashes in AgentOS state/audit; raw identity/PHI/PII remains local staging data.
- Deduplicate intra-batch and cross-batch before TARGET INSERT while preserving lineage from every SOURCE binding.
- Never reinsert an entity that already has committed TARGET lineage.
- If TARGET commit succeeds but lineage finalization is pending, never retry the INSERT.
<!-- AGENTOS_V0221_IDENTITY_RESOLUTION_END -->

<!-- AGENTOS_V0222_RECONCILIATION_RECOVERY_BEGIN -->
## AgentOS v0.22.2 — Reconciliation & Recovery

- TARGET reconciliation MUST be SELECT-only and scoped to business keys already approved by the identity policy/TARGET contract.
- Reconciliation MUST compare privacy-safe keyed whole-row fingerprints for all inserted columns; row counts alone are insufficient evidence.
- Never persist business-key values, TARGET row values, reconciliation query parameters, PHI/PII, credentials, or raw result rows in AgentOS SQLite/audit/checkpoints.
- `committing` and `in_doubt` insert runs MUST NOT auto-retry and MUST NOT auto-resolve to committed/failed.
- `committed_verified` requires a completed `matched` reconciliation plus explicit human confirmation.
- `not_committed_verified` requires a completed `observed_none` reconciliation plus explicit human confirmation. It may enable manual retry of the existing approved plan; automatic retry remains forbidden.
- `observed_partial` or `mismatch` MUST require manual intervention. AgentOS MUST NOT automatically UPDATE, DELETE, UPSERT, MERGE, or otherwise repair TARGET data.
- SOURCE writes remain forbidden during reconciliation and recovery.
- Pending local lineage may be rebuilt idempotently only for a known committed insert receipt; never retry TARGET INSERT merely to repair lineage.
- Recovery checkpoints/evidence MUST contain hashes/counts/status only and remain privacy-safe.
- MCP may expose read-only reconciliation/recovery summaries but MUST NOT expose reconciliation execution, recovery decisions, lineage-finalization mutation, credentials, or raw values.
<!-- AGENTOS_V0222_RECONCILIATION_RECOVERY_END -->
