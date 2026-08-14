# v0.24.3 — MCP Feature Runtime Refactor

## Mục tiêu

Tách **active MCP feature handlers** khỏi các module `mcp_*_gateway.py` lịch sử
mà trước đây vừa chứa read-only handler vừa chứa `subprocess`/version-forwarding
compatibility logic.

v0.24.3 là runtime refactor thuần code. **Database schema giữ nguyên 49**.

## Kiến trúc trước v0.24.3

```text
mcp_runtime
  ├─ mcp_catalog
  │   ├─ mcp_identity_gateway
  │   ├─ mcp_selection_gateway
  │   ├─ ...
  │   └─ mcp_reconciliation_recovery_gateway
  └─ mcp_server.TOOLS
```

`mcp_runtime` không subprocess-forward trực tiếp, nhưng active catalog vẫn import
handler từ các legacy gateway module có `subprocess.Popen` và version-chaining.

## Kiến trúc v0.24.3

```text
mcp_runtime                 JSON-RPC + dispatch only
  ├─ mcp_core_runtime       14 governed core tools
  │    └─ gateway_client → gatewayd
  │         trusted enforcement boundary
  └─ mcp_feature_runtime
       ├─ mcp_feature_handlers
       │    37 handlers migrated out of legacy gateways
       └─ modern read-only MCP feature modules
```

`mcp_catalog.py` chỉ còn compatibility facade re-export active feature runtime.

## Legacy gateway status

Các `mcp_*_gateway.py` lịch sử có thể vẫn tồn tại để giữ historical source/test
compatibility, nhưng:

- không được import bởi `mcp_runtime.py`;
- không được import bởi `mcp_feature_runtime.py`;
- không được import bởi `mcp_feature_handlers.py`;
- không được import bởi `mcp_catalog.py`;
- không được sở hữu active handler;
- không được subprocess/version-forward trong active execution path.

`mcp_server.py` cũng không còn cung cấp tool catalog cho active runtime.

## Trusted core enforcement gateway

`gateway_client → gatewayd` **không phải legacy MCP gateway forwarding**. Đây là
security boundary hiện tại cho 14 governed core tools có filesystem/process/network
và task/session operations.

v0.24.3 giữ nguyên boundary này để không nới quyền.

## Tool surface

v0.24.3 không thêm tool mới và không đổi tên tool:

- 14 governed core tools;
- 63 read-only feature tools;
- 1 `agentos.mcp_health`;
- tổng 78 tools.

37 feature tools từng nằm trong gateway modules được chuyển sang runtime-native
handlers.

## Governance invariants

- MCP feature mutation authority không thay đổi.
- SOURCE/TARGET database mutation policy không thay đổi.
- Human approval/review gates không thay đổi.
- Secret/privacy/context boundaries không thay đổi.
- Không schema migration.
- Không subprocess/version forwarding trong active MCP feature runtime.
- Duplicate tool names vẫn fail-closed.

## Health

`agentos.mcp_health` báo thêm:

- `runtime = mcp_feature_runtime_v1`;
- `legacy_gateway_handler_count = 0`;
- `runtime_native_migrated_tool_count = 37`;
- `trusted_enforcement_gateway = true`.
