# Windows

Dùng launcher hiện hành:

```powershell
.\.agents\bin\agentos.cmd --help
.\.agents\bin\agentos-mcp.cmd
```

PowerShell:

- đặt global options trước command;
- ưu tiên lệnh một dòng khi JSON hoặc human-decision options dài;
- không thêm dấu backslash trước option;
- backtick chỉ hợp lệ khi là ký tự cuối dòng.

POSIX và Windows wrappers phải đi vào cùng `agentos.cli_runtime` và `agentos.mcp_runtime`.
