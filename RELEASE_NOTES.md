# AgentOS Local Governance v0.28.3 — Privileged Control Plane Separation

v0.28.3 separates normal agent execution from privileged human/operator authority.

## Release identity

- AgentOS version: **0.28.3**
- Database schema: **61**
- MCP privileged mutation authority: **none**
- Web mutation authority: **none**

## Main changes

- Added dedicated `agentos-admin` launchers for Windows and POSIX.
- Removed privileged command dispatch from the normal `agentos` execution plane.
- Added explicit agent-plane and privileged-plane registries.
- Added fail-closed command-surface separation.
- Added argument-level dual-plane enforcement for `project-adopt` and `architecture-init`.
- `project-adopt` remains read-only through `agentos`; `--apply` requires `agentos-admin`.
- `architecture-init --overwrite` requires `agentos-admin`.
- Human/operator authority commands are isolated from the agent execution plane.
- Installed project payloads include `agentos-admin` and `agentos-admin.cmd`.
- `commands-list` exposes only the normal agent execution surface.

## Preserved governance

Existing governed mutation enforcement remains authoritative:

task/session context → approval → owner session → workflow approval → baseline/drift checks → one-time execution token → signed audit.

MCP remains without privileged mutation authority.

The optional Web Control Plane remains read-only and cannot execute privileged CLI operations.

## Deliberately deferred

v0.28.3 establishes structural authority separation only.

It does not claim hard anti-bypass, direct-module-call prevention, tool exclusivity, or enforcement attestation.

Those capabilities are reserved for **v0.28.4 — Tool Exclusivity & Enforcement Attestation**.
