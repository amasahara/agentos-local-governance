# Upgrade AgentOS v0.22.3 → v0.22.4

## Dry run

```bash
python3 tools/apply_v0224.py /path/to/agentos-v0.22.3 --dry-run
```

## Apply

```bash
python3 tools/apply_v0224.py /path/to/agentos-v0.22.3
```

## Validate

```bash
.agents/bin/agentos release-integrity-check
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
python3 -m pytest -q .agents/tests
python3 tools/verify_manifest.py .
python3 tools/validate_release.py .
```

## Operational change

Privileged database commands now require task/session context:

```bash
.agents/bin/agentos --task-id TASK-001 --session-id AGENT-1 <privileged-db-command> ...
```

The task must already be approved, owned by the session, have a completed `approve_task` workflow step, and run against an acknowledged drift-free governance baseline.
