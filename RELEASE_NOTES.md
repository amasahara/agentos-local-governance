# AgentOS Local Governance v0.22.5 — Release Notes

## Unified CLI/MCP & Cross-Platform Runtime

- Added `agentos.cli_runtime`: one in-process command registry for core and v0.20-v0.22 extension CLIs.
- Added `agentos.mcp_runtime`: one stdio JSON-RPC MCP server with flat catalog/direct dispatch.
- Added `agentos.mcp_catalog` for unique extension read-only tool registration.
- Added POSIX/Windows parity wrappers for both CLI and MCP.
- Removed version-chained launchers and subprocess gateway forwarding from the top-level execution path.
- Historical version launchers/gateways remain as inactive compatibility/audit artifacts.
- Added `agentos.mcp_health`, `runtime-health`, and `commands-list` diagnostics.
- Preserved 14 governed core proxy MCP tools and 37 extension read-only MCP tools.
- Kept privileged extension mutation outside MCP and inside v0.22.4 task/session/signed-audit enforcement.
- Fixed stale `SCHEMA_VERSION` imports in v0.20.0/v0.20.1 CLI modules exposed by direct in-process loading.
- Moved manifest verification logic into an AgentOS library so unified CLI verification stays in-process.
- Database schema remains 41.
