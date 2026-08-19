# AgentOS Local Governance — English

**Current release: v0.27.2 — Multi-Agent Worker Supervisor**

Database schema: **60**. Schema bootstrap baseline remains **46**.

v0.27.2 adds a governed **Multi-Agent Worker Supervisor** that coordinates already-approved worker tasks through dependency-DAG, plan/session/role freshness, and planned-write overlap gates without launching processes or expanding authority.

## Supervisor flow

```text
Human-approved parent task + ACTIVE plan
     ↓
Approved worker tasks + ACTIVE worker plans
     ↓
Distinct capability sessions + active roles
     ↓
Optional current v0.27.1 skill-selection binding
     ↓
Parent-plan subset + DAG + write-overlap gates
     ↓
RUNNABLE WORKERS
(no process launch)
```

The supervisor is **not execution authority**. It cannot create/approve tasks or plans, grant capabilities, execute skills, select a model/provider, or merge workspaces.

Core invariants:
- The parent task is the orchestration envelope; each worker uses its own task/session.
- Worker plans cannot exceed the parent file/architecture envelope.
- Capability session, role, and optional skill binding must remain current.
- Dependency cycles and overlapping executor write targets fail closed.
- `worker_start` changes state only and does not launch a process.
- MCP exposes supervisor status/workers/readiness inspection only.
- Worktree isolation and controlled integration remain v0.27.3 scope.

## CLI

```bash
agentos multi-agent-supervisor-create --parent-task-id T-PARENT --created-by human:architect
agentos multi-agent-supervisor-worker-add --supervisor-id 1 --worker-key worker-a --task-id T-A --session-id S-A --role executor
agentos multi-agent-supervisor-activate --supervisor-id 1 --approved-by human:architect
agentos multi-agent-supervisor-status --supervisor-id 1
```

## Distribution

AgentOS uses the **Latest Full Release** model with **no updater script**. Project-owned user skills, workflows, source, architecture working copies, local governance overrides, state, and runtime data remain outside the managed release partition.

- [v0.27.2 documentation](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [v0.27.1 skill-selection documentation](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)
- [Tiếng Việt](README.vi.md)
