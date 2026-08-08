# Upgrade AgentOS v0.20.1 → v0.20.2

## Dry run

```bash
python3 tools/apply_v0202.py /path/to/agentos-v0.20.1 --dry-run
```

## Apply

```bash
python3 tools/apply_v0202.py /path/to/agentos-v0.20.1
```

The upgrader fails closed unless it finds the expected v0.20.1 identity/selection runtime, migration 33, governance policy, and wrappers.

It creates a backup under:

```text
.agents/runtime/upgrade-backups/v0.20.2-<UTC>/
```

Then it installs v0.20.2 runtime/tests/docs, upgrades schema 33 → 34, preserves the v0.20.1 CLI/MCP stack as backends, and updates GitHub VI/EN documentation.

## Verify

```bash
.agents/bin/agentos project-consolidation-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests/test_project_consolidation_v0202.py
```
