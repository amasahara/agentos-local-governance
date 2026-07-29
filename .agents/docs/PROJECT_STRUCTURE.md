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
