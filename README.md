# AgentOS Local Governance

**Local-first governance for AI coding agents.**  
**Lớp quản trị local-first dành cho AI coding agent.**

AgentOS Local Governance helps developers keep AI coding agents aligned with one shared set of project rules, workflows, approval gates, file conventions, and auditable execution policies.

AgentOS Local Governance giúp developer kiểm soát AI coding agent bằng một bộ rules, workflow, approval gate, quy ước cấu trúc và chính sách thực thi có thể kiểm tra thống nhất trong project.

> Repository slug: `agentos-local-governance`  
> Current version: `v0.5.1`

---

## English

### Why this project exists

AI coding agents can move quickly, but they may also:

- infer missing requirements;
- modify code before the task is sufficiently clear;
- repeat failing tool calls;
- create files in inconsistent locations;
- duplicate existing capabilities;
- apply rules differently across models and IDEs;
- leave project documentation out of sync with actual behavior.

AgentOS Local Governance provides a repository-local governance layer to reduce those risks. It is designed to work alongside different LLMs, coding agents, IDE integrations, CLI tools, and local or remote models.

It is **not** an LLM, agent framework, or cloud service.

### Core capabilities

- **Single instruction authority** through `AGENTS.md`
- **Requirement clarification gate** before planning or implementation
- **Approval and write gates** before modifying project files
- **Tool-call budget** and repeated-failure protection
- **Environment-aware execution** for shell, operating system, paths, encoding, and Python runtime
- **Controlled file placement** for source, tests, scripts, and temporary artifacts
- **Duplicate implementation detection** using Python AST fingerprints
- **Similar-symbol discovery** before creating new capabilities
- **Local runtime isolation** under `.agents/runtime/`
- **Bilingual developer documentation** in Vietnamese and English
- **Rules and workflow synchronization checks** across instructions, configuration, runtime code, tests, documentation, changelog, and version

### Standard workflow

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

A modifying tool may run only when:

- the task status is `ready`;
- approval has been recorded;
- the requested write path is allowed;
- the tool-call budget has not been exhausted.

### Project structure

```text
project-root/
├── README.md
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

### Where to start

| Goal | Read |
|---|---|
| Understand the project | `README.md` |
| Understand developer usage and architecture | `huong_dan.md` |
| Understand mandatory agent behavior | `AGENTS.md` |
| Inspect structured policy values | `.agents/config/governance.json` |
| Learn the CLI | `.agents/docs/USAGE.md` |
| Review component responsibilities | `.agents/docs/PROJECT_STRUCTURE.md` |
| Review rules and workflow history | `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` |
| Verify enforced behavior | `.agents/tests/` |

`README.md` and `huong_dan.md` are explanatory documents. `AGENTS.md` remains the sole instruction authority for coding agents.

### Quick start

#### Linux or macOS

```bash
chmod +x .agents/bin/agentos

.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos detect-environment --session-id SESSION-1
python -m pytest -q .agents/tests
```

#### Windows

```bat
.agents\bin\agentos.cmd instruction-check
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd detect-environment --session-id SESSION-1
python -m pytest -q .agents\tests
```

Expected validation result for v0.5.1:

```text
6 passed
docs-check: ok
```

### Clarification gate example

```bash
.agents/bin/agentos clarity-check \
  --task-id TASK-001 \
  --request "Fix schedule printing" \
  --payload '{
    "intent": "modify_existing_feature",
    "target": null,
    "expected_behavior": null,
    "current_behavior": null,
    "acceptance_criteria": [],
    "scope": null,
    "risk": "medium"
  }'
```

An unclear task receives:

```json
{
  "status": "needs_clarification",
  "ambiguities": [
    "The affected feature, module, file, or behavior is unknown.",
    "The expected result is missing.",
    "Acceptance criteria are missing."
  ]
}
```

A task in `needs_clarification` cannot be approved and cannot modify files.

### Tool-loop protection

Default limits:

```text
Maximum tool calls per work unit: 12
Maximum identical tool calls: 1
Maximum retries per normalized failure signature: 1
Maximum consecutive failures: 3
```

Before a tool call:

```bash
.agents/bin/agentos tool-guard \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}'
```

After the call:

```bash
.agents/bin/agentos record-tool \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}' \
  --success \
  --summary "Read the relevant printing functions."
```

### Composite change preparation

`prepare-change` combines placement resolution, similar-symbol discovery, duplicate-risk scanning, write permission, and recommended context:

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation modify \
  --target schedules/views/printing.py \
  --intent "Print approved schedules only" \
  --symbols '["print_schedule"]'
```

### Documentation and governance synchronization

When a user changes project rules or workflow, AgentOS requires evaluation of:

```text
AGENTS.md
.agents/config/governance.json
huong_dan.md
.agents/docs/PROJECT_STRUCTURE.md
.agents/docs/USAGE.md
.agents/docs/RULES_WORKFLOW_CHANGELOG.md
.agents/agentos/
.agents/tests/
VERSION
```

Run:

```bash
.agents/bin/agentos docs-check
```

This checks required documentation, bilingual markers, version consistency, and changelog synchronization.

### Current scope

Version `v0.5.1` currently focuses on:

- Python-based local governance utilities;
- Python and Django source-inspection guidance;
- local SQLite audit state;
- CLI-based integration points;
- repository-local documentation and policy enforcement.

The project does not yet provide a packaged installer, hosted service, IDE extension, or complete MCP server distribution.

### Contributing

Contributions should preserve these principles:

1. `AGENTS.md` remains the sole agent instruction source.
2. New enforced behavior must be reflected in configuration, implementation, and tests.
3. Rules and workflow changes must update bilingual documentation and the changelog.
4. Temporary artifacts must remain outside persistent source locations.
5. Changes should pass:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
python -m pytest -q .agents/tests
```

### License

A license has not yet been included in this release. Add a `LICENSE` file before inviting broad external reuse or contributions.

---

## Tiếng Việt

### Vì sao project này được xây dựng?

AI coding agent có thể làm việc rất nhanh, nhưng cũng có thể:

- tự suy diễn khi yêu cầu còn thiếu;
- sửa code trước khi task đủ rõ;
- gọi lại tool bị lỗi nhiều lần;
- tạo file sai vị trí hoặc thiếu nhất quán;
- tạo implementation trùng với chức năng đã có;
- áp dụng rules khác nhau giữa các model và IDE;
- làm tài liệu project không còn đồng bộ với hành vi thực tế.

AgentOS Local Governance cung cấp một lớp quản trị nằm trực tiếp trong repository để giảm các rủi ro này. Hệ thống được thiết kế để hoạt động cùng nhiều LLM, coding agent, IDE integration, CLI, local model hoặc remote model.

Đây **không phải** là LLM, agent framework hay cloud service.

### Chức năng chính

- **Một nguồn instruction duy nhất** thông qua `AGENTS.md`
- **Requirement clarification gate** trước khi lập kế hoạch hoặc triển khai
- **Approval gate và write gate** trước khi sửa file
- **Giới hạn tool call** và chống lặp lại lỗi
- **Nhận diện môi trường thực thi** gồm shell, hệ điều hành, đường dẫn, encoding và Python runtime
- **Kiểm soát vị trí file** cho source, test, script và artifact tạm
- **Phát hiện implementation trùng lặp** bằng Python AST fingerprint
- **Tìm symbol tương tự** trước khi tạo chức năng mới
- **Cô lập runtime local** trong `.agents/runtime/`
- **Tài liệu song ngữ** tiếng Việt và tiếng Anh
- **Kiểm tra đồng bộ rules và workflow** giữa instruction, config, runtime code, test, tài liệu, changelog và version

### Workflow chuẩn

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

Tool có khả năng thay đổi project chỉ được chạy khi:

- task có trạng thái `ready`;
- approval đã được ghi nhận;
- đường dẫn ghi được cho phép;
- tool-call budget chưa bị sử dụng hết.

### Bắt đầu đọc project

| Mục tiêu | File nên đọc |
|---|---|
| Xem tổng quan public của project | `README.md` |
| Hiểu cách sử dụng và kiến trúc | `huong_dan.md` |
| Hiểu hành vi bắt buộc của agent | `AGENTS.md` |
| Xem policy có cấu trúc | `.agents/config/governance.json` |
| Xem ví dụ CLI | `.agents/docs/USAGE.md` |
| Hiểu trách nhiệm từng thành phần | `.agents/docs/PROJECT_STRUCTURE.md` |
| Xem lịch sử rules và workflow | `.agents/docs/RULES_WORKFLOW_CHANGELOG.md` |
| Kiểm chứng hành vi | `.agents/tests/` |

`README.md` và `huong_dan.md` là tài liệu giải thích. `AGENTS.md` vẫn là nguồn instruction duy nhất dành cho coding agent.

### Khởi động nhanh

#### Linux hoặc macOS

```bash
chmod +x .agents/bin/agentos

.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos detect-environment --session-id SESSION-1
python -m pytest -q .agents/tests
```

#### Windows

```bat
.agents\bin\agentos.cmd instruction-check
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd detect-environment --session-id SESSION-1
python -m pytest -q .agents\tests
```

Kết quả kiểm tra mong đợi ở v0.5.1:

```text
6 passed
docs-check: ok
```

### Ví dụ kiểm tra yêu cầu chưa rõ

```bash
.agents/bin/agentos clarity-check \
  --task-id TASK-001 \
  --request "Sửa phần in lịch" \
  --payload '{
    "intent": "modify_existing_feature",
    "target": null,
    "expected_behavior": null,
    "current_behavior": null,
    "acceptance_criteria": [],
    "scope": null,
    "risk": "medium"
  }'
```

Task chưa rõ sẽ nhận trạng thái:

```json
{
  "status": "needs_clarification",
  "ambiguities": [
    "Chưa xác định chức năng, module, file hoặc hành vi bị ảnh hưởng.",
    "Chưa mô tả kết quả mong muốn.",
    "Chưa có tiêu chí nghiệm thu."
  ]
}
```

Task ở trạng thái `needs_clarification` không thể được phê duyệt và không được phép sửa file.

### Chống vòng lặp tool

Giới hạn mặc định:

```text
Tối đa 12 tool call cho mỗi work unit
Tối đa 1 tool call giống hệt
Tối đa 1 lần thử lại cho cùng failure signature
Tối đa 3 lỗi liên tiếp
```

Trước tool call:

```bash
.agents/bin/agentos tool-guard \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}'
```

Sau tool call:

```bash
.agents/bin/agentos record-tool \
  --task-id TASK-001 \
  --tool bounded_file_read \
  --args '{"path":"schedules/views/printing.py","start":1,"end":160}' \
  --success \
  --summary "Đã đọc các hàm in lịch liên quan."
```

### Chuẩn bị thay đổi bằng một lệnh tổng hợp

`prepare-change` gộp placement resolution, tìm symbol tương tự, duplicate scan, write permission và recommended context:

```bash
.agents/bin/agentos prepare-change \
  --task-id TASK-001 \
  --operation modify \
  --target schedules/views/printing.py \
  --intent "Chỉ in các lịch đã được duyệt" \
  --symbols '["print_schedule"]'
```

### Đồng bộ tài liệu và governance

Khi người dùng yêu cầu thay đổi rules hoặc workflow, AgentOS phải đánh giá:

```text
AGENTS.md
.agents/config/governance.json
huong_dan.md
.agents/docs/PROJECT_STRUCTURE.md
.agents/docs/USAGE.md
.agents/docs/RULES_WORKFLOW_CHANGELOG.md
.agents/agentos/
.agents/tests/
VERSION
```

Chạy:

```bash
.agents/bin/agentos docs-check
```

Lệnh này kiểm tra tài liệu bắt buộc, dấu hiệu song ngữ, tính nhất quán của version và changelog.

### Phạm vi hiện tại

Phiên bản `v0.5.1` hiện tập trung vào:

- tiện ích governance local viết bằng Python;
- hướng dẫn phân tích source Python và Django;
- audit state local bằng SQLite;
- điểm tích hợp qua CLI;
- tài liệu và policy nằm trực tiếp trong repository.

Project chưa cung cấp packaged installer, hosted service, IDE extension hoặc bản phân phối MCP server hoàn chỉnh.

### Đóng góp

Contribution nên giữ các nguyên tắc:

1. `AGENTS.md` tiếp tục là nguồn instruction duy nhất.
2. Hành vi cưỡng chế mới phải được phản ánh trong config, implementation và test.
3. Thay đổi rules hoặc workflow phải cập nhật tài liệu song ngữ và changelog.
4. Artifact tạm không được đưa vào vị trí source lâu dài.
5. Mọi thay đổi nên vượt qua:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
python -m pytest -q .agents/tests
```

### Giấy phép

Phiên bản này chưa kèm file `LICENSE`. Nên bổ sung giấy phép trước khi mời cộng đồng tái sử dụng hoặc đóng góp rộng rãi.

---

## Project status

AgentOS Local Governance is under active development. Version `v0.5.1` is suitable for evaluation, experimentation, and repository-local integration, but should be reviewed before use in security-critical or production automation.

AgentOS Local Governance đang được phát triển tích cực. Phiên bản `v0.5.1` phù hợp để đánh giá, thử nghiệm và tích hợp local trong repository, nhưng cần được review trước khi dùng cho automation production hoặc môi trường có yêu cầu bảo mật cao.
