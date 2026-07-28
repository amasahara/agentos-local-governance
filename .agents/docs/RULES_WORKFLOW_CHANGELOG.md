# RULES & WORKFLOW CHANGELOG / NHẬT KÝ RULES VÀ WORKFLOW

Mỗi thay đổi governance phải được thêm vào đầu file.

Add each governance change at the top of this file.

## Entry template / Mẫu ghi nhận

```markdown
## YYYY-MM-DD — vX.Y.Z — Title

### Yêu cầu / Request
...

### Quyết định / Decision
...

### Enforcement
- instruction:
- configuration:
- runtime:
- tests:

### File ảnh hưởng / Affected files
...

### Migration note
...
```

---

## 2026-07-28 — v0.5.1 — Bilingual developer documentation and synchronization gate

### Yêu cầu / Request

Bổ sung tài liệu tiếng Việt/tiếng Anh để developer dễ hiểu cấu trúc project, đặc biệt khi yêu cầu người dùng thay đổi rules hoặc workflow.

Add Vietnamese/English documentation so developers can understand the project, especially after user requests that modify project rules or workflows.

### Quyết định / Decision

- Thêm `huong_dan.md` làm điểm bắt đầu đọc project.
- Thêm mô tả cấu trúc chi tiết.
- Thêm changelog riêng cho rules/workflow.
- Quy định governance change phải đánh giá và đồng bộ instruction, config, implementation, tests, documentation và version.
- Thêm `docs-check` để phát hiện thiếu tài liệu hoặc version drift.

- Add `huong_dan.md` as the project reading entry point.
- Add a detailed structure document.
- Add a dedicated rules/workflow changelog.
- Require governance changes to evaluate and synchronize instructions, configuration, implementation, tests, documentation, and version.
- Add `docs-check` to detect missing documentation or version drift.

### Enforcement

- instruction: `AGENTS.md`
- configuration: `.agents/config/governance.json`
- runtime: `.agents/agentos/core.py`, `.agents/agentos/cli.py`
- tests: `.agents/tests/test_agentos.py`

### Migration note

Projects upgrading from v0.5.0 should copy the three documentation files, update the governance synchronization policy, and run:

```bash
.agents/bin/agentos docs-check
```

---

## 2026-07-28 — v0.5.0 — Clarification gate and tool-loop guard

### Yêu cầu / Request

Ngăn LLM tự suy diễn yêu cầu chưa rõ và giảm tool call lỗi lặp lại.

Prevent LLMs from inferring unclear requirements and reduce repeated failing tool calls.

### Quyết định / Decision

Added clarity assessment, approval/write gates, environment detection, tool budgets, normalized failure signatures, and composite change preparation.
