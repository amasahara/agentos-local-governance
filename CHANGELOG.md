## v0.31.0 — Governed Learning Signal Integration

- Schema 63 → 64.
- Governed learning signal/link/knowledge-usage integration.
- Raw learning signals remain outside context retrieval and instruction authority.

# Changelog

## v0.30.1 — Release & Schema Metadata Coherence
- Repaired current schema-bootstrap metadata to schema 63 while keeping bootstrap baseline 46 unchanged.
- Added fail-closed contiguous post-bootstrap migration validation for the exact sequence 47..63.
- Integrated schema-bootstrap coherence into release metadata validation, manifest generation, and release validation.
- Reconciled current README/release-note identity that was still describing v0.29.5/schema 62.
- Kept historical subsystem `database_schema` introduction metadata unchanged.
- Database schema remains 63; no learning-loop feature is introduced in this prerequisite node.


## v0.30.0 — Context Authority & Untrusted Provenance

- Added deterministic source-origin context authority/provenance classification.
- Added schema 63 hash/label-only provenance records, authority evaluations, and findings.
- Bound `provenance_manifest_hash` and `context_authority_hash` into Context Transport packs.
- Added fail-closed provenance pin revalidation and authority/provenance stale detection.
- Renamed context knowledge selection wording from `trusted_provenance` to `verified_evidence_provenance`.
- Added four read-only CLI and four read-only MCP context-authority inspection surfaces.
- Added structural context-authority attestation with explicit broad non-claims.
- Preserved existing Requirement-Preserving Context Transport and v0.29.x enforcement boundaries.

## v0.29.5 — Native Physical Isolation Extensions
- Extended the v0.29.4 Windows Restricted Token boundary with verified Low
  Integrity (`S-1-16-4096`, RID 4096) for AgentOS-mediated process execution.
- Added native `TokenIntegrityLevel` mutation and verification while preserving
  the exact v0.29.4 Restricted Token profile and forbidding `SANDBOX_INERT`.
- Added Low mandatory-label SACLs with `NO_WRITE_UP`; directories use inheritable
  OI/CI labels and existing sandbox objects are explicitly labeled and verified.
- Added a bounded current-user DACL contract so Restricted/LUA workers can
  read/write/execute inside the AgentOS sandbox without granting `Everyone`,
  `WRITE_DAC`, `WRITE_OWNER`, or `ACCESS_SYSTEM_SECURITY`.
- Kept generic Low-MIC primitives root-local while production sandboxes require
  the controlled `*.agentos-sandboxes` ancestry.
- Switched synchronous production execution to Restricted + Low child creation,
  actual child-token verification, Job Object assignment, then resume.
- Switched governed asynchronous worker roots to Restricted + Low while keeping
  the async broker as the trusted lifecycle process.
- Added live Windows write-up probes: governed Low workers can write inside the
  Low-labeled sandbox and are denied writes to controlled Medium targets.
- Added dedicated physical-isolation structural attestation and focused
  `windows-latest` CI coverage for token, MIC, DACL, sync, async, and activation.
- Activated only the scoped claims
  `low_integrity_attested = true` and
  `sandbox_low_integrity_label_attested = true` under
  `agentos_mediated_process_execution`.
- General host-filesystem isolation, general OS write confinement, desktop
  isolation, credential isolation, primary-root-wide write confinement, and
  same-user host-bypass resistance remain unclaimed.
- Database schema remains **62**; no migration is added.
## v0.29.4 — Windows Restricted Execution
- Added Windows Restricted Token execution using
  `DISABLE_MAX_PRIVILEGE | LUA_TOKEN`; `SANDBOX_INERT` is forbidden.
- Governed workers launch with `CreateProcessAsUserW(CREATE_SUSPENDED)`.
- Re-verify the actual child token before Job Object assignment and resume.
- Bound sync production execution to the restricted runner without an
  unrestricted fallback.
- Bound production async worker roots to Restricted Token while preserving the
  trusted named-Job broker lifecycle.
- Added fail-closed negative tests, structural attestation and focused Windows
  CI coverage.
- Activated only `restricted_token_attested = true` under
  `agentos_mediated_process_execution`.
- Low Integrity, desktop isolation, host-filesystem isolation, OS write
  confinement, credential isolation and same-user host-bypass resistance
  remain unclaimed.
- Database schema remains 62.

## v0.29.3 — Sandbox Configuration & Credential Boundary
- Moved runtime-profile authority to governed effective-policy configuration
  with deterministic configuration hashes and fail-closed invariant validation.
- Added `secret://alias` process credential bindings backed by the existing
  trusted Secret Resolver and provider pin/capability approval.
- Added sync launch-time credential resolution, secret-independent environment
  evidence, and exact-value captured-output redaction.
- Added async credential hash/count binding, immutable spec verification before
  resolution, launch-time revalidation/resolution, and disabled persistence of
  credential-bearing async stdout/stderr.
- Added machine-verifiable credential-boundary structural attestation and
  focused Ubuntu/Windows CI suites.
- Preserved v0.29.1 Windows process-tree containment and v0.29.2 sandbox/runtime
  profile regressions.
- Activated only bounded sandbox-configuration and credential-boundary claims
  under `agentos_mediated_process_execution`.
- Kept credential isolation, Restricted Token, Low Integrity, host-filesystem
  isolation, OS write confinement, and same-user host-bypass resistance false.
- Schema remains 62.
## v0.29.2 — Windows Sandbox Workspace & Tool Runtime Profiles

- Added deterministic runtime profiles and bounded sandbox workspaces for
  AgentOS-mediated process execution.
- Added sync/async enforcement, async snapshot/hash binding and pre-launch
  revalidation, mutable-state redirects, and cleanup evidence.
- Preserved v0.29.1 Windows process-tree containment and its activation
  regression.
- Added v0.29.2 Windows CI activation coverage.
- Activated only the bounded runtime-profile sandbox attestation.
- Kept Restricted Token, Low Integrity, credential isolation,
  host-filesystem isolation, OS write confinement, and same-user host-bypass
  resistance claims false.
- Schema remains 62.

## v0.29.1 — Windows Process-Tree Containment

- Added native Windows Job Object containment for AgentOS-mediated process execution.
- Synchronous roots are created suspended, assigned to a Job Object before resume, and whole-tree terminated on timeout/teardown.
- Async execution now uses a dedicated Job broker that durably owns a named `KILL_ON_JOB_CLOSE` Job Object.
- Async status uses Job membership and broker evidence rather than root-PID liveness.
- Async cancellation and timeout terminate the entire named Job; timeout persists `timed_out` with exit code 124.
- Broker failure is fail-closed for the associated worker process tree.
- Broker completion receipts carry the worker root exit code; non-zero exit materializes `failed`.
- Added bounded machine-verifiable process-tree attestation under `agentos_mediated_process_execution`.
- Added a `windows-latest` GitHub Actions validation job with focused containment and full regression coverage.
- Database schema remains **62**.
- Broad nonclaims remain unchanged: no same-user host bypass resistance, no general OS process isolation, and no arbitrary host-process containment claim.

## v0.29.0 — Independent Completion Verification

- Added schema **62** completion verification request/attempt state.
- Accepted completion requires a fresh reviewer receipt bound to the exact subject hash.
- Verifier task/session/assignment must be independent from the producer and reviewer authority remains governed.
- Passing verification requires all declared checks plus evidence; subject mutation invalidates the receipt.
- Applied the receipt boundary to workflow finalization, worker completion, and integration readiness.
- Added `completion-request`, `completion-verify`, `completion-status`, plus read-only MCP `agentos.completion_status_get`.
- Extended enforcement attestation and release integrity with independent-completion gates.
- Runtime surface: 344 canonical / 248 agent / 98 privileged commands; MCP 124 tools.
- Claim scope remains `agentos_mediated_agent_execution`; semantic correctness, provider independence, and replacement of human review/approval are not claimed.

## v0.28.4 — Tool Exclusivity & Enforcement Attestation

- Added deterministic enforcement attestation for AgentOS-mediated execution surfaces.
- Routed `job-submit` and `agentos.run_command_async` through the canonical proxy lifecycle.
- Revalidated execution authority immediately before the actual asynchronous `subprocess.Popen()` side effect.
- Routed `agentos run-tests` through governed `process.exec`.
- Attested that the active MCP runtime has no legacy subprocess-forwarding path.
- Classified canonical, internal-governance, and inactive-legacy process primitives.
- Integrated fail-closed attestation into runtime health, doctor, policy validation, and release integrity.
- Preserved Privileged Control Plane separation introduced in v0.28.3.
- Database schema remains **61**.
- The attestation scope is explicitly limited to `agentos_mediated_agent_execution`.
- No claim is made for same-user host bypass resistance, OS-level process isolation, or arbitrary host-process containment.

## v0.28.3 — Privileged Control Plane Separation

- Added separate `agentos` and `agentos-admin` execution planes.
- Removed privileged command dispatch from the normal agent plane.
- Isolated command discovery to the agent execution surface.
- Added explicit control-plane classification and dual-plane argument enforcement.
- Preserved MCP/Web no-mutation authority.
- Preserved existing governed mutation and signed-audit gates.
- Added Windows and POSIX `agentos-admin` launchers to installed payloads.
- Database schema remains 61.
- Tool exclusivity and anti-bypass attestation remain reserved for v0.28.4.


## v0.28.2 — Project Bootstrap & Repository Normalization

- Separated distribution metadata from installed-project metadata and introduced role-aware repository validation.
- Replaced the legacy installer flow with `project-init` and `project-adopt`.
- Removed representative project identity and purpose from the distribution and kept AgentOS documentation out of application roots.
- Normalized the current release payload by removing obsolete root benchmarks and superseded upgrade documents.
- Redesigned README as a durable project overview, including the boundary between AgentOS and user-owned source layouts.
- Made manifest generation compile and LF-normalize deterministic effective policy before hashing release artifacts.
- Added a CI reproducibility gate for generated policy, package metadata, manifest, and checksums.
- Added no new security feature; schema remains 61.

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
- Coordinates only existing approved worker tasks, active architecture-aware plans, capability sessions and role assignments.
- Uses parent-plan subset checks and blocks overlapping executor write targets.
- Supports acyclic worker dependencies and deterministic runnable-worker readiness.
- Optional skill binding accepts only current, eligible/recommendable graduated Contract-v2 selections from v0.27.1.
- Does not create/approve tasks or plans, issue capabilities, execute skills, choose model/providers, or launch worker processes.
- MCP adds read-only supervisor status/workers/readiness tools; supervisor mutation remains CLI/operator governed.
- Isolated workspace and controlled integration remain reserved for v0.27.3.

## 0.27.1 — Architecture-Aware Skill Selection & Evaluation

- Added schema 59 selection/evaluation observability.
- Added deterministic advisory ranking of current graduated Skill Contract v2 skills against active architecture-aware plans.
- Added least-authority gates for architecture sections, write scopes, capabilities, tools, dependencies, external services, and tests.
- Added observational outcome evaluation without automatic lifecycle or ranking mutation.
- Added 4 CLI commands and 3 read-only MCP inspection tools.
- Preserved Latest Full Release / no-updater distribution and project-owned partitions.
- Updated README, bilingual guides, release notes, policy, release integrity and current-node documentation.

## 0.27.0 — Governed Skill Contract v2

- Upgrade the existing procedural skill lifecycle to deterministic Governed Skill Contract v2 without creating a second skill framework.
- Add schema 58 contract state/events, architecture hash binding, least-authority scope/capability/tool declarations, and human-gated graduation.
- Preserve legacy v1 skills without in-place rewrite; automatic architecture-aware selection remains reserved for v0.27.1.
- Replace version-specific updater scripts with the download-latest-full-release distribution model while keeping project-owned skills/workflows/source/state isolated.
- Synchronize README VI/EN and current developer documentation for v0.27.0.

## 0.26.3 — Quality/Operational Enforcement

- Enforce explicit ARCH-15..21 logging/error/security/performance/scalability/deployment/testing contracts.
- Add schema 57 quality runs/findings, plan declarations, target safeguards, precommit gate, and read-only MCP inspection.
- Preserve human-only Architecture Authority and deterministic static analysis.

## 0.26.2 — Runtime/Data/API & Business Boundary Enforcement

- Enforce ARCH-06/07/08/09/10/11/13/14 at plan-time and pre-commit using deterministic static analysis.
- Add schema 56 runtime-boundary runs/findings, target-only ARCH-09/14 write gating, and read-only MCP inspection.
- Preserve human-only Architecture Authority; no LLM waiver/approval/activation authority is introduced.

# Changelog

## 0.25.2 — 27-Section Architecture Contract & Human Clarification Gates
- Added schema 50 with immutable architecture baseline/section/artifact/event state plus structured clarity assessments and first-class human decision requests/resolutions.
- Added the fixed `ARCH-01`…`ARCH-27` registry; `ARCH-26 Improvement Proposal` is permanently proposal-only and working-copy files never carry activation authority.
- Added deterministic architecture baseline hashing and explicit human review → approve → activate lifecycle with exact-hash confirmation and single-active-baseline supersession.
- Upgraded `assess_requirement_clarity` / `clarify_if_needed` into a fail-closed Grill Me gate: material assumptions and ambiguities block task/plan approval until explicitly resolved and reassessed.
- Added runtime Human Decision Gate: AI may open a blocker and recommend options, while human-only resolution controls resume/reapproval; open blockers stop dependent writes/tools/precommit/privileged mutations while bounded reads remain available.
- Human question/answer text remains local; signed external audit receives hashes and bounded metadata only.
- Added read-only Architecture/Human Decision MCP inspection plus the single monotonic `agentos.human_decision_request` blocker signal; no MCP resolve/waive/architecture approval authority was added.
- Fixed CLI/MCP release version drift by deriving runtime version from `agentos.__version__`; fresh DB still bootstraps schema 46 and now applies migrations 47→50, while schema-49 databases apply only migration 50.


## 0.25.1 — Release Metadata Coherence
- Established `VERSION` as the single release-version source of truth across runtime, governance, manifest, package completeness, and current-release identity documents.
- Added fail-closed read-only release metadata coherence validation to both generic release validation and release-integrity paths.
- Made `tools/build_manifest.py` synchronize `PACKAGE_COMPLETENESS.json` before hashing and removed generated `VALIDATION_REPORT.json` from clean-main requirements.
- Removed current-release validator hard-coding of the v0.25.0 literal and synchronized bilingual current docs/runtime package metadata.
- Database schema remains 49; v0.25.0 schema-bootstrap behavior and all governance/MCP authority boundaries are unchanged.

## 0.25.0 — Schema Bootstrap Baseline
- Fresh DB materializes schema 46 directly and then applies migrations 47→49.
- Existing DBs retain incremental migrations from their recorded version.
- Added deterministic bootstrap DDL/fingerprint and equivalence regression.
- Current schema remains 49; governance/mutation authority is unchanged.


## 0.24.3 — MCP Feature Runtime Refactor
- Active MCP feature handlers are detached from historical gateway modules.
- Added runtime-native feature/core modules; schema remains 49 and tool authority is unchanged.

## 0.24.2 — DB-Aware Context Projection
- Repository release cleanup: clean-main packaging, external release archive, generic current-release validator, and runtime/state/cache Git isolation.
- Schema 49 adds hash/count-only DB-aware projection telemetry.
- Reversible schema/mapping/manifest codecs apply only to Context Evidence Plane.
- Control Plane and DB mutation authority remain unchanged.

## 0.24.1 — Risk-Tiered Batch Review
- Added schema 48 mapping-level risk review state and immutable LOW-risk review bundles.
- LOW bundles are pin-bound to the exact consolidation plan and mapping snapshots and are signed through the external Ed25519 audit chain.
- MEDIUM/HIGH mappings require individual explicit human review; CONFLICT remains blocked.
- Existing whole-plan human approval and execution gates are unchanged; MCP remains read-only for this feature.
## 0.23.4 — Incremental Symbol Index
- Replaced repeated full symbol-index rebuilds with deterministic per-file content-hash incremental updates.
- Added schema 47 file-state metadata, bootstrap full rebuild, deletion cleanup and atomic parse-failure rollback.
- Added no-change/change/delete benchmark contracts against the measured v0.23.3 full-rebuild baseline.
- Preserved all SOURCE/TARGET, privacy, signed-audit, human approval and lossless Context Control Plane invariants.

## 0.23.3 — Consolidation Cockpit & Performance Baseline
- Added a read-only end-to-end consolidation cockpit from project selection through reconciliation/recovery.
- Added isolated fresh-migration and full-rebuild symbol-index timing plus read-only cockpit latency measurement.
- Added a fail-closed measured-baseline release gate; environment-specific timing thresholds remain disabled until the runner is pinned.
- Added two MCP read-only inspection tools; benchmark execution and all consolidation mutations remain outside MCP.
- Preserved schema 46 and all SOURCE/TARGET, human approval, signed-audit, privacy/secret/key and lossless Context Control Plane invariants.


## 0.23.2 — Context Expansion & Compression Evaluation

- Added schema 46 expansion-session telemetry, enriched expansion event metadata, deterministic compression evaluation runs, and shadow comparison records.
- Added bounded line/token expansion, Requirement Ledger bindings, allowlisted reason codes, and aggregate batch token caps.
- Ensured expanded evidence remains ephemeral: no excerpt/raw source content is persisted in expansion/evaluation state.
- Added Compression Evaluation v2 hard gates for 100% requirement preservation, canonical candidate accountability, handle integrity, token-budget compliance, transport integrity, and source freshness.
- Preserved the v0.23.0 metric contract while adding candidate accountability, expansion success/failure, budget utilization, hard-failure and warning metrics.
- Added deterministic shadow comparison for READY/SUPERSEDED revisions without activation authority.
- Added five read-only MCP operations; no evaluation persistence, comparison persistence, or transport mutation over MCP.
- Full GitHub-ready materialization restores historical governance sections and upgrade guides from repository Git history instead of relying on overlay-only replacement.
- Completed v0.22.7 privacy implementation hardening (one-way locator retention, immutable request/plan triggers, canonical UUID tombstoning, bounded erasure reasons, active/in-doubt blockers, staging-only deletion) and added schema-46 repair for existing schema-45 databases.
- Synchronized unified MCP runtime metadata to v0.23.2 and added automatic GitHub Actions release validation for upload-only workflows.

## 0.23.1 — Adaptive Token Budget & Model Profiles

- Added schema 45 for hash-pinned model-profile snapshots, per-transport budget decisions and numeric/hash-only token calibration observations.
- Added local data-only model profiles with exact profile SHA-256 pinning; network/provider discovery, dynamic profile code and tokenizer auto-download are forbidden.
- Added deterministic adaptive budget calculation that allocates Control Plane first and adjusts output/safety protection without weakening configured floors.
- Added local calibration using input-underestimation and observed-output percentiles; calibration can only increase protective headroom and never stores prompt/response content.
- Preserved v0.23.0 `fixed` budget behavior as an explicit compatibility mode while making `adaptive` the default policy mode.
- Added budget decision/profile-hash provenance to Transport Packs and evaluation/token reports.
- Added CLI inspection/observation commands and three read-only MCP inspection tools; MCP model/profile/budget/observation mutation remains forbidden.
- Preserved all v0.22.3-v0.23.0 safety invariants, SOURCE read-only boundary, Controlled Target Insert authority, privacy lifecycle and requirement-preservation gate.

## 0.23.0 — Requirement-Preserving Context Compression

- Added schema 44 transport packs, stable Requirement Ledger persistence, expansion observability and transport evaluation metrics.
- Added deterministic LLM Transport Compiler derived from fresh canonical Context Packs.
- Added LOSSLESS Control Plane with verbatim original request, AGENTS authority, approved scope, active plan and protected policy authority.
- Added 100% Requirement Preservation Gate and fail-closed behavior when protected content exceeds model budget.
- Added deterministic Evidence Plane compression ladder: exact dedup, metadata normalization, structural projection, requirement-aware ranking, omission handles, fail-closed.
- Added Python symbol/dependency windows, JSON policy-key projection and repetitive-log aggregation without word-level deletion.
- Added tokenizer abstraction with exact-local preference and multilingual offline heuristic fallback.
- Added model budget accounting for capacity, reserved output, system/tool overhead and safety margin.
- Added five read-only MCP tools: `context_transport_get`, `context_transport_explain`, `context_expand`, `context_requirement_get`, `context_token_report`; no compile/evaluation mutation over MCP.
- Added canonical-vs-transport evaluation/shadow metrics including compression, requirement preservation, context misses, expansion requests, task/test success, rework and tool-call counts.
- Fixed clean/fresh `db.connect(immediate=True)` migration transaction sequencing by committing the migration boundary before `BEGIN IMMEDIATE`; foreign keys remain enabled.

## 0.22.7 — Data Subject Rights & Privacy Lifecycle

- Added schema 43 with immutable `data_subject_erasure_requests` and `data_subject_erasure_plans`, plus separate immutable review, approval, execution, tombstone and append-only event evidence.
- Added database-level no-UPDATE/no-DELETE triggers for privacy request/plan/review/approval/execution/tombstone records and append-only event protection.
- Added human-reviewed and human-approved local erasure execution inside the existing task/session/capability/baseline-drift/one-time-token/signed-audit enforcement boundary.
- Added one-way request entity locator retention; local execution replaces the original canonical entity UUID/HMAC lookup material with non-relinkable tombstone markers and removes lineage `key_id` from the tombstoned entity.
- Added privacy-first purge/invalidation of local identity bindings/candidates/lineage plus related staging/cache/project-memory/embedding/index artifacts according to policy.
- Added `PRAGMA secure_delete=ON` to the unified AgentOS SQLite connection while preserving `foreign_keys=ON` and migration continuity.
- Added active/uncertain-operation gates for identity resolution, extraction, Controlled Target Insert, reconciliation and recovery, including `in_doubt` insert detection through related extraction batches before lineage finalization.
- Added explicit `local_erasure_completed` and `external_target_erasure_required` outcomes. No TARGET UPDATE/DELETE/UPSERT/MERGE authority was added.
- Added three read-only MCP inspection tools for erasure request/plan/status; no privacy approval/execution mutation is exposed over MCP.
- Added focused tests for idempotency, unauthorized erasure, DB immutability, active/in-doubt blockers, pending identity candidates, lineage-key interaction, one-way locator behavior and sensitive-data leakage.
- Upgrader normalizes the currently committed v0.22.6 governance metadata gap only when exact v0.22.6 runtime evidence is present, then layers v0.22.7 policy without weakening earlier safety invariants.

## 0.22.6 — Secret Resolver & Lineage Key Lifecycle

- Added a static trusted secret-resolver registry for `env://`, `keychain://`, `vault://`, bounded `file-secret=[REDACTED], and `secret=[REDACTED] aliases.
- Added provider identity/version/implementation-hash pins, capability-scoped operator approval, fail-closed dependency/provider handling, and memory-only credential resolution.
- Removed production callback-injection authority and forbade governance-config dynamic `importlib module:function` resolver loading.
- Routed read-only extraction, Controlled Target Insert, and reconciliation through the shared trusted resolver boundary.
- Added schema 42 with resolver approval/evidence tables, versioned lineage-key metadata, rotation/rekey plans, and `key_id` provenance on identity/lineage records.
- Replaced the single-key authority with `active/retired/revoked` key lifecycle; new tokens use active key while retired keys remain lookup/verification capable.
- Migrated legacy lineage key bytes without historical re-HMAC; initialization is privileged and read-only inspection cannot initialize key material.
- Added restart-safe recovery for a single crash-left key file and fail-closed key-material path validation.
- Added human-reviewed/approved rotation with signed domain/audit mirroring and governed SOURCE-reread rekey authorization.
- Pinned reconciliation to the identity-resolution `key_id` so later rotation does not invalidate historical reconciliation.
- Added five read-only MCP inspection tools; no secret/key mutation or credential authority is exposed.

- Erasure `reason_code` is a bounded enum (not free-form subject text), and filesystem purge is restricted to non-symlink `.agents/runtime/data-staging` artifacts plus the dedicated derived cache root.
