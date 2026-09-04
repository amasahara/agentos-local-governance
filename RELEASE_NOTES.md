# AgentOS Local Governance v0.32.0 — Execution Identity & Model Provenance

Database schema: **65**

v0.32.0 adds durable, privacy-safe execution identity and provider/model provenance. This is a provenance release, not a model-routing release.

## Schema 65

Schema 65 adds `execution_provenance` and `task_outcome_provenance_links`. The existing `task_outcomes` table is deliberately not altered because v0.31.x learning signals hash complete task-outcome rows; changing the historical shape could make valid evidence appear stale.

## Privileged registration

`execution-provenance-register` is control-plane-only. Normal agents receive read-only `execution-provenance-get` and `execution-provenance-status`.

Supported reference classes are `async_job`, `governed_operation`, and `external_agent_run`. `runtime_bound` means a declaration is bound to an immutable local execution reference. It does not claim remote-provider cryptographic attestation.

## Privacy-safe identity

Persisted evidence can include bounded provider/model/model-revision/deployment/agent/runtime identifiers and endpoint class. Provider request IDs are stored only as SHA-256 hashes.

v0.32.0 does not persist API keys, credentials, authorization headers, endpoint URLs, raw prompts, raw responses, or raw provider request IDs.

## Context and outcome binding

Every provenance record requires a current Context Authority evaluation and binds `context_revision`, `context_authority_hash`, `provenance_manifest_hash`, policy revision, and available architecture/plan hashes.

New task outcomes may bind `execution_provenance_id`. AgentOS rejects task/session/agent/model/policy/context metadata that conflicts with canonical provenance and writes the outcome link in the separate schema-65 table.

Legacy outcomes remain valid.

## Learning effectiveness

`provider_model_matching_required = true`.

Strict comparative cohorts add provider/model/model revision and verification class to the v0.31.3 cohort dimensions. Legacy outcomes without schema-65 provenance are excluded from strict matched cohorts rather than invalidated. Analysis remains observational, not causal.

## Authority and model selection

`context_authority_affected = false`, `instruction_authority = false`, and `auto_model_provider_select = false`.

Provider/model metadata cannot become Human Request, Governance Authority, Architecture Authority, policy authority, or skill authority.

## Expected surfaces

```text
CLI commands          = 367
agent commands        = 269
privileged commands   = 100
MCP tools             = 132
```

No v0.32.0 MCP mutation module is added.

## Predecessor contracts preserved

- v0.31.3 — Learning Effectiveness & Drift
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

v0.32.0 does not claim remote-provider cryptographic attestation, causal model effectiveness, autonomous provider/model selection, semantic correctness, prompt injection elimination, replacement of human review, or general host containment.
