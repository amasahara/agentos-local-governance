# Hướng dẫn AgentOS v0.10.1 / AgentOS v0.10.1 Developer Guide

> Tài liệu này là điểm bắt đầu dành cho developer khi đưa AgentOS vào một project.
> Phần quan trọng nhất là lựa chọn đúng quy trình cho **project mới** hoặc **project đang tồn tại**.
>
> This document is the developer entry point for adopting AgentOS. The most
> important decision is choosing the correct path for a **new project** or an
> **existing project**.

---

# Tiếng Việt

## 1. AgentOS dùng để làm gì?

AgentOS là lớp governance cục bộ nằm trực tiếp trong repository. Hệ thống giúp coding agent làm việc theo một bộ rule và workflow có thể kiểm tra, thay vì chỉ dựa vào việc LLM nhớ nội dung hội thoại.

AgentOS đồng bộ các thành phần:

```text
AGENTS.md                       nguồn instruction duy nhất
.agents/config/governance.json  policy có cấu trúc
.agents/agentos/                runtime enforcement
.agents/state/                  SQLite audit và workflow state
.agents/runtime/                current task và artifact tạm
.agents/tests/                  hành vi được kiểm thử
README.md, huong_dan.md         tài liệu cho con người
.agents/docs/                   usage, structure và changelog
VERSION                         định danh phiên bản
```

AgentOS không phải sandbox hệ điều hành. Một tool bên ngoài vẫn có thể ghi file trực tiếp nếu framework cho phép. AgentOS giảm rủi ro bằng approval gate, write check, audit trail, workflow checklist, drift detection và Git hook.

---

## 2. Chọn đúng quy trình cài đặt

Trước khi làm bất kỳ bước nào, xác định project thuộc trường hợp nào:

| Trường hợp | Quy trình |
|---|---|
| Chưa có source code hoặc repository đang khởi tạo | **Project mới** |
| Đã có source, README, cấu trúc thư mục, rule hoặc lịch sử Git | **Project đang tồn tại** |
| Chỉ muốn thử AgentOS mà không sửa repository chính | Tạo một bản sao hoặc branch thử nghiệm, sau đó dùng quy trình project đang tồn tại |

Không copy thủ công toàn bộ gói AgentOS đè lên project đang tồn tại. Với project cũ, luôn dùng installer an toàn hoặc merge từng file có review.

---

# PHẦN A — PROJECT MỚI

## 3. Mục tiêu khi dùng AgentOS cho project mới

Với project mới, AgentOS nên được cài trước khi coding agent bắt đầu tạo source. Điều này giúp:

- chọn cấu trúc project ngay từ đầu;
- giữ `AGENTS.md` là nguồn instruction duy nhất;
- thiết lập source root và placement policy trước khi tạo file;
- tạo baseline governance ban đầu;
- cài Git hook trước commit đầu tiên;
- tránh phải di chuyển hoặc sửa hàng loạt file về sau.

## 4. Quy trình cài project mới

### Bước 1 — Tạo repository rỗng

Linux/macOS:

```bash
mkdir my-project
cd my-project
git init
```

Windows PowerShell:

```powershell
mkdir my-project
cd my-project
git init
```

Nếu repository đã được tạo từ GitHub/GitLab nhưng chưa có source đáng kể, vẫn có thể coi là project mới.

### Bước 2 — Chạy installer AgentOS

Từ thư mục bản phân phối AgentOS:

```bash
/path/to/agentos-local-governance-v0.9.0/.agents/bin/install.sh /path/to/my-project
```

Windows:

```bat
C:\path\to\agentos-local-governance-v0.9.0\.agents\bin\install.cmd C:\path\to\my-project
```

Installer sẽ:

1. copy `.agents/` vào project;
2. copy `AGENTS.md`, `README.md`, `huong_dan.md`, `VERSION` nếu chưa tồn tại;
3. không ghi đè file root đã có;
4. chạy các kiểm tra cài đặt cơ bản;
5. tạo baseline ban đầu vì người dùng đã chủ động chạy installer.

### Bước 3 — Chọn source root ngay từ đầu

Mặc định AgentOS giả định source root là `src`.

Cấu trúc đề nghị:

```text
my-project/
├── AGENTS.md
├── README.md
├── huong_dan.md
├── VERSION
├── src/
├── tests/
└── .agents/
```

Nếu muốn dùng source root khác, ví dụ `app`, đặt biến khi cài:

```bash
SOURCE_ROOT=app /path/to/agentos/.agents/bin/install.sh /path/to/my-project
```

Installer sẽ tạo:

```text
.agents/config/governance.local.json
```

Ví dụ:

```json
{
  "source_root": "app"
}
```

Không sửa `governance.json` chỉ để thay đổi source root riêng của một project.

### Bước 4 — Review governance trước khi tạo code

Đọc theo thứ tự:

```text
README.md
→ huong_dan.md
→ AGENTS.md
→ .agents/config/governance.json
→ .agents/config/governance.local.json (nếu có)
→ .agents/docs/PROJECT_STRUCTURE.md
→ .agents/docs/USAGE.md
```

Kiểm tra đặc biệt:

- source root;
- feature/layer convention;
- naming policy;
- file placement;
- claim policy;
- network evidence policy;
- workflow bắt buộc;
- documentation contract.

### Bước 5 — Xác nhận baseline của con người

Nếu installer đã tạo baseline thành công, kiểm tra:

```bash
.agents/bin/agentos drift-check
```

Kết quả mong đợi:

```json
{
  "drift_detected": false
}
```

Nếu bạn đã sửa governance sau khi cài, review bằng:

```bash
.agents/bin/agentos drift-diff --file AGENTS.md
.agents/bin/agentos drift-diff --file .agents/config/governance.json
```

Sau khi tự xác nhận thay đổi là đúng:

```bash
.agents/bin/agentos ack-baseline --acknowledged-by human
```

Coding agent không được gọi `ack-baseline` thay người dùng.

### Bước 6 — Cài Git hook trước commit đầu tiên

```bash
.agents/bin/install-git-hooks.sh
```

Hook kiểm tra:

```text
instruction-check
→ docs-check
→ docs-scan
→ drift-check
→ AgentOS tests
```

Nếu project chưa dùng Git, có thể bỏ qua tạm thời nhưng phải chạy checklist thủ công trước khi merge hoặc phát hành.

### Bước 7 — Xác nhận cài đặt

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos db-status
.agents/bin/agentos drift-check
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Kết quả mong đợi ở v0.9.0:

```text
instruction-check: ok
docs-check: ok
database schema: current 7 / required 7
drift_detected: false
AgentOS tests: passed
```

### Bước 8 — Bắt đầu task đầu tiên

```bash
.agents/bin/agentos start-task \
  --task-id TASK-001 \
  --request "Khởi tạo chức năng đầu tiên"
```

Kiểm tra context:

```bash
.agents/bin/agentos whoami
.agents/bin/agentos workflow-status
.agents/bin/agentos next-step
```

Sau đó thực hiện workflow chuẩn:

```text
đánh giá yêu cầu
→ approve-task
→ index-build
→ prepare-change
→ execute có guard
→ docs-scan
→ run-tests
→ evidence review
→ structural review
→ sync-check
→ report
```

## 5. Checklist hoàn tất cho project mới

Project mới chỉ được xem là sẵn sàng khi:

- [ ] `.agents/` đã được cài;
- [ ] `AGENTS.md` là instruction source duy nhất;
- [ ] source root đã được quyết định;
- [ ] `governance.local.json` chỉ chứa override cần thiết;
- [ ] baseline đã được người dùng review;
- [ ] `drift-check` không còn cảnh báo;
- [ ] Git hook đã được cài hoặc có quy trình kiểm tra thay thế;
- [ ] schema DB là version 7;
- [ ] test AgentOS pass;
- [ ] task đầu tiên được tạo qua `start-task`, không sửa code tự do ngoài workflow.

---

# PHẦN B — PROJECT ĐANG TỒN TẠI

## 6. Vì sao project cũ cần quy trình riêng?

Project đang tồn tại có thể đã có:

- `README.md` và tài liệu riêng;
- rule hoặc hướng dẫn agent khác;
- source root không phải `src`;
- naming và architecture convention riêng;
- test framework và dependency riêng;
- file `AGENTS.md` do team quản lý;
- CI/CD và Git hook hiện có;
- dữ liệu quan trọng không được ghi đè.

Mục tiêu khi cài AgentOS vào project cũ là **bổ sung governance mà không làm mất hoặc âm thầm thay đổi dữ liệu hiện có**.

## 7. Chuẩn bị trước khi cài vào project cũ

### Bước 1 — Tạo điểm phục hồi

Ưu tiên tạo branch riêng:

```bash
git switch -c chore/install-agentos-v0.9.0
```

Hoặc ít nhất tạo backup trước khi cài.

Kiểm tra working tree:

```bash
git status
```

Nên commit hoặc stash các thay đổi chưa liên quan để diff cài đặt AgentOS dễ review.

### Bước 2 — Ghi nhận cấu trúc hiện tại

Xác định:

- project root;
- source root: `src`, `app`, `lib`, `packages`, hay cấu trúc khác;
- test root;
- script/tool directories;
- instruction files hiện có;
- CI command;
- Python runtime dùng cho AgentOS;
- các file root không được ghi đè.

Ví dụ project cũ:

```text
legacy-project/
├── README.md
├── app/
├── test/
├── scripts/
├── CONTRIBUTING.md
└── .github/
```

Trong trường hợp này, source root nên được override thành `app`.

### Bước 3 — Kiểm tra instruction source hiện có

Tìm các file có thể cạnh tranh với `AGENTS.md`:

```text
CLAUDE.md
GEMINI.md
COPILOT.md
CODEX.md
CURSOR.md
.agent-rules
cursorrules
```

AgentOS yêu cầu một nguồn instruction duy nhất là `AGENTS.md`. Không xóa file cũ ngay lập tức nếu chưa review. Hãy:

1. đọc nội dung các file cũ;
2. merge rule còn hiệu lực vào `AGENTS.md`;
3. loại bỏ hoặc chuyển các file cũ thành tài liệu không mang tính instruction;
4. chạy `instruction-check`.

## 8. Cài đặt an toàn vào project cũ

### Bước 1 — Chạy installer, không copy đè thủ công

```bash
/path/to/agentos/.agents/bin/install.sh /path/to/existing-project
```

Windows:

```bat
C:\path\to\agentos\.agents\bin\install.cmd C:\path\to\existing-project
```

Nếu project dùng `app`:

```bash
SOURCE_ROOT=app /path/to/agentos/.agents/bin/install.sh /path/to/existing-project
```

### Bước 2 — Hiểu cách installer xử lý xung đột

Với file chưa tồn tại, installer copy trực tiếp.

Với file đã tồn tại, installer không ghi đè. Bản AgentOS được ghi bằng hậu tố `.agentos`:

```text
README.md             giữ nguyên file project
README.agentos.md     bản mẫu AgentOS để review

AGENTS.md             giữ nguyên file project
AGENTS.agentos.md     rule AgentOS để merge

huong_dan.md          giữ nguyên nếu đã có
huong_dan.agentos.md  bản hướng dẫn AgentOS

VERSION               giữ nguyên nếu project dùng VERSION riêng
VERSION.agentos       version của AgentOS
```

Không đổi tên `.agentos` thành file chính một cách tự động. Phải review và merge có chủ đích.

### Bước 3 — Merge `AGENTS.md` cẩn thận

Đây là bước quan trọng nhất.

Nếu project chưa có `AGENTS.md`, dùng bản AgentOS được cài.

Nếu project đã có `AGENTS.md`:

1. so sánh `AGENTS.md` và `AGENTS.agentos.md`;
2. giữ rule nghiệp vụ/kiến trúc đặc thù của project;
3. bổ sung các gate AgentOS: approval, placement, write containment, evidence, workflow, drift;
4. loại bỏ rule mâu thuẫn hoặc trùng lặp;
5. đảm bảo cuối cùng chỉ còn một file `AGENTS.md` có hiệu lực;
6. chạy `instruction-check`.

Không nên thay toàn bộ `AGENTS.md` hiện có bằng bản generic nếu file cũ chứa rule quan trọng của project.

### Bước 4 — Merge README và tài liệu

Không bắt buộc thay README của project bằng README AgentOS.

Cách đề nghị:

- giữ README hiện tại làm tài liệu sản phẩm;
- lấy phần “AgentOS governance” cần thiết từ `README.agentos.md`;
- thêm một mục ngắn trỏ tới `huong_dan.md` và `.agents/docs/USAGE.md`;
- xóa file `.agentos` sau khi merge xong hoặc giữ trong branch review, không để lâu dài gây nhầm lẫn.

### Bước 5 — Tạo local override

Không sửa policy phân phối chỉ vì cấu trúc project khác mặc định.

Tạo hoặc cập nhật:

```text
.agents/config/governance.local.json
```

Ví dụ:

```json
{
  "source_root": "app",
  "claim_policy": {
    "allow_network_evidence": false
  }
}
```

Override được merge theo từng section cấp một. Sau khi sửa local override, `drift-check` sẽ yêu cầu review lại baseline.

### Bước 6 — Migrate database

Nếu project chưa từng dùng AgentOS, database mới sẽ được tạo tới schema 7.

Nếu nâng từ AgentOS cũ:

```bash
.agents/bin/agentos db-status
```

Kết quả phải là:

```text
current: 7
required: 7
is_current: true
```

Migrations được áp dụng theo thứ tự và không sửa migration cũ.

### Bước 7 — Build index theo source root thực tế

Ví dụ source root `app`:

```bash
.agents/bin/agentos index-build app
```

Không chạy mặc định `index-build src` nếu project không có `src`.

### Bước 8 — Chạy documentation scan theo phạm vi phù hợp

Không nên lập tức scan toàn bộ project cũ rồi sửa hàng nghìn finding trong cùng một thay đổi.

Chiến lược an toàn:

1. scan module sẽ được agent sửa trước;
2. sửa header/docstring cho file bị tác động;
3. mở rộng phạm vi theo từng feature;
4. chỉ đặt toàn bộ project thành gate khi codebase đã sẵn sàng.

Ví dụ:

```bash
.agents/bin/agentos docs-scan --scope app/orders
```

Sau đó mở rộng:

```bash
.agents/bin/agentos docs-scan --scope app
```

Không tắt documentation contract chỉ để làm test xanh. Nếu cần rollout theo giai đoạn, ghi rõ phạm vi và kế hoạch trong changelog/project policy.

### Bước 9 — Tích hợp với test hiện có

AgentOS tests:

```bash
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Project tests phải tiếp tục chạy bằng command hiện có của project, ví dụ:

```bash
pytest
npm test
pnpm test
mvn test
dotnet test
```

`agentos run-tests` có thể dùng làm workflow wrapper, nhưng không được thay thế bộ test thật của project bằng chỉ `.agents/tests`.

### Bước 10 — Review drift và tạo baseline mới

Sau khi merge rule, policy và local override:

```bash
.agents/bin/agentos drift-check
```

Review từng thay đổi governance:

```bash
.agents/bin/agentos drift-diff --file AGENTS.md
.agents/bin/agentos drift-diff --file .agents/config/governance.json
.agents/bin/agentos drift-diff --file .agents/config/governance.local.json
```

Khi người dùng đã review và chấp nhận:

```bash
.agents/bin/agentos ack-baseline --acknowledged-by human
```

Không tạo baseline trước khi merge xong vì điều đó sẽ xác nhận một trạng thái trung gian chưa hoàn chỉnh.

### Bước 11 — Tích hợp Git hook mà không phá hook cũ

Trước khi chạy:

```bash
.agents/bin/install-git-hooks.sh
```

kiểm tra:

```text
.git/hooks/pre-commit
```

Nếu project đã có pre-commit hook, không ghi đè mù quáng. Chọn một trong các cách:

- gọi hook AgentOS từ hook hiện có;
- merge nội dung hai hook;
- dùng framework như pre-commit để thêm AgentOS thành một entry;
- giữ hook dự án làm entry point duy nhất.

Sau khi tích hợp, thử commit giả hoặc chạy hook trực tiếp để xác nhận cả gate cũ và gate AgentOS đều hoạt động.

## 9. Rollout đề nghị cho project cũ

Không nên kích hoạt mọi rule trên toàn codebase trong một commit lớn. Dùng ba giai đoạn:

### Giai đoạn 1 — Cài governance foundation

```text
cài .agents
→ merge AGENTS.md
→ cấu hình source root
→ migrate DB
→ chạy instruction/docs checks
→ tạo baseline
```

Chưa sửa hàng loạt source chỉ để đáp ứng docs contract.

### Giai đoạn 2 — Áp dụng cho code mới và file được sửa

Mọi task mới phải:

- dùng `start-task`;
- chạy `prepare-change`;
- tuân placement và write gate;
- cập nhật docstring cho file bị tác động;
- chạy test thực của project;
- hoàn tất workflow checklist.

### Giai đoạn 3 — Mở rộng dần tới toàn repository

Theo feature hoặc module:

```text
index
→ duplicate review
→ docs-scan
→ sửa findings
→ test
→ baseline/release review
```

Cách này giảm diff lớn, tránh thay đổi hành vi ngoài ý muốn và dễ rollback.

## 10. Checklist hoàn tất cho project đang tồn tại

- [ ] Đã tạo branch hoặc backup;
- [ ] Installer được dùng thay vì copy đè;
- [ ] Các file `.agentos` đã được review và merge;
- [ ] Chỉ còn một instruction source có hiệu lực là `AGENTS.md`;
- [ ] Source root thực tế đã được cấu hình;
- [ ] Không ghi đè README hoặc VERSION riêng của project;
- [ ] Schema DB đã lên 7;
- [ ] Index đã build đúng source root;
- [ ] Documentation rollout có phạm vi rõ ràng;
- [ ] AgentOS tests và project tests đều pass;
- [ ] Git hook cũ không bị mất;
- [ ] Governance diff đã được con người review;
- [ ] Baseline chỉ được tạo sau khi merge hoàn chỉnh;
- [ ] `drift-check` trả không có thay đổi chưa xác nhận.

---

## 11. Workflow hằng ngày sau khi cài

Dù là project mới hay project cũ, mỗi task thay đổi code nên bắt đầu bằng:

```bash
.agents/bin/agentos start-task \
  --task-id TASK-042 \
  --request "Mô tả yêu cầu"
```

Nếu tiếp tục task cũ:

```bash
.agents/bin/agentos use-task --task-id TASK-042
```

Luôn phục hồi context trước khi làm tiếp:

```bash
.agents/bin/agentos whoami
.agents/bin/agentos workflow-status
.agents/bin/agentos next-step
```

Workflow điển hình:

```text
receive_request
→ assess_requirement_clarity
→ approve_task
→ detect_environment
→ build_or_update_local_index
→ prepare_change
→ execute_guarded
→ documentation_check
→ tests
→ evidence_review
→ egress_review
→ structural_review
→ synchronize
→ report
```

Bước không áp dụng phải được skip có lý do:

```bash
.agents/bin/agentos mark-step \
  --step egress_review \
  --status skipped \
  --note "Task không có network call."
```

Không được để step biến mất âm thầm.

---

## 12. Claim và evidence

Claim là kết luận ảnh hưởng tới business logic, security, data behavior, destructive effect hoặc governance.

Quy trình:

```text
thực thi tool
→ record-tool
→ lấy tool_call_id
→ record-claim
→ show-claim để review
```

Ví dụ:

```bash
.agents/bin/agentos record-tool \
  --tool bounded_file_read \
  --args '{"path":"src/orders/service.py"}' \
  --success \
  --summary "Read order validation logic."
```

Sau đó:

```bash
.agents/bin/agentos record-claim \
  --claim "Order approval is not checked before persistence" \
  --claim-type business_logic \
  --risk high \
  --evidence-call-ids '[12]'
```

Claim rủi ro cao không có evidence hợp lệ sẽ bị chặn.

---

## 13. Source documentation contract

Mỗi source file phải có module header một lần:

```python
"""
File: src/orders/service.py

Purpose:
    Coordinate order application behavior.

Responsibilities:
    - Validate order input.
    - Coordinate repositories.
"""
```

Public class/function/method phải có docstring mô tả contract cần thiết:

- mục đích;
- input;
- output;
- error;
- side effect quan trọng.

Kiểm tra:

```bash
.agents/bin/agentos docs-scan --scope src
```

Với project cũ, scan theo module trước rồi mở rộng dần.

---

## 14. Governance drift

Các file governance được theo dõi bằng hash. `drift-check` phát hiện thay đổi kể từ baseline gần nhất.

```bash
.agents/bin/agentos drift-check
```

Xem nội dung:

```bash
.agents/bin/agentos drift-diff --file AGENTS.md
```

Sau khi con người review:

```bash
.agents/bin/agentos ack-baseline --acknowledged-by human
```

`ack-baseline` là hành động xác nhận, không phải công cụ làm sạch cảnh báo tự động. Không gọi lệnh này chỉ để làm hook pass.

---

## 15. Checklist trước merge

Chạy tối thiểu:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope <source-root-or-changed-scope>
.agents/bin/agentos db-status
.agents/bin/agentos drift-check
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Sau đó chạy test thật của project.

Nếu task được quản lý bằng workflow:

```bash
.agents/bin/agentos workflow-status
.agents/bin/agentos sync-check
.agents/bin/agentos report
```

`report` bị chặn nếu còn required step pending.

---

## 16. Thứ tự nên đọc

```text
README.md
→ huong_dan.md
→ AGENTS.md
→ .agents/config/governance.json
→ .agents/config/governance.local.json (nếu có)
→ .agents/docs/PROJECT_STRUCTURE.md
→ .agents/docs/USAGE.md
→ .agents/agentos/
→ .agents/tests/
→ .agents/docs/RULES_WORKFLOW_CHANGELOG.md
```

`README.md` và `huong_dan.md` là tài liệu giải thích. `AGENTS.md` vẫn là nguồn instruction duy nhất dành cho coding agent.

---

# English

## 17. Choose the correct adoption path

Use the **new project** procedure when the repository has little or no source code. Use the **existing project** procedure when the repository already has source code, documentation, conventions, CI, hooks, or agent instructions.

Never manually overwrite an existing repository with the AgentOS distribution. Use the safe installer and review every conflict.

## 18. New project procedure

1. Create an empty repository and initialize Git.
2. Run the AgentOS installer before generating source code.
3. Select the source root (`src` by default, or set `SOURCE_ROOT`).
4. Review `AGENTS.md`, structured policy, workflow, placement, and documentation rules.
5. Verify or create the human-reviewed governance baseline.
6. Install the Git hook before the first commit.
7. Run instruction, documentation, database, drift, and AgentOS test checks.
8. Start the first work item through `start-task` rather than modifying files outside the workflow.

Example:

```bash
/path/to/agentos/.agents/bin/install.sh /path/to/new-project
cd /path/to/new-project
.agents/bin/install-git-hooks.sh
.agents/bin/agentos drift-check
.agents/bin/agentos start-task --task-id TASK-001 --request "Initialize the first feature"
```

A new project is ready only when the source root is decided, schema 7 is current, AgentOS tests pass, the baseline has been reviewed, and no unacknowledged drift remains.

## 19. Existing project procedure

1. Create a backup or dedicated installation branch.
2. Identify the actual source root, tests, scripts, CI commands, hooks, and existing instruction files.
3. Run the safe installer; do not copy over existing root files.
4. Review `.agentos` conflict files individually.
5. Merge the AgentOS governance gates into the project's existing `AGENTS.md` without discarding project-specific rules.
6. Store project-specific source-root or policy values in `governance.local.json`.
7. Migrate the database to schema 7.
8. Build the symbol index for the real source root.
9. Roll out documentation scanning by changed module or feature before enforcing it repository-wide.
10. Run both AgentOS tests and the project's real test suite.
11. Integrate the AgentOS pre-commit gate without overwriting an existing hook.
12. Review governance drift and create a baseline only after the merge is complete.

Conflict behavior:

```text
README.md             preserved
README.agentos.md     AgentOS copy for manual merge
AGENTS.md             preserved
AGENTS.agentos.md     AgentOS governance copy for manual merge
```

Do not acknowledge a temporary or partially merged state as the baseline.

## 20. Recommended rollout for an existing codebase

Use three stages:

```text
foundation installation
→ enforce AgentOS for new and modified files
→ expand compliance feature by feature
```

This avoids a single large documentation or structure rewrite and makes review and rollback safer.

## 21. Daily workflow

Start or resume the task:

```bash
.agents/bin/agentos start-task --task-id TASK-042 --request "Describe the change"
# or
.agents/bin/agentos use-task --task-id TASK-042
```

Recover context:

```bash
.agents/bin/agentos whoami
.agents/bin/agentos workflow-status
.agents/bin/agentos next-step
```

Complete or explicitly skip every workflow step. A skipped step requires a reason, and the final `report` remains blocked while required work is pending.

## 22. Human baseline responsibility

`drift-check` detects changed governance content. It does not approve the change. A human must inspect the diff and run:

```bash
.agents/bin/agentos ack-baseline --acknowledged-by human
```

A coding agent must never acknowledge governance changes for the user.

## 23. Final validation

Run:

```bash
.agents/bin/agentos instruction-check
.agents/bin/agentos docs-check
.agents/bin/agentos docs-scan --scope <actual-source-root-or-changed-scope>
.agents/bin/agentos db-status
.agents/bin/agentos drift-check
PYTHONPATH=.agents python3 -m pytest .agents/tests -q
```

Then run the project's own test suite and complete the workflow report gate.

---

## Tiếng Việt — Thay đổi bắt buộc khi dùng v0.9.0

### Tool execution không còn tự khai báo

Không dùng `record-tool` để tạo evidence. Luồng đúng:

```bash
.agents/bin/agentos --session-id SESSION-1 guard-tool \
  --task-id TASK-001 --tool bounded_file_read \
  --args '{"path":"src/orders/service.py"}'

.agents/bin/agentos --session-id SESSION-1 complete-tool \
  --execution-token TOKEN_FROM_GUARD \
  --input '{"path":"src/orders/service.py"}' \
  --success --output "Đã đọc contract và logic liên quan."
```

Classification do AgentOS suy ra từ registry. Token chỉ dùng một lần, hết hạn,
gắn với session và hash của arguments. Agent không thể đổi `web` thành `local`.

### Workflow automated-only

Các bước `approve_task`, `build_or_update_local_index`, `prepare_change`,
`execute_guarded`, `documentation_check`, `tests`, `evidence_review`, và
`synchronize` chỉ được command chính thức hoàn thành. `mark-step --status done`
cho các bước này bị từ chối. Mỗi step lưu provenance và result hash.

### Session riêng cho nhiều agent

Dùng `--session-id` hoặc biến `AGENTOS_SESSION_ID`. Không dùng chung current task
giữa hai agent chạy song song.

### Baseline và drift

Project chưa có baseline trả `baseline_state=not_initialized`, không bị gọi nhầm
là drift. Installer không tự xác nhận. Người dùng review rồi chạy tương tác:

```bash
.agents/bin/agentos ack-baseline --identity TEN_NGUOI_REVIEW
```

`report` bị chặn nếu chưa có baseline, có drift, provenance không hợp lệ, hoặc
sensitive local override chưa được duyệt.

### Local override nhạy cảm

`source_root`, `test_path`, `encoding`, `runtime_paths` có thể áp dụng ngay.
Các section policy nhạy cảm được giữ ở trạng thái `pending` cho đến khi review:

```bash
.agents/bin/agentos local-override-status
.agents/bin/agentos approve-local-override \
  --reviewed-by TEN_NGUOI_REVIEW \
  --note "Đã kiểm tra tác động của override"
```

## English — Required v0.9.0 operational changes

Use `guard-tool` and `complete-tool`; direct evidence recording is disabled.
Automated workflow gates require canonical command provenance. Use a unique session
ID for concurrent agents. The installer does not acknowledge the baseline. Final
reporting is blocked by uninitialized baseline, drift, invalid provenance, or an
unapproved sensitive local override.


## Tiếng Việt — Triển khai MCP proxy và external signed audit

1. Cài dependency: `python3 -m pip install -r .agents/requirements.txt`.
2. Tạo task, approval, index và `prepare-change` như workflow chuẩn.
3. Review governance rồi tạo baseline bằng `ack-baseline`.
4. Cấu hình IDE/agent chỉ kết nối lệnh `.agents/bin/agentos-mcp --task-id TASK-ID --session-id SESSION-ID`.
5. Gỡ hoặc vô hiệu hóa mọi filesystem/shell/network MCP server được cấp trực tiếp cho agent. Backend credentials chỉ thuộc proxy.
6. Đặt `AGENTOS_AUDIT_HOME` tới thư mục ngoài repository do người dùng hoặc service account sở hữu.
7. Chạy `agentos audit-verify` trong pre-merge/CI.

Project cũ nên triển khai theo ba giai đoạn: chạy proxy ở chế độ quan sát; loại bỏ direct backend access; cuối cùng chuyển write/process/network sang fail-closed khi audit sink không khả dụng. Không bật enforcement nếu agent vẫn có terminal hoặc filesystem tool trực tiếp nằm ngoài proxy.

## English — Deploying the MCP proxy and signed external audit

Install `.agents/requirements.txt`, bind the MCP gateway to an approved task and session, remove direct backend tools from the agent configuration, place `AGENTOS_AUDIT_HOME` outside the repository under a separate owner, and run `agentos audit-verify` in CI. Adopt in observe, restricted, and enforced phases for existing repositories.
