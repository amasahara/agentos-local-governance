# Upgrade AgentOS v0.22.7 → v0.23.0

## Preconditions

- `VERSION` must be exactly `0.22.7`.
- v0.22.7 privacy lifecycle must already be present.
- Existing SOURCE read-only, Controlled Target Insert, identity/recovery, secret/key lifecycle, and privacy invariants remain authoritative.

## Apply

```bash
python3 tools/apply_v0230.py /path/to/agentos-v0.22.7 --dry-run
python3 tools/apply_v0230.py /path/to/agentos-v0.22.7
```

Then run:

```bash
.agents/bin/agentos context-transport-db-sync
.agents/bin/agentos runtime-health
.agents/bin/agentos docs-check
python3 tools/validate_v0230.py .
python3 -m pytest -q .agents/tests
```

Schema migrates 43 → 44 through the central migration chain. Existing canonical Context Packs remain canonical evidence; v0.23.0 creates new derived Transport Packs only when explicitly compiled. No existing context pack is rewritten.
