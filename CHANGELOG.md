# Changelog
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
