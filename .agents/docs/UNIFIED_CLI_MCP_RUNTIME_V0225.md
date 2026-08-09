# v0.22.5 — Unified CLI/MCP & Cross-Platform Runtime

## Objective

Replace the historical version-chained shell/MCP forwarding execution path with one deterministic Python CLI registry and one deterministic Python MCP runtime, without weakening v0.22.4 governance enforcement.

## CLI contract

Top-level launchers:

- `.agents/bin/agentos` — POSIX
- `.agents/bin/agentos.cmd` — Windows

Both invoke `agentos.cli_runtime`.

`cli_runtime` imports all supported CLI modules in-process, builds one command registry, rejects duplicate command names and dispatches directly to the owning module. Current-release special gates (`docs-check`, `release-integrity-check`, `manifest-verify`) also execute in-process.

Privileged extension mutations remain task/session-bound. The runtime exports `AGENTOS_TASK_ID`, `AGENTOS_SESSION_ID`, and `AGENTOS_PROJECT_ROOT` before dispatch; it does not bypass `governed_mutation`.

## MCP contract

Top-level launchers:

- `.agents/bin/agentos-mcp` — POSIX
- `.agents/bin/agentos-mcp.cmd` — Windows

Both invoke `agentos.mcp_runtime`.

The runtime merges:

1. historical core governed proxy tools;
2. flat read-only extension tool registrations;
3. `agentos.mcp_health`.

Extension handlers are registered directly by owning gateway module tool set. No subprocess forwarding occurs on the active MCP path.

Core proxy tools still require bound task/session context plus `AGENTOS_SESSION_TOKEN` and execute through the existing gateway client. Extension database/identity/recovery tools exposed by v0.20-v0.22 remain read-only.

## Fail-closed invariants

- duplicate CLI command → runtime load failure;
- duplicate MCP tool name → runtime load failure;
- missing Windows/POSIX wrapper parity → release-integrity failure;
- top wrapper referencing `agentos.v0*` / `agentos-mcp.v0*` → release-integrity failure;
- unified runtime importing subprocess → release-integrity failure;
- unknown CLI command → exit 2;
- unknown JSON-RPC method → `-32601`;
- extension mutation MCP exposure → policy/test failure.

## Historical compatibility artifacts

Versioned CLI launchers and MCP gateway modules may remain in the repository as historical evidence and compatibility material. They are not referenced by top-level launchers and are not part of the v0.22.5 active execution path.

## Schema

No new persistent business/governance state is required. Database schema remains **41**.
