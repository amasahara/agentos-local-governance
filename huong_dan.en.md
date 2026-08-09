# AgentOS v0.22.5 Developer Guide

English

After upgrade, run `release-integrity-check`, `db-status`, `docs-check`, `instruction-check`, the complete pytest suite, and `manifest-verify`. Do not use production TARGET writes unless the integrity gate passes.

Database schema: **41**


## v0.22.5 — Unified CLI/MCP

Use `.agents/bin/agentos` or `.agents\bin\agentos.cmd`; both enter `agentos.cli_runtime`. MCP uses `agentos.mcp_runtime`. Verify with `agentos runtime-health`. Do not use the historical `agentos.v02xx` chain as the current runtime path.
