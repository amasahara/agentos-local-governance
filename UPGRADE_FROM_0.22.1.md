# Upgrade v0.22.1 → v0.22.2

```bash
python3 tools/apply_v0222.py /path/to/agentos-v0.22.1 --dry-run
python3 tools/apply_v0222.py /path/to/agentos-v0.22.1

.agents/bin/agentos db-reconciliation-recovery-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```

Migration is additive: schema 39 → 40. Existing committed runs remain committed. Existing `committing/in_doubt` runs are not automatically retried or resolved; use v0.22.2 recovery scanning and read-only reconciliation. Generic TARGET writes and SOURCE writes remain forbidden.
