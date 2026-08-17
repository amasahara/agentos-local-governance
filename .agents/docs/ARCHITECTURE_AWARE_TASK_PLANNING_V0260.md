# AgentOS v0.26.0 — Architecture-Aware Task Planning

**Release:** 0.26.0 — Architecture-Aware Task Planning
**Database schema:** 54

v0.26.0 connects the human-owned Architecture Contract to the existing immutable task-plan lifecycle. It does not create a second planner and does not grant AI architecture authority.

## Planning contract

When no ACTIVE Architecture Baseline exists, historical planning remains `not_evaluable` and non-blocking. When a human-activated baseline exists, every submitted implementation plan is normalized and system-bound to:

- requirements;
- exact `architecture_baseline_hash` from the ACTIVE baseline;
- affected `ARCH-01..ARCH-27` sections;
- expected modules;
- expected dependency edges;
- expected files;
- acceptance criteria;
- deterministic `architecture_impact_hash`.

The caller may not spoof the baseline hash. A supplied mismatching hash fails closed. The persisted `plan_hash` includes the system-owned architecture baseline and impact hashes.

## Pre-approval impact analysis

Before plan persistence under an ACTIVE baseline, AgentOS validates declared expected files/modules/dependency edges against the current machine-readable Architecture Contract. Hard path/module/import-edge violations block plan submission and require implementation redesign or the v0.25.5 Architecture Change Proposal/ADR lifecycle.

## Stale plan semantics

Plan approval revalidates the architecture pin. If the ACTIVE baseline changed after submission, the plan becomes stale and cannot be approved. When a new baseline activates, plans pinned to the superseded baseline are marked stale when their declared affected sections intersect changed architecture sections. Plans with an empty/unknown affected-section declaration are conservatively treated as affected. Plans created while architecture was not evaluable become stale when the first baseline becomes ACTIVE.

Precommit also rejects a stale architecture plan before execution completion.

## Schema 54

Adds:

- `task_plan_architecture_contexts`
- `task_plan_architecture_events`

The schema stores hashes and normalized planning metadata, not raw source code or secret values.

## CLI

- `architecture-plan-impact` — deterministic prospective impact analysis; no persistence or authority mutation.
- `architecture-plan-show` — read a persisted plan plus architecture binding.
- `architecture-plan-status` — read baseline/current/stale readiness.

Existing `plan-submit`, `plan-approve`, `plan-show`, and `precommit-check` now use the architecture-aware planning contract automatically.

## MCP boundary

Read-only only:

- `agentos.architecture_plan_get`
- `agentos.architecture_plan_status_get`
- `agentos.architecture_plan_impact_get`

The MCP impact tool reads persisted impact only; MCP cannot submit/approve plans, run authority-changing analysis, approve ADRs, mutate Architecture Contracts, or activate baselines.

## Authority invariants

- ACTIVE Architecture Baseline remains human authority.
- AI may draft a plan but cannot choose a different baseline hash.
- Human plan approval does not change Architecture Authority.
- Architecture Change Proposal/ADR remains a separate human-governed lifecycle.
- Baseline changes invalidate affected plans instead of silently rebasing them.
- Project-owned source, rules, workflows, architecture working copies, and state remain protected from AgentOS updater overwrite.
