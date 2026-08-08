# Upgrade v0.22.0 → v0.22.1

```bash
python3 tools/apply_v0221.py /path/to/agentos-v0.22.0 --dry-run
python3 tools/apply_v0221.py /path/to/agentos-v0.22.0
.agents/bin/agentos db-identity-resolution-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```

## Important migration behavior

- Database schema upgrades from 38 to 39 additively.
- Existing SOURCE/TARGET, schema mapping, extraction, and controlled insert state is preserved.
- New controlled insert plans require a `resolved` v0.22.1 identity-resolution artifact.
- Pre-existing v0.22.0 insert plans without identity binding are intentionally fail-closed/stale after upgrade and must be rebuilt after identity resolution.
- `.agents/state/identity_lineage.key` is generated locally on first identity resolution; do not commit or share it across unrelated projects.
