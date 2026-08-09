# v0.22.6 — Secret Resolver & Lineage Key Lifecycle

## 1. Trusted resolver boundary

Production credential resolution is owned by `agentos.secret_lineage` and a static shipped registry. `governance.json` may define `secret://alias` → trusted URI mappings, but it may not load code by `importlib`, `module:function`, executable path, or arbitrary plugin reference.

Built-ins:

- `env://NAME` — JSON object from one environment variable.
- `keychain://service/account` — JSON object through the optional OS `keyring` provider.
- `vault://mount/path#field` — HashiCorp Vault KV v2 through optional `hvac`; Vault bootstrap credentials remain process environment/memory only.
- `file-secret://relative.json` — owner-only JSON file under `.agents/state/secrets/`, path-contained and permission checked.
- `secret://alias` — one governance alias resolving to one of the trusted schemes above.

Every provider is pinned by `provider_id`, provider version, and SHA-256 of the shipped implementation. The exact pin must be human-approved for the exact capability. Production capabilities are allowlisted as `db.source.select`, `db.target.controlled_insert`, and `db.target.reconciliation_select`.

`resolve_runtime_secret()` rejects callback injection when the root is a governed AgentOS project. The callback parameter remains only to preserve non-governed v0.22.5 unit/integration adapter compatibility.

Resolved objects are returned to the immediate in-process DB adapter only. Resolver events contain provider/ref hashes and counts, never credential values.

## 2. Keyring migration and lifecycle

Schema 42 adds:

- `secret_resolver_approvals`
- `secret_resolver_events`
- `lineage_keys`
- `lineage_key_rotation_plans`
- `lineage_rekey_plans`
- `key_id` on identity-resolution state and source/target key provenance on `target_record_lineage`

Keyring material lives in `.agents/state/lineage-keys/` and is never shipped in release artifacts.

Keyring initialization is privileged (`identity.lineage.key.initialize`). Read-only `keyring_status()` and MCP inspection do not initialize the keyring. During initialization, an existing `.agents/state/identity_lineage.key` is moved with identical bytes into the versioned keyring. Existing HMAC/token columns are untouched; only `key_id` metadata is backfilled.

Exactly one key may be active. New tokens/fingerprints use it. Active + retired keys are used for deterministic lookup of current SOURCE raw identifiers so historical records remain discoverable. Revoked keys are excluded from lookup and cannot be loaded by the lifecycle API.

## 3. Rotation and signed governance

Rotation is:

```text
create immutable plan
→ human review
→ human approval
→ governed execution
→ predecessor retired
→ fresh active key
→ signed domain/audit evidence
```

The privileged CLI commands remain under the existing task/session/capability/baseline-drift/one-time-token/internal-hash-chain/Ed25519 external audit boundary. They are absent from the MCP mutation catalog.

## 4. Rekey

AgentOS never computes a replacement HMAC from an existing HMAC/token. A rekey plan records only key IDs, SOURCE connection ID, hashes, approval metadata, and status. Before rekey execution can proceed, AgentOS re-checks `authorize_operation(..., "select_read")` for a registered SOURCE. Downstream rekey processing must read the raw identifier again under that governed SOURCE boundary.

## 5. MCP boundary

Read-only MCP operations:

- `agentos.secret_provider_catalog_get`
- `agentos.secret_provider_approvals_get`
- `agentos.lineage_keyring_get`
- `agentos.lineage_rotation_plan_get`
- `agentos.lineage_rekey_plan_get`

Not exposed: credential resolution/results, provider approval/revocation, keyring initialization, rotation/revocation, rekey authorization, identity decisions, TARGET mutation, recovery mutation.
