# v0.22.6 Guide — Secret Resolver & Lineage Key Lifecycle

1. Upgrade only from exact `VERSION=0.22.5`.
2. Run `tools/apply_v0226.py` and `agentos secret-lineage-db-sync` to reach schema 42.
3. Inspect `secret-provider-catalog`; approve only required capabilities: `db.source.select`, `db.target.controlled_insert`, `db.target.reconciliation_select`.
4. Never place raw credentials in `governance.json`; `secret://alias` may only target a trusted resolver URI.
5. Inspect `lineage-keyring-status`. If not initialized, run privileged `lineage-keyring-initialize` inside a valid task/session. Read-only MCP inspection does not create or migrate key material.
6. Legacy `.agents/state/identity_lineage.key` bytes are moved unchanged into the keyring; historical fingerprints/tokens are not recomputed.
7. Rotation is create plan → review → approve → execute. Do not expose key mutation over MCP.
8. Rekey requires governed SOURCE `select_read` and a raw-identifier re-read; never re-HMAC an old hash/token.
9. Run focused regression, registry collision tests, leakage tests, manifest/checksum verification, and clean-upgrade validation before production.
