# AgentOS Local Governance — Tiếng Việt

**Phiên bản hiện tại: v0.27.3 — Isolated Workspace & Controlled Integration**

Database schema: **61**. Schema bootstrap baseline vẫn là **46**.

v0.27.3 bổ sung isolated Git worktree cho executor worker và Controlled Integration có human review/approval, trong khi primary AgentOS vẫn giữ state, policy, lease và audit authority.

## Luồng workspace / integration

```text
approved worker task/session
      ↓
detached worktree riêng
      ↓
governed read/write/test
      ↓
diff hash + architecture/security/test gates
      ↓
sealed workspace + conflict analysis
      ↓
HUMAN REVIEW + APPROVAL
      ↓
parent-task controlled apply
```

Invariant chính:
- Executor worker không được fallback ghi/chạy trên primary tree khi workspace policy bật.
- Changed files phải nằm trong worker plan.
- Workspace sau seal là read-only.
- Conflict với primary block integration; không auto-resolve.
- Không `git merge`, auto-commit hoặc auto-push.
- MCP chỉ đọc workspace/proposal/readiness.

## CLI chính

```powershell
agentos multi-agent-workspace-provision --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-workspace-collect --supervisor-id 1 --worker-key worker-a
agentos multi-agent-workspace-seal --supervisor-id 1 --worker-key worker-a
agentos multi-agent-integration-proposal-create --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-integration-proposal-review --proposal-id 1 --reviewed-by human:reviewer
agentos multi-agent-integration-proposal-approve --proposal-id 1 --approved-by human:approver
agentos multi-agent-integration-apply --proposal-id 1 --applied-by human:integrator
```
## Distribution

Từ v0.27.0+, AgentOS dùng **Latest Full Release** và **no updater script**. Không xóa user skills, workflows, project source, architecture working copy, `governance.local.json`, `.agents/state/**` hoặc `.agents/runtime/**` khi refresh AgentOS-managed runtime.

- [Tài liệu v0.27.3](.agents/docs/ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md)
- [Supervisor v0.27.2](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [Tài liệu skill-selection v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Cài đặt latest release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [English](README.en.md)
