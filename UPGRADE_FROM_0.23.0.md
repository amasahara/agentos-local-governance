# Upgrade v0.23.0 → v0.23.1

The upgrader accepts only an exact **v0.23.0 / schema 44** predecessor with the v0.23.0 context-transport runtime and policy present.

```bash
python3 tools/apply_v0231.py /path/to/agentos-v0.23.0 --dry-run
python3 tools/apply_v0231.py /path/to/agentos-v0.23.0

.agents/bin/agentos context-transport-db-sync
.agents/bin/agentos runtime-health
.agents/bin/agentos docs-check
python3 tools/validate_v0231.py .
python3 tools/validate_release.py .
python3 -m pytest -q .agents/tests
```

Migration is **44 → 45** and stays in the central `agentos.db.connect()` chain with `foreign_keys=ON`.

Existing v0.23.0 transport packs remain historical records. New v0.23.1 packs pin `model_profile_hash`, `budget_mode`, and `budget_decision_id`. Calibration starts empty and never requires replaying or rewriting historical prompts.
