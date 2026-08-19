# AgentOS Local Governance — Tiếng Việt

**Phiên bản hiện tại: v0.27.1 — Architecture-Aware Skill Selection & Evaluation**

Database schema: **59**. Schema bootstrap baseline vẫn là **46**.

v0.27.1 nối **Governed Skill Contract v2** vào active architecture-aware task plan để AgentOS có thể đề xuất skill phù hợp một cách deterministic, local và least-authority.

## Luồng lựa chọn

```text
Yêu cầu người dùng
      ↓
Requirement Ledger + ACTIVE plan
      ↓
Architecture Baseline
      ↓
Graduated Skill Contract v2
      ↓
Kiểm tra contract current
      ↓
Architecture / scope / capability / tool / dependency / service / test gates
      ↓
Deterministic ranking
      ↓
ADVISORY RECOMMENDATION
```

Lựa chọn **không phải execution authority**. AgentOS không tự attach skill vào plan, không tự chạy skill, không cấp capability, không approve architecture và không chọn model/provider.

## Invariant chính

- Chỉ skill `graduated` có Contract v2 current mới eligible.
- `legacy_v1` vẫn được bảo tồn nhưng không được architecture-aware selection chọn.
- Contract stale/invalid bị loại fail-closed.
- Planned files phải nằm trong `allowed_write_scope`.
- Capability phải nằm trong governed capability inventory.
- Required tools phải được khai báo là available cho selection run.
- Dependencies, external services, architecture sections và required test suites không được vượt contract.
- Evaluation chỉ quan sát `task_outcomes`; không auto-graduate/revoke và không tự đổi ranking cho tương lai.
- MCP chỉ đọc status/candidates/evaluation.

## CLI

```powershell
agentos skill-selection-run --task-id T-123
agentos skill-selection-status --task-id T-123
agentos skill-selection-candidates --run-id 1
agentos skill-evaluation-run --selection-run-id 1
```

## Distribution

Từ v0.27.0+, AgentOS dùng **Latest Full Release** và **no updater script**. Không xóa user skills, workflows, project source, architecture working copy, `governance.local.json`, `.agents/state/**` hoặc `.agents/runtime/**` khi refresh AgentOS-managed runtime.

- [Tài liệu v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Cài đặt latest release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [English](README.en.md)
