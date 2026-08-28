"""
Path: .agents/tests/test_optional_web_control_plane_v0281.py
Purpose: Verify that v0.28.1 provides a hardened local-only Web Control Plane without creating AgentOS mutation authority.
"""
from __future__ import annotations

from http.client import HTTPConnection
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit

import pytest

from agentos import web_control_plane as wcp


_POLICY = {
    "web_control_plane_policy": {
        "enabled": True,
        "optional": True,
        "web_version": 1,
        "database_schema": 62,
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
}

_SNAPSHOT = {
    "ok": True,
    "version": "0.28.1",
    "schema": 61,
    "overall_status": "pass",
    "architecture": {"active_baseline": None},
    "execution": {"workers_total": 0},
    "compliance": {"overall": "not_evaluable"},
    "human_actions": {"count": 0, "blocking_count": 0, "items": []},
    "authority": {
        "projection_only": True,
        "mutation_authority": False,
        "physical_workspace_paths_exposed": False,
    },
}


@pytest.fixture()
def running_web(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(wcp, "load_policy", lambda _root: _POLICY)
    monkeypatch.setattr(wcp, "command_center_snapshot", lambda _root: dict(_SNAPSHOT))
    monkeypatch.setattr(
        wcp,
        "command_center_human_actions",
        lambda _root: {"ok": True, "count": 0, "blocking_count": 0, "items": [], "mutation_authority": False},
    )
    monkeypatch.setattr(
        wcp,
        "command_center_section",
        lambda _root, section: {"ok": True, "section": section, "data": _SNAPSHOT[section], "mutation_authority": False},
    )
    server, launch = wcp.create_web_control_plane(root, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield root, server, launch
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _conn(launch: wcp.WebControlPlaneLaunch) -> HTTPConnection:
    return HTTPConnection(launch.host, launch.port, timeout=3)


def _request(
    launch: wcp.WebControlPlaneLaunch,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
):
    c = _conn(launch)
    merged = {"Host": urlsplit(launch.origin).netloc}
    if headers:
        merged.update(headers)
    c.request(method, path, body=body, headers=merged)
    response = c.getresponse()
    raw = response.read()
    result = (response.status, dict(response.getheaders()), raw)
    c.close()
    return result


def _bootstrap(server, launch):
    body = json.dumps({"bootstrap_token": server.bootstrap_secret}).encode("utf-8")
    status, headers, raw = _request(
        launch,
        "POST",
        "/api/session",
        body=body,
        headers={
            "Origin": launch.origin,
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    assert status == 200, raw
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    return cookie


def test_non_loopback_bind_is_forbidden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(wcp, "load_policy", lambda _root: _POLICY)
    with pytest.raises(ValueError, match="non_loopback_bind_forbidden"):
        wcp.create_web_control_plane(tmp_path, host="0.0.0.0", port=0)


def test_localhost_is_normalized_to_loopback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(wcp, "load_policy", lambda _root: _POLICY)
    server, launch = wcp.create_web_control_plane(tmp_path, host="localhost", port=0)
    try:
        assert launch.host == "127.0.0.1"
        assert launch.origin.startswith("http://127.0.0.1:")
    finally:
        server.server_close()


def test_policy_poisoning_mutation_authority_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    poisoned = json.loads(json.dumps(_POLICY))
    poisoned["web_control_plane_policy"]["mutation_authority"] = True
    monkeypatch.setattr(wcp, "load_policy", lambda _root: poisoned)
    with pytest.raises(RuntimeError, match="authority_invariant_violated"):
        wcp.create_web_control_plane(tmp_path, port=0)


def test_root_is_static_shell_and_bootstrap_secret_is_fragment_only(running_web):
    _root, server, launch = running_web
    status, headers, raw = _request(launch, "GET", "/")
    text = raw.decode("utf-8")
    assert status == 200
    assert "AgentOS Optional Local Web Control Plane" in text
    assert server.bootstrap_secret not in text
    assert "#bootstrap=" in launch.launch_url
    assert server.bootstrap_secret in launch.launch_url
    assert "Cache-Control" in headers


def test_fragment_navigation_retries_bootstrap_without_reload(running_web):
    _root, _server, launch = running_web
    status, _headers, raw = _request(launch, "GET", "/")
    text = raw.decode("utf-8")
    assert status == 200
    assert 'addEventListener("hashchange"' in text
    assert "runLifecycle" in text
    assert 'history.replaceState(null, "", "/")' in text


def test_security_headers_are_present(running_web):
    _root, _server, launch = running_web
    status, headers, _raw = _request(launch, "GET", "/")
    assert status == 200
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    csp = headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "connect-src 'self'" in csp


def test_api_requires_authenticated_session(running_web):
    _root, _server, launch = running_web
    status, _headers, raw = _request(launch, "GET", "/api/snapshot")
    assert status == 401
    assert json.loads(raw)["error"] == "web_session_required"


def test_bootstrap_requires_exact_same_origin(running_web):
    _root, server, launch = running_web
    body = json.dumps({"bootstrap_token": server.bootstrap_secret}).encode("utf-8")
    # Repeat the rejected POST so Windows socket-reset races are exercised rather
    # than depending on one timing-sensitive request. The bootstrap must remain unused.
    for _ in range(12):
        status, _headers, raw = _request(
            launch,
            "POST",
            "/api/session",
            body=body,
            headers={
                "Origin": "http://evil.example",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        assert status == 403
        assert json.loads(raw)["error"] == "same_origin_required"
        assert server.bootstrap_used is False


def test_bootstrap_is_one_time_and_cookie_is_hardened(running_web):
    _root, server, launch = running_web
    cookie = _bootstrap(server, launch)
    assert cookie.startswith(wcp.SESSION_COOKIE + "=")
    assert server.bootstrap_used is True

    body = json.dumps({"bootstrap_token": server.bootstrap_secret}).encode("utf-8")
    status, headers, raw = _request(
        launch,
        "POST",
        "/api/session",
        body=body,
        headers={
            "Origin": launch.origin,
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    assert status == 403
    assert json.loads(raw)["error"] == "invalid_or_consumed_bootstrap"


def test_authenticated_snapshot_uses_command_center_read_model(running_web):
    _root, server, launch = running_web
    cookie = _bootstrap(server, launch)
    status, _headers, raw = _request(
        launch,
        "GET",
        "/api/snapshot",
        headers={"Cookie": cookie},
    )
    assert status == 200
    payload = json.loads(raw)
    assert payload["version"] == "0.28.1"
    assert payload["authority"]["mutation_authority"] is False


def test_actions_and_sections_remain_read_only(running_web):
    _root, server, launch = running_web
    cookie = _bootstrap(server, launch)

    status, _headers, raw = _request(launch, "GET", "/api/actions", headers={"Cookie": cookie})
    assert status == 200
    assert json.loads(raw)["mutation_authority"] is False

    status, _headers, raw = _request(
        launch,
        "GET",
        "/api/section/authority",
        headers={"Cookie": cookie},
    )
    assert status == 200
    assert json.loads(raw)["mutation_authority"] is False


def test_invalid_section_is_rejected(running_web):
    _root, server, launch = running_web
    cookie = _bootstrap(server, launch)
    status, _headers, raw = _request(
        launch,
        "GET",
        "/api/section/secrets",
        headers={"Cookie": cookie},
    )
    assert status == 400
    assert json.loads(raw)["error"] == "invalid_command_center_section"


def test_mutation_routes_do_not_exist(running_web):
    _root, server, launch = running_web
    cookie = _bootstrap(server, launch)
    body = b"{}"
    for path in (
        "/api/architecture/approve",
        "/api/integration/apply",
        "/api/worker/launch",
        "/api/task/create",
    ):
        status, _headers, raw = _request(
            launch,
            "POST",
            path,
            body=body,
            headers={
                "Cookie": cookie,
                "Origin": launch.origin,
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        assert status == 405
        assert json.loads(raw)["error"] == "web_mutation_surface_forbidden"


def test_host_header_rebinding_attempt_is_rejected(running_web):
    _root, _server, launch = running_web
    c = _conn(launch)
    c.putrequest("GET", "/healthz", skip_host=True)
    c.putheader("Host", "evil.example")
    c.endheaders()
    response = c.getresponse()
    payload = json.loads(response.read())
    c.close()
    assert response.status == 400
    assert payload["error"] == "invalid_host_header"


def test_foreground_server_handles_keyboard_interrupt_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    class FakeServer:
        closed = False

        def serve_forever(self, poll_interval: float = 0.25):
            assert poll_interval == 0.25
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    fake = FakeServer()
    launch = wcp.WebControlPlaneLaunch(
        host="127.0.0.1",
        port=8765,
        origin="http://127.0.0.1:8765",
        launch_url="http://127.0.0.1:8765/#bootstrap=redacted",
    )
    monkeypatch.setattr(
        wcp,
        "create_web_control_plane",
        lambda _root, host="127.0.0.1", port=8765: (fake, launch),
    )

    result = wcp.serve_web_control_plane(tmp_path)

    assert result == launch
    assert fake.closed is True
    output = capsys.readouterr().out
    assert '"ok": true' in output
    assert '"mutation_authority": false' in output


def test_healthz_exposes_only_minimal_read_only_runtime_metadata(running_web):
    _root, _server, launch = running_web
    status, _headers, raw = _request(launch, "GET", "/healthz")
    payload = json.loads(raw)
    assert status == 200
    assert payload["mode"] == "local_read_only"
    assert payload["mutation_authority"] is False
    assert "launch_url" not in payload
    assert "bootstrap" not in repr(payload).lower()
