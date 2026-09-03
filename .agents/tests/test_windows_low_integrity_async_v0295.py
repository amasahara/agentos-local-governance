from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from agentos.tool_runtime_profiles import build_runtime_environment, cleanup_sandbox_workspace, create_sandbox_workspace
from agentos.windows_physical_isolation import SECURITY_MANDATORY_MEDIUM_RID, inspect_path_mandatory_label
from agentos.windows_process_tree import async_job_object_name

ROOT = Path(__file__).resolve().parents[2]


def test_v0295_phase4_production_jobs_require_low_ready_evidence():
    source = (ROOT / '.agents/agentos/jobs.py').read_text(encoding='utf-8')
    start = source.index('def _launch_windows_job_broker(')
    end = source.index('def _job_dir(', start)
    body = source[start:end]
    for marker in ('"restricted_execution": True','"low_integrity_execution": True','"restricted_token_verified"','"low_integrity_token_verified"','"sandbox_low_integrity_boundary_required"','"assigned_before_resume"'):
        assert marker in body


def test_v0295_phase4_broker_keeps_compatibility_branches_but_low_is_production_capable():
    source = (ROOT / '.agents/agentos/windows_job_broker.py').read_text(encoding='utf-8')
    assert 'spawn_low_integrity_restricted_suspended_in_job' in source
    assert 'spawn_restricted_suspended_in_job' in source
    assert 'spawn_suspended_in_job' in source
    assert 'windows_job_broker_low_integrity_requires_restricted_execution' in source
    assert '"low_integrity_token_verified"' in source


@pytest.mark.skipif(os.name != 'nt', reason='Windows async Restricted + Low worker')
def test_v0295_phase4_real_broker_low_worker_writes_sandbox_and_denies_medium(tmp_path):
    primary = tmp_path / 'primary'
    source = primary / 'source'
    source.mkdir(parents=True)
    (source / 'input.txt').write_text('async-low-ok', encoding='utf-8', newline='\n')
    medium = tmp_path / 'medium-target.txt'
    medium.write_text('before', encoding='utf-8', newline='\n')
    evidence = inspect_path_mandatory_label(medium)
    assert evidence.rid >= SECURITY_MANDATORY_MEDIUM_RID
    assert evidence.low_integrity is False

    job_id = 'v0295phase4' + uuid.uuid4().hex[:12]
    sandbox = create_sandbox_workspace(primary, source, 'v0295-phase4', 'async-low', job_id, 'test')
    workspace = Path(sandbox['workspace'])
    env = build_runtime_environment(dict(os.environ), sandbox)
    stdout_path = tmp_path / 'worker.stdout.log'
    stderr_path = tmp_path / 'worker.stderr.log'
    ready_path = tmp_path / 'worker.ready.json'
    completion_path = tmp_path / 'worker.completion.json'
    code = (
        "from pathlib import Path\n"
        "value=Path('input.txt').read_text(encoding='utf-8')\n"
        "Path('async-low-write.txt').write_text(value,encoding='utf-8')\n"
        f"target=Path({str(medium)!r})\n"
        "denied=False\n"
        "try:\n"
        "    target.write_text('forbidden',encoding='utf-8')\n"
        "except PermissionError:\n"
        "    denied=True\n"
        "print('MEDIUM_WRITE_DENIED' if denied else 'MEDIUM_WRITE_ALLOWED')\n"
        "raise SystemExit(0 if denied else 88)\n"
    )
    payload = {
        'job_id': job_id,
        'job_name': async_job_object_name(job_id),
        'command': [sys.executable, '-c', code],
        'cwd': str(workspace),
        'env': env,
        'stdout_path': str(stdout_path),
        'stderr_path': str(stderr_path),
        'ready_path': str(ready_path),
        'completion_path': str(completion_path),
        'restricted_execution': True,
        'low_integrity_execution': True,
    }
    broker = subprocess.Popen([sys.executable, '-m', 'agentos.windows_job_broker'], cwd=ROOT, env=dict(os.environ), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        assert broker.stdin is not None and broker.stdout is not None and broker.stderr is not None
        broker.stdin.write(json.dumps(payload, sort_keys=True) + '\n')
        broker.stdin.flush()
        broker.stdin.close()
        ready_line = broker.stdout.readline()
        if not ready_line:
            raise AssertionError('broker did not produce READY: ' + broker.stderr.read())
        ready = json.loads(ready_line)
        assert ready['restricted_execution'] is True
        assert ready['restricted_token_verified'] is True
        assert ready['low_integrity_execution'] is True
        assert ready['low_integrity_token_verified'] is True
        assert ready['assigned_before_resume'] is True
        assert ready['low_integrity_attested'] is False
        broker.wait(timeout=15)
        assert broker.returncode == 0, broker.stderr.read()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not completion_path.exists():
            time.sleep(0.05)
        completion = json.loads(completion_path.read_text(encoding='utf-8'))
        assert completion['worker_exit_code'] == 0
        assert completion['restricted_token_verified'] is True
        assert completion['low_integrity_execution'] is True
        assert completion['low_integrity_token_verified'] is True
        assert (workspace / 'async-low-write.txt').read_text(encoding='utf-8') == 'async-low-ok'
        assert medium.read_text(encoding='utf-8') == 'before'
        assert 'MEDIUM_WRITE_DENIED' in stdout_path.read_text(encoding='utf-8', errors='replace')
    finally:
        if broker.poll() is None:
            broker.terminate()
            try:
                broker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                broker.kill(); broker.wait(timeout=5)
        cleanup_sandbox_workspace(primary, Path(sandbox['root']))


def test_v0295_phase4_release_identity_and_schema_v0295():
    assert tuple(int(part) for part in (ROOT / "VERSION").read_text(encoding="utf-8").strip().split(".")) >= (0, 29, 5)
    from agentos import __version__
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    assert __version__ == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert CURRENT_SCHEMA_VERSION >= 62
