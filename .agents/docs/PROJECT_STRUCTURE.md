# Project Structure

## Authority and documentation

- `AGENTS.md`: sole coding-agent instruction authority.
- `README.md`: complete installation, architecture, command, and operational reference.
- `huong_dan.md`: bilingual developer entry point.
- `.agents/config/governance.json`: machine-readable active policy.
- `.agents/docs/RULES_WORKFLOW_CHANGELOG.md`: governance decision history.
- `.agents/docs/USAGE.md`: command recipes.

## Runtime modules

- `core.py`: task lifecycle, write guard, placement, composite preparation, tool audit, claims, checks, and status.
- `cli.py`: command parsing, JSON argument handling, and JSON output.
- `db.py`: SQLite connection, foreign keys, transactions, and migrations.
- `policy.py`: fail-closed structured-policy validation.
- `indexing.py`: Python AST symbol index and duplicate candidate reports.

## Generated state

- `.agents/state/agentos.db`: persistent project-local audit state.
- `.agents/runtime/`: temporary task workspaces, validation artifacts, exports, and downloads.

## Tests

`.agents/tests/test_agentos.py` locks runtime guarantees, including:

- task and scope enforcement;
- path traversal denial;
- file and directory symlink escape denial;
- internal symlink allowance when scope permits;
- prepare-change consistency;
- claim evidence policy and atomicity;
- documentation and version synchronization.

## Reading paths

To understand a rule:

```text
AGENTS.md
→ governance.json
→ policy.py/core.py
→ tests
→ changelog
```

To review a workflow change:

```text
changelog
→ AGENTS.md diff
→ governance.json diff
→ runtime diff
→ test diff
→ README/guide diff
→ docs-check
```


## v0.9.0 repaired modules

- `.agents/agentos/tooling.py`: conservative tool classification, guard decisions, tool audit events, and egress reports. It does not write canonical `tool_calls`.
- `.agents/agentos/cache.py`: task/path/range-scoped file-read summaries validated by mtime, size, and SHA-256 content hash.
- `.agents/agentos/documentation.py`: AST-based source documentation scan for module headers and public-symbol docstrings.
- `.agents/agentos/db.py` migration 5: creates `tool_events`, `egress_events`, and `file_read_cache`.

## v0.9.0 components

- `.agents/agentos/workflow.py`: current-task persistence, workflow seeding, step state, next-step and completion status.
- `.agents/agentos/drift.py`: governance baseline hashing, change logging, drift reports and diffs.
- `.agents/bin/install.sh` / `install.cmd`: non-destructive installation.
- `.agents/bin/install-git-hooks.sh`: optional Git gate installation.
- `.agents/bin/hooks/pre-commit`: instruction, documentation, drift and test gate.
- `.agents/config/governance.local.json`: optional project-specific override, tracked when present.
- `.agents/runtime/current_task.json`: generated local session heartbeat; never committed.

## v0.9.0 hardening components

- `tooling.py`: guarded execution tokens, derived classification, redaction, audit hash chain.
- `workflow.py`: session-scoped task state and automated-step provenance.
- `drift.py`: recursive tracking, baseline states, acknowledgement methods.
- `policy.py`: safe override merge and sensitive override approval staging.
- migration 8: `guarded_executions`, `policy_override_approvals`, `audit_events`, and provenance columns.


## v0.10.1 enforcement components

- `.agents/agentos/proxy.py`: policy decision and bounded backend adapters.
- `.agents/agentos/mcp_server.py`: agent-facing MCP-compatible stdio gateway.
- `.agents/agentos/external_audit.py`: external Ed25519-signed JSONL audit chain.
- `.agents/bin/agentos-mcp`: MCP gateway launcher.
- `.agents/requirements.txt`: cryptography and test dependencies.
- `proxy_executions`: canonical proxy execution metadata.
- `external_audit_checkpoints`: verified external audit checkpoints.

## Current v0.11.0 runtime additions

Schema at that milestone: `18`

- `proxy.py`: proxy-only filesystem/process/network enforcement, command profiles, environment filtering, domain/IP/redirect validation.
- `external_audit.py`: Ed25519 key registry, signed JSONL/daemon/remote sinks, key rotation, historical verification.
- `audit_daemon.py`: minimal authenticated append-only audit ingestion service.
- `process_exec_events`: command profile, working directory, decision, result, and exit-code audit state.
- `audit_key_rotations`: durable key-rotation metadata linked to signed events.


## v0.12.0 concurrency components

- `concurrency.py`: resource leases, expected-hash compare-and-swap, atomic writes, task ownership and handoff.
- `resource_leases`: expiring read/write ownership.
- `file_versions`: version and hash history for committed file mutations.
- `task_handoffs`: audited writer ownership transfers.

### Knowledge Runtime v0.15.1

```text
.agents/agentos/context_runtime.py  → deterministic context manifests and stale detection
.agents/agentos/memory.py           → findings and provenance-aware project memory
context_packs                       → revisioned task context packages
project_findings                    → deduplicated recurring findings
project_memory                      → semantic/episodic/procedural/evidence knowledge
```

Schema at that milestone: `18`.


### Execution Platform v0.16.0–v0.16.2

- `.agents/agentos/jobs.py`: asynchronous job lifecycle, recovery, and tool discovery.
- `.agents/agentos/planning.py`: task-plan revisions and Git-aware pre-commit checks.
- `.agents/agentos/evaluation.py`: aggregate metrics and JSON/CSV export.
- Migrations 19–21: async jobs, task plans/precommit records, and evaluation runs.

Database schema at that milestone: `21`.

### Adaptive Multi-Agent Platform v0.17.0–v0.17.1

- `.agents/agentos/evolution.py`: evaluation-driven policy proposal lifecycle, simulation, staged activation, and rollback.
- `.agents/agentos/collaboration.py`: capability/role/context readiness, structured messages, and disclosure enforcement.
- Schema 22: `evolution_proposals`, `evolution_stage_events`.
- Schema 23: `task_role_assignments`, `task_messages`.


### Transparent Context Runtime v0.17.2–v0.18.0

- `.agents/agentos/context_runtime.py`: relevance ranking, symbol-window compaction, global/per-file budgets, omission reporting, stale detection, and mode comparison.
- `.agents/agentos/cache.py` + `proxy.py`: validated task-scoped filesystem read cache.
- `.agents/agentos/collaboration.py`: enforced disclosure payload filtering.
- Database schema remained 23 because context manifests were additive JSON.


### Knowledge promotion and retrieval (v0.18.1–v0.19.1)

- `.agents/agentos/skills.py`: candidate/graduated skill lifecycle and audit.
- `.agents/agentos/retrieval.py`: backend-neutral local knowledge retrieval.
- `.agents/skills/`: human-approved, drift-tracked procedural skills.

## v0.19 Knowledge Retrieval Components

```text
.agents/agentos/embeddings.py       → optional dependency-free local embeddings and bounded RAG bundles
.agents/agentos/knowledge_graph.py  → evidence-backed relationship graph for concrete use cases
```

The lexical retriever remains the default. The graph is not a general-purpose inference engine; it materializes only relationships backed by AgentOS state or AST import evidence.


## v0.22.3 Core reintegration

The release runtime now requires both layers:

```text
Historical governance core
  core.py / policy.py / proxy.py / security.py / tooling.py / workflow.py
  external_audit.py / memory.py / db.py migrations 1-31
                    +
Project/database extension
  project_identity.py ... reconciliation_recovery.py migrations 32-40
                    ↓
Central db.py + CURRENT_SCHEMA_VERSION=40
```

`release_integrity.py`, `tools/verify_manifest.py`, and the historical + extension test suites are release gates.
