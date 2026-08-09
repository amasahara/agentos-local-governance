# Upgrade v0.21.0 → v0.21.1

Run a dry-run first:

```bash
python3 tools/apply_v0211.py /path/to/agentos-v0.21.0 --dry-run
```

Apply:

```bash
python3 tools/apply_v0211.py /path/to/agentos-v0.21.0
.agents/bin/agentos db-schema-mapping-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests/test_schema_mapping_v0211.py
```

Migration is additive: schema 35 → 36. v0.21.0 connection/consolidation state is preserved. No external database is contacted by the upgrader.
