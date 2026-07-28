# HƯỚNG DẪN AGENTOS / AGENTOS GUIDE

> Tài liệu đọc nhanh dành cho developer và coding agent.  
> Quick-reference documentation for developers and coding agents.

---

## 1. Mục đích / Purpose

### Tiếng Việt

AgentOS là lớp quản trị cho coding agent. Hệ thống không thay thế LLM hoặc framework của project. Nó quy định:

- khi nào agent phải hỏi lại người dùng;
- khi nào agent được phép lập kế hoạch và sửa code;
- cách giới hạn và ghi nhận tool call;
- cách đặt file, tìm code tương tự và tránh trùng lặp;
- cách đồng bộ rules, workflow, tài liệu và kiểm thử;
- cách giúp developer hiểu các quyết định đã được áp dụng.

### English

AgentOS is a governance layer for coding agents. It does not replace the LLM or the application's framework. It defines:

- when the agent must ask the user for clarification;
- when planning and code modification are allowed;
- how tool calls are limited and recorded;
- how files are placed and duplicate implementations are avoided;
- how rules, workflows, documentation, and tests stay synchronized;
- how developers can understand the decisions applied to the project.

---

## 2. Bắt đầu đọc project ở đâu? / Where should I start?

| Thứ tự / Order | File hoặc thư mục / File or directory | Mục đích / Purpose |
|---|---|---|
| 1 | `huong_dan.md` | Bản đồ tổng quan song ngữ / Bilingual project map |
| 2 | `AGENTS.md` | Nguồn rules duy nhất cho agent / Sole agent instruction source |
| 3 | `.agents/config/governance.json` | Cấu hình thực thi có cấu trúc / Machine-readable governance |
| 4 | `.agents/docs/USAGE.md` | Ví dụ CLI / CLI examples |
| 5 | `.agents/docs/PROJECT_STRUCTURE.md` | Mô tả từng thành phần / Component-by-component structure |
| 6 | `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` | Lịch sử thay đổi rules và workflow / Rules and workflow history |
| 7 | `.agents/agentos/core.py` | Logic quản trị chính / Core governance implementation |
| 8 | `.agents/tests/` | Hành vi được đảm bảo bằng test / Tested guarantees |

### Quy tắc đọc nhanh / Fast reading rule

- Muốn biết agent **phải làm gì**: đọc `AGENTS.md`.
- Muốn biết hệ thống **được cấu hình thế nào**: đọc `governance.json`.
- Muốn biết **chạy lệnh nào**: đọc `USAGE.md`.
- Muốn biết **vì sao rules/workflow đã thay đổi**: đọc `RULES_WORKFLOW_CHANGELOG.md`.
- Muốn kiểm chứng hành vi: đọc `.agents/tests/`.

---

## 3. Cấu trúc project / Project structure

```text
project-root/
├── AGENTS.md
├── huong_dan.md
├── VERSION
├── .gitignore
└── .agents/
    ├── agentos/
    │   ├── __init__.py
    │   ├── core.py
    │   └── cli.py
    ├── bin/
    │   ├── agentos
    │   └── agentos.cmd
    ├── config/
    │   └── governance.json
    ├── docs/
    │   ├── USAGE.md
    │   ├── PROJECT_STRUCTURE.md
    │   └── RULES_WORKFLOW_CHANGELOG.md
    ├── tests/
    │   └── test_agentos.py
    ├── state/
    ├── cache/
    └── runtime/
```

### Phân loại / Classification

- **Human entry points:** `huong_dan.md`, `PROJECT_STRUCTURE.md`, changelog.
- **Agent authority:** `AGENTS.md`.
- **Machine policy:** `governance.json`.
- **Implementation:** `.agents/agentos/`.
- **Validation:** `.agents/tests/`.
- **Runtime state:** `.agents/state/`, `.agents/cache/`, `.agents/runtime/`.

`huong_dan.md` là tài liệu giải thích, không phải nguồn instruction thứ hai. Khi có xung đột, `AGENTS.md` và `governance.json` phải được sửa đồng bộ; agent không được tự chọn một tài liệu cũ hơn.

`huong_dan.md` is explanatory documentation, not a second instruction source. If documents conflict, `AGENTS.md` and `governance.json` must be synchronized; the agent must not silently choose an older document.

---

## 4. Workflow chuẩn / Standard workflow

```text
receive_request
→ analyze_intent
→ assess_requirement_clarity
→ clarify_if_needed
→ create_task_brief
→ governance_check
→ plan
→ await_approval
→ prepare_change
→ execute
→ validate
→ review
→ synchronize
→ report
```

### Ý nghĩa / Meaning

1. **Receive request:** giữ nguyên yêu cầu gốc.
2. **Analyze intent:** xác định loại công việc và rủi ro.
3. **Assess clarity:** kiểm tra target, hành vi hiện tại, kết quả mong muốn, scope và acceptance criteria.
4. **Clarify:** dừng để hỏi khi thiếu thông tin có thể làm thay đổi cách triển khai.
5. **Task brief:** ghi lại yêu cầu đã được làm rõ và các giả định được phép.
6. **Governance check:** kiểm tra rules, quyền ghi và giới hạn tool.
7. **Plan:** tạo kế hoạch sau khi task đủ rõ.
8. **Approval:** chờ phê duyệt khi workflow yêu cầu.
9. **Prepare change:** gộp placement, duplicate scan, write check và context recommendation.
10. **Execute:** thay đổi trong scope được duyệt.
11. **Validate:** chạy kiểm thử phù hợp.
12. **Review:** kiểm tra cấu trúc, bảo mật, duplication và regression.
13. **Synchronize:** cập nhật tài liệu, rules, config, changelog và version khi cần.
14. **Report:** báo cáo kết quả, giả định và hạn chế còn lại.

---

## 5. Khi người dùng yêu cầu thay đổi rules hoặc workflow / When a user requests rules or workflow changes

Đây là thay đổi quản trị, không phải thay đổi code thông thường.

This is a governance change, not an ordinary code change.

### Bộ file bắt buộc xem xét / Required synchronization set

```text
AGENTS.md
.agents/config/governance.json
huong_dan.md
.agents/docs/PROJECT_STRUCTURE.md
.agents/docs/USAGE.md
.agents/docs/RULES_WORKFLOW_CHANGELOG.md
.agents/agentos/core.py or cli.py, when behavior changes
.agents/tests/, when behavior changes
VERSION
```

Không phải mọi file đều cần sửa trong mọi thay đổi, nhưng agent phải đánh giá từng file và ghi lý do nếu không sửa.

Not every file must change every time, but the agent must evaluate each file and record why an item was unchanged.

### Quy trình bắt buộc / Required process

```text
classify as governance_change
→ clarify desired rule and enforcement level
→ identify authoritative files
→ assess compatibility and migration impact
→ update rule text
→ update machine-readable policy
→ update implementation if enforcement changes
→ add or update tests
→ update bilingual documentation
→ append changelog entry
→ bump version
→ run docs-check and tests
→ report synchronization matrix
```

### Ma trận báo cáo / Synchronization matrix

Báo cáo cuối phải cho biết:

| Thành phần / Component | Trạng thái / Status | Lý do / Reason |
|---|---|---|
| `AGENTS.md` | updated / unchanged | Rule text changed or not |
| `governance.json` | updated / unchanged | Machine policy changed or not |
| implementation | updated / unchanged | Runtime enforcement changed or documentation-only |
| tests | updated / unchanged | New behavior covered or not applicable |
| bilingual docs | updated | Developer explanation synchronized |
| changelog | updated | Decision recorded |
| version | updated | Governance release identified |

---

## 6. Phân biệt rules, workflow và tài liệu / Rules vs workflow vs documentation

### Rule

Một điều kiện hoặc giới hạn bắt buộc.

A mandatory condition or constraint.

Ví dụ / Example:

```text
Do not modify files while task status is needs_clarification.
```

### Workflow

Thứ tự các bước và gate chuyển trạng thái.

The ordered stages and transition gates.

Ví dụ / Example:

```text
assess_requirement_clarity → clarify_if_needed → plan
```

### Documentation

Giải thích cho con người hiểu rule và workflow.

Human-readable explanation of rules and workflows.

Tài liệu không được âm thầm thay đổi hành vi. Mọi hành vi cưỡng chế phải tồn tại trong `AGENTS.md`, `governance.json`, code hoặc test phù hợp.

Documentation must not silently change behavior. Enforced behavior must be represented in `AGENTS.md`, `governance.json`, implementation, or tests as appropriate.

---

## 7. Cách xử lý yêu cầu chưa rõ / Handling unclear requests

Yêu cầu ngắn không tự động bị coi là mơ hồ.

A short request is not automatically ambiguous.

Agent hỏi lại khi thiếu thông tin có thể làm thay đổi:

- hành vi nghiệp vụ;
- quyền truy cập hoặc bảo mật;
- dữ liệu được đọc, sửa hoặc xóa;
- schema hoặc migration;
- kết quả tính toán;
- phạm vi file hoặc module;
- tiêu chí hoàn thành.

Câu hỏi phải cụ thể. Không chỉ hỏi “hãy mô tả rõ hơn”.

Clarification questions must be specific, not merely “please clarify.”

---

## 8. Tool-call policy dễ kiểm tra / Auditable tool-call policy

Mặc định / Defaults:

```text
max tool calls per work unit: 12
max identical calls: 1
max retry per normalized failure signature: 1
max consecutive failures: 3
```

Trước mỗi tool call, agent chạy `tool-guard`. Sau mỗi tool call, agent chạy `record-tool`.

Before each tool call, the agent runs `tool-guard`. After each call, it runs `record-tool`.

Khi hết ngân sách, agent phải dừng và báo lỗi, không được tiếp tục đổi cách viết command để lách giới hạn.

When the budget is exhausted, the agent must stop and report; it must not evade the guard by cosmetically rewriting a command.

---

## 9. Checklist dành cho developer / Developer checklist

### Khi bắt đầu task / At task start

- Đọc yêu cầu gốc.
- Xem task đã `ready` chưa.
- Xác nhận scope và acceptance criteria.
- Xác nhận môi trường đã được detect.
- Xem tool budget còn lại.

### Trước khi merge / Before merge

- Thay đổi nằm trong scope.
- Test phù hợp đã chạy.
- Không có instruction file trùng lặp.
- Không có source file sai vị trí.
- Không tạo duplicate implementation.
- Rules/workflow change đã đồng bộ tài liệu.
- Changelog và version đã cập nhật khi cần.
- Runtime artifacts không bị commit.

---

## 10. Lệnh quan trọng / Important commands

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos detect-environment --session-id SESSION-1
.agents/bin/agentos clarity-check --task-id TASK-001 --request "..." --payload '{...}'
.agents/bin/agentos approve-task TASK-001
.agents/bin/agentos tool-guard --task-id TASK-001 --tool TOOL --args '{...}'
.agents/bin/agentos prepare-change --task-id TASK-001 --operation modify --target PATH --intent "..."
```

Windows:

```bat
.agents\bin\agentos.cmd docs-check
```

---

## 11. Nguyên tắc cập nhật tài liệu / Documentation update principles

- Viết tiếng Việt trước, tiếng Anh ngay sau hoặc trong cùng bảng.
- Dùng thuật ngữ kỹ thuật tiếng Anh nhất quán.
- Không sao chép toàn bộ `AGENTS.md` vào tài liệu giải thích.
- Liên kết tới nguồn có thẩm quyền thay vì tạo rules song song.
- Mỗi thay đổi governance phải có ngày, version, lý do, file bị ảnh hưởng và migration note.
- Ví dụ CLI phải chạy được hoặc được kiểm thử.
- Tài liệu cấu trúc phải phản ánh cây thư mục thực tế.

---

## 12. Nguồn sự thật / Sources of truth

| Nội dung / Concern | Nguồn có thẩm quyền / Authority |
|---|---|
| Agent instructions | `AGENTS.md` |
| Structured policy values | `.agents/config/governance.json` |
| Runtime behavior | `.agents/agentos/` |
| Expected behavior | `.agents/tests/` |
| Human explanation | `huong_dan.md`, `.agents/docs/` |
| Governance history | `RULES_WORKFLOW_CHANGELOG.md` |
| Release identity | `VERSION` |

Khi phát hiện không đồng bộ, không được sửa một phần rồi tiếp tục. Hãy phân loại thành governance synchronization issue và hoàn tất synchronization gate.

When synchronization drift is detected, do not patch one file and continue. Classify it as a governance synchronization issue and complete the synchronization gate.
