# Windows

Dùng launcher hiện hành:

```powershell
.\.agents\bin\agentos.cmd --help
.\.agents\bin\agentos-admin.cmd --help
.\.agents\bin\agentos-mcp.cmd
```

PowerShell:

- đặt global options trước command;
- ưu tiên lệnh một dòng khi JSON hoặc human-decision options dài;
- không thêm dấu backslash trước option;
- backtick chỉ hợp lệ khi là ký tự cuối dòng.

POSIX và Windows wrappers phải giữ parity theo từng plane: `agentos` → `agentos.cli_runtime`, `agentos-admin` → `agentos.privileged_control_plane`, và `agentos-mcp` → `agentos.mcp_runtime`.
