"""
Path: .agents/agentos/web_control_plane.py
Purpose: Serve the optional v0.28.1 local Web Control Plane as a hardened read-only presentation of the v0.28.0 Command Center read model.

The web plane is deliberately not an AgentOS authority. It never opens the state
database directly, never executes privileged CLI commands, never launches workers,
and never approves architecture or controlled integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
import time
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .command_center import (
    command_center_human_actions,
    command_center_section,
    command_center_snapshot,
)
from .policy import load_policy
from .schema_version import CURRENT_SCHEMA_VERSION

WEB_CONTROL_PLANE_VERSION = 1
SESSION_COOKIE = "agentos_web_session"
MAX_REQUEST_BODY = 4096
_ALLOWED_SECTIONS = {"architecture", "execution", "compliance", "human_actions", "authority"}

_DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "optional": True,
    "web_version": WEB_CONTROL_PLANE_VERSION,
    "database_schema": 61,
    "default_host": "127.0.0.1",
    "default_port": 8765,
    "loopback_only": True,
    "command_center_read_model_only": True,
    "direct_database_access": False,
    "mutation_authority": False,
    "privileged_cli_execution_allowed": False,
    "architecture_approval_authority": False,
    "integration_approval_authority": False,
    "worker_launch_authority": False,
    "model_provider_selection_authority": False,
    "external_assets_allowed": False,
    "cors_allowed": False,
    "websocket_allowed": False,
    "host_header_validation_required": True,
    "same_origin_bootstrap_required": True,
    "one_time_bootstrap_required": True,
    "session_ttl_seconds": 3600,
}


@dataclass(frozen=True)
class WebControlPlaneLaunch:
    """Resolved local Web Control Plane launch metadata.

    Attributes:
        host: Loopback bind address.
        port: Actual bound TCP port.
        origin: Exact local origin accepted by Host/Origin validation.
        launch_url: Browser URL containing the bootstrap token in the fragment only.
    """

    host: str
    port: int
    origin: str
    launch_url: str


def _policy(root: Path) -> dict[str, Any]:
    """Load and fail-closed validate the v0.28.1 Web Control Plane policy."""
    merged = dict(_DEFAULT_POLICY)
    configured = load_policy(root).get("web_control_plane_policy", {})
    if isinstance(configured, dict):
        merged.update(configured)
    if merged.get("enabled") is not True or merged.get("optional") is not True:
        raise PermissionError("web_control_plane_disabled")
    required_true = (
        "loopback_only",
        "command_center_read_model_only",
        "host_header_validation_required",
        "same_origin_bootstrap_required",
        "one_time_bootstrap_required",
    )
    disabled = [key for key in required_true if merged.get(key) is not True]
    if disabled:
        raise RuntimeError(f"web_control_plane_required_invariant_disabled:{disabled}")
    required_false = (
        "direct_database_access",
        "mutation_authority",
        "privileged_cli_execution_allowed",
        "architecture_approval_authority",
        "integration_approval_authority",
        "worker_launch_authority",
        "model_provider_selection_authority",
        "external_assets_allowed",
        "cors_allowed",
        "websocket_allowed",
    )
    poisoned = [key for key in required_false if merged.get(key) is not False]
    if poisoned:
        raise RuntimeError(f"web_control_plane_authority_invariant_violated:{poisoned}")
    if int(merged.get("database_schema", 0)) != CURRENT_SCHEMA_VERSION:
        raise RuntimeError("web_control_plane_schema_mismatch")
    if int(merged.get("web_version", 0)) != WEB_CONTROL_PLANE_VERSION:
        raise RuntimeError("web_control_plane_version_mismatch")
    ttl = int(merged.get("session_ttl_seconds", 0) or 0)
    if ttl < 60 or ttl > 86400:
        raise RuntimeError("web_control_plane_session_ttl_invalid")
    return merged


def _normalize_loopback_host(host: str) -> str:
    """Return a canonical loopback host or fail closed for non-loopback binds."""
    value = str(host or "").strip()
    if value == "localhost":
        return "127.0.0.1"
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("web_control_plane_loopback_ip_required") from exc
    if not address.is_loopback:
        raise ValueError("web_control_plane_non_loopback_bind_forbidden")
    return address.compressed


def _origin(host: str, port: int) -> str:
    """Build the exact HTTP origin for an IPv4/IPv6 loopback listener."""
    rendered = f"[{host}]" if ":" in host else host
    return f"http://{rendered}:{port}"


def _cookie_session(header: str | None) -> str | None:
    """Extract the Web Control Plane session cookie without accepting other auth sources."""
    if not header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def _html(nonce: str) -> str:
    """Return the dependency-free local Command Center web shell."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentOS Web Control Plane</title>
<style nonce="{nonce}">
:root {{ color-scheme: dark; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
body {{ margin:0; background:#0b0e14; color:#e6edf3; }}
header {{ padding:18px 22px; border-bottom:1px solid #273142; position:sticky; top:0; background:#0b0e14; }}
h1 {{ font-size:18px; margin:0 0 4px; }}
small,.muted {{ color:#8b949e; }}
main {{ padding:20px; max-width:1200px; margin:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; }}
.card {{ border:1px solid #273142; border-radius:10px; padding:14px; background:#111722; }}
.card h2 {{ font-size:14px; margin:0 0 10px; color:#9ecbff; }}
pre {{ white-space:pre-wrap; word-break:break-word; font-size:12px; }}
.pass {{ color:#7ee787; }} .warn {{ color:#d29922; }} .block {{ color:#ff7b72; }}
#auth {{ margin:14px 0; }}
</style>
</head>
<body>
<header>
  <h1>AgentOS Optional Local Web Control Plane</h1>
  <small>v{__version__} · schema {CURRENT_SCHEMA_VERSION} · read-only Command Center projection</small>
</header>
<main>
  <div id="auth" class="muted">Authenticating local session…</div>
  <div class="grid">
    <section class="card"><h2>Architecture</h2><pre id="architecture">-</pre></section>
    <section class="card"><h2>Execution</h2><pre id="execution">-</pre></section>
    <section class="card"><h2>Compliance</h2><pre id="compliance">-</pre></section>
    <section class="card"><h2>Human Actions</h2><pre id="actions">-</pre></section>
    <section class="card"><h2>Authority</h2><pre id="authority">-</pre></section>
  </div>
</main>
<script nonce="{nonce}">
const auth = document.getElementById("auth");
function pretty(value) {{ return JSON.stringify(value, null, 2); }}
async function api(path, options={{}}) {{
  const r = await fetch(path, Object.assign({{credentials:"same-origin", cache:"no-store"}}, options));
  if (!r.ok) throw new Error((await r.text()) || ("HTTP " + r.status));
  return await r.json();
}}
async function bootstrap() {{
  const params = new URLSearchParams(location.hash.slice(1));
  const token = params.get("bootstrap");
  if (token) {{
    await api("/api/session", {{
      method:"POST",
      headers:{{"Content-Type":"application/json"}},
      body:JSON.stringify({{bootstrap_token:token}})
    }});
    history.replaceState(null, "", "/");
  }}
}}
async function refresh() {{
  const s = await api("/api/snapshot");
  auth.textContent = "Authenticated · Overall " + String(s.overall_status || "unknown").toUpperCase();
  document.getElementById("architecture").textContent = pretty(s.architecture);
  document.getElementById("execution").textContent = pretty(s.execution);
  document.getElementById("compliance").textContent = pretty(s.compliance);
  document.getElementById("actions").textContent = pretty(s.human_actions);
  document.getElementById("authority").textContent = pretty(s.authority);
}}
let lifecycleBusy = false;
async function runLifecycle() {{
  if (lifecycleBusy) return;
  lifecycleBusy = true;
  try {{
    await bootstrap();
    await refresh();
  }}
  catch (e) {{
    auth.textContent = "Authentication required or snapshot unavailable: " + e.message;
    auth.className = "block";
  }}
  finally {{
    lifecycleBusy = false;
  }}
}}
window.addEventListener("hashchange", () => {{ void runLifecycle(); }});
void runLifecycle();
</script>
</body>
</html>"""


class _AgentOSWebServer(ThreadingHTTPServer):
    """Threaded local-only HTTP server carrying ephemeral in-memory auth state."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, root: Path, policy: dict[str, Any]):
        super().__init__(address, handler)
        self.agentos_root = root
        self.agentos_policy = policy
        self.bootstrap_secret = secrets.token_urlsafe(32)
        self.bootstrap_used = False
        self.sessions: dict[str, float] = {}
        self.origin = _origin(str(self.server_address[0]), int(self.server_address[1]))

    def create_session(self) -> str:
        """Create one bounded in-memory web session; no AgentOS state is mutated."""
        token = secrets.token_urlsafe(32)
        ttl = int(self.agentos_policy["session_ttl_seconds"])
        self.sessions[token] = time.time() + ttl
        return token

    def session_valid(self, token: str | None) -> bool:
        """Return whether an opaque session token exists and has not expired."""
        if not token:
            return False
        expires = self.sessions.get(token)
        if expires is None:
            return False
        if expires <= time.time():
            self.sessions.pop(token, None)
            return False
        return True


class _Handler(BaseHTTPRequestHandler):
    """Hardened same-origin handler for the read-only Web Control Plane."""

    server: _AgentOSWebServer

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging so auth metadata cannot leak into logs."""
        return

    def _security_headers(self, nonce: str | None = None) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        script = f"'nonce-{nonce}'" if nonce else "'none'"
        style = f"'nonce-{nonce}'" if nonce else "'none'"
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; script-src {script}; style-src {style}; connect-src 'self'; "
            "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )

    def _allowed_host(self) -> bool:
        host = str(self.headers.get("Host") or "")
        expected = urlsplit(self.server.origin).netloc
        return hmac.compare_digest(host.lower(), expected.lower())

    def _same_origin(self) -> bool:
        origin = str(self.headers.get("Origin") or "")
        return hmac.compare_digest(origin, self.server.origin)

    def _authenticated(self) -> bool:
        return self.server.session_valid(_cookie_session(self.headers.get("Cookie")))

    def _read_bounded_post_body(self) -> tuple[bytes | None, str | None]:
        """Consume one declared POST body up to the fixed local-control-plane limit.

        The body is consumed before security rejection responses so Windows does not
        reset the TCP connection while unread request bytes remain in the socket.
        The bytes are not parsed until all Host/Origin/route gates permit it.
        """
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            return None, "invalid_request_body_size"
        if length < 0 or length > MAX_REQUEST_BODY:
            self.close_connection = True
            return None, "invalid_request_body_size"
        try:
            return self.rfile.read(length) if length else b"", None
        except OSError:
            self.close_connection = True
            return None, "request_body_read_failed"

    def _json(self, status: int, payload: dict[str, Any], *, cookie: str | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        if cookie:
            ttl = int(self.server.agentos_policy["session_ttl_seconds"])
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}={cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={ttl}",
            )
        self._security_headers()
        self.end_headers()
        self.wfile.write(raw)
        self.wfile.flush()

    def _reject_host(self) -> bool:
        if self._allowed_host():
            return False
        self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_host_header"})
        return True

    def do_OPTIONS(self) -> None:
        if self._reject_host():
            return
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "cors_preflight_not_supported"})

    def do_GET(self) -> None:
        if self._reject_host():
            return
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._json(HTTPStatus.OK, {
                "ok": True,
                "version": __version__,
                "schema": CURRENT_SCHEMA_VERSION,
                "web_version": WEB_CONTROL_PLANE_VERSION,
                "mode": "local_read_only",
                "mutation_authority": False,
            })
            return
        if path == "/":
            nonce = secrets.token_urlsafe(18)
            raw = _html(nonce).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self._security_headers(nonce)
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
            return
        if not path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        if not self._authenticated():
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "web_session_required"})
            return
        try:
            if path == "/api/snapshot":
                self._json(HTTPStatus.OK, command_center_snapshot(self.server.agentos_root))
                return
            if path == "/api/actions":
                self._json(HTTPStatus.OK, command_center_human_actions(self.server.agentos_root))
                return
            if path.startswith("/api/section/"):
                section = path.removeprefix("/api/section/")
                if section not in _ALLOWED_SECTIONS:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_command_center_section"})
                    return
                self._json(HTTPStatus.OK, command_center_section(self.server.agentos_root, section))
                return
        except Exception as exc:
            self._json(HTTPStatus.CONFLICT, {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            })
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if not self._allowed_host():
            # Drain only a bounded declared body before rejecting so Windows does not
            # convert the HTTP rejection into a connection reset for the client.
            self._read_bounded_post_body()
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_host_header"})
            return
        path = urlsplit(self.path).path
        raw_body, body_error = self._read_bounded_post_body()
        if body_error:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": body_error})
            return
        if path != "/api/session":
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {
                "ok": False,
                "error": "web_mutation_surface_forbidden",
            })
            return
        if not self._same_origin():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "same_origin_required"})
            return
        if not raw_body:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_request_body_size"})
            return
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid_json"})
            return
        supplied = str(payload.get("bootstrap_token") or "") if isinstance(payload, dict) else ""
        if self.server.bootstrap_used or not hmac.compare_digest(supplied, self.server.bootstrap_secret):
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "invalid_or_consumed_bootstrap"})
            return
        self.server.bootstrap_used = True
        session = self.server.create_session()
        self._json(HTTPStatus.OK, {
            "ok": True,
            "authenticated": True,
            "mutation_authority": False,
        }, cookie=session)


def create_web_control_plane(
    root: Path | str,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> tuple[_AgentOSWebServer, WebControlPlaneLaunch]:
    """Create but do not start the optional local Web Control Plane.

    Args:
        root: Governed AgentOS project root.
        host: Numeric loopback bind address or ``localhost``.
        port: TCP port, or ``0`` to request an ephemeral OS-assigned port.
    Returns:
        Server plus launch metadata. The bootstrap secret is placed only in the URL
        fragment so it is never transmitted in the initial HTTP request.
    """
    root_path = Path(root).resolve()
    policy = _policy(root_path)
    bind_host = _normalize_loopback_host(host)
    resolved_port = int(port)
    if resolved_port < 0 or resolved_port > 65535:
        raise ValueError("web_control_plane_port_invalid")
    server = _AgentOSWebServer((bind_host, resolved_port), _Handler, root=root_path, policy=policy)
    actual_host = str(server.server_address[0])
    actual_port = int(server.server_address[1])
    origin = _origin(actual_host, actual_port)
    launch = WebControlPlaneLaunch(
        host=actual_host,
        port=actual_port,
        origin=origin,
        launch_url=f"{origin}/#bootstrap={server.bootstrap_secret}",
    )
    return server, launch


def serve_web_control_plane(
    root: Path | str,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> WebControlPlaneLaunch:
    """Run the optional local Web Control Plane in the foreground until interrupted."""
    server, launch = create_web_control_plane(root, host=host, port=port)
    print(json.dumps({
        "ok": True,
        "version": __version__,
        "schema": CURRENT_SCHEMA_VERSION,
        "web_version": WEB_CONTROL_PLANE_VERSION,
        "origin": launch.origin,
        "launch_url": launch.launch_url,
        "loopback_only": True,
        "command_center_read_model_only": True,
        "mutation_authority": False,
        "message": "Open launch_url in a local browser. Ctrl+C stops the server.",
    }, ensure_ascii=False, indent=2))
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return launch
