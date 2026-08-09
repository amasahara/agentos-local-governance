# Hướng dẫn AgentOS v0.22.4

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Database schema: **41**

## Chạy privileged database command

1. Tạo task và hoàn tất approval workflow.
2. Claim task bằng session sẽ thực thi.
3. Acknowledge governance baseline và xử lý mọi drift trước khi mutation.
4. Gọi lệnh với context:

```bash
.agents/bin/agentos --task-id TASK-001 --session-id AGENT-1 db-target-insert-execute --insert-run-id 12
```

AgentOS sẽ kiểm task/session, policy, workflow, baseline/drift, cấp one-time guard token, chạy domain transaction, ký các domain event và complete token.

Nếu signed audit không ghi được, mutation phải fail-closed.
