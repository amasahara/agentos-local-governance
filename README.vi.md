# AgentOS Local Governance v0.26.1 — Structural Enforcement

[README landing](README.md) | [English](README.en.md)

## Phiên bản hiện tại

- Version: **0.26.1**
- Database schema: **55**
- Schema bootstrap baseline: **46** (không đổi)

v0.26.1 đưa **Structural Enforcement** vào các boundary thực thi hiện hữu của AgentOS. Thay vì chỉ phát hiện drift sau khi source đã thay đổi, AgentOS có thể chặn sớm một đường dẫn/module/dependency/import edge/coding structure trái với Architecture Contract đã được con người activate.

## Phạm vi hard contract

Node này chỉ tập trung vào:

- `ARCH-02` Tech Stack
- `ARCH-03` Folder Structure
- `ARCH-04` System Architecture
- `ARCH-05` Module Breakdown
- `ARCH-12` Dependency Graph
- `ARCH-22` Coding Convention
- `ARCH-23` Design Pattern

Các boundary runtime/data/API/business sẽ ở v0.26.2; quality/security/operational architecture ở v0.26.3.

## Luồng enforcement

```text
Human-approved ACTIVE Architecture Baseline
                    ↓
           Architecture-Aware Plan
                    ↓
         Structural pre-plan checks
                    ↓
             Human plan approval
                    ↓
             check_write / prepare
                    ↓
        Static structural enforcement
                    ↓
                 Precommit
                    ↓
            PASS hoặc BLOCK
```

Nếu `BLOCK` là một thay đổi kiến trúc hợp lệ, AI không được tự sửa contract để làm cho code pass. Luồng đúng là:

```text
BLOCK
  ↓
Architecture Change Proposal
  ↓
ADR
  ↓
Human Review / Approval
  ↓
New candidate baseline
  ↓
Human activation
  ↓
Re-plan
```

## Các invariant chính

- `AGENTS.md` vẫn là coding-agent instruction authority duy nhất.
- Architecture Authority vẫn thuộc con người.
- Không có ACTIVE baseline → `not_evaluable`, không tự block project cũ.
- Có ACTIVE baseline → explicit structural contract có thể block write/plan/precommit.
- AgentOS chỉ enforce các field machine-readable được khai rõ; không tự suy luận rule từ prose.
- Không execute source project, không network, không tự cài dependency.
- MCP structural tools chỉ read-only; không approve/waive/activate.
- Updater không overwrite source/rules/workflows/architecture working copy của project.

## Ví dụ chống “AI vibe”

Nếu architecture cấm module chung chung:

```json
{
  "forbidden_module_names": ["utils.py"],
  "module_location_rules": [
    {
      "match": "utils.py",
      "allowed_paths": ["src/shared/date.py", "src/shared/validation.py"]
    }
  ]
}
```

AI tạo `src/utils.py` sẽ bị chặn trước write/precommit.

Nếu `ARCH-02` chỉ cho phép `requests` nhưng plan/dependency manifest thêm `sqlalchemy`, plan hoặc precommit sẽ bị block và yêu cầu Architecture Change Proposal.

## Coding convention

`ARCH-22` có thể khai rõ các rule như:

- `require_file_header_path`
- `require_module_purpose`
- `require_public_symbol_docstrings`
- `forbid_wildcard_imports`
- `max_module_lines`
- `forbidden_file_names`

Các rule không được khai thì không tự trở thành authority.

## Command

```bash
agentos architecture-structural-status
agentos architecture-structural-check --task-id TASK-1 --changed-file src/example.py
agentos architecture-structural-findings --task-id TASK-1

agentos architecture-plan-impact --task-id TASK-1 --plan '{...}'
agentos architecture-plan-status --task-id TASK-1
agentos precommit-check --task-id TASK-1
```

Xem [tài liệu v0.26.1](.agents/docs/ARCHITECTURE_STRUCTURAL_ENFORCEMENT_V0261.md) và [hướng dẫn nâng cấp](.agents/docs/UPGRADE_FROM_0.26.0.md).
