# Upgrade v0.21.2 → v0.22.0

```bash
python3 tools/apply_v0220.py /path/to/agentos-v0.21.2 --dry-run
python3 tools/apply_v0220.py /path/to/agentos-v0.21.2

.agents/bin/agentos db-controlled-target-insert-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```

The upgrader requires exact `VERSION=0.21.2`, preserves a backup under `.agents/runtime/upgrade-backups/`, installs schema 38, chains the previous CLI/MCP wrappers, and keeps generic TARGET INSERT denied.

Before production execution, configure a TARGET credential reference. Prefer a database account whose grants permit INSERT only on the approved target schema/tables plus required catalog reads.
