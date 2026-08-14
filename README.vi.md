# AgentOS Local Governance v0.24.3 — MCP Feature Runtime Refactor

[README landing](README.md) | [English](README.en.md)

**Phiên bản hiện tại: v0.24.3 — MCP Feature Runtime Refactor**  
Database schema: **49**.

## v0.24.3

Active MCP feature handlers đã được tách khỏi các `mcp_*_gateway.py` lịch sử.
Các gateway cũ có thể vẫn tồn tại để giữ historical compatibility nhưng không
còn được import bởi active runtime.

```text
mcp_runtime
├─ mcp_core_runtime
│  └─ gateway_client → gatewayd
└─ mcp_feature_runtime
   ├─ mcp_feature_handlers
   └─ modern read-only feature modules
```

37 read-only handlers được chuyển sang runtime-native implementation. Tool surface
không đổi: 14 core + 63 feature + health.

## Invariant

- Schema vẫn 49.
- Không subprocess/version-forward trong active MCP runtime.
- Governed core tools vẫn đi qua trusted enforcement gateway.
- Không thêm mutation authority cho feature MCP.
- SOURCE/TARGET DB boundary, approval, privacy, audit và Context Control Plane giữ nguyên.

## Kiểm tra

```powershell
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

Xem [UPGRADE_FROM_0.24.2.md](UPGRADE_FROM_0.24.2.md) và
[MCP Feature Runtime Refactor](.agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md).
