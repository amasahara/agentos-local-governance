# AgentOS v0.22.6 Release Notes

**Secret Resolver & Lineage Key Lifecycle** — database schema **42**.

## Security and privacy changes

- Adds a static trusted resolver registry for `env://`, `keychain://`, `vault://`, `secret://` aliases and bounded `file-secret://`.
- Pins provider identity, provider version and implementation SHA-256, with capability-scoped human approval and fail-closed provider/dependency handling.
- Forbids governance-config dynamic `importlib module:function` resolver loading and rejects production callback injection.
- Keeps resolved credentials in operation memory only; no raw credential value is written to AgentOS SQLite, audit, MCP, context/LLM or caches.
- Routes SOURCE extraction, Controlled Target Insert and reconciliation through the same trusted resolver boundary.

## Lineage key lifecycle

- Replaces the single lineage-key authority with a versioned local keyring using `key_id` and `active/retired/revoked` states.
- Adds created/activated/retired/revoked timestamps, predecessor and rotation-plan provenance.
- Migrates an existing `.agents/state/identity_lineage.key` using identical bytes and backfills only `key_id`; historical HMAC/token columns are not automatically recomputed.
- New tokens use the active key; active + retired keys are available for deterministic historical lookup; revoked keys are unavailable.
- Keyring status is read-only. Initialization, provider approval/revocation, key rotation/revocation and SOURCE-reread rekey authorization are privileged mutations under the existing v0.22.4 governance boundary.
- Adds restart-safe recovery for one crash-left key material and fail-closed key-material path validation.
- Rekey is designed around a governed SOURCE `select_read` re-read of the raw identifier; AgentOS does not derive a new HMAC from a historical HMAC.

## Runtime and MCP

Unified in-process CLI/MCP routing from v0.22.5 is preserved. The release adds five metadata-only MCP tools for provider/keyring/plan inspection. MCP does not expose credential resolution/results, approval, key mutation, identity decisions, TARGET mutation or recovery mutation.

## Verification performed

Focused v0.22.6 regression: **17 passed**. Representative clean upgrade verified schema **41 → 42**, `foreign_keys=ON`, exact predecessor refusal, **210/210 unique CLI commands**, **57/57 unique MCP tools**, unknown CLI failure and MCP JSON-RPC `-32601`, target manifest rebuild, Python compilation, secret leakage negatives and key lifecycle negatives.

The exact full GitHub tree could not be cloned/materialized by the build shell, so the full historical suite is **not claimed as passed**. Live OS keychain, live Vault, native Windows `cmd.exe`, and full production signed-audit integration for the new mutations were not available; see `VALIDATION_REPORT.json` for the precise verification boundary.
