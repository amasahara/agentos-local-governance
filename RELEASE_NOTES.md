# AgentOS Local Governance v0.22.4 — Release Notes

## Unified Governance Enforcement & Signed Audit

- Added schema 41 `governed_operations`.
- Added `governed_operation_id` and `external_event_hash` to six database-domain event tables.
- Added task/session-bound `governed_mutation` enforcement for privileged database mutations.
- Reused the core `guard_tool` / `complete_tool` single-use token lifecycle.
- Added Ed25519 signed request, domain-event, denial, and completion evidence.
- Blocked mutations on unapproved tasks, wrong session ownership, incomplete workflow approval, uninitialized baseline, governance drift, unapproved sensitive override, and signed-audit failure.
- Replaced six module-local SQLite connection factories with the central hardened database connection through a lazy migration registry.
- Added non-overridable policy-poisoning checks for SOURCE/TARGET/identity/recovery safety flags.
- Added CLI prefix context: `--task-id` and `--session-id`.
- MCP mutation exposure remains disabled.

v0.22.5 remains responsible for flattening version-chained CLI/MCP routing and completing cross-platform runtime parity.
