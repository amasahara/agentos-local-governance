# AgentOS Local Governance

**Current release: v0.28.1 — Optional Local Web Control Plane**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **61**. Schema bootstrap baseline remains **46**.

v0.28.1 adds an **optional local Web Control Plane** on top of the same privacy-safe Command Center Snapshot. It binds only to loopback, uses ephemeral browser authentication, adds no database/API authority, and keeps schema 61.

## Architecture governance progression

```text
v0.25.2  Architecture Contract + Human Clarification
   ↓
v0.25.3  Architecture Discovery & Evidence Binding
   ↓
v0.25.4  Architecture Drift & Compliance
   ↓
v0.25.5  Architecture Change Proposal & ADR
   ↓
v0.26.0  Architecture-Aware Task Planning
   ↓
v0.26.1  Structural Enforcement
   ↓
v0.26.2  Runtime/Data/API & Business Boundary Enforcement
   ↓
v0.26.3  Quality/Operational Enforcement
   ↓
v0.27.0  Governed Skill Contract v2
   ↓
v0.27.1  Architecture-Aware Skill Selection & Evaluation
   ↓
v0.27.2  Multi-Agent Worker Supervisor
   ↓
v0.27.3  Isolated Workspace & Controlled Integration
   ↓
v0.28.0  Architecture & Agent Command Center
   ↓
v0.28.1  Optional Local Web Control Plane
```

## v0.28.1 Optional Local Web Control Plane

```text
Command Center Snapshot v1
      ↓
local-only HTTP presentation
      ↓
browser dashboard
```

Launch explicitly:

```bash
agentos web-control-plane
```

Default bind is `127.0.0.1:8765`. Non-loopback binds fail closed. The browser uses a one-time fragment bootstrap and an ephemeral HttpOnly/SameSite session. The web plane has no architecture approval, integration approval, worker launch, model/provider, privileged CLI, direct database, Git, or MCP mutation authority.

## v0.28.0 Command Center

```text
Architecture + Tasks/Agents + Workspaces + Compliance + Human Actions
                              ↓
                   read-only Snapshot v1
                       ↓             ↓
                  terminal TUI    MCP/JSON
```

Main commands:

```bash
agentos command-center
agentos command-center --format json
agentos command-center-actions
agentos command-center-section --section compliance
```

The Command Center never persists a second dashboard state, never exposes raw source/question content or physical workspace paths, and never creates approval/integration/worker-launch authority.

## v0.27.3 workspace / integration flow

```text
Approved supervisor worker (task + session)
        ↓
detached worker worktree
        ↓
governed read/write/test routing
        ↓
hash-only diff collection
        ↓
architecture + security + test gates
        ↓
sealed workspace
        ↓
conflict analysis
        ↓
HUMAN REVIEW + APPROVAL
        ↓
parent-task controlled integration
(no git merge / no auto-commit)
```

Core invariants:
- Executor workers cannot fall back to primary-tree filesystem/process execution when v0.27.3 workspace policy is enabled.
- Workspace ownership is exact `task_id + session_id`; AgentOS state and leases remain in the primary repository.
- Changed paths must remain inside the worker plan; raw source is not persisted in workspace/integration state.
- Sealing requires immutable diff, architecture/security gates, and a successful governed test receipt.
- Primary drift produces explicit conflicts and blocks review/approval/apply; conflicts are never auto-resolved.
- Controlled apply uses parent task/session scope, leases, hashes, backup, atomic replace/delete and rollback.
- AgentOS never invokes `git merge`, auto-commit, auto-push, or grants merge authority to MCP/AI.

## Main v0.27.3 commands

```bash
agentos multi-agent-workspace-provision --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-workspace-collect --supervisor-id 1 --worker-key worker-a
agentos multi-agent-workspace-seal --supervisor-id 1 --worker-key worker-a
agentos multi-agent-integration-proposal-create --supervisor-id 1 --worker-key worker-a --created-by human:operator
agentos multi-agent-integration-proposal-review --proposal-id 1 --reviewed-by human:reviewer
agentos multi-agent-integration-proposal-approve --proposal-id 1 --approved-by human:approver
agentos multi-agent-integration-apply --proposal-id 1 --applied-by human:integrator
```

## MCP read-only surface added in v0.27.3

```text
agentos.multi_agent_workspace_status_get
agentos.multi_agent_workspace_diff_summary_get
agentos.multi_agent_integration_proposal_get
agentos.multi_agent_integration_readiness_get
```

## Distribution model

Current AgentOS releases use the **Latest Full Release** model with **no updater script**. AgentOS-managed runtime is separate from project-owned user skills, workflows, source, architecture working copies, `governance.local.json`, `.agents/state/**`, and `.agents/runtime/**`.

See [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md).

## Validation

```bash
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
git diff --check
```

## Current node documentation

- [Optional Local Web Control Plane v0.28.1](.agents/docs/OPTIONAL_LOCAL_WEB_CONTROL_PLANE_V0281.md)
- [Architecture & Agent Command Center v0.28.0](.agents/docs/ARCHITECTURE_AGENT_COMMAND_CENTER_V0280.md)
- [Isolated Workspace & Controlled Integration v0.27.3](.agents/docs/ISOLATED_WORKSPACE_CONTROLLED_INTEGRATION_V0273.md)
- [Multi-Agent Worker Supervisor v0.27.2](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [Architecture-Aware Skill Selection & Evaluation v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Governed Skill Contract v2](.agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

`AGENTS.md` remains the only coding-agent instruction authority. Architecture Authority remains human-owned.
