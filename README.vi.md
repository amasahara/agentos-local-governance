# AgentOS Local Governance

**Hệ thống quản trị cục bộ cho AI coding agents trong project.**

[README chính](README.md) · [🇬🇧 English](README.en.md) · [Bản phát hành mới nhất](https://github.com/amasahara/agentos-local-governance/releases/latest) · [Changelog](CHANGELOG.md)

---

## 1. AgentOS Local Governance là gì?

AgentOS Local Governance là một **lớp quản trị nằm trực tiếp trong project**, dùng để kiểm soát cách AI coding agents đọc ngữ cảnh, lập kế hoạch, sử dụng công cụ, sửa file, phối hợp nhiều worker và đưa thay đổi vào project.

Mục tiêu của hệ thống không phải là tạo thêm một AI agent mới. AgentOS đóng vai trò như một **operating/governance layer** bao quanh các agent hiện có.

Một luồng thực thi được quản trị có thể như sau:

```text
Yêu cầu của người dùng
        ↓
Policy / quyền / phạm vi project
        ↓
Context + knowledge có provenance
        ↓
Task / plan được quản trị
        ↓
Architecture contract
        ↓
Skill / capability hợp lệ
        ↓
Worker / workspace được phép
        ↓
Kiểm tra compliance
        ↓
Human approval khi cần
        ↓
Controlled integration
        ↓
Audit / Command Center
```

AgentOS phù hợp với các project muốn dùng AI mạnh hơn nhưng vẫn cần:

- quyền của con người là authority cuối cùng;
- AI không tự mở rộng quyền;
- thay đổi có thể truy vết;
- nhiều agent không ghi đè công việc của nhau;
- architecture và policy không bị bỏ qua;
- state, privacy, secrets và audit được kiểm soát;
- việc tích hợp thay đổi vào project phải có boundary rõ ràng.

---

## 2. AgentOS giải quyết vấn đề gì?

Khi sử dụng coding agents trực tiếp trong repository, các vấn đề thường gặp gồm:

- agent sửa file vượt ngoài phạm vi yêu cầu;
- nhiều agent cùng sửa một file hoặc cùng giữ resource;
- context bị cắt/nén làm mất yêu cầu quan trọng;
- agent dùng knowledge cũ hoặc không rõ provenance;
- architecture bị drift sau nhiều lần sửa;
- task được thực hiện nhưng không có approval/decision trail;
- skill/tool được sử dụng mà không có contract rõ ràng;
- thay đổi của worker được integrate quá sớm;
- secrets hoặc dữ liệu nhạy cảm lọt qua context/tool boundary;
- người vận hành không biết hệ thống hiện đang ở trạng thái nào.

AgentOS xây dựng các primitive để xử lý các vấn đề này ở cấp project thay vì phụ thuộc vào prompt riêng của từng agent.

---

## 3. Các lớp chức năng chính

### Governance & Authority

- policy enforcement;
- capability/session boundaries;
- human clarification và approval gates;
- auditable state;
- fail-closed validation;
- separation giữa human authority và agent execution.

### Context, Knowledge & Privacy

- context transport;
- requirement-preserving compression;
- adaptive token budget;
- context expansion/evaluation;
- knowledge provenance;
- stale detection;
- memory scope;
- privacy lifecycle và data subject rights.

### Architecture Governance

- Architecture Contract;
- discovery và evidence binding;
- drift/compliance;
- Architecture Change Proposal;
- ADR;
- architecture-aware task planning;
- structural enforcement;
- runtime/data/API/business-boundary enforcement;
- quality/security/operational enforcement.

### Governed Skills

- Governed Skill Contract v2;
- architecture-aware skill selection;
- evaluation và eligibility;
- skill binding có provenance và freshness checks.

### Multi-Agent Governance

- Multi-Agent Worker Supervisor;
- dependency DAG;
- role/session/lease validation;
- file/write-overlap protection;
- isolated worker workspaces;
- controlled integration;
- conflict detection;
- human-reviewed integration.

### Visibility & Operator Interfaces

- unified CLI;
- MCP governed/read-only surfaces;
- Architecture & Agent Command Center;
- Optional Local Web Control Plane.

---

## 4. Kiến trúc tổng thể

```text
                    Human / Project Owner
                           │
                           ▼
                  Governance & Policy
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
         Context       Architecture      Privacy
        /Knowledge      Governance       /Security
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                    Governed Task/Plan
                           │
                           ▼
                    Governed Skills
                           │
                           ▼
                Multi-Agent Supervisor
                           │
                           ▼
                  Isolated Workspaces
                           │
                           ▼
                 Controlled Integration
                           │
                           ▼
              State / Audit / Compliance
                           │
               ┌───────────┼───────────┐
               ▼           ▼           ▼
              CLI         MCP     Command Center
                                      │
                                      ▼
                            Optional Local Web UI
```

Điểm quan trọng: **Web UI, MCP và CLI không tạo authority mới**. Chúng sử dụng cùng AgentOS core và cùng governed state.

---

## 5. AgentOS không phải là gì?

AgentOS Local Governance không phải:

- một LLM provider;
- một IDE;
- một Git replacement;
- một dịch vụ cloud bắt buộc;
- một agent tự trị được quyền tự approve;
- một hệ thống tự động merge/commit/push mọi thay đổi;
- một updater chain buộc người dùng phải chạy từng version lịch sử.

Model/provider selection vẫn nằm ngoài authority của AgentOS. Human/project authority vẫn là nguồn quyết định cuối cùng.

---

## 6. Cách phân phối: lấy Full Release và chạy

Các release hiện tại sử dụng mô hình **Latest Full Release**.

Người dùng mới **không cần** chạy chuỗi updater lịch sử:

```text
v0.25.x updater
→ v0.26.x updater
→ v0.27.x updater
→ v0.28.x updater
```

Thay vào đó:

```text
GitHub Release / source archive
            ↓
       lấy full source
            ↓
      extract hoặc clone
            ↓
         chạy AgentOS
```

Development patch/hotfix chỉ được dùng trong quá trình phát triển release và **không phải artifact bắt buộc đối với người dùng cuối**.

### Lấy source bằng Git

```bash
git clone https://github.com/amasahara/agentos-local-governance.git
cd agentos-local-governance
git checkout v0.28.1
```

Hoặc download source archive từ:

- [GitHub Releases](https://github.com/amasahara/agentos-local-governance/releases)
- [GitHub Tags](https://github.com/amasahara/agentos-local-governance/tags)

Hướng dẫn đầy đủ:

[Install / Refresh from Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

---

## 7. Chạy nhanh

### Windows PowerShell

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path

.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd command-center
```

Optional Local Web Control Plane:

```powershell
.agents\bin\agentos.cmd web-control-plane
```

Mặc định Web Control Plane chỉ bind:

```text
127.0.0.1:8765
```

Non-loopback bind bị fail-closed.

### POSIX

```bash
export PYTHONPATH="$(pwd)/.agents"

.agents/bin/agentos runtime-health
.agents/bin/agentos command-center
```

---

## 8. Phiên bản mới nhất — v0.28.1

### Optional Local Web Control Plane

v0.28.1 bổ sung browser interface local trên cùng read model của Command Center v0.28.0.

```text
Architecture
Tasks / Agents
Workspaces
Compliance
Human Actions
      │
      ▼
Command Center Snapshot
   │      │      │
   ▼      ▼      ▼
  CLI    MCP   Web UI
```

Các invariant quan trọng:

- loopback-only mặc định;
- one-time browser bootstrap;
- ephemeral in-memory session;
- Host/Origin validation;
- no CORS;
- no external assets;
- no direct database mutation;
- no architecture approval authority;
- no worker-launch authority;
- no integration approval authority;
- no model/provider authority.

| Thành phần | v0.28.1 |
|---|---:|
| Database schema | 61 |
| CLI commands | 336 |
| MCP tools | 123 |
| Manifest files | 300 |
| Focused Web tests | 16 passed |
| Full regression | 565 passed, 1 expected Windows skip |

Tài liệu:

- [Release Notes v0.28.1](RELEASE_NOTES.md)
- [Optional Local Web Control Plane v0.28.1](.agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md)
- [Install Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

---

## 9. Các bản nâng cấp gần đây

| Phiên bản | Nội dung chính |
|---|---|
| [v0.28.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.28.1) | Optional Local Web Control Plane |
| [v0.28.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.28.0) | Architecture & Agent Command Center |
| [v0.27.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.3) | Isolated Workspace & Controlled Integration |
| [v0.27.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.2) | Multi-Agent Worker Supervisor |
| [v0.27.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.1) | Architecture-Aware Skill Selection & Evaluation |
| [v0.27.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.27.0) | Governed Skill Contract v2 |
| [v0.26.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.3) | Quality / Security / Operational Enforcement |
| [v0.26.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.2) | Runtime / Data / API / Business Boundary Enforcement |
| [v0.26.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.1) | Structural Enforcement |
| [v0.26.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.26.0) | Architecture-Aware Task Planning |
| [v0.25.5](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.5) | Architecture Change Proposal & ADR |
| [v0.25.4](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.4) | Architecture Drift & Compliance |
| [v0.25.3](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.3) | Architecture Discovery & Evidence Binding |
| [v0.25.2](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.2) | Architecture Contract & Human Clarification |
| [v0.25.1](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.1) | Release Metadata Coherence |
| [v0.25.0](https://github.com/amasahara/agentos-local-governance/releases/tag/v0.25.0) | Schema Bootstrap Baseline |

Toàn bộ lịch sử:

- [CHANGELOG.md](CHANGELOG.md)
- [GitHub Releases](https://github.com/amasahara/agentos-local-governance/releases)
- [GitHub Tags](https://github.com/amasahara/agentos-local-governance/tags)

---

## 10. Ownership boundary khi cập nhật

AgentOS phân biệt:

### AgentOS-managed distribution

```text
.agents/agentos/**
release-owned policy
AgentOS docs/tests/runtime launchers
release metadata
```

### Project-owned data

```text
user skills
project workflows / workflow state
project source
architecture working copy
governance.local.json
.agents/state/**
.agents/runtime/**
```

Khi refresh AgentOS trong project đang sử dụng, không xóa project-owned partition chỉ để thay runtime distribution.

Xem chi tiết tại [Install / Refresh from Latest Full Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

---

## 11. Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

v0.28.1 final validation:

```text
565 passed
1 expected Windows skip
0 failed
```

---

## 12. Nguyên tắc authority

```text
Human Architect / Project Owner
             │
             ▼
      xác định authority
             │
             ▼
AgentOS kiểm tra và enforcement
             │
             ▼
Agents thực thi trong boundary
             │
             ▼
Audit / Compliance / Visibility
```

> **Human defines authority. AgentOS governs execution. Agents do not grant themselves authority.**
