# AgentOS v0.31.3 — Learning Effectiveness & Drift

## Scope

v0.31.3 measures comparative/observational effectiveness and detects knowledge
drift without creating a second learning lifecycle and without granting automated
authority.

The database schema remains **64**. Existing `knowledge_usage`, `task_outcomes`,
`learning_signals`, `skill_evaluation_runs`, Skill Contract v2, Architecture
Baselines, and Human Decision state are sufficient for this node.

## Comparative effectiveness

Treatment means tasks where the exact knowledge artifact/version was actually
included in context through `knowledge_usage`.

Control means outcome-bearing tasks in the same deterministic cohort where that
artifact was not included.

Matching dimensions are:

```text
task_category
policy_revision
retrieval_backend
architecture_baseline_hash
```

Provider/model provenance remains incomplete before v0.32.0, so results are
called comparative/observational rather than causal.

The default gate uses:

```text
window_days              = 90
minimum treatment tasks  = 5
minimum control tasks    = 5
minimum distinct tasks   = 5
minimum effect size      = 0.10
significance alpha       = 0.05
small-sample warning     < 30 per cohort
```

Reported states:

```text
insufficient_evidence
possibly_ineffective
comparatively_better
no_clear_difference
```

A p-value or confidence interval never changes artifact lifecycle automatically.

## Drift states

```text
current
review_required_architecture_change
stale
scope_unresolved
```

A changed Architecture Baseline is not itself proof that knowledge is stale.

For Skill Contract v2, required Architecture sections are compared section by
section. If only unrelated sections changed, the skill remains `current`. A
required section becoming unavailable/not-applicable can be `stale`; a changed
required section that cannot be proven incompatible requires human review.

For promoted memory/finding evidence without section-level applicability binding,
a changed baseline produces `review_required_architecture_change`, not `stale`.

## Human review

Automated evaluation may recommend review, but it cannot deactivate, supersede,
revise, graduate, activate policy, or mutate Architecture Authority.

`learning-effectiveness-review-request` requires the exact current assessment
hash and opens the existing Human Decision lifecycle with options:

```text
retain
revise
supersede
deactivate
```

The Human Decision resolution is audited through the existing privileged
`decision-resolve` path. Resolution does not itself silently mutate the knowledge
artifact.

## Authority

Learning/effectiveness evidence remains:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

No MCP mutation is added; the MCP catalog remains 132 tools.

## Non-claims

v0.31.3 does not claim causal effectiveness, autonomous deactivation, automatic
knowledge correction, semantic correctness, provider/model-controlled comparison,
prompt-injection elimination, human-review replacement, or general host isolation.
