# AgentOS Local Governance v0.22.6

**Node:** Secret Resolver & Lineage Key Lifecycle  
**Schema:** 42  
**Baseline:** v0.22.5 — Unified CLI/MCP & Cross-Platform Runtime

## Production secret resolver

The production DB pipeline now uses one trusted resolver registry instead of a standalone `env://` default. Supported references are `env://`, `keychain://`, `vault://`, `secret://` aliases, and bounded `file-secret://` under `.agents/state/secrets/`.

Every shipped provider has a stable provider identity, version, and implementation SHA-256 pin. A human operator must approve the exact provider pin for the exact runtime capability. Missing/untrusted providers, changed pins, unapproved capabilities, or unavailable optional dependencies fail closed.

Governance configuration may map aliases to trusted URIs but may not name arbitrary `importlib`, `module:function`, executable, or plugin resolver code. Legacy callback injection is compatibility-only for non-governed tests/library roots and is rejected on production AgentOS roots.

Resolved credentials exist only in operation memory. Raw credential values are not persisted to AgentOS SQLite, audit, MCP, context/LLM, or caches.

## Versioned lineage keyring

The single `identity_lineage.key` model is replaced by a versioned local keyring with `key_id`, `active/retired/revoked` lifecycle states, timestamps, predecessor metadata, and rotation-plan provenance.

Keyring initialization is a privileged mutation and is never triggered by read-only MCP status inspection. A legacy key is moved with identical bytes into the keyring and historical rows are only backfilled with `key_id`; historical HMACs are not recomputed.

New tokens use the active key. Identity lookup evaluates active plus retired keys so old records remain resolvable. Revoked keys are excluded.

Rotation requires immutable plan → human review → human approval → governed execution → signed audit. Rekey never derives a new HMAC from an old HMAC; it requires a governed SOURCE `select_read` re-read of the raw identifier.

## Preserved invariants

- Continuous migrations schema 1 → 42 through `agentos.db.connect()` with `foreign_keys=ON`.
- Unified CLI/MCP remains in-process with no active version/subprocess forwarding.
- Privileged mutations remain inside task/session/capability/baseline-drift/one-time-token/hash-chain/Ed25519 signed-audit enforcement.
- MCP exposes no credential resolution, approval, identity decision, key mutation, TARGET mutation, or recovery mutation.
- SOURCE remains read-only; TARGET writes remain Controlled Target Insert only.
