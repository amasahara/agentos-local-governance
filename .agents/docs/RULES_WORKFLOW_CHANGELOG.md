# Rules and Workflow Changelog

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
