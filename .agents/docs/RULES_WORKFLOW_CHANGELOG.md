# Rules and Workflow Changelog

## 2026-07-30 — v0.11.0 — MCP boundary repair, process confinement, audit key rotation

### Request

Repair the v0.10.1 MCP boundary, remove process/network bypass paths, add real symlink regression tests, unify proxy-only execution, and add key rotation plus external sink foundations.

### Enforcement

- `process.exec` now uses executable/module/action allowlists, denies shells, network clients, inline code, URLs, out-of-root working directories, and secret-bearing environment variables.
- `network.http` is default-deny and validates scheme, domain, resolved IP addresses, and redirects.
- Legacy `guard-tool`/`complete-tool` calls are blocked when proxy-only mode is enabled.
- External audit supports a historical public-key registry, cross-signed key rotation, and JSONL/daemon/remote sink modes.
- Schema 10 adds process execution events and audit-key rotation records.
- `agentos doctor` consolidates release and installation checks.

### Compatibility

Existing v0.10.1 state migrates in place. Commands that relied on unrestricted `process.exec` or the legacy guard lifecycle must migrate to approved proxy capabilities.

## 2026-07-30 — v0.10.1 — MCP Enforcement Gateway and External Signed Audit

### Request
Move enforcement from voluntary CLI calls into the actual MCP/tool path and persist signed audit evidence outside the repository.

### Decision
Add an MCP-compatible stdio gateway, stable capability normalization, bounded filesystem/process/HTTP adapters, fail-closed proxy preflight, Ed25519 signed external JSONL audit, verification CLI, schema migration 9, adversarial tests, and bilingual deployment documentation.

### Security boundary
The proxy is enforceable only when direct backend tools and credentials are removed from the agent. External audit storage must be outside the repository and outside agent write permissions.

### Affected files
`proxy.py`, `mcp_server.py`, `external_audit.py`, `cli.py`, `db.py`, `governance.json`, tests, README, AGENTS.md, bilingual guide, usage, structure, VERSION.

## 2026-07-29 — v0.8.1 — Runtime repair: tooling, cache, and docs-scan

### Request

Analyze the post-v0.7.1 audit and release a patch that repairs broken or unwired runtime modules without introducing the planned v0.8.0 workflow changes.

### Decision

Restored `tooling.py`, `cache.py`, and `documentation.py`; retained `core.record_tool_execution()` as the canonical `tool_calls` writer; added migration 5 for `tool_events`, `egress_events`, and `file_read_cache`; wired `docs-scan` and the repaired audit/cache commands into the CLI; added regression coverage and synchronized all release documentation.

### Enforcement

- runtime: `.agents/agentos/tooling.py`, `cache.py`, `documentation.py`, `db.py`, `cli.py`;
- schema: migration 5, `SCHEMA_VERSION = 5`;
- tests: migration, tool guard, egress audit, cache invalidation, documentation scan, CLI exposure;
- documentation: `README.md`, `AGENTS.md`, `huong_dan.md`, `.agents/docs/*`;
- release identity: `VERSION`, `governance.json`, `agentos.__version__`.

### Scope boundary

Task heartbeat, persistent workflow checklist, governance drift detection, safe installer, and git hooks remain planned for v0.8.0/v0.8.1 and are intentionally not included in this patch.

### Migration note

Migration 5 is additive and creates only the missing runtime tables and indexes. Existing v0.7.1 task, tool-call, index, claim, and evidence data remain compatible.

## 2026-07-29 — v0.7.1 — Governance synchronization and evidence-grounded claims

### Request

Upgrade the complete AgentOS system from v0.7.0 to v0.7.1 and provide a complete README.

### Decision

Implemented composite `prepare-change`; activated claim/evidence runtime and CLI; added `show-claim`; added `claim_policy`; enforced evidence type, risk, task ownership, success, and local classification; added schema indexes; locked symlink containment behavior; synchronized all documentation and version identities.

### Enforcement

- instruction: `AGENTS.md`;
- structured policy: `.agents/config/governance.json`;
- runtime: `.agents/agentos/core.py`, `policy.py`, `db.py`, `cli.py`, `indexing.py`;
- tests: `.agents/tests/test_agentos.py`;
- human documentation: `README.md`, `huong_dan.md`, `.agents/docs/*`.

### Migration note

Migration 4 adds indexes for tool-call and claim/evidence lookup. Existing v0.7.0 state is migrated automatically when AgentOS opens the database.

## 2026-07-28 — v0.7.0 — Local-first tools, cache, indexing, documentation contracts

Introduced local-first tool governance, file-read cache contracts, incremental Python symbol indexing, database migrations, documentation-code contracts, and aggregate status.

## 2026-07-29 — v0.8.1 — Persistent workflow, governance drift, and safe installation

### Request / Yêu cầu

Implement the proposed v0.8 workflow state, drift detection, safe installer, local policy override, and Git gate on top of v0.7.2.

Triển khai trạng thái workflow bền vững, phát hiện drift, installer an toàn, local override và Git gate trên nền v0.7.2.

### Decision / Quyết định

- Added migrations 6 and 7 without modifying existing migrations.
- Persisted current task outside the LLM context window.
- Seeded workflow steps from structured policy and made skip reasons auditable.
- Added a final report gate with non-zero failure behavior.
- Added human-acknowledged governance baselines and drift reporting.
- Added non-destructive Linux/macOS and Windows installers.
- Added optional pre-commit enforcement and local policy overrides.

### Enforcement

- instruction: `AGENTS.md`
- policy: `.agents/config/governance.json`
- runtime: `workflow.py`, `drift.py`, `cli.py`, `core.py`, `policy.py`, `db.py`
- installation: `.agents/bin/install.sh`, `install.cmd`, `install-git-hooks.sh`, `hooks/pre-commit`
- tests: `.agents/tests/test_agentos.py`
- documentation: `README.md`, `huong_dan.md`, `USAGE.md`, `PROJECT_STRUCTURE.md`

### Migration note

Schema advances from 5 to 7. Migration 6 creates `workflow_steps`; migration 7 creates `governance_baseline` and `governance_change_log`. Existing v0.7.2 data is preserved.

## 2026-07-29 — v0.9.0 — Trust Boundary Hardening

### Yêu cầu / Request

Audit v0.8.1 identified self-attestation in tool classification, workflow completion,
baseline acknowledgement, drift-aware reporting, and sensitive local overrides.

### Quyết định / Decision

AgentOS now derives tool classification, requires single-use guarded execution
tokens, records command provenance for automated workflow steps, isolates current
tasks by session, stages sensitive local overrides, redacts audit content, tracks
governance recursively, and blocks final reports on drift or invalid provenance.

### Enforcement

- schema migration 8: guarded executions, workflow provenance, override approvals,
  acknowledgement methods, and hash-chained audit events;
- runtime: `tooling.py`, `workflow.py`, `drift.py`, `policy.py`, `core.py`, `cli.py`;
- tests: adversarial bypass, token, session, drift, override, redaction, and provenance tests;
- documentation: README, AGENTS.md, huong_dan.md, usage, and structure docs.

### Compatibility

Direct `record-tool` is intentionally disabled. Integrations must use
`guard-tool` followed by `complete-tool`. Database migrations remain additive.

## 2026-08-01 — v0.12.0 — Concurrent Work Coordination

### Request

Support multiple CLI processes and coding agents without lost updates or overlapping writes.

### Enforcement

- migration 11 adds task ownership, resource leases, file versions, and handoff records;
- SQLite uses WAL, FULL synchronous mode, busy timeout, and immediate lease transactions;
- proxy file writes require expected hashes for existing files;
- proxy acquires exclusive file leases and performs atomic replacement;
- task ownership and handoff are explicit and auditable;
- multi-process deployments should use one external audit daemon.

### Compatibility

Existing v0.11.0 state migrates automatically. Clients writing existing files must add `expected_hash`.

## 2026-08-01 — v0.13.0 — Coordination Enforcement Boundary

- Đưa coordination vào MCP/tool proxy boundary.
- Thêm signed audit, caller-bound handoff, scope enforcement, expiry/stale reclaim và schema 12.
- Expose coordination MCP tools và bổ sung adversarial tests.

- Moved coordination into the MCP/tool-proxy boundary.
- Added signed audit, caller-bound handoff, scope enforcement, expiry/stale reclaim, and schema 12.


## 2026-08-02 — v0.13.1–v0.14.3 — Security Foundation Program

### Quyết định / Decision

- v0.13.1: vá audit daemon fail-closed, audit-home isolation và session revocation.
- v0.14.0: thêm `agentos-gatewayd` và thin IPC client.
- v0.14.1: thêm capability session, token hash, expiry, revoke và replay protection.
- v0.14.2: thêm isolated workspace, environment filtering và static AgentOS-import denial.
- v0.14.3: thêm signed-state index, workflow verification và state reconciliation/recovery history.

### Enforcement

Schema 13–16, `gatewayd.py`, `gateway_client.py`, `security.py`, hardened proxy, signed workflow state, adversarial tests và tài liệu song ngữ.

### Compatibility

Migrations are additive. Agent-facing writes should move to the gateway protocol; direct local APIs remain for operator/testing compatibility during this security program.

## 2026-08-02 — v0.15.0–v0.15.1 — Knowledge Runtime

- v0.15.0: thêm deterministic context pack, source hash, revision, line budget, stale detection và `context-explain`.
- v0.15.1: thêm project findings deduplication và semantic/episodic/procedural/evidence memory có provenance.
- Schema nâng từ 16 lên 18 qua hai migration additive.
- Runtime: `context_runtime.py`, `memory.py`; CLI và tài liệu song ngữ được đồng bộ.
- Tests: context budget/stale/revision, finding deduplication, memory provenance/stale và schema.


## 2026-08-02 — v0.16.0–v0.16.2 — Execution Platform

### Quyết định / Decision

- v0.16.0: asynchronous governed jobs, immutable specs, recovery, and workflow-aware tool discovery.
- v0.16.1: revisioned task plans, human approval, and Git-aware pre-commit enforcement.
- v0.16.2: versioned aggregate evaluation metrics and JSON/CSV export.

### Enforcement

Schema 19–21; runtime modules `jobs.py`, `planning.py`, and `evaluation.py`; CLI/MCP integration; regression tests; bilingual README and developer guide synchronization.

### Compatibility

Migrations are additive. Existing synchronous proxy execution remains available. The async job API adds a non-blocking path without removing prior commands.

## 2026-08-02 — v0.17.0–v0.17.1 — Adaptive Multi-Agent Platform

- v0.17.0 adds evaluation-baseline-gated governance proposals, deterministic simulation, human review, shadow, canary, activation, and rollback stages.
- Automatic policy activation is forbidden.
- v0.17.1 adds authenticated task-role assignments and structured task messages.
- Multi-agent messaging is fail-closed unless capability sessions, roles, and a fresh context pack are all present.
- Context disclosure is explicitly bounded and every role/message transition is externally signed.
- Database schema upgraded from 21 to 23.


## 2026-08-02 — v0.17.2–v0.18.0 — Knowledge Runtime fixes and transparent context compaction

- v0.17.2 connects validated file-read caching to the proxy, enforces collaboration disclosure filtering, and exposes context completeness counts.
- v0.18.0 adds deterministic relevance ranking, symbol-window compaction, global/per-file budgets, approximate token accounting, omitted file/symbol reasons, and `context-compare`.
- No schema migration is required; `context_packs.manifest_json` remains additive.
- README and `huong_dan.md` are synchronized with the current release.


## 2026-08-02 — v0.18.1 — Skill Promotion Runtime

- Added schema 24 and versioned `promoted_skills`.
- Added candidate/graduated lifecycle, human-only graduation, signed audit, matching, and revocation.
- Added `.agents/skills/**` to governance drift tracking.

## 2026-08-02 — v0.19.1 — Local Semantic Retrieval Abstraction

- Added schema 25 retrieval observability.
- Added backend-neutral `KnowledgeRetriever` contract and deterministic `lexical_structured` backend.
- Unified local search across active memory, findings, symbols, and graduated skills without LLM or network calls.

## 2026-08-02 — v0.19.0 — Optional Local Embeddings and RAG

- Added deterministic, dependency-free `local_feature_hash_v1` embeddings as an optional retrieval backend.
- Added persisted embedding index, cosine search, bounded RAG context bundles, provenance, and retrieval audit events.
- Kept `lexical_structured` as the default backend; no network, LLM, API key, or external model download is required.
- Added schema migration 26.

## 2026-08-02 — v0.19.1 — Use-case-driven Knowledge Relationship Graph

- Added a compact SQLite relationship graph only for concrete use cases: impact analysis, finding-to-symbol links, and skill provenance.
- Added graph build, neighbor, and bounded path commands.
- Graph edges require evidence from existing indexes/tables; no general-purpose speculative knowledge graph is created.
- Added schema migration 27.
