# AgentOS Local Governance v0.24.3 — MCP Feature Runtime Refactor

[README landing](README.md) | [Tiếng Việt](README.vi.md)

**Current release: v0.24.3 — MCP Feature Runtime Refactor**  
Database schema: **49**.

v0.24.3 moves active feature handlers out of historical version-forwarding MCP
gateway modules. `mcp_runtime` now delegates read-only feature execution to
`mcp_feature_runtime` and governed core execution to `mcp_core_runtime`.

37 gateway-embedded feature handlers are now runtime-native. The public tool
surface remains 78 tools and no extension mutation permission is added.

The trusted `gateway_client → gatewayd` boundary remains active for governed
core operations; this is an enforcement boundary, not legacy MCP forwarding.

See [Upgrade v0.24.2 → v0.24.3](UPGRADE_FROM_0.24.2.md) and
[MCP Feature Runtime Refactor](.agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md).
