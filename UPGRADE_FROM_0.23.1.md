# Upgrade v0.23.1 → v0.23.2

Run only on an exact **v0.23.1 / schema 45** repository.

```bash
python3 tools/apply_v0232.py /path/to/agentos-v0.23.1 --dry-run
python3 tools/apply_v0232.py /path/to/agentos-v0.23.1

.agents/bin/agentos context-expansion-evaluation-db-sync
python3 tools/validate_v0232.py /path/to/agentos-v0.23.2
python3 tools/validate_release.py /path/to/agentos-v0.23.2
python3 -m pytest -q .agents/tests
```

The upgrader backs up replaced files, refuses the wrong predecessor version/schema, preserves earlier governance sections, installs migration 46, and rebuilds the target repository manifest/checksums.

No raw expanded content is migrated or persisted.
