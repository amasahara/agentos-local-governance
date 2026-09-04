# AgentOS v0.32.0 — Execution Identity & Model Provenance

## Scope

v0.32.0 introduces durable execution identity and provider/model provenance at database schema **65**.

Schema 65 adds `execution_provenance` and `task_outcome_provenance_links`. The existing `task_outcomes` table is deliberately not altered because v0.31.x learning signals hash complete task-outcome rows.

`execution-provenance-register` is privileged control-plane-only. Agents can read privacy-safe provenance with `get/status` but cannot register or rewrite their own model identity.

Supported references are `async_job`, `governed_operation`, and `external_agent_run`. `runtime_bound` means binding to an immutable local execution reference; it is not remote-provider cryptographic attestation.

Every record binds provider/model/agent/runtime identity, current context revision, `context_authority_hash`, `provenance_manifest_hash`, policy revision, and optional active architecture/plan hashes. Provider request IDs are stored only as SHA-256 hashes. Credentials, endpoint URLs, raw prompts, raw responses and raw provider request IDs are not persisted.

New task outcomes may bind `execution_provenance_id`. Canonical task/session/agent/model/policy/context provenance is revalidated and linkage is stored separately.

Learning effectiveness now requires provider/model matching and excludes legacy unprovenanced outcomes from strict matched cohorts without invalidating them. Results remain observational, not causal.

Execution provenance has no instruction authority, does not alter Context Authority, does not select provider/model automatically, and adds no MCP mutation. MCP remains 132 tools.
