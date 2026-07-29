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


## v0.8.1 repaired modules

- `.agents/agentos/tooling.py`: conservative tool classification, guard decisions, tool audit events, and egress reports. It does not write canonical `tool_calls`.
- `.agents/agentos/cache.py`: task/path/range-scoped file-read summaries validated by mtime, size, and SHA-256 content hash.
- `.agents/agentos/documentation.py`: AST-based source documentation scan for module headers and public-symbol docstrings.
- `.agents/agentos/db.py` migration 5: creates `tool_events`, `egress_events`, and `file_read_cache`.

## v0.8.1 components

- `.agents/agentos/workflow.py`: current-task persistence, workflow seeding, step state, next-step and completion status.
- `.agents/agentos/drift.py`: governance baseline hashing, change logging, drift reports and diffs.
- `.agents/bin/install.sh` / `install.cmd`: non-destructive installation.
- `.agents/bin/install-git-hooks.sh`: optional Git gate installation.
- `.agents/bin/hooks/pre-commit`: instruction, documentation, drift and test gate.
- `.agents/config/governance.local.json`: optional project-specific override, tracked when present.
- `.agents/runtime/current_task.json`: generated local session heartbeat; never committed.
