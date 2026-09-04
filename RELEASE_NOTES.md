# AgentOS Local Governance v0.31.3 — Learning Effectiveness & Drift

Database schema: **64**

v0.31.3 measures comparative/observational effectiveness of actually-used
project knowledge and detects architecture/scope drift without creating a new
learning lifecycle or granting automated lifecycle authority.

No migration 65 is introduced. Existing schema-64 `knowledge_usage` records
actual context inclusion, while existing task outcomes, learning signals, Skill
Contract v2, Architecture Baselines, and Human Decision state provide the
evidence needed for this node.

## Comparative effectiveness

Treatment tasks are tasks where the exact knowledge artifact/version was
actually included in context.

Control tasks are deterministic non-inclusion tasks matched on available:

```text
task_category
policy_revision
retrieval_backend
architecture_baseline_hash
```

Results report success rates, Wilson confidence intervals, effect size, z-test
and p-value where valid, plus small-sample warnings.

Possible verdicts are:

```text
insufficient_evidence
possibly_ineffective
comparatively_better
no_clear_difference
```

The result is explicitly observational, not causal. Provider/model provenance is
not treated as complete before v0.32.0.

## Drift

Drift states are:

```text
current
review_required_architecture_change
stale
scope_unresolved
```

An Architecture Baseline change alone never automatically makes knowledge stale.

Skill Contract v2 can use `required_architecture_sections` and declared scopes to
distinguish unrelated section changes from relevant review requirements. Memory
and finding evidence without precise section binding receive a review warning
rather than an unsupported stale verdict when their pinned baseline changes.

## Human review only

Automated results cannot deactivate, supersede, revise, graduate, activate
policy, or mutate Architecture Authority.

An explicit `learning-effectiveness-review-request` binds the current assessment
hash into the existing Human Decision lifecycle. Existing privileged
`decision-resolve` remains the review-resolution authority path.

Review options are:

```text
retain
revise
supersede
deactivate
```

Resolution is audited but does not silently mutate the reviewed artifact.

## Authority and MCP

Effectiveness/drift evidence remains:

```text
trust_class           = project_evidence
authority_class       = none
instruction_authority = false
```

v0.31.3 adds no MCP tool. MCP remains 132 tools and governed-learning MCP remains
read-only.

Expected CLI surface:

```text
CLI commands          = 364
agent commands        = 267
privileged commands   = 99
MCP tools             = 132
```

## Predecessor contracts preserved

v0.31.3 preserves:
- v0.31.2 — Closed-Loop Skill & Policy Improvement
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

These are bounded predecessor attestations and not claims of general host
filesystem isolation.

This release does not claim causal learning effectiveness, autonomous knowledge
correction/deactivation, semantic correctness, prompt injection elimination,
human-review replacement, or general host containment.

Next node: **v0.32.0 — Execution Identity & Model Provenance**.
