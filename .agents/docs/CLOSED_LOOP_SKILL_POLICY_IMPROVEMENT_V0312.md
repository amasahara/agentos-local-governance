# AgentOS v0.31.2 — Closed-Loop Skill & Policy Improvement

## Scope

v0.31.2 closes the governed learning loop without creating a new feedback,
lesson, skill, or policy-authority subsystem.

The database schema remains **64**. Schema-64 learning links already support
`skill_candidate` and `evolution_proposal`, while AgentOS already has
`promoted_skills`, observational `skill_evaluation_runs`, and
`evolution_proposals`.

## Closed-loop flow

```text
verified findings
    ↓
human-approved active procedural memory (v0.31.1)
    ↓
non-active Governed Skill Contract v2 candidate
    ↓
existing human skill graduation
    ↓
advisory skill selection + observational skill evaluation
    ↓
repeated current adverse evaluations across distinct verified tasks
    ↓
explicit caller-supplied policy patch
    ↓
draft evolution proposal
    ↓
deterministic simulation
    ↓
existing control-plane review / shadow / canary / active lifecycle
```

Automatic skill candidate creation does not grant skill authority. Closed-loop
candidates revalidate source hashes, verified-task eligibility, learning links,
and Architecture Authority binding again before human graduation.

Policy readiness is observational. Default thresholds are 2 adverse evaluations,
at least 1 negative evaluation, at least 2 distinct evaluation tasks, and a
30-day evidence window. `mixed` and `negative` are the only adverse statuses.

AgentOS does not synthesize a policy patch from learning evidence. The caller
must supply the concrete patch, expected benefit, risks, rollback plan, title,
and creator identity. AgentOS may run deterministic simulation after that
explicit draft is created, but it does not automatically review, transition,
activate, roll back, or modify Architecture Authority.

The existing proposal lifecycle remains:

```text
draft → simulated → reviewed → shadow → canary → active → rolled_back
```

`skill-graduate` and `evolution-transition` remain existing control-plane
authority surfaces.

## Context Authority

Learning-derived memory, skill evidence, and proposal evidence remain:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

Human actions authorize lifecycle transitions only and do not convert learning
evidence into instruction authority.

## MCP

v0.31.2 adds no MCP tool and no MCP mutation. The catalog remains 132 tools.

## Failure semantics

Skill-candidate creation and proposal simulation are non-active learning-support
operations and are degraded-safe with respect to already-approved memory and
existing execution evidence. Skill graduation and proposal lifecycle transitions
remain governed/fail-closed through their existing authority paths.

## Non-claims

v0.31.2 does not claim autonomous policy synthesis, autonomous skill authority,
automatic policy activation, automatic architecture mutation, causal learning
effectiveness, semantic correctness, prompt-injection elimination, or
replacement of human review.
