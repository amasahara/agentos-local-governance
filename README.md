# AgentOS Local Governance

Current release: **v0.22.6 — Secret Resolver & Lineage Key Lifecycle**  
Database schema: **42**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.22.6 extends the v0.22.5 unified in-process CLI/MCP runtime with a trusted secret-resolver registry and a versioned lineage-key lifecycle. It preserves the existing SOURCE/TARGET database safety boundary and the v0.22.4 privileged-mutation enforcement boundary.

## Key guarantees

- Trusted resolver registry only: `env://`, `keychain://`, `vault://`, `secret://` aliases and bounded `file-secret://`.
- Exact provider identity/version/implementation-hash pin plus capability-scoped human approval.
- No governance-config `importlib module:function` resolver loading.
- Resolved credentials remain memory-only and are never exposed through MCP.
- Versioned lineage keyring with `active`, `retired`, and `revoked` states.
- Historical HMAC/token values are not automatically recomputed during migration.
- New identity/lineage tokens use the active key; retired keys remain available for historical lookup/verification.
- Key initialization, rotation, revocation and rekey authorization are privileged CLI operations, not MCP mutation tools.
- Rekey requires governed SOURCE `select_read` re-read of raw identifiers.

See [Release Notes](RELEASE_NOTES.md), [Upgrade from v0.22.5](UPGRADE_FROM_0.22.5.md), and [Secret Resolver & Lineage Key Lifecycle](.agents/docs/SECRET_RESOLVER_LINEAGE_KEY_LIFECYCLE.md).
