## v0.31.2 — Closed-Loop Skill & Policy Improvement

- Schema remains 64; no migration 65.
- Reuses human-approved procedural memory for non-active skill candidates.
- Revalidates learning evidence before closed-loop skill graduation.
- Uses repeated observational adverse evaluations for policy readiness.
- Requires an explicit policy patch; may simulate but never auto-activate policy.
- MCP remains read-only at 132 tools and authority classes are unchanged.

## v0.31.1 — Governed Memory Promotion & Context Binding

- Schema remains 64; no migration 65.
- Reuses project_memory candidate state, learning links, and Human Decision.
- Requires distinct verified tasks, source freshness, architecture match, and cooldown.
- Candidate flagging may be automatic; activation is human-confirmed and privileged.
- Promoted memory remains project evidence with no instruction authority.

## v0.31.0 — Governed Learning Signal Integration

- Schema 63 → 64.
- Governed learning signal/link/knowledge-usage integration.
- Raw learning signals remain outside context retrieval and instruction authority.

## v0.30.1 — Release & Schema Metadata Coherence
- Release/schema coherence prerequisite only; database schema remains 63.
- Bootstrap schema remains 46; post-baseline migrations are exactly 47..63.
- Generated effective policy, package completeness, manifest, and checksums are regenerated from authoritative sources.
- Historical release-coherence fixtures without a declared schema-bootstrap contract remain valid.
- v0.30.0 Context Authority and bounded v0.29.5/v0.29.4 Windows predecessor contracts remain preserved.
## v0.30.0 — Context Authority & Untrusted Provenance

- Added deterministic source-origin context authority/provenance classification.
- Evidence, tool output, external content, generated summaries, and unknown
  provenance do not gain AgentOS instruction authority from their text.
- Added schema 63 hash/label-only provenance state and Context Transport
  `provenance_manifest_hash` / `context_authority_hash` pins.
- Added four read-only CLI commands and four read-only MCP inspection tools.
- Added bounded structural attestation and explicit broad non-claims.
- Prompt-injection elimination, semantic correctness, universal model
  manipulation prevention, replacement of human review, and general host
  isolation remain explicitly unclaimed.
- Database schema is 63.

## v0.29.5 — Native Physical Isolation Extensions

- Added bounded Windows Low Integrity enforcement for AgentOS-mediated sync and async worker roots.
- Added Low mandatory-label sandbox SACLs with `NO_WRITE_UP` plus a bounded current-user DACL accessibility contract.
- Production sandboxes require the controlled `*.agentos-sandboxes` ancestry; unrelated parent directories are not modified.
- Added dedicated physical-isolation structural attestation, focused Windows CI, release activation, and release-integrity gates.
- Activated only `low_integrity_attested` and `sandbox_low_integrity_label_attested` inside `windows_physical_isolation_policy`.
- General host-filesystem isolation, general OS write confinement, primary-root-wide write confinement, desktop isolation, credential isolation, and same-user host-bypass resistance remain unclaimed.
- Schema remains 62.

## v0.29.4 — Windows Restricted Execution
- AgentOS-mediated Windows production process execution requires a verified
  Restricted Token on sync and async worker-root paths.
- Profile is `DISABLE_MAX_PRIVILEGE | LUA_TOKEN`; `SANDBOX_INERT` is forbidden.
- Child-token verification and Job Object assignment must complete before
  resume.
- Restricted production paths have no unrestricted fallback or caller
  downgrade.
- Async broker remains the trusted named Job Object lifecycle owner.
- Fail-closed negative tests and structural attestation are mandatory.
- `restricted_token_attested = true` is bounded to
  `agentos_mediated_process_execution`.
- Low Integrity and broader host/OS isolation claims remain false.
- Database schema remains 62.
## v0.29.3 — Sandbox Configuration & Credential Boundary
- Governed sandbox/runtime-profile configuration with deterministic configuration/reference hash binding.
- Reference-only `secret://alias` process credential bindings reuse the trusted Secret Resolver and provider capability approval.
- Sync credentials resolve immediately before launch with exact-value captured-output redaction.
- Async jobs persist credential hashes/count only, verify immutable spec before resolution, and do not persist stdout/stderr for credential-bearing jobs.
- Added independent credential-boundary structural attestation and focused Ubuntu/Windows CI validation.
- Preserved v0.29.1 Windows process-tree containment and v0.29.2 sandbox/runtime-profile enforcement.
- Activated bounded claims only within `agentos_mediated_process_execution`.
- Credential isolation, Restricted Token, Low Integrity, host-filesystem isolation, OS write confinement, same-user host-bypass resistance, and Windows file-secret projection remain unclaimed.
- Database schema remains 62.
## v0.29.2 — Windows Sandbox Workspace & Tool Runtime Profiles

- Added deterministic tool runtime profiles and bounded sandbox workspaces for
  AgentOS-mediated process execution.
- Added sync/async runtime-profile enforcement, async snapshot/hash pinning and
  pre-launch revalidation, sandbox-local mutable-state redirects, and terminal
  cleanup evidence.
- Preserved v0.29.1 Windows process-tree containment and its Windows CI
  activation regression.
- Activated only the bounded `runtime_profile_sandbox_attested` claim.
- Restricted Token, Low Integrity, credential isolation, host-filesystem
  isolation, OS write confinement, general host isolation, and same-user
  host-bypass resistance remain explicitly unclaimed.
- Database schema remains 62.

## v0.29.1 — Windows Process-Tree Containment

- Windows process execution mediated by AgentOS must use Job Object containment.
- Root user-mode execution begins only after successful Job assignment.
- Synchronous timeout/teardown terminates or closes the contained Job tree.
- Async execution uses a dedicated broker that owns a named `KILL_ON_JOB_CLOSE` Job Object.
- Async cancellation and timeout terminate the named Job tree, not only the root PID.
- Broker loss is fail-closed for the contained worker tree.
- Normal async terminal state is bound to broker completion evidence including the root exit code.
- v0.29.1 release integrity requires a `windows-latest` CI job containing both the focused containment suite and full regression.
- Release scope is `agentos_mediated_process_execution`; same-user host bypass resistance, general OS isolation, and arbitrary host-process containment are not claimed.
- Release is **0.29.1**; database schema remains **62**.

## v0.29.0 — Independent Completion Verification

- Added schema 62 independent completion receipts bound to exact subject hash, required checks, evidence, and reviewer authority.
- Producer task/session/assignment cannot self-establish accepted completion.
- Workflow report finalization, worker completion, and integration readiness revalidate the current receipt and fail closed on stale subjects.
- Added agent-plane completion CLI commands and one read-only MCP completion status tool; MCP completion mutation remains forbidden.
- Release is 0.29.0; database schema is 62.
- Completion is attested as producer-independent and evidence-bound only within `agentos_mediated_agent_execution`.

## v0.28.4 — Tool Exclusivity & Enforcement Attestation
  * Added deterministic enforcement attestation for AgentOS-mediated execution surfaces.
  * Routed synchronous test execution and asynchronous job execution through canonical governed process boundaries.
  * Revalidated async execution authority immediately before the actual subprocess side effect.
  * Active MCP runtime remains bound to the trusted enforcement gateway with no legacy subprocess forwarding.
  * Added process-primitive classification for canonical, internal-governance, and inactive-legacy execution sites.
  * Integrated fail-closed attestation into runtime health, doctor, policy validation, and release integrity.
  * Tool-exclusivity scope is limited to agentos_mediated_agent_execution; OS-level isolation and same-user host bypass resistance are not claimed.
  * Release is 0.28.4; database schema remains 61.
## v0.28.3 — Privileged Control Plane Separation

- Separated normal agent execution from human/operator privileged authority.
- Added `agentos-admin` as the privileged control-plane launcher.
- Agent discovery and execution no longer expose privileged commands.
- `project-adopt` and `architecture-init` use argument-level dual-plane enforcement.
- MCP and Web retain no privileged mutation authority.
- Existing task/session, approval, baseline/drift, token, and signed-audit enforcement remains authoritative.
- Release is 0.28.3; database schema remains 61.

## v0.28.2 — Project Bootstrap & Repository Normalization
- Added no new security feature; normalized repository bootstrap and release payload.
- Separated authoritative distribution metadata from installed-project metadata.
- Added `project-init` and `project-adopt` with generated project UUID and `UNCONFIRMED` purpose.
- Excluded AgentOS root docs, release tests, historical docs, historical launchers, and historical tools from the current installed payload.
- Added modular policy sources, deterministic effective-policy generation, and role-aware repository validation.
- Release is 0.28.2; database schema remains 61.
## v0.28.1 — Optional Local Web Control Plane
- Added an opt-in, foreground, loopback-only local Web Control Plane on the v0.28.0 Command Center Snapshot.
- Added one-time fragment bootstrap plus ephemeral HttpOnly/SameSite browser sessions with Host/Origin validation.
- Added CSP/no-store/frame/referrer/CORP/Permissions-Policy hardening; no CORS, WebSocket or external assets.
- Added no AgentOS mutation endpoints, no direct database access, no privileged CLI execution and no new MCP tools.
- Database schema remains 61; MCP remains 123 tools.

## v0.28.0 — Architecture & Agent Command Center
- Added one privacy-safe read-only Snapshot v1 across Architecture, execution, compliance and pending human/operator actions.
- Added deterministic terminal TUI plus JSON/section/action CLI projections without persisting a second dashboard state.
- Added three MCP read-only Command Center tools; no mutation/approval/worker-launch authority is exposed.
- Database schema remains 61; v0.27.3 workspace/integration and all earlier governance authorities are unchanged.
- Optional local Web Control Plane remains reserved for v0.28.1 and must consume the same read model.

## v0.27.3 — Isolated Workspace & Controlled Integration
- Added schema 61 isolated worktree, diff/hash, proposal and integration event state.
- Executor filesystem/process routing is bound to the exact worker task/session worktree while primary AgentOS remains state/lease/audit authority.
- Changed files must stay within worker plan; sealed workspaces require architecture, security and governed-test gates.
- Primary drift is checked with Git semantic diff against the pinned base commit, avoiding CRLF/LF false conflicts while remaining fail-closed; conflicts are never auto-resolved.
- Controlled integration requires human review/approval plus parent-task scope, leases, CAS/hash verification, backup and rollback.
- AgentOS never invokes Git merge, auto-commit or auto-push; MCP adds four read-only workspace/integration inspection tools only.

## v0.27.2 — Multi-Agent Worker Supervisor
- Added schema 60 governed supervisor/worker/dependency/event state.
- Coordinates only existing approved worker tasks, ACTIVE architecture-aware plans, capability sessions, and collaboration roles.
- Enforces parent-plan file/architecture containment, acyclic worker dependencies, and overlapping executor planned-write blocking.
- Optional skill binding accepts only current eligible/recommendable graduated Contract-v2 selections from v0.27.1.
- Does not create/approve tasks or plans, issue capabilities, execute skills, select model/providers, or launch worker processes.
- MCP adds three read-only supervisor status/workers/readiness tools; mutation remains governed CLI/operator authority.
- Isolated workspace and controlled integration remain reserved for v0.27.3.
## v0.27.1 — Architecture-Aware Skill Selection & Evaluation

- Skill selection is explicit, deterministic and advisory; it does not modify task/architecture authority.
- Only graduated current Contract-v2 skills are selection-eligible.
- Least-authority compatibility now checks plan architecture sections, write targets, capabilities, tools, dependencies, external services and tests.
- Evaluation is observational only and cannot automatically mutate skill lifecycle or future ranking weights.
- MCP adds read-only selection/evaluation inspection only.
- Current release distribution remains Latest Full Release with no updater script and project-owned partition preservation.

## v0.27.0 — Governed Skill Contract v2

- Added deterministic Skill Contract v2 with schema 58 and least-authority defaults.
- Bound architecture-sensitive skill validation to the exact ACTIVE human-approved Architecture Baseline.
- Preserved human-only graduation/revocation, legacy v1 artifacts, and read-only MCP inspection.
- Switched current distribution to download-latest-full-release with no version-specific updater scripts; project-owned skills/workflows/source/state are excluded from the managed release payload.

## v0.26.3 — Quality/Operational Enforcement

- Added deterministic quality/security/operational enforcement for ARCH-15..21.
- Added schema 57 quality runs/findings and three read-only MCP inspection tools.
- Generic best practices and LLM inference do not become Architecture Authority.

## v0.26.2 — Runtime/Data/API & Business Boundary Enforcement

- Added deterministic enforcement for ARCH-06/07/08/09/10/11/13/14.
- Added schema 56 runtime-boundary runs/findings and three read-only MCP inspection tools.
- Preserved human-only Architecture Authority; no LLM approval/waiver/activation authority was added.

## v0.25.3 — Architecture Discovery & Evidence Binding
- Added schema 51 for deterministic static architecture scan runs, observations, evidence bindings, and advisory discrepancies.
- Discovery is read-only: project code is not executed, network access and symlink traversal are forbidden, and raw source text is not persisted in AgentOS state.
- Evidence is bound by project-relative path, SHA-256, and bounded locator metadata; scanner output cannot mutate or activate the 27-section Architecture Contract.
- Added five CLI discovery commands and four read-only MCP inspection tools; scan execution and architecture mutation remain outside MCP.
- Added an ownership-aware update preservation boundary: project source, `AGENTS.md`, local governance overrides, architecture working copy, skills, workflows, and runtime/state artifacts are never overwritten by the updater.
- AgentOS-managed distribution files require exact baseline hashes before replacement; post-migration failure restores both distribution files and the SQLite state snapshot.
- Architecture discrepancy findings remain advisory in v0.25.3; drift/compliance enforcement is reserved for v0.25.4.

## v0.25.2 — 27-Section Architecture Contract & Human Clarification Gates
- Added the fixed 27-section Architecture Contract registry `ARCH-01` through `ARCH-27`.
- Added immutable architecture baselines with deterministic content hashing and human-only review, approval, activation, rejection, and supersession lifecycle.
- Added structured requirement clarity assessment and the Grill Me gate before task approval.
- Added blocking Human Decision requests for material ambiguity discovered before or during execution.
- Added fail-closed mutation blocking while dependent human decisions remain unresolved.
- Added human resolution impact handling for requirement, scope, plan, and architecture changes.
- Added protected human clarification/decision authority to the task control plane.
- Added read-only Architecture MCP inspection and the monotonic `agentos.human_decision_request` blocker signal; MCP cannot resolve, waive, approve, or activate human authority.
- Added database schema 50 while preserving schema bootstrap baseline 46.
- Preserved `AGENTS.md` as the only coding-agent instruction authority.

## v0.25.1 — Release Metadata Coherence
- **User requirement:** establish one coherent release identity before starting the 27-section Architecture Contract roadmap.
- **Decision:** make `VERSION` the release-version source of truth and add a fail-closed read-only coherence validator across runtime, policy, manifest, package completeness, and current-release identity docs.
- **Packaging:** synchronize `PACKAGE_COMPLETENESS.json` before manifest hashing; generated `VALIDATION_REPORT*.json` remains outside clean-main authoritative source.
- **Documentation:** current version/schema checks follow explicit `documentation_policy` file lists so historical schema references are not treated as current drift.
- **Compatibility:** database schema remains 49; schema bootstrap, SOURCE/TARGET, privacy, signed audit, context, and MCP authority are unchanged.
## v0.24.3 — MCP Feature Runtime Refactor
- **Decision:** active MCP feature handlers may not be owned/imported from legacy gateway modules.
- **Core boundary:** governed core tools keep gateway_client → gatewayd enforcement.
- **Authority:** no MCP mutation permission or database schema migration is introduced.

## v0.24.2 — DB-Aware Context Projection
- **Decision:** schema/mapping/manifest compression is deterministic and reversible.
- **Boundary:** codecs apply only to Evidence Plane; Control Plane remains lossless.
- **Persistence:** only hash/count/codec telemetry is stored.
- **MCP:** read-only telemetry only.

## v0.24.1 — Risk-Tiered Batch Review
- **Decision:** only deterministic LOW-risk component mappings may share one signed human review bundle.
- **Safety:** bundle and mapping hashes are pinned to the exact plan; plan drift makes prior bundle reviews stale.
- **Authority:** MEDIUM/HIGH remain individual human review, CONFLICT remains blocked, and existing whole-plan approval/execution authority is unchanged.
- **MCP:** read-only inspection only; no review/approval mutation.

# Changelog
## v0.23.4 — Incremental Symbol Index
- **Decision:** persist content hashes for indexed Python files and parse only new/changed bytes.
- **Safety:** first post-upgrade run bootstraps metadata with a full rebuild; parse failure rolls back the transaction; source path escape is blocked.
- **Performance contract:** no-change parse count is zero; one-file change parses one file; deleted files remove stale rows. Timing remains advisory until environment-pinned.
- **Authority:** no MCP mutation is added and database/privacy/context governance boundaries are unchanged.

## v0.23.3 — Consolidation Cockpit & Performance Baseline
- **User requirement:** aggregate the complete consolidation pipeline status and establish a measurable performance baseline before concurrency/index optimizations.
- **Decision:** add a SQLite read-only cockpit spanning candidate/primary selection, project consolidation, DB boundary, schema/mapping, extraction, identity, controlled insert, reconciliation and recovery.
- **Performance baseline:** benchmark fresh schema migration, the current full-rebuild `index_build`, and cockpit latency only in temporary/non-mutating fixtures; absolute wall-clock thresholds remain disabled until the environment is pinned.
- **MCP boundary:** add read-only `agentos.consolidation_status_get` and `agentos.performance_baseline_get`; benchmark execution remains CLI/operator-only.
- **Compatibility:** schema remains 46; SOURCE read-only, Controlled Target Insert, human risk gates, signed audit, privacy/secret/key and lossless Context Control Plane remain unchanged.


## v0.23.0 — Requirement-Preserving Context Compression

- User requirement: compress LLM transport tokens without changing user requirements, constraints, authority, safety rules, or approved scope.
- Decision: add a lossless Control Plane and deterministic/extractive Evidence Plane derived from canonical Context Pack.
- Enforcement: 100% Requirement Preservation Gate, source/authority/plan/scope/hash freshness, token-budget fail-closed, read-only MCP expansion.
- Runtime: `context_transport.py`, CLI/MCP registries, schema migration 44.
- Tests: preservation, tokenizer fallback, exact dedup, omission handles, stale-source blocking, integrity tamper, evaluation metrics, MCP no-mutation boundary.
- Migration: 43 → 44.

## v0.20.0 — Project Identity

## v0.20.1 — Primary Project Selection & Domain Compatibility

**User requirement:** Before consolidating projects, identify one main/primary project and allow consolidation only when projects serve the same business domain/purpose.

**Decision:** Added read-only candidate scanning, deterministic domain/purpose compatibility, advisory primary ranking, human confirmation for conditional purpose compatibility, and human-only primary selection. Domain mismatch is fail-closed and non-overridable.

**Runtime enforcement:** `.agents/agentos/project_selection.py`, CLI human gates, read-only MCP sidecar, schema 33.

**Documentation:** README and developer guide remain split into Vietnamese/English files linked from compact GitHub landing pages.

**Migration:** v0.20.0 schema 32 → v0.20.1 schema 33. No project source is consolidated in this release.

<!-- AGENTOS_V0202_CHANGELOG_BEGIN -->
# Rules & Workflow Changelog — v0.20.2

## User requirement

Consolidate multiple projects into one user-selected Primary Project, provided they already passed v0.20.1 business-domain/purpose compatibility. Secondary projects must remain read-only.

## Decision

Added Primary-Project Consolidation as a directed, plan-hashed workflow:

`selected primary → explicit mappings → human review → human approval → guarded primary-only materialization → provenance → completion/rollback`

## Enforcement

- Schema 34 consolidation state.
- Secondary metadata and component reads only.
- Primary-root identity authority check.
- Reserved governance path block.
- Source manifest/file hash verification.
- Target expected-hash/expected-absence verification.
- Atomic target writes and rollback backup.
- Read-only MCP visibility; no LLM mutation tools.

## Version

`0.20.2`

<!-- AGENTOS_V0210_CHANGELOG_BEGIN -->
## v0.21.0 — Source/Target Database Boundary

- Added database connection registry with explicit `SOURCE` / `TARGET` role.
- Added schema 35 tables for connections, consolidations, sources, and boundary evidence.
- SOURCE is catalog/SELECT-only and must be explicitly verified read-only before registration in a consolidation.
- Read-only verification by attempted write is forbidden.
- Raw credentials and DSNs are forbidden; only secret references are persisted and all read APIs redact them.
- Each database consolidation has exactly one TARGET and the same business domain across TARGET/SOURCE.
- Target writes remain disabled in v0.21.0; controlled INSERT is reserved for v0.22.0.
- Added read-only MCP tools for connection/consolidation inspection and abstract authorization checks.
<!-- AGENTOS_V0210_CHANGELOG_END -->

## v0.21.1 — Target Schema Contract & Cross-DB Field Mapping

- Added schema 36 metadata tables for schema snapshots, target contracts, field mappings, and evidence events.
- Target contract is authoritative and must validate against an active TARGET snapshot.
- SOURCE snapshots remain metadata-only and require prior read-only verification.
- Mapping direction is SOURCE→TARGET only; human confirmation is required.
- Mapping suggestions are local/read-only advisory output.
- Snapshot/contract drift invalidates dependent mappings fail-closed.
- Record extraction remains deferred to v0.21.2; TARGET INSERT remains deferred to v0.22.0.

## v0.21.2 — Read-Only Extraction & Data Validation

- Added schema 37 extraction batches, pinned mapping sets, validation findings, and extraction evidence.
- Enabled business-record reads from verified SOURCE databases via AgentOS-generated SELECT-only statements.
- `SELECT *`, arbitrary SQL, SOURCE writes, TARGET writes, and dynamic transform execution are fail-closed.
- Valid rows are transformed into approved TARGET-contract shape and stored only in local hashed staging artifacts.
- Invalid rows are quarantined with value hashes and rule evidence; raw record values are not stored in SQLite/audit.
- MCP exposes read-only summaries/integrity only; extraction execution and staging contents stay outside MCP.
- Controlled TARGET INSERT remains reserved for v0.22.0.

## v0.22.0 — Controlled Target Insert

- Added schema 38 controlled-target-insert runs and privacy-safe events.
- Enabled INSERT-only TARGET writes from fully validated v0.21.2 staging batches.
- Generic TARGET INSERT remains denied; controlled insert is the sole external-write boundary.
- Insert plans are immutable/hash-bound and require explicit human review + approval.
- Generated parameterized INSERT statements only; UPDATE/UPSERT/MERGE/DELETE/DDL/raw SQL remain forbidden.
- External pre-commit failure rolls back; uncertain commit becomes `in_doubt` and cannot auto-retry.
- SOURCE write capability remains forbidden and is rechecked before TARGET execution.
- MCP remains read-only and never exposes staged values or credentials.

## v0.22.1 — Identity Resolution, Deduplication & Lineage

- Added schema 39 identity policies, resolution runs, canonical entities, source bindings, human-review candidates, target lineage, and privacy-safe events.
- Exact business-key resolution is deterministic only under a human-reviewed/approved policy bound to TARGET contract business keys.
- Strong multi-field matches never auto-merge and require explicit human decisions.
- LLM/MCP has read-only identity visibility and cannot approve policies, decide candidates, execute resolution, or write TARGET.
- Deduplicated local staging is now mandatory for new controlled insert plans.
- Cross-batch duplicates already committed to TARGET are not reinserted, but all new SOURCE bindings retain pseudonymous lineage.
- Raw identity values remain outside AgentOS SQLite/audit; local HMAC lineage key is Git-ignored.

## v0.22.2 — Reconciliation & Recovery

- Added schema 40 reconciliation runs, findings, recovery cases, checkpoints, and privacy-safe events.
- Reconciliation reads only TARGET rows addressed by approved identity business keys and compares keyed whole-row fingerprints.
- Raw TARGET values, business-key query parameters, credentials, and PHI/PII remain outside SQLite/audit/checkpoints.
- `committing/in_doubt` is never auto-retried or auto-resolved.
- Human `committed_verified` requires `matched`; human `not_committed_verified` requires `observed_none`.
- A human-verified `not_committed` run becomes eligible for manual retry of the existing approved insert plan; automatic retry remains forbidden.
- Partial/mismatched target state requires manual intervention; AgentOS does not auto UPDATE/DELETE/UPSERT/MERGE repair.
- Known-commit pending lineage can be rebuilt locally/idempotently without repeating TARGET INSERT.
- MCP remains read-only for reconciliation/recovery.

## v0.22.3 — Core Reintegration & Release Integrity

- Restored central SQLite persistence and migration continuity 1→40.
- Merged core governance policy with v0.20-v0.22 policy blocks.
- Repaired v0.19.5 compatibility launchers.
- Added release-integrity and manifest verification gates.
- Reintroduced historical core regression as a mandatory release gate.


## v0.22.4 — Unified Governance Enforcement & Signed Audit

- Added schema 41 `governed_operations` and signed-domain-event correlation.
- Routed privileged v0.21-v0.22 domain mutations through approved task/session, workflow, baseline and drift gates.
- Reused one-time `guard_tool` / `complete_tool` lifecycle instead of creating per-SQL tokens.
- Mirrored privacy-safe domain events to the Ed25519 external audit chain.
- Replaced six module-local SQLite connection factories with the central hardened `agentos.db.connect()` through a lazy migration registry.
- Added fail-closed policy poisoning checks for SOURCE/TARGET/identity/recovery invariants.

## v0.22.5 — Unified CLI/MCP & Cross-Platform Runtime

- Replaced active version-chained CLI routing with one Python `cli_runtime` registry.
- Replaced active subprocess MCP forwarding with one Python `mcp_runtime` and flat unique catalog.
- Added POSIX/Windows CLI and MCP wrapper parity.
- Added fail-loud unknown-command / JSON-RPC method-not-found behavior and `agentos.mcp_health`.
- Kept historical version launchers/gateway modules as inactive compatibility/audit artifacts only.
- Preserved v0.22.4 privileged mutation enforcement and kept extension mutation outside MCP.
- Fixed stale v0.20.0/v0.20.1 CLI schema constant imports exposed by unified loading.
- Database schema remains 41.

## v0.22.6 — Secret Resolver & Lineage Key Lifecycle

- Added a trusted built-in resolver registry with provider identity/version/hash pins and capability-scoped human approval.
- Replaced the single lineage-key authority with an `active/retired/revoked` keyring while preserving legacy key material and historical HMAC values.
- Kept credential values memory-only and all secret/key mutations outside MCP.

## v0.22.7 — Data Subject Rights & Privacy Lifecycle

- Added schema 43 and an immutable data-subject erasure request/plan lifecycle with separate human review, approval and execution evidence.
- Added local canonical tombstoning, relinkable derived-state purge/privacy invalidation, one-way request locator retention, and `PRAGMA secure_delete=ON`.
- Added fail-closed blockers for active/uncertain identity, extraction, TARGET insert, reconciliation and recovery work, including `in_doubt` inserts.
- Preserved SOURCE SELECT-only and Controlled Target Insert safety; v0.22.7 adds no TARGET UPDATE/DELETE/UPSERT/MERGE authority.
- Added explicit `local_erasure_completed` and `external_target_erasure_required` outcomes for external TARGET handoff.
- Added three read-only MCP inspection tools; request/review/approval/execute remain governed operator mutations.

## v0.23.1 — Adaptive Token Budget & Model Profiles

- **User requirement:** make token budgeting adapt to model capacity/runtime observations without weakening requirement preservation or granting AgentOS model-routing authority.
- **Decision:** add hash-pinned local model profiles and deterministic adaptive budget decisions; keep a fixed v0.23.0 compatibility mode.
- **Enforcement:** profile registry is data-only/local; no network/provider discovery, dynamic code or tokenizer downloads; calibration is numeric/hash-only and may only increase protection.
- **Persistence:** schema 45 adds profile snapshots, budget decisions and token observations, plus exact profile/budget provenance on transport packs.
- **Control Plane invariant:** protected request/instruction/scope/plan content remains lossless and budgeted before evidence; control overflow fails closed.
- **MCP boundary:** added read-only profile/history/calibration inspection only; observation/profile/budget/model mutation is not exposed.
- **Compatibility:** SOURCE/TARGET, signed-audit, privacy, secret/key and v0.23.0 transport invariants remain unchanged.


## v0.23.2 — Context Expansion & Compression Evaluation

- **User requirement:** add bounded read-only evidence expansion and deterministic compression evaluation.
- **Enforcement:** schema 46, source/transport hash pins, ephemeral expanded content, evaluation hard gates, read-only MCP, and shadow comparison without activation authority.
- **Compatibility:** lossless Control Plane, adaptive budgeting, privacy, secret/key, SOURCE/TARGET, signed-audit and unified-runtime boundaries remain unchanged.

## v0.25.0 — Schema Bootstrap Baseline
- Fresh state bootstrap is pinned at schema 46.
- Historical migrations 1..46 are coverage markers, not invoked on fresh startup.
- Existing versioned databases remain incremental.
- Bootstrap fingerprint mismatch or unversioned non-empty state fails closed.

## 0.25.4 — Architecture Drift & Compliance Engine
- Added schema 52 compliance runs/findings bound to ACTIVE human Architecture baselines.
- Integrated hard architecture gates into write preparation, precommit, and final report.
- Added scanner v2 module/domain/environment-name observations without raw secret persistence.
- Added read-only MCP compliance inspection; no waiver/approval/architecture mutation authority.

## 0.25.5 — Architecture Change Proposal & ADR Lifecycle
- Added schema 53 immutable proposal, compliance-finding binding, ADR, and lifecycle-event records.
- AI/system actors may draft and submit proposal-only records; no architecture approval authority is granted.
- Human review/approval/rejection and target-baseline binding require explicit confirmation and exact proposal hash.
- Approved proposals do not edit Architecture Contract working copies or activate baselines; the existing human baseline lifecycle remains mandatory.
- Added read-only MCP proposal/ADR inspection with no create/review/approve/reject/bind/activate tools.
- Hardened the v0.25.4 compliance regression so schema 52 remains a historical floor while v0.25.5 advances to schema 53.

## 0.26.0 — Architecture-Aware Task Planning
- Added schema 54 architecture-bound task-plan contexts and lifecycle events.
- Plans under an ACTIVE Architecture Baseline are system-pinned to the exact baseline hash and deterministic architecture impact hash.
- Requirements, affected architecture sections, expected modules/dependency edges/files, and acceptance criteria become plan contract inputs.
- Plan approval and precommit fail closed when the architecture baseline pin is stale.
- Baseline activation marks affected plans stale instead of silently rebasing them.
- Added three read-only MCP planning inspection tools with no plan/ADR/architecture approval authority.

## 0.26.1 — Structural Enforcement
- Added schema 55 structural enforcement runs/findings for ARCH-02/03/04/05/12/22/23.
- Added static pre-plan, pre-write, and precommit structural hard-contract gates.
- Added explicit dependency/language/module/component/import-edge/coding-convention/design-artifact checks.
- Structural BLOCK routes to the existing Proposal/ADR/human successor-baseline lifecycle; no automatic architecture mutation is exposed.
- Added three read-only MCP structural inspection tools.
- Repaired root README release/schema coherence and added fail-closed README regression checks.
