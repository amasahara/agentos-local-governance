# AgentOS Local Governance v0.24.3 — MCP Feature Runtime Refactor

Database schema remains **49**; this node has no state migration.

- Added `mcp_core_runtime.py` as the active owner of the 14 governed core MCP tools.
- Added `mcp_feature_handlers.py` and migrated 37 read-only handlers out of historical `mcp_*_gateway.py` modules.
- Added `mcp_feature_runtime.py` as the active flat feature catalog/dispatcher.
- Converted `mcp_catalog.py` into a compatibility facade; it no longer imports legacy gateway modules.
- `mcp_runtime.py` now imports neither `mcp_server.py` nor any `mcp_*_gateway.py`.
- Existing modern read-only feature modules remain direct in-process handlers.
- Public MCP surface remains 78 tools: 14 core + 63 feature + health.
- Governed core operations still traverse `gateway_client → gatewayd`; this trusted enforcement boundary is intentionally preserved.
- MCP feature mutation authority, SOURCE/TARGET database boundaries, human approval, privacy, signed audit and context-preservation rules are unchanged.
- Release integrity now rejects active MCP import paths that reintroduce legacy gateway ownership or subprocess forwarding.
