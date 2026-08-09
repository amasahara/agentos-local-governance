# AgentOS Local Governance v0.23.0 — Release Notes

## Requirement-Preserving Context Compression

v0.23.0 introduces an LLM Transport Compiler derived from the canonical Context Pack. The new transport is split into a **LOSSLESS Control Plane** and a **COMPRESSIBLE Evidence Plane**.

### Protected Control Plane

The original user request is stored verbatim with SHA-256. Stable Requirement Ledger entries are extractive exact spans classified as objective, constraint, prohibition, deliverable, or acceptance criterion. AGENTS authority is verbatim. Approved scope is lossless. Active plan JSON and plan hash are pinned. Protected governance authority is deterministically projected from the current policy and source/projection hashes are pinned.

A pack is not READY unless the preservation gate verifies 100% requirement preservation, request/scope/plan/authority hashes, canonical source freshness, and transport integrity. If protected content exceeds the model input budget, compilation fails closed.

### Evidence compression

The fixed ladder is exact deduplication → metadata normalization → structural projection → requirement-aware ranking → omission handles → fail-closed. Python uses exact symbol/dependency windows; JSON uses deterministic key projection; repetitive logs may be structurally aggregated. No generative LLM summarization, gzip/base64 semantic compression, or word-level deletion is used.

### Token budget

Budget is `context_capacity - reserved_output - system/tool overhead - safety margin`; Control Plane is allocated first. Tokenizer abstraction prefers an exact local tokenizer if available and otherwise uses the offline multilingual heuristic fallback.

### Schema 44

Adds `context_transport_packs`, `context_requirement_ledger`, `context_expansion_events`, and `context_transport_evaluations`. Migration remains centralized through `agentos.db.connect()` with `foreign_keys=ON`. Clean/fresh `connect(immediate=True)` now commits the migration boundary before `BEGIN IMMEDIATE`, fixing a latent first-write transaction issue.

### MCP boundary

Read-only tools: `agentos.context_transport_get`, `agentos.context_transport_explain`, `agentos.context_expand`, `agentos.context_requirement_get`, `agentos.context_token_report`. Compile/evaluate/mutate is not exposed via MCP. MCP expansion is strictly read-only and does not persist an expansion event.

### Evaluation

Shadow/evaluation metrics include raw/transport tokens, compression ratio, protected/preserved requirements, preservation rate, context misses, expansion requests, task/test success, rework, and tool-call count. Initial optimization target: stable 2–4x compression rather than extreme compression.
