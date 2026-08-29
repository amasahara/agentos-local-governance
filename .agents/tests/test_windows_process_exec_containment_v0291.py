from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from agentos import proxy


def test_v0291_windows_sync_route_uses_contained_runner(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(proxy, '_is_windows_host', lambda: True)

    from agentos import windows_process_tree

    def fake_run(command, *, cwd, env, timeout):
        calls.append((list(command), Path(cwd), dict(env), timeout))
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')

    monkeypatch.setattr(windows_process_tree, 'run_contained_capture', fake_run)

    result, metadata = proxy._run_process_command(
        ['python', '-m', 'pytest'],
        cwd=tmp_path,
        env={'PATH': 'x'},
        timeout=7,
    )

    assert result.returncode == 0
    assert len(calls) == 1
    assert metadata['process_tree_contained'] is True
    assert metadata['process_tree_containment_profile'] == windows_process_tree.CONTAINMENT_PROFILE
    assert metadata['process_tree_containment_scope'] == 'agentos_mediated_process_execution'


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
    source = Path(proxy.__file__).read_text(encoding='utf-8')
    start = source.index('def _run_process_command(')
    end = source.index('\ndef _execute_adapter(', start)
    helper = source[start:end]

    assert 'run_contained_capture' in helper
    assert 'os.kill(' not in helper
    assert 'taskkill' not in helper.lower()
