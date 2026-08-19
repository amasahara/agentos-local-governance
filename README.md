# AgentOS Local Governance

**Current release: v0.27.2 — Multi-Agent Worker Supervisor**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **60**. Schema bootstrap baseline remains **46**.

v0.27.2 adds a governed **Multi-Agent Worker Supervisor** above the existing task/session/role/lease primitives. It coordinates existing approved worker tasks as an acyclic dependency graph, revalidates architecture/plan/session/role/optional-skill freshness, blocks overlapping executor write targets, and reports runnable workers without launching processes or expanding authority.

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
```

## v0.27.2 supervisor flow

```text
Human-approved parent task + ACTIVE plan
        ↓
Existing approved worker tasks + ACTIVE plans
        ↓
Distinct capability sessions + active collaboration roles
        ↓
Optional current v0.27.1 skill-selection binding
        ↓
Parent-plan file / architecture subset gate
        ↓
Dependency DAG + executor write-overlap gate
        ↓
RUNNABLE WORKERS (state only; no process launch)
```

Core invariants:
- The supervisor never creates or approves tasks/plans and never grants capabilities.
- Every worker uses a distinct worker task and session; the parent task is the orchestration envelope.
- Worker plan files and affected architecture sections must remain subsets of the parent plan.
- Active capability sessions and active collaboration roles are revalidated.
- Optional skill bindings must remain current v0.27.1 eligible/recommendable graduated Contract-v2 selections.
- Dependency cycles fail closed and overlapping executor planned write targets block activation.
- `worker_start` changes supervisor state only; it does not launch a worker process.
- Model/provider selection authority remains outside AgentOS.
- MCP exposes supervisor status/readiness inspection only; no mutation authority is added.
- Worktree isolation and controlled integration remain reserved for v0.27.3.

## Main commands

```bash
agentos multi-agent-supervisor-create --parent-task-id T-PARENT --created-by human:architect
agentos multi-agent-supervisor-worker-add --supervisor-id 1 --worker-key worker-a --task-id T-A --session-id S-A --role executor
agentos multi-agent-supervisor-dependency-add --supervisor-id 1 --worker-key worker-b --depends-on worker-a
agentos multi-agent-supervisor-activate --supervisor-id 1 --approved-by human:architect
agentos multi-agent-supervisor-status --supervisor-id 1
agentos multi-agent-supervisor-workers --supervisor-id 1
```

Existing v0.27.1 skill-selection and Governed Skill Contract v2 commands remain available; supervisor skill binding is optional and does not execute a skill.

## MCP read-only surface added in v0.27.2

```text
agentos.multi_agent_supervisor_status_get
agentos.multi_agent_supervisor_workers_get
agentos.multi_agent_supervisor_readiness_get
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

- [Multi-Agent Worker Supervisor v0.27.2](.agents/docs/MULTI_AGENT_WORKER_SUPERVISOR_V0272.md)
- [Architecture-Aware Skill Selection & Evaluation v0.27.1](.agents/docs/ARCHITECTURE_AWARE_SKILL_SELECTION_EVALUATION_V0271.md)
- [Governed Skill Contract v2](.agents/docs/GOVERNED_SKILL_CONTRACT_V0270.md)
- [Install Latest Release](.agents/docs/INSTALL_LATEST_RELEASE.md)

`AGENTS.md` remains the only coding-agent instruction authority. Architecture Authority remains human-owned.
