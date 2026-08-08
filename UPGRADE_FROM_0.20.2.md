# Upgrade v0.20.2 → v0.21.0

```bash
python3 tools/apply_v0210.py /path/to/agentos-v0.20.2 --dry-run
python3 tools/apply_v0210.py /path/to/agentos-v0.20.2
.agents/bin/agentos db-boundary-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests/test_database_boundary_v0210.py
```

The upgrader refuses any baseline whose `VERSION` is not exactly `0.20.2` or whose v0.20.2 consolidation policy/migration is missing.

No database credentials are migrated. v0.21.0 introduces only endpoint metadata and boundary state.
