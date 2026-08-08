# Primary-Project Consolidation — v0.20.2

## Mục tiêu

AgentOS v0.20.2 gộp có hướng: **N Secondary Project → 1 Primary Project đã được người dùng chọn ở v0.20.1**.

```text
Secondary A ─┐
Secondary B ─┼── read-only ──> mapping/review/approval ──> Primary
Secondary C ─┘                                        controlled write
```

## Invariants

1. Primary phải là active AgentOS root và đã được human-select ở v0.20.1.
2. Secondary chỉ được đọc; AgentOS v0.20.2 không tạo/sửa/xóa file, state hay SQLite trong Secondary.
3. `AGENTS.md`, `VERSION`, `.agents/` và `.git/` không được nhập từ Secondary và không được ghi bởi consolidation.
4. Governance của Primary luôn là authority.
5. Không copy toàn repository. Mỗi component phải có mapping tường minh.
6. Approval gắn với `plan_hash`; plan đổi thì phải review/approve lại.
7. Trước execution phải re-verify source project manifest, source file hash và target expected hash/absence.
8. Mọi materialized component có provenance và backup nếu target cũ bị thay thế.

## Actions

- `REUSE`: dùng component đã tồn tại trong Primary; không ghi file.
- `MOVE`: tên nghiệp vụ; implementation **copy exact bytes** vào Primary và không xóa Source.
- `ADAPT`: ghi nội dung đã chuẩn bị trong Primary vào target đã duyệt.
- `REIMPLEMENT`: tương tự ADAPT nhưng thể hiện implementation mới dựa trên yêu cầu/capability nguồn.
- `IGNORE`: không đưa component vào Primary.
- `CONFLICT`: đánh dấu xung đột; block review/approval cho tới khi lập lại mapping đã giải quyết.

## Workflow

```text
primary selected (v0.20.1)
→ create consolidation
→ register component mappings
→ human review
→ human approval
→ execute từng mapping
→ complete
```

Rollback từng mapping ghi file yêu cầu human confirmation và chỉ chạy khi target vẫn đúng `target_after_hash`; nếu target đã bị thay đổi sau consolidation, rollback fail-closed.

## MCP boundary

MCP chỉ expose read-only:

- `agentos.project_consolidation_get`
- `agentos.project_consolidation_plan_get`
- `agentos.project_consolidation_provenance_get`

Review, approval, execution và rollback không expose cho LLM qua MCP.
