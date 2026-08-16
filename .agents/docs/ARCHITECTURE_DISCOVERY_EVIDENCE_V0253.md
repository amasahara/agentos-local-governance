# AgentOS v0.25.3 — Architecture Discovery & Evidence Binding

**Release:** 0.25.3 — Architecture Discovery & Evidence Binding  
**Database schema:** 51

## Mục tiêu

v0.25.3 bổ sung lớp **Observed Architecture** nằm dưới Architecture Contract 27 phần của v0.25.2. Scanner chỉ quan sát source một cách deterministic và read-only; kết quả không có authority để review, approve, activate hoặc tự sửa Architecture Contract.

```text
PROJECT SOURCE
    │ read-only static scan
    ▼
architecture_scan_runs
    ├── architecture_observations
    ├── architecture_evidence  (path + SHA-256 + locator)
    └── architecture_discrepancies  (advisory only)
             │
             ▼
27-section Architecture Contract
HUMAN remains authority
```

## Discovery scope v1

Scanner phát hiện các tín hiệu deterministic sau:

- `ARCH-02`: ngôn ngữ và dependency manifests.
- `ARCH-03`: cấu trúc thư mục top-level của source root.
- `ARCH-09`: migration/schema files.
- `ARCH-10`: CLI/MCP surfaces có literal tĩnh.
- `ARCH-12`: Python import graph theo AST.
- `ARCH-14`: configuration-file inventory.
- `ARCH-20`: CI và deployment files.
- `ARCH-21`: test-file inventory.

Scanner **không** import project module, không chạy project code, không gọi network, không follow symlink và bỏ qua file lớn hơn 2 MiB. Khi scan project root mặc định, `.agents/` được loại khỏi source discovery để tránh biến governance metadata thành kiến trúc nghiệp vụ; có thể scan chính AgentOS bằng `--source-root .agents/agentos` khi cần.

## Evidence contract

SQLite chỉ lưu metadata có provenance:

```text
section_id
observation_kind
subject
value_json       # inventory/metadata, không phải raw source
observation_hash
source_path
source_hash      # SHA-256
locator_json
evidence_hash
```

Không lưu raw source bytes. Evidence thay đổi giữa hai scan tạo `evidence_hash_changed` ở mức `info`. Nếu active Architecture Contract khai báo `not_applicable` nhưng source có evidence, scanner tạo advisory discrepancy. Evidence mới chưa được bind vào contract cũng chỉ tạo finding `info`.

**v0.25.3 không biến discrepancy thành execution blocker.** Architecture Drift & Compliance Engine thuộc v0.25.4.

## CLI

```bash
.agents/bin/agentos architecture-scan --created-by human
.agents/bin/agentos architecture-scan --source-root src --created-by human
.agents/bin/agentos architecture-scan-show --scan-id 1
.agents/bin/agentos architecture-observations --scan-id 1 --section-id ARCH-12
.agents/bin/agentos architecture-evidence --scan-id 1 --section-id ARCH-02
.agents/bin/agentos architecture-discrepancies --scan-id 1
```

Scan giống hệt source + active baseline tạo cùng `scan_hash` và trả lại scan hiện hữu (`idempotent=true`).

## MCP boundary

MCP chỉ đọc:

- `agentos.architecture_scan_get`
- `agentos.architecture_observations_get`
- `agentos.architecture_evidence_get`
- `agentos.architecture_discrepancies_get`

Không expose `architecture-scan` qua MCP; LLM không có quyền kích hoạt scan mutation trong local state và không có quyền sửa/approve/activate architecture.

## Update Preservation Boundary

v0.25.3 bổ sung update contract để các release sau không ghi đè state của project:

```text
PROJECT_OWNED — NEVER OVERWRITE
AGENTS.md
.agents/config/governance.local.json
.agents/config/project.id
.agents/config/project.purpose.json
.agents/architecture/**
.agents/state/**
.agents/skills/**
.agents/workflows/**
unknown paths

DISTRIBUTION_MANAGED — HASH GATED
known AgentOS runtime/config files from the installed release lock
```

Upgrade chạy theo chuỗi:

```text
preflight every planned write
→ verify baseline SHA-256
→ abort on any conflict
→ backup managed files + consistent SQLite snapshot
→ atomic replace managed files only
→ additive DB migration
→ verify pre-existing table row counts did not decrease
→ verify protected project-owned hashes unchanged
→ write distribution lock
→ two-pass finalize distribution lock + release metadata
```

Nếu `.agents/config/governance.json` đã được chỉnh tay, updater **không ghi đè** mà dừng trước mutation. Custom rule phải được chuyển vào `.agents/config/governance.local.json`; file local này được giữ nguyên xuyên suốt update.

Architecture working copy, active baseline data, task/workflow state và promoted skills không bị reset. Migration 51 chỉ thêm bảng discovery/evidence.
