# AgentOS Instruction Authority

`AGENTS.md` is the only coding-agent instruction source in this repository.

## Core principles

- Understand the user's language directly; do not call a translation tool merely to parse intent.
- Preserve the original request and reply in the user's language.
- Keep technical identifiers in English unless the project explicitly requires otherwise.
- Work local-first. Unknown tools and writes outside approved scope fail closed.
- New files must be placed by responsibility, feature, layer, and lifecycle.
- Reuse stable shared capabilities; do not create generic monolithic `utils.py`, `helpers.py`, or `common.py` files.
- Keep temporary scripts, tests, fixtures, downloads, and validation artifacts under `.agents/runtime/`.

## Source documentation contract

Each source file must contain one header declaring:

- `File:` project-relative path;
- `Purpose:` module purpose;
- `Responsibilities:` bounded responsibilities.

Public classes, functions, and methods must document their contract at the symbol itself, including inputs, outputs, raised errors, and material side effects. Do not repeat the file path in every symbol.

## Guarded change workflow

Before creating or modifying code:

1. create and approve a task;
2. build or update the local symbol index;
3. run `prepare-change`;
4. read the recommended bounded context;
5. review similar symbols and duplicate candidates;
6. verify write permission;
7. execute the change;
8. run `docs-scan` for the affected source scope;
9. run tests, structural review, and synchronization checks.

A failed write check blocks execution.

## Evidence-grounded claims

Conclusions about business logic, security behavior, data visibility, destructive effects, or governance enforcement must be traceable to recorded tool evidence when required by `claim_policy`.

A high-risk claim must not be recorded or reported without at least one successful supporting tool call from the same task. Sensitive medium-risk claims also require evidence.

Evidence is local by default. Network evidence is rejected unless the active structured policy explicitly permits it and the relevant egress has been authorized and audited.

Use:

- `record-tool` to preserve a bounded execution record;
- `record-claim` to link a conclusion to evidence;
- `list-claims` to review task claims;
- `show-claim` to inspect the supporting tool calls.

## Governance changes

A governance change is incomplete when instruction text, structured configuration, runtime enforcement, tests, human documentation, changelog, or version identity materially disagree.

For every governance change, evaluate and report the status of:

- `AGENTS.md`;
- `.agents/config/governance.json`;
- `.agents/agentos/` runtime;
- `.agents/tests/`;
- `README.md` and `huong_dan.md`;
- `.agents/docs/`;
- `VERSION` and package version.


## v0.9.0 runtime repair gates

- Run `agentos docs-scan --scope <source-root-or-affected-path>` before reporting a source change complete. A failed source documentation scan blocks completion.
- Use `tool-guard` before governed tool execution. Unknown tools fail closed; network tools require reason, justification, and prior successful local evidence.
- Keep `record-tool` as the canonical evidence writer. `record-tool-result` records guard/audit outcomes and must not replace evidence records.
- Use `cache-lookup` before repeating an identical bounded file read and `cache-store` only for bounded, non-sensitive summaries. A stale cache entry must not be reused.

## Persistent task heartbeat and workflow gates (v0.9.0)

AgentOS workflow state is persisted outside the conversation context. Starting a task sets `.agents/runtime/current_task.json` and seeds `workflow_steps` from the configured workflow. Commands may resolve the current task when `--task-id` is omitted.

Before continuing a resumed task, inspect `whoami` or `next-step`. Do not bypass a pending required workflow step because a conversation is long or because a user asks to skip governance. A skipped step must be recorded with `mark-step --status skipped --note ...`; the reason is mandatory.

The final `report` command is fail-closed and must return a non-zero exit code while any required step other than `report` remains pending.

## Governance drift acknowledgement

Governance files are compared against a human-acknowledged hash baseline. Use `drift-check` and `drift-diff` to review changes. A coding agent must not call `ack-baseline` on behalf of the user. Human acknowledgement is required after reviewing intentional governance changes.

## Safe installation and local policy

Installers must preserve existing root files. Conflicting files are written with an `.agentos` suffix for manual merge. Project-specific overrides belong in `.agents/config/governance.local.json`; the canonical `.agents/config/governance.json` remains the distributed baseline.

## v0.9.0 trust-boundary rules

- Never use direct `record-tool`; obtain a guard token and complete that token.
- Never supply or override tool classification. Runtime classification is authoritative.
- Do not mark automated-only workflow steps done manually.
- Use a distinct session ID for each concurrent agent or IDE session.
- Do not approve sensitive local overrides or acknowledge baselines on behalf of a human.
- Do not report completion while baseline, drift, provenance, or override gates are blocked.


## v0.11.0 proxy-only enforcement boundary

For filesystem, process, and network capabilities, the MCP gateway or `proxy-execute` is the only permitted production execution path. Legacy `guard-tool` and `complete-tool` commands are disabled while `tool_policy.proxy_only_mode` is true.

`process.exec` is not a general shell. It must use an allowlisted executable and a recognized test, build, lint, or inspection profile. Shell interpreters, network clients, inline code, URL-bearing commands, out-of-root working directories, and secret-bearing environment variables are forbidden. Source mutation must use `agentos.write_file`.

`network.http` is default-deny and must validate the approved HTTPS domain, DNS-resolved address, and every redirect destination.

External audit keys must remain outside the repository. Historical public keys must be retained. Key rotation must be recorded with `rotate-audit-key`, and the external chain must pass `audit-verify` before final reporting.

## Historical v0.10.1 MCP enforcement boundary

When the AgentOS MCP proxy is available, all filesystem, process, network, Git, database, deployment, and secret-access operations must pass through the proxy. Do not call or expose a backend tool directly. A proxy deployment is not an enforcement boundary while the agent retains any bypass path.

The proxy must derive capability and classification, bind the request to the active task and session, evaluate approval, workflow, scope, drift, overrides, and egress policy, invoke the backend itself, and create canonical evidence from the actual result.

Signed external audit records must be stored outside the repository. The coding agent must not receive the signing private key or write/delete access to the audit home. A failed audit write blocks filesystem writes, process execution, and network calls.

## v0.13.0 concurrent work coordination

Every concurrent CLI or agent process must use a unique session identifier. A task has one writer-owner session unless an explicit audited handoff occurs.

Filesystem writes must go through the AgentOS proxy. Existing-file writes require the content hash returned by the most recent proxy read. The proxy must acquire an exclusive file lease, compare the expected hash, perform an atomic replacement, record the new file version, and release the lease. Never retry a `stale_write_conflict` by dropping the expected hash; reread, reconcile, and submit a new change.

Do not share one session ID between concurrent processes. Do not modify another task's leased resource. Use the audit daemon when multiple proxy processes are active.

## v0.20–v0.22 extension policies

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

<!-- AGENTOS_V0223_CORE_REINTEGRATION_BEGIN -->
## AgentOS v0.22.3 — Core Reintegration & Release Integrity

- A release MUST contain the historical governance core and the v0.20-v0.22 extensions together; feature-only packages are invalid.
- `.agents/agentos/db.py` is the central SQLite connection/migration authority and MUST expose `connect`, `migrate`, and schema migrations 1 through 40.
- `CURRENT_SCHEMA_VERSION` in `schema_version.py` is the single schema-version source of truth; feature modules MUST NOT declare divergent current schema constants.
- SQLite connections through the core persistence layer MUST enable foreign keys and busy timeout.
- The v0.19.5 compatibility launchers MUST delegate to the real core CLI/MCP server; silent `exit 0` and echo-only `cat` backends are forbidden.
- Historical `test_agentos.py` and current extension tests are both release-critical regression coverage.
- `governance.json` MUST retain the core governance sections and all v0.20-v0.22 policy sections.
- Runtime caches (`__pycache__`, `*.pyc`, `.pytest_cache`) MUST NOT be shipped as authoritative release source.
- Release packaging MUST generate and verify `MANIFEST.json` and `CHECKSUMS.sha256`; a hash mismatch fails closed.
- v0.22.3 restores integrity only. Full task/session enforcement and signed audit for database-domain mutations is scheduled for v0.22.4.
<!-- AGENTOS_V0223_CORE_REINTEGRATION_END -->



<!-- AGENTOS_V0224_UNIFIED_GOVERNANCE_ENFORCEMENT_BEGIN -->
## AgentOS v0.22.4 — Unified Governance Enforcement & Signed Audit

- Every privileged v0.21-v0.22 database-domain mutation on a valid AgentOS project MUST run inside one task/session-bound governed operation.
- The task MUST be approved, the caller session MUST own it, and the `approve_task` workflow step MUST already be complete.
- Governance baseline MUST be initialized and unacknowledged drift MUST block mutation. Sensitive local overrides MUST already be approved.
- One business operation MUST consume one single-use `guard_tool` execution token and MUST complete it exactly once; do not issue tokens per internal SQL statement.
- A signed `governed_operation.request` event MUST exist before mutation. Privacy-safe domain events MUST be mirrored to Ed25519 signed audit. Completion/denial MUST also be signed.
- Failure to write required signed audit evidence MUST fail closed.
- Domain event rows MUST correlate to `governed_operation_id` and `external_event_hash` where schema 41 provides those fields.
- SOURCE writes, raw/generic TARGET writes, automatic identity decisions, automatic `in_doubt` recovery, and automatic partial-target repair are non-overridable safety invariants.
- MCP MUST remain read-only for privileged database-domain operations.
- Database-domain modules MUST use the central AgentOS SQLite connection policy; local independent `sqlite3.connect()` state paths are forbidden.
<!-- AGENTOS_V0224_UNIFIED_GOVERNANCE_ENFORCEMENT_END -->
