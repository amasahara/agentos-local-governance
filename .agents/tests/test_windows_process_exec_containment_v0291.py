from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from agentos import proxy



def test_v0291_windows_sync_route_uses_contained_runner(monkeypatch, tmp_path):
    """
    Successor contract: the inherited v0.29.1 requirement remains that
    Windows process.exec uses the contained production runner.

    v0.29.5 strengthens that runner to Restricted Token + Low Integrity +
    Job Object. Patch the successor primitive actually imported by proxy at
    call time rather than the v0.29.4 restricted-only predecessor primitive.
    """
    calls = []

    monkeypatch.setattr(
        proxy,
        "_is_windows_host",
        lambda: True,
    )

    from agentos import (
        windows_physical_isolation,
        windows_process_tree,
    )

    def fake_run(command, *, cwd, env, timeout):
        calls.append(
            (
                list(command),
                Path(cwd),
                dict(env),
                timeout,
            )
        )

        return SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        )

    monkeypatch.setattr(
        windows_physical_isolation,
        "run_low_integrity_restricted_contained_capture",
        fake_run,
    )

    result, metadata = proxy._run_process_command(
        ["python", "-m", "pytest"],
        cwd=tmp_path,
        env={"PATH": "x"},
        timeout=7,
    )

    assert result.returncode == 0
    assert len(calls) == 1

    assert metadata["process_tree_contained"] is True
    assert (
        metadata[
            "process_tree_containment_profile"
        ]
        == windows_process_tree.CONTAINMENT_PROFILE
    )
    assert (
        metadata[
            "process_tree_containment_scope"
        ]
        == "agentos_mediated_process_execution"
    )

    assert metadata["restricted_execution"] is True
    assert metadata["restricted_token_verified"] is True

    assert metadata["low_integrity_execution"] is True
    assert metadata["low_integrity_token_verified"] is True
    assert (
        metadata[
            "sandbox_low_integrity_boundary_required"
        ]
        is True
    )

    # Per-execution metadata remains a runtime evidence record, not the
    # release-level attestation projection.
    assert metadata["low_integrity_attested"] is False
    assert (
        metadata[
            "host_filesystem_isolation_attested"
        ]
        is False
    )
    assert (
        metadata[
            "os_write_confinement_attested"
        ]
        is False
    )

def test_v0291_posix_sync_route_preserves_subprocess_run(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(proxy, '_is_windows_host', lambda: False)

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        return subprocess.CompletedProcess(command, 0, stdout='ok', stderr='')

    monkeypatch.setattr(proxy.subprocess, 'run', fake_run)

    result, metadata = proxy._run_process_command(
        ['python', '-m', 'pytest'],
        cwd=tmp_path,
        env={'PATH': 'x'},
        timeout=11,
    )

    assert result.returncode == 0
    assert len(calls) == 1
    _, kwargs = calls[0]
    assert kwargs['shell'] is False
    assert kwargs['capture_output'] is True
    assert kwargs['text'] is True
    assert kwargs['timeout'] == 11
    assert metadata == {
        'process_tree_contained': False,
        'process_tree_containment_profile': None,
        'process_tree_containment_scope': None,
    }



def test_v0291_proxy_source_has_no_windows_root_only_fallback():
    source = Path(
        proxy.__file__
    ).read_text(
        encoding="utf-8"
    )
    start = source.index(
        "def _run_process_command("
    )
    end = source.index(
        "\ndef _execute_adapter(",
        start,
    )
    helper = source[start:end]

    assert (
        "run_restricted_contained_capture"
        in helper
    )
    assert "os.kill(" not in helper
    assert "taskkill" not in helper.lower()
