# Hướng dẫn AgentOS v0.24.3 — MCP Feature Runtime Refactor

Current version: **0.24.3**. Database schema: **49**.

## Quy tắc active MCP

- `mcp_runtime`: chỉ JSON-RPC và dispatch.
- `mcp_core_runtime`: 14 governed core tools.
- `mcp_feature_runtime`: flat feature catalog/dispatch.
- `mcp_feature_handlers`: 37 handlers được tách khỏi legacy gateway.
- Không import `mcp_*_gateway.py` hoặc `mcp_server.py` vào active path.
- Không subprocess/version forwarding.
- Feature mutation authority không đổi.
- Trusted `gateway_client → gatewayd` vẫn bắt buộc cho governed core tools.

## Kiểm tra

```powershell
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```
