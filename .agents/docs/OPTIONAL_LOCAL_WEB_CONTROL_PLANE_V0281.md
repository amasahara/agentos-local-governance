# AgentOS v0.28.1 — Optional Local Web Control Plane

## Purpose

v0.28.1 adds an **optional local Web Control Plane** as the final presentation layer
of the Architecture Authority roadmap.

It consumes the same v0.28.0 Command Center read model:

```text
Architecture / Tasks / Agents / Workspaces / Compliance / Human Actions
                              |
                              v
                   Command Center Snapshot
                     /       |       \
                    /        |        \
                  CLI       MCP      Web UI
```

The Web Control Plane is not a second AgentOS backend and is not an authority.

## Schema

Database schema: **61**. Schema remains unchanged from v0.28.0.

No web-session, dashboard, cache, or UI state is persisted in SQLite.

## Launch

The web plane is explicitly opt-in and foreground-only:

```powershell
.agents\bin\agentos.cmd web-control-plane
```

Default bind:

```text
127.0.0.1:8765
```

An ephemeral port may be requested with `--port 0`.

Non-loopback binds such as `0.0.0.0` are fail-closed.

The command prints a browser launch URL such as:

```text
http://127.0.0.1:8765/#bootstrap=<one-time-secret>
```

The bootstrap secret is placed in the URL fragment. Browser fragments are not sent
in the initial HTTP request.

## Authentication

The static shell may load without authentication, but all Command Center data APIs
require an ephemeral local session.

Flow:

```text
one-time bootstrap secret
        ↓
same-origin POST /api/session
        ↓
HttpOnly + SameSite=Strict session cookie
        ↓
GET /api/snapshot /api/actions /api/section/*
```

Bootstrap tokens are single-use and sessions exist only in server memory.

The browser shell listens for `hashchange`, so pasting a fresh `#bootstrap=...`
launch URL into an already-open local control-plane tab retries bootstrap without
requiring a manual page reload.

Stopping the foreground server with `Ctrl+C` is handled as a normal shutdown:
the listener is closed without emitting an AgentOS Python traceback, and all in-memory
web sessions are destroyed.

## HTTP surface

Read-only:

```text
GET /
GET /healthz
GET /api/snapshot
GET /api/actions
GET /api/section/{architecture|execution|compliance|human_actions|authority}
POST /api/session
```

`POST /api/session` creates only an in-memory HTTP session. It does not mutate AgentOS.

There are no endpoints for:

- task/plan creation or approval;
- architecture review/approval/activation;
- ADR approval;
- worker/process launch;
- model/provider selection;
- capability issuance;
- controlled-integration review/approval/apply;
- Git merge/commit/push;
- direct database mutation.

## Security boundary

The server enforces:

- numeric loopback bind only (`localhost` normalizes to `127.0.0.1`);
- exact Host header validation against the bound origin;
- exact same-origin validation for bootstrap;
- no CORS;
- no WebSocket;
- no external assets;
- `Cache-Control: no-store`;
- CSP with per-response nonce;
- `X-Frame-Options: DENY`;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- `Cross-Origin-Resource-Policy: same-origin`;
- restrictive Permissions Policy;
- bounded bootstrap request body;
- bounded POST bodies are consumed before rejection responses to avoid Windows socket-reset races;
- suppressed default HTTP request logging.

## Authority invariants

```text
direct_database_access                 false
mutation_authority                     false
privileged_cli_execution_allowed       false
architecture_approval_authority        false
integration_approval_authority         false
worker_launch_authority                false
model_provider_selection_authority     false
external_assets_allowed                false
cors_allowed                           false
websocket_allowed                      false
```

The web UI can show a pending human action, but it cannot execute that action.

Human/operator authority continues through the existing governed CLI/runtime boundary.

## Distribution

v0.28.1 keeps the **Latest Full Release / no updater script** distribution model.

Development patch helpers are not final-release artifacts and must not be committed.
