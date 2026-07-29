# Hướng dẫn AgentOS v0.7.1 / AgentOS v0.7.1 Developer Guide

## Tiếng Việt

### Mục đích

AgentOS là lớp governance cục bộ cho coding agent. Hệ thống giữ một nguồn instruction duy nhất, policy có cấu trúc, runtime enforcement, SQLite audit, test và tài liệu trong cùng project.

### Thứ tự nên đọc

```text
README.md
→ AGENTS.md
→ .agents/config/governance.json
→ .agents/docs/PROJECT_STRUCTURE.md
→ .agents/docs/USAGE.md
→ .agents/agentos/
→ .agents/tests/
→ .agents/docs/RULES_WORKFLOW_CHANGELOG.md
```

### Workflow chuẩn

```text
nhận yêu cầu
→ đánh giá độ rõ
→ tạo và duyệt task
→ index code cục bộ
→ prepare-change
→ đọc context đề xuất
→ kiểm tra reuse/duplicate
→ kiểm tra write
→ thực thi
→ test và docs-check
→ ghi claim có evidence khi cần
→ review và báo cáo đồng bộ
```

### Claim và evidence

Claim là một kết luận có thể ảnh hưởng tới quyết định kỹ thuật, bảo mật, dữ liệu hoặc hành vi phá huỷ. Với claim rủi ro cao, agent phải ghi tool call thành công trước, lấy `tool_call_id`, rồi dùng ID đó trong `record-claim`.

`show-claim` cho phép reviewer xem chính xác tool nào, classification nào và output summary nào hỗ trợ kết luận.

### Quy tắc comment

Mỗi source file có một header chứa `File`, `Purpose`, `Responsibilities`. Contract của class/function nằm trong docstring của symbol và mô tả input, output, lỗi và side effect cần thiết.

### Checklist trước merge

```bash
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
.agents/bin/agentos docs-check
.agents/bin/agentos instruction-check
.agents/bin/agentos db-status
.agents/bin/agentos status
```

## English

### Purpose

AgentOS is a repository-local governance layer for coding agents. It synchronizes one instruction authority, structured policy, runtime enforcement, SQLite audit state, tests, and developer documentation.

### Recommended reading order

```text
README.md
→ AGENTS.md
→ .agents/config/governance.json
→ .agents/docs/PROJECT_STRUCTURE.md
→ .agents/docs/USAGE.md
→ .agents/agentos/
→ .agents/tests/
→ .agents/docs/RULES_WORKFLOW_CHANGELOG.md
```

### Standard workflow

```text
receive request
→ assess clarity
→ create and approve task
→ index local code
→ prepare-change
→ read recommended context
→ review reuse and duplicates
→ verify write permission
→ execute
→ test and docs-check
→ record evidence-grounded claims when required
→ review and report synchronization
```

### Claims and evidence

A claim is a conclusion that can affect engineering, security, data, destructive behavior, or governance decisions. High-risk claims require at least one successful tool execution from the same task. Use `show-claim` to inspect the exact evidence chain.

### Source documentation

Each source file has one `File`, `Purpose`, and `Responsibilities` header. Public symbol docstrings define input, output, errors, and material side effects.

### Pre-merge checklist

Run the test, documentation, instruction, database, and aggregate status commands shown in the Vietnamese section.
