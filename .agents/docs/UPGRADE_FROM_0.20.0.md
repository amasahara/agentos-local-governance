# Upgrade AgentOS v0.20.0 → v0.20.1

v0.20.1 is an additive governance upgrade. It does not consolidate project source code.

## Pre-conditions

- `VERSION` must be exactly `0.20.0`.
- v0.20.0 Project Identity & Purpose must be present and human-confirmed.
- Schema 32 migration registry must be present.
- The v0.20.0 CLI wrapper and identity MCP sidecar must be intact.

## Apply

```bash
python3 tools/apply_v0201.py /path/to/agentos-v0.20.0 --dry-run
python3 tools/apply_v0201.py /path/to/agentos-v0.20.0
```

The upgrader backs up every changed file under:

```text
.agents/runtime/upgrade-backups/v0.20.1-<UTC>/
```

## Migration

```text
schema 32 → schema 33
```

New tables:

- `project_candidate_sets`
- `project_candidates`
- `project_compatibility`
- `primary_project_selections`
- `project_selection_events`

## Verify

```bash
.agents/bin/agentos project-selection-db-sync
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
PYTHONPATH=.agents python3 -m pytest .agents/tests/test_project_selection_v0201.py -q
```

## Behavior change

v0.20.1 adds a mandatory business compatibility and human Primary-selection gate. It still performs no physical merge; v0.20.2 owns that capability.
