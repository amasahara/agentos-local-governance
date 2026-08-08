# Upgrade AgentOS v0.21.1 → v0.21.2

## Dry run

```bash
python3 tools/apply_v0212.py /path/to/agentos-v0.21.1 --dry-run
```

## Apply

```bash
python3 tools/apply_v0212.py /path/to/agentos-v0.21.1
```

The upgrader validates `VERSION=0.21.1`, schema-36 integration, database/schema-mapping policy, then creates a backup before patching.

## Verify

```bash
.agents/bin/agentos db-readonly-extraction-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```

Expected AgentOS state schema: **37**.

## Operational note

v0.21.2 can read SOURCE business records only through generated SELECT-only extraction batches. Production extraction requires an optional local DB driver and a trusted secret resolver. TARGET INSERT remains blocked until v0.22.0.
