# Upgrade AgentOS v0.22.4 → v0.22.5

## Scope

v0.22.5 replaces active version-forwarded CLI/MCP routing with unified Python runtimes. Database schema remains 41; v0.22.4 governance enforcement remains mandatory.

## Apply

```bash
python3 tools/apply_v0225.py /path/to/agentos-v0.22.4 --dry-run
python3 tools/apply_v0225.py /path/to/agentos-v0.22.4
```

## Validate

```bash
.agents/bin/agentos runtime-health
.agents/bin/agentos release-integrity-check
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
python3 -m pytest -q .agents/tests/test_unified_runtime_v0225.py
```

Windows:

```bat
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd release-integrity-check
```

## Expected invariants

- `VERSION = 0.22.5`;
- schema remains `41`;
- top-level POSIX/Windows wrappers call `agentos.cli_runtime` / `agentos.mcp_runtime`;
- top-level wrappers do not call versioned launchers;
- MCP catalog has unique tool names and contains `agentos.mcp_health`;
- privileged database-domain mutation still requires v0.22.4 task/session enforcement.
