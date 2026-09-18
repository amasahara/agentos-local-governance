from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from agentos import gateway_client, gatewayd


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None


def test_v0322_gateway_transport_selection_matches_platform():
    if os.name == "nt":
        assert gatewayd.ipc_family() == "AF_PIPE"
        assert gatewayd.pipe_address(Path.cwd()).startswith(r"\\.\pipe\agentos-gateway-")
    else:
        assert gatewayd.ipc_family() == "AF_UNIX"


def test_v0322_pipe_address_is_project_scoped_and_deterministic(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    assert gatewayd.pipe_address(one) == gatewayd.pipe_address(one)
    assert gatewayd.pipe_address(one) != gatewayd.pipe_address(two)


def test_v0322_windows_pipe_client_fails_closed_without_authkey(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway_client, "ipc_family", lambda: "AF_PIPE")
    with pytest.raises(RuntimeError, match="authentication key is missing"):
        gateway_client.request(tmp_path, {"action": "health"})


@pytest.mark.skipif(os.name != "nt", reason="Windows AF_PIPE regression")
def test_v0322_windows_named_pipe_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(gatewayd, "connect", lambda root: _FakeConnection())
    monkeypatch.setattr(
        gatewayd,
        "dispatch",
        lambda root, req: {"echo": req.get("action"), "ok": True},
    )

    errors = []

    def run_server():
        try:
            gatewayd._serve_windows_pipe(tmp_path, max_requests=1)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    key_path = gatewayd.gateway_authkey_path(tmp_path)
    deadline = time.monotonic() + 5.0
    while not key_path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)

    assert key_path.exists(), f"gateway auth key was not published; errors={errors!r}"

    result = gateway_client.request(tmp_path, {"action": "health"})
    assert result == {"echo": "health", "ok": True}

    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert not errors
    assert not key_path.exists()
def test_v0322_gatewayd_has_no_direct_process_creation_primitives():
    source = gatewayd.Path(gatewayd.__file__).read_text(encoding="utf-8")
    assert "subprocess.run" not in source
    assert "subprocess.Popen" not in source
    assert "os.system(" not in source


@pytest.mark.skipif(os.name != "nt", reason="Windows identity regression")
def test_v0322_windows_execution_identity_sid_is_resolved():
    sid = gatewayd._windows_current_user_sid()
    assert sid.startswith("S-1-")


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL regression")
def test_v0322_windows_authkey_acl_hardening_succeeds(tmp_path):
    path = tmp_path / "gateway.auth"
    path.write_text("00" * 32, encoding="ascii")
    gatewayd._harden_windows_authkey_acl(path)
    assert path.read_text(encoding="ascii") == "00" * 32

def test_v0324_windows_pipe_cleans_up_when_gateway_registration_fails(
    tmp_path,
    monkeypatch,
):
    class FakeListener:
        instances = []

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.closed = False
            type(self).instances.append(self)

        def accept(self):
            raise AssertionError(
                "accept() must not be reached when _register_gateway fails"
            )

        def close(self):
            self.closed = True

    sentinel = "v0324-register-gateway-failure"

    monkeypatch.setattr(gatewayd, "Listener", FakeListener)

    def fail_register(*args, **kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(gatewayd, "_register_gateway", fail_register)

    with pytest.raises(RuntimeError, match=sentinel):
        gatewayd._serve_windows_pipe(tmp_path, max_requests=1)

    assert len(FakeListener.instances) == 1
    assert FakeListener.instances[0].closed is True
    assert not gatewayd.gateway_authkey_path(tmp_path).exists()

    runtime = tmp_path / ".agents" / "runtime"
    if runtime.exists():
        remaining_files = [p for p in runtime.rglob("*") if p.is_file()]
        assert remaining_files == []
