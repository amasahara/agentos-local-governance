# AgentOS v0.31.1 — Governed Memory Promotion & Context Binding

## Scope

v0.31.1 turns repeated, verified project findings into reusable project-memory
candidates through the existing `project_memory`, Human Decision, learning-link,
and context retrieval subsystems.

The database schema remains **64**. No lesson registry, pattern registry,
`feedback_*` subsystem, or parallel proposal lifecycle is introduced.

## Promotion flow

```text
recurring project finding
        ↓
learning signals from distinct verified tasks
        ↓
occurrence + distinct-task + freshness + architecture + cooldown gates
        ↓
project_memory(status='candidate')
        ↓
existing Human Decision request
        ↓
human-confirmed approve/reject
        ↓
control-plane memory-promotion-finalize
        ↓
project_memory(status='active' or 'rejected')
```

Automatic behavior may flag/create the candidate only. It cannot activate it.

## Eligibility

Default policy requires:

- minimum occurrences: 3
- minimum distinct verified tasks: 2
- evidence window: 30 days
- promotion cooldown: 7 days
- current source-hash revalidation
- active Architecture Authority baseline match

Ten repetitions from one task are not equivalent to recurrence across distinct
verified tasks.

## Existing memory and context path

Candidates reuse `project_memory` with `status='candidate'`. Existing retrieval
selects only active memory, so a candidate cannot enter future context before
human-governed finalization.

Context retrieval remains `skill`, `memory`, and `finding`. No new lesson source
kind is added.

## Context Authority

Activated promoted memory uses the existing `knowledge_memory` provenance path:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

Human approval authorizes the lifecycle transition only. It does not convert
memory content into Human Request, Governance, or any other instruction authority.

## Human authority

Candidate finalization requires a resolved existing Human Decision with explicit
human confirmation. Approval also revalidates candidate identity, source hashes,
verified-task eligibility, occurrence threshold, and the active architecture
baseline. Reject transitions the candidate to `rejected`.

The `memory-promotion-finalize` command is control-plane only.

## MCP

v0.31.1 adds no MCP tool. The v0.31.0 learning MCP surface remains read-only and
unchanged.

## Failure semantics

Candidate observation/flagging is degraded-safe for the learning subsystem.
Activation is fail-closed on missing human approval, stale source evidence,
eligibility regression, architecture drift, or candidate/link identity mismatch.

## Non-claims

v0.31.1 does not auto-graduate skills, auto-activate policy evolution, mutate
Architecture Authority, grant memory instruction authority, replace human review,
eliminate prompt injection, guarantee semantic correctness, or prove causal
learning effectiveness.
