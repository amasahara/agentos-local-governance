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

- Added a static trusted secret-resolver registry for `env://`, `keychain://`, `vault://`, bounded `file-secret://`, and `secret://` aliases.
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
