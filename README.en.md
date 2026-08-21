# AgentOS Local Governance — English

**Current release: v0.28.1 — Optional Local Web Control Plane**

Database schema: **61**. Schema bootstrap baseline remains **46**.

v0.28.1 adds an optional local-only Web Control Plane on the same Command Center Snapshot without creating a second database/API authority; schema remains 61.

## Web Control Plane v0.28.1

```bash
agentos web-control-plane
```

The default bind is `127.0.0.1:8765`. The browser uses a one-time bootstrap and in-memory session. No CORS, external assets, mutation, approval, worker-launch, model/provider or direct database authority is added.

## Command Center v0.28.0

v0.28.0 uses one read-only Snapshot v1 shared by the terminal TUI, JSON CLI and MCP. It adds no mutation, approval, worker-launch or model/provider authority.

```bash
agentos command-center
agentos command-center-actions
```

## Workspace / integration flow

```text
approved worker task/session
      ↓
dedicated detached worktree
      ↓
governed read/write/test routing
      ↓
hash-only diff + architecture/security/test gates
      ↓
sealed workspace + conflict analysis
      ↓
HUMAN REVIEW + APPROVAL
      ↓
parent-task controlled apply
```

Core invariants:
- Executor workers cannot fall back to primary-tree filesystem/process execution when workspace policy is enabled.
- Changed files stay inside the worker plan and sealed workspaces become read-only.
- Primary conflicts block integration and are never auto-resolved.
- Controlled apply uses parent scope, leases, hashes, backup and rollback.
- AgentOS never invokes `git merge`, auto-commit, or auto-push.
- MCP remains read-only for workspace/proposal/readiness inspection.

## Main CLI

```bash
agentos multi-agent-workspace-provision --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-workspace-collect --supervisor-id 1 --worker-key worker-a
agentos multi-agent-workspace-seal --supervisor-id 1 --worker-key worker-a
agentos multi-agent-integration-proposal-create --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-integration-proposal-review --proposal-id 1 --reviewed-by human:reviewer
agentos multi-agent-integration-proposal-approve --proposal-id 1 --approved-by human:approver
agentos multi-agent-integration-apply --proposal-id 1 --applied-by human:integrator
```
## Distribution
- [v0.28.1 Web Control Plane documentation](.agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md)
- [v0.28.0 Command Center documentation](.agents/docs/ARCHITECTURE_AGENT_COMMAND_CENTER_V0280.md)

AgentOS uses the **Latest Full Release** model with **no updater script**. Project-owned user skills, workflows, source, architecture working copies, local governance overrides, state, and runtime data remain outside the managed release partition.

- [v0.27.3 documentation](.agents/docs/ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md)
- [v0.27.2 supervisor documentation](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [v0.27.1 skill-selection documentation](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [Tiếng Việt](README.vi.md)
