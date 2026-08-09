# Hướng dẫn AgentOS v0.23.0

## Luồng chuẩn

1. Tạo/duyệt task và approved scope.
2. Xây canonical Context Pack bằng runtime hiện có.
3. Kiểm tra Context Pack không stale.
4. Chạy `context-transport-compile`.
5. Kiểm tra `context-transport-explain` và `context-token-report`.
6. Chỉ dùng transport có trạng thái `READY`.
7. Khi LLM cần evidence đã bỏ, dùng expansion handle read-only thay vì nới compression tùy ý.

Ví dụ:

```bash
.agents/bin/agentos --task-id TASK-001 context-transport-compile --model-profile generic-128k
.agents/bin/agentos --task-id TASK-001 context-transport-explain
.agents/bin/agentos --task-id TASK-001 context-token-report
.agents/bin/agentos --task-id TASK-001 context-requirement-get
```

Nếu Control Plane vượt budget, đổi sang model profile có context capacity lớn hơn hoặc giảm overhead hợp lệ; **không được cắt original request/AGENTS/scope/plan/requirements**.
