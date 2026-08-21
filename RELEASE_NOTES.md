# AgentOS Local Governance v0.28.1 — Optional Local Web Control Plane

v0.28.1 completes the Architecture Authority roadmap with an **optional local Web Control Plane** built directly on the v0.28.0 Command Center read model.

The web plane is presentation only. It does not become a second governance backend and does not gain architecture, integration, worker-launch, model/provider, or database mutation authority.

## Core architecture

```text
Architecture / Tasks / Agents / Workspaces / Compliance / Human Actions
                              |
                              v
                   Command Center Snapshot v1
                   /        |         \
                 CLI       MCP      Web UI
```

All three surfaces consume the same AgentOS core/read model.

## Schema

Database schema remains **61**.

No web-session or dashboard state is persisted in SQLite.

## Optional local server

New CLI command:

```text
web-control-plane
```

Default:

```text
host: 127.0.0.1
port: 8765
foreground: true
optional: true
```

Expected unified CLI count: **335 → 336**.

MCP remains **123 tools**. No v0.28.1 MCP mutation surface is added.

## Authentication and local hardening

- numeric loopback bind only;
- `localhost` normalizes to `127.0.0.1`;
- non-loopback binds fail closed;
- exact Host header validation;
- same-origin bootstrap;
- one-time bootstrap secret in URL fragment;
- ephemeral in-memory session;
- HttpOnly + SameSite=Strict cookie;
- no CORS;
- no WebSocket;
- no external JS/CSS assets;
- CSP with per-response nonce;
- `Cache-Control: no-store`;
- frame embedding denied;
- MIME sniffing disabled;
- referrer disabled;
- restrictive Permissions Policy;
- request logging suppressed.

## HTTP surface

Read-only AgentOS data:

```text
GET /
GET /healthz
GET /api/snapshot
GET /api/actions
GET /api/section/{section}
```

The only POST route is:

```text
POST /api/session
```

It creates an ephemeral HTTP session in server memory only.

No endpoint exists for task/plan creation, architecture approval, ADR approval,
worker/process launch, capability issuance, model/provider selection, integration
approval/apply, Git merge/commit/push, or direct database mutation.

## Authority invariants

```text
command_center_read_model_only          true
direct_database_access                  false
mutation_authority                      false
privileged_cli_execution_allowed        false
architecture_approval_authority         false
integration_approval_authority          false
worker_launch_authority                 false
model_provider_selection_authority      false
external_assets_allowed                 false
cors_allowed                            false
websocket_allowed                       false
```

Human/operator actions shown in the browser remain informational. Execution stays on
the existing governed AgentOS CLI/runtime boundary.

## Final Validation

v0.28.1 đã hoàn tất đầy đủ focused validation, full repository regression,
runtime smoke tests và release gates.

### Web Control Plane Focused Tests

- 16 passed
- 0 failed

### Full AgentOS Regression

- 565 passed
- 1 skipped
- 0 failed

Expected Windows platform skip:

.agents/tests/test_secret_lineage_v0226.py:67

POSIX chmod mode-bit enforcement is not a Windows security primitive.

Đây là expected platform skip, không phải regression.

### Release Gates

- docs-check: PASS
- release-integrity-check: PASS
- runtime-health: PASS
- Command Center: PASS
- Web Control Plane: PASS
- Manifest verification: PASS
- Release validation: PASS
- git diff --check: PASS

### Final Runtime Identity

- Version: 0.28.1
- Schema: 61
- CLI commands: 336
- MCP tools: 123
- Manifest files: 300

### Web Control Plane Runtime Validation

Browser authentication flow đã được xác minh:

unauthenticated request
→ 401 web_session_required
→ one-time same-origin bootstrap
→ ephemeral authenticated browser session
→ Command Center Snapshot
→ Overall PASS

Non-loopback binding tiếp tục fail-closed:

--host 0.0.0.0
→ web_control_plane_non_loopback_bind_forbidden

Web Control Plane tiếp tục giữ các authority invariants:

- command_center_read_model_only: true
- database_read_only: true
- mutation_authority: false
- architecture_approval_authority: false
- integration_approval_authority: false
- worker_launch_authority: false
- model_provider_selection_authority: false
- mcp_mutation_allowed: false

### Hardening Completed During Release Validation

Các vấn đề phát hiện trong quá trình validation đã được sửa trước khi khóa release:

- Windows POST rejection path được harden để tránh socket reset khi request body vẫn còn unread.
- Cross-origin bootstrap tiếp tục trả 403 same_origin_required.
- POST mutation routes tiếp tục fail với 405 web_mutation_surface_forbidden.
- Browser shell hỗ trợ hashchange, cho phép fresh #bootstrap=... hoạt động ngay cả khi được paste vào Web Control Plane tab đang mở.
- Bootstrap token vẫn one-time và same-origin.
- Browser session vẫn ephemeral, HttpOnly và SameSite=Strict.
- Ctrl+C được xử lý như graceful foreground shutdown; AgentOS không còn phát Python KeyboardInterrupt traceback.
- Không có database schema migration mới.
- Không bổ sung MCP mutation surface.
- Không tạo authority stack thứ hai cho Web UI.
