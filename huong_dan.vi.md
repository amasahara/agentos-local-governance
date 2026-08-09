# Hướng dẫn AgentOS v0.22.5

Tiếng Việt

Sau khi nâng cấp, chạy `release-integrity-check`, `db-status`, `docs-check`, `instruction-check`, toàn bộ pytest, rồi `manifest-verify`. Không triển khai TARGET write production nếu integrity gate chưa pass.

Database schema: **41**


## v0.22.5 — Unified CLI/MCP

Dùng `.agents/bin/agentos` hoặc `.agents\bin\agentos.cmd`; cả hai đi vào `agentos.cli_runtime`. MCP dùng `agentos.mcp_runtime`. Kiểm tra bằng `agentos runtime-health`. Không gọi trực tiếp chuỗi `agentos.v02xx` trong vận hành mới.
