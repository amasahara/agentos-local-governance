# AgentOS Local Governance v0.29.0 — Independent Completion Verification

AgentOS v0.29.0 makes accepted completion producer-independent and evidence-bound for AgentOS-mediated workflows.

Database schema is **62**.

## Highlights

### Independent completion receipt

Accepted completion can no longer be established solely by the producer that produced the work. AgentOS records a completion request bound to the subject, producer task/session/assignment, subject hash, and required checks. Verification runs under governed reviewer authority.

A passing receipt requires verifier task/session/assignment independence, exact subject-hash match, every required check to pass, and non-empty evidence. If the subject changes after verification, the receipt becomes stale and completion fails closed until independently verified again.

### Workflow, worker, and integration enforcement

Single-task workflow completion separates candidate readiness from final completion and binds the terminal report to the accepted receipt. Multi-agent workers cannot self-terminalize as `completed`; a current independent receipt is required. Controlled integration proposals pin the worker receipt and readiness revalidates it.

### CLI and MCP

Agent-plane CLI adds:

```text
completion-request
completion-verify
completion-status
```

MCP adds exactly one completion surface:

```text
agentos.completion_status_get
```

It is read-only and privacy-redacted. Completion request/verify mutation authority is not exposed over MCP.

### Attestation and release integrity

`agentos enforcement-attest` now verifies independent reviewer authority, producer/verifier separation, subject-hash binding, passing-check/evidence requirements, stale-subject rejection, workflow/worker/integration receipt enforcement, CLI plane isolation, and MCP read-only exposure.

v0.29.0 release policy declares:

```text
independent_completion_attested = true
scope = agentos_mediated_agent_execution
database_schema = 62
```

### Runtime surface

```text
344 canonical commands
248 agent-plane commands
98 privileged-control-plane commands
2 intentional dual-plane commands
0 unexpected agent/privileged overlap
124 MCP tools
```

The intentional dual-plane commands remain `architecture-init` and `project-adopt`.

### Explicit claim boundary

> AgentOS completion is producer-independent and evidence-bound.

The scope is `agentos_mediated_agent_execution`.

This release does **not** guarantee semantic correctness, attest model/provider independence, replace human review, replace human approval, claim same-user host bypass resistance, claim OS-level process isolation, or claim arbitrary host-process containment.

## Compatibility

v0.29.0 upgrades AgentOS state from schema **61** to **62**. Fresh databases materialize the existing schema bootstrap baseline and apply the ordered migration chain through migration 62. Existing schema-61 state upgrades incrementally.

The v0.28.4 Tool Exclusivity & Enforcement Attestation contract and v0.28.3 Privileged Control Plane separation remain intact.

## Distribution

The distribution model remains **Latest Full Release**. No version-specific updater script is required in the release payload. Project-owned source, skills/workflows, and local runtime state remain outside the managed replacement boundary.
