[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.5

## Unified CLI/MCP & Cross-Platform Runtime

v0.22.5 removes version-forwarding chains from the **active runtime path** while preserving the v0.22.4 enforcement boundary.

### Runtime architecture

```text
POSIX agentos ─┐
Windows .cmd ──┴→ agentos.cli_runtime → one command registry → in-process handlers

POSIX MCP ─────┐
Windows MCP.cmd┴→ agentos.mcp_runtime → one flat tool catalog → direct handlers
```

### Guarantees

- No top-level CLI execution through `agentos.v0224 → ... → agentos.v0195`.
- No MCP subprocess forwarding through historical gateway/version chains.
- POSIX and Windows wrappers execute the same Python runtimes.
- Duplicate CLI commands and MCP tool names fail closed.
- Unknown CLI commands return non-zero; unknown MCP methods return JSON-RPC `-32601`.
- `agentos.mcp_health` reports privacy-safe runtime/catalog health.
- 14 historical core MCP proxy tools remain governed through the session gateway.
- 37 project/database extension MCP tools remain read-only; privileged database/identity/recovery mutation is not exposed.
- Privileged extension CLI commands still require task/session context and v0.22.4 signed governance enforcement.
- Historical launchers/gateways may remain for audit/reference but are not active runtime dependencies.

Current registry size: **193 CLI commands** and **52 MCP tools**. Database schema remains **41**.

## Upgrade

See [UPGRADE_FROM_0.22.4.md](UPGRADE_FROM_0.22.4.md).
