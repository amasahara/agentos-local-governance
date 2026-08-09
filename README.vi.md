[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.5

## Unified CLI/MCP & Cross-Platform Runtime

v0.22.5 loại bỏ chuỗi version-forwarding khỏi **đường chạy thực tế** của CLI và MCP, đồng thời giữ nguyên enforcement boundary v0.22.4.

### Runtime mới

```text
Linux/macOS                      Windows
.agents/bin/agentos             .agents/bin/agentos.cmd
        \                           /
         → agentos.cli_runtime ←
                  ↓
          unified command registry
                  ↓
      core CLI / feature CLI in-process

.agents/bin/agentos-mcp         .agents/bin/agentos-mcp.cmd
        \                           /
         → agentos.mcp_runtime ←
                  ↓
          one flat MCP catalog
                  ↓
core governed proxy + extension read-only handlers
```

### Guarantee

- Top-level CLI không `exec` qua `agentos.v0224 → ... → agentos.v0195`.
- Top-level MCP không `Popen` qua chuỗi gateway/version backend.
- POSIX và Windows gọi cùng Python runtime.
- Registry CLI phát hiện duplicate command và fail-closed.
- MCP catalog phát hiện duplicate tool và fail-closed.
- Unknown CLI command trả exit code khác 0.
- Unknown MCP method trả JSON-RPC `-32601`.
- MCP có `agentos.mcp_health` để kiểm tra catalog/runtime mà không lộ secret.
- 14 core proxy tools vẫn đi qua session gateway/enforcement hiện hữu.
- 37 extension tools vẫn chỉ đọc; database/identity/recovery mutation không được expose qua MCP.
- Privileged extension CLI mutation vẫn bắt buộc `--task-id` + `--session-id` và dùng enforcement v0.22.4.
- Legacy `agentos.v02xx`, `agentos-mcp.v02xx` và gateway module có thể còn trong source để audit/backward reference nhưng không được top-level wrapper gọi.

### Quy mô catalog hiện tại

```text
CLI commands:                 193 unique
MCP core proxy tools:          14
MCP extension read-only:       37
MCP health:                     1
MCP total:                     52 unique
Database schema:               41
```

### Lệnh kiểm tra

```bash
.agents/bin/agentos runtime-health
.agents/bin/agentos commands-list
.agents/bin/agentos release-integrity-check
```

MCP health:

```text
agentos.mcp_health
```

### Windows

```bat
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd commands-list
```

MCP:

```bat
.agents\bin\agentos-mcp.cmd --task-id TASK-001 --session-id AGENT-A
```

Core MCP proxy actions yêu cầu task/session binding và `AGENTOS_SESSION_TOKEN`. Extension read-only tools và health/discovery không yêu cầu mutation context.

### Security boundary

v0.22.5 **không nới quyền** so với v0.22.4. Unified runtime chỉ thay transport/dispatch. Task approval, session ownership, baseline/drift, one-time token và signed audit của privileged database-domain mutation vẫn giữ nguyên.

## Upgrade

Xem [UPGRADE_FROM_0.22.4.md](UPGRADE_FROM_0.22.4.md).
