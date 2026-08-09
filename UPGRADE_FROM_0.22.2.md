# Upgrade v0.22.2 → v0.22.3

This overlay targets GitHub `main` v0.22.2 from `amasahara/agentos-local-governance`.

```bash
python3 tools/apply_v0223.py /path/to/agentos-v0.22.2 --dry-run
python3 tools/apply_v0223.py /path/to/agentos-v0.22.2

.agents/bin/agentos release-integrity-check
.agents/bin/agentos db-status
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
python3 tools/build_manifest.py . --kind full
python3 tools/verify_manifest.py .
```

The upgrader fails unless `VERSION` is exactly `0.22.2` and the known broken 10-line `db.py` pattern plus historical core files are present. It creates a timestamped backup before mutation.
