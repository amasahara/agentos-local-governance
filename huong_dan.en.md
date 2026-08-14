# AgentOS v0.24.3 Developer Guide — MCP Feature Runtime Refactor

Current version: **0.24.3**. Database schema: **49**.

Active MCP rules:

- `mcp_runtime` owns protocol/dispatch only.
- `mcp_core_runtime` owns the 14 governed core tools.
- `mcp_feature_runtime` owns the flat read-only feature runtime.
- `mcp_feature_handlers` owns the 37 migrated legacy-embedded handlers.
- Active modules must not import `mcp_*_gateway.py` or `mcp_server.py`.
- Active runtime must not use subprocess/version forwarding.
- Core governance enforcement remains `gateway_client → gatewayd`.

Run manifest verification, generic release validation, and full regression before release.
