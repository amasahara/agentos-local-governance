# AgentOS Local Governance v0.31.2 — Closed-Loop Skill & Policy Improvement

Database schema: **64**

v0.31.2 closes the governed learning loop from human-approved project memory to
reusable skill candidates and evidence-backed policy improvement proposals while
preserving existing authority boundaries.

No migration 65 and no parallel feedback, lesson, skill, or policy subsystem are
introduced.

## Closed-loop skill improvement

Human-approved active procedural memory may produce a non-active Governed Skill
Contract v2 candidate when its original learning evidence remains current.

Candidate creation requires current learning links, current source hashes,
verified cross-task eligibility, the active Architecture Authority baseline, the
existing skill confidence threshold, and the existing distinct verified-task
threshold.

Candidate creation does not graduate the skill. Existing human-controlled
`skill-graduate` remains the graduation path, and closed-loop candidates
revalidate linked learning evidence immediately before graduation.

## Closed-loop policy improvement

Observational skill evaluations can establish readiness for a policy-improvement
proposal. The default gate requires within 30 days:

- at least 2 adverse evaluations;
- at least 1 negative evaluation;
- at least 2 distinct evaluation tasks;
- current task-outcome learning signals;
- current source hashes;
- current architecture-baseline binding;
- an existing evaluation baseline.

Only `mixed` and `negative` count as adverse evidence.

AgentOS does not synthesize policy authority from learning evidence. A proposal
is created only when a caller explicitly supplies the concrete policy patch,
expected benefit, risks, rollback plan, title, and creator identity.

The closed loop may automatically run the existing deterministic simulation
after that explicit draft is created. It may not automatically review,
transition, activate, roll back, or mutate Architecture Authority.

The existing proposal lifecycle remains:

```text
draft → simulated → reviewed → shadow → canary → active → rolled_back
```

`evolution-transition` remains a control-plane command.

## Learning linkage and schema

Schema-64 `learning_signal_links` already reserves `skill_candidate` and
`evolution_proposal`. v0.31.2 therefore keeps schema 64 and reuses
`project_memory`, `promoted_skills`, `skill_contracts`, `skill_evaluation_runs`,
`evolution_proposals`, `evolution_stage_events`, `learning_signals`, and
`learning_signal_links`.

## Context Authority

Learning-derived memory, skill evidence, and proposal evidence remain:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

Human actions authorize lifecycle transitions only and do not convert evidence
into instruction authority.

## Command and MCP surfaces

v0.31.2 adds four agent-plane orchestration/readiness commands and no privileged
command.

Expected release surface:

```text
CLI commands          = 360
agent commands        = 263
privileged commands   = 99
MCP tools             = 132
```

No MCP tool is added; governed-learning MCP remains read-only.

There is no automatic skill graduation, policy-patch synthesis, policy
transition, policy activation, or Architecture Authority mutation.

## Predecessor contracts preserved

v0.31.2 preserves:
- v0.31.1 — Governed Memory Promotion & Context Binding
- v0.31.0 — Governed Learning Signal Integration
- v0.30.1 — Release & Schema Metadata Coherence
- v0.30.0 — Context Authority & Untrusted Provenance
- v0.29.5 — Native Physical Isolation Extensions
- v0.29.4 Restricted Token

```text
restricted_token_attested = true
low_integrity_attested = true
host_filesystem_isolation_attested = false
```

These are bounded predecessor attestations and not a claim of general host
filesystem isolation.

This release does not claim prompt injection elimination, autonomous policy
synthesis, semantic correctness, causal learning effectiveness, replacement of
human review, or general host containment.

Next node: **v0.31.3 — Learning Effectiveness & Drift**.
