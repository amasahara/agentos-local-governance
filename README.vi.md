[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

# AgentOS Local Governance v0.22.4

## Unified Governance Enforcement & Signed Audit

v0.22.4 đưa nhánh project/database v0.20–v0.22 vào cùng enforcement boundary với lõi governance đã được khôi phục ở v0.22.3.

### Luồng bắt buộc cho privileged mutation

```text
approved task + owner session
        ↓
workflow approve_task done
        ↓
initialized baseline + no drift
        ↓
approved sensitive override only
        ↓
one-time guard token
        ↓
domain transaction
        ↓
privacy-safe signed domain events
        ↓
guarded completion + signed completion
```

### Guarantee

- Privileged database-domain mutation trên một AgentOS project hợp lệ bắt buộc có `task_id` và `session_id`.
- Task phải được approve và session gọi phải là owner hiện tại.
- Governance baseline chưa acknowledge hoặc có drift chưa acknowledge sẽ chặn mutation.
- Mỗi business operation dùng đúng một guard token; không tạo token theo từng câu SQL nội bộ.
- Sáu event table của database pipeline lưu `governed_operation_id` và `external_event_hash`.
- Signed audit failure chặn operation trước khi local domain event được persist.
- Sáu module database dùng chung `agentos.db.connect()`; SQLite foreign keys và busy timeout áp dụng nhất quán.
- Các invariant SOURCE write/raw TARGET write/identity auto-decision/in-doubt auto-recovery được validate fail-closed và không thể bật bằng policy override.
- MCP tiếp tục read-only đối với privileged database mutations.

### CLI

Privileged command dùng governance context ở trước command:

```bash
.agents/bin/agentos \
  --task-id TASK-001 \
  --session-id AGENT-1 \
  db-connection-register ...
```

Có thể dùng `AGENTOS_TASK_ID` và `AGENTOS_SESSION_ID` thay cho prefix flags.

### Schema

Database schema: **41**

Schema 41 bổ sung `governed_operations` và correlation columns cho:

- `db_boundary_events`
- `db_schema_mapping_events`
- `db_extraction_events`
- `db_target_insert_events`
- `identity_resolution_events`
- `db_recovery_events`

### Roadmap tiếp theo

v0.22.5 sẽ flatten CLI/MCP và hoàn thiện cross-platform runtime; v0.22.4 cố ý chưa thực hiện refactor đó.
