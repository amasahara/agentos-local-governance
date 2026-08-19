# AgentOS Local Governance — Tiếng Việt

**Phiên bản hiện tại: v0.27.2 — Multi-Agent Worker Supervisor**

Database schema: **60**. Schema bootstrap baseline vẫn là **46**.

v0.27.2 bổ sung **Multi-Agent Worker Supervisor** để điều phối các worker task đã được duyệt bằng DAG dependency, plan/session/role freshness và planned-write overlap gate mà không tự launch process hoặc mở rộng authority.

## Luồng supervisor

```text
Parent task + ACTIVE plan đã được duyệt
      ↓
Approved worker tasks + ACTIVE worker plans
      ↓
Distinct capability sessions + active roles
      ↓
Optional v0.27.1 skill-selection binding
      ↓
Parent-plan subset + DAG + write-overlap gates
      ↓
RUNNABLE WORKERS
(no process launch)
```

Supervisor **không phải execution authority**: không tự tạo/approve task hoặc plan, không cấp capability, không execute skill, không chọn model/provider và không merge workspace.

## Invariant chính
- Parent task chỉ là orchestration envelope; mỗi worker dùng task/session riêng.
- Worker plan không được vượt file/architecture envelope của parent plan.
- Capability session, role và optional skill binding phải luôn current.
- Dependency cycle và overlapping executor write targets fail-closed.
- `worker_start` chỉ đổi state, không launch process.
- MCP chỉ đọc supervisor status/workers/readiness.
- Worktree isolation và controlled integration thuộc v0.27.3.

## CLI

```powershell
agentos multi-agent-supervisor-create --parent-task-id T-PARENT --created-by human:architect
agentos multi-agent-supervisor-worker-add --supervisor-id 1 --worker-key worker-a --task-id T-A --session-id S-A --role executor
agentos multi-agent-supervisor-activate --supervisor-id 1 --approved-by human:architect
agentos multi-agent-supervisor-status --supervisor-id 1
```

## Distribution

Từ v0.27.0+, AgentOS dùng **Latest Full Release** và **no updater script**. Không xóa user skills, workflows, project source, architecture working copy, `governance.local.json`, `.agents/state/**` hoặc `.agents/runtime/**` khi refresh AgentOS-managed runtime.

- [Tài liệu v0.27.2](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [Tài liệu skill-selection v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Cài đặt latest release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [English](README.en.md)
