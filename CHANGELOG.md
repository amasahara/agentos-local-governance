# Changelog

## 0.22.6 — Secret Resolver & Lineage Key Lifecycle

- Added a static trusted secret-resolver registry for `env://`, `keychain://`, `vault://`, bounded `file-secret://`, and `secret://` aliases.
- Added provider identity/version/implementation-hash pins, capability-scoped operator approval, fail-closed dependency/provider handling, and memory-only credential resolution.
- Removed production callback-injection authority and forbade governance-config dynamic `importlib module:function` resolver loading.
- Routed read-only extraction, Controlled Target Insert, and reconciliation through the shared trusted resolver boundary.
- Added schema 42 with resolver approval/evidence tables, versioned lineage-key metadata, rotation/rekey plans, and `key_id` provenance on identity/lineage records.
- Replaced the single-key authority with `active/retired/revoked` key lifecycle; new tokens use active key while retired keys remain lookup/verification capable.
- Migrated legacy lineage key bytes without historical re-HMAC; initialization is privileged and read-only inspection cannot initialize key material.
- Added restart-safe recovery for a single crash-left key file and fail-closed key-material path validation.
- Added human-reviewed/approved rotation with signed domain/audit mirroring and governed SOURCE-reread rekey authorization.
- Pinned reconciliation to the identity-resolution `key_id` so later rotation does not invalidate historical reconciliation.
- Added five read-only MCP inspection tools; no secret/key mutation or credential authority is exposed.
- Expanded focused regression to 17 tests covering provider pins/capabilities, env/file/keychain/Vault contracts, aliases, leakage, callback denial, privileged-boundary denial, key migration/rotation/revocation/restart recovery, path tamper, and CLI/MCP catalog safety.
