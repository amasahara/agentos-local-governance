from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from agentos import windows_process_tree as process_tree


def test_v0291_descriptor_is_narrow_and_fail_closed():
    descriptor = process_tree.DESCRIPTOR

    assert descriptor.version == 1
    assert (
        descriptor.scope
        == "agentos_mediated_process_execution"
    )
    assert (
        descriptor.profile
        == "windows_job_object_kill_on_close_v1"
    )
    assert descriptor.kill_on_job_close is True
    assert descriptor.breakaway_allowed is False
    assert descriptor.silent_breakaway_allowed is False
    assert descriptor.root_created_suspended is True
    assert descriptor.assigned_before_resume is True

    assert (
        process_tree.JOB_LIMIT_FLAGS
        == process_tree.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )
    assert not (
        process_tree.JOB_LIMIT_FLAGS
        & process_tree.JOB_OBJECT_LIMIT_BREAKAWAY_OK
    )
    assert not (
        process_tree.JOB_LIMIT_FLAGS
        & process_tree.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
    )


def test_v0291_non_windows_import_is_safe():
    assert isinstance(
        process_tree.is_supported_host(),
        bool,
    )

    if os.name != "nt":
        with pytest.raises(
            process_tree.WindowsProcessTreeUnavailable,
            match="windows_process_tree_requires_windows",
        ):
            process_tree.create_kill_on_close_job()


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Job Object containment contract",
)
def test_v0291_root_is_created_assigned_before_resume(tmp_path):
    marker = tmp_path / "root-started.txt"
    script = tmp_path / "root.py"

    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "import time",
                "Path(sys.argv[1]).write_text(",
                "    'started', encoding='utf-8'",
                ")",
                "time.sleep(60)",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    proc = process_tree.spawn_suspended_in_job(
        [
            sys.executable,
            str(script),
            str(marker),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
    )

    try:
        deadline = time.monotonic() + 5.0

        while (
            time.monotonic() < deadline
            and not marker.exists()
        ):
            time.sleep(0.05)

        assert marker.read_text(
            encoding="utf-8"
        ) == "started"
        assert proc.poll() is None
    finally:
        try:
            proc.terminate_tree(91)
            proc.wait(timeout=5)
        finally:
            proc.close()


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Job Object descendant containment contract",
)
def test_v0291_terminate_job_kills_descendant_tree(tmp_path):
    grandchild_pid_file = tmp_path / "grandchild.pid"
    script = tmp_path / "root_with_child.py"

    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import subprocess",
                "import sys",
                "import time",
                "child = subprocess.Popen([",
                "    sys.executable,",
                "    '-c',",
                "    'import time; time.sleep(60)',",
                "])",
                "Path(sys.argv[1]).write_text(",
                "    str(child.pid), encoding='utf-8'",
                ")",
                "time.sleep(60)",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    proc = process_tree.spawn_suspended_in_job(
        [
            sys.executable,
            str(script),
            str(grandchild_pid_file),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
    )

    try:
        deadline = time.monotonic() + 8.0

        while (
            time.monotonic() < deadline
            and not grandchild_pid_file.exists()
        ):
            time.sleep(0.05)

        assert grandchild_pid_file.is_file()

        grandchild_pid = int(
            grandchild_pid_file.read_text(
                encoding="utf-8"
            )
        )

        assert process_tree.pid_is_alive(
            grandchild_pid
        )

        proc.terminate_tree(92)
        proc.wait(timeout=5)

        deadline = time.monotonic() + 5.0

        while (
            time.monotonic() < deadline
            and process_tree.pid_is_alive(
                grandchild_pid
            )
        ):
            time.sleep(0.05)

        assert not process_tree.pid_is_alive(
            grandchild_pid
        )
    finally:
        try:
            proc.terminate_tree(93)
        except Exception:
            pass
        proc.close()


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows Job Object kill-on-close contract",
)
def test_v0291_job_close_kills_descendant_tree(tmp_path):
    grandchild_pid_file = (
        tmp_path / "grandchild-close.pid"
    )
    script = tmp_path / "root_with_child_close.py"

    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import subprocess",
                "import sys",
                "import time",
                "child = subprocess.Popen([",
                "    sys.executable,",
                "    '-c',",
                "    'import time; time.sleep(60)',",
                "])",
                "Path(sys.argv[1]).write_text(",
                "    str(child.pid), encoding='utf-8'",
                ")",
                "time.sleep(60)",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    proc = process_tree.spawn_suspended_in_job(
        [
            sys.executable,
            str(script),
            str(grandchild_pid_file),
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
    )

    deadline = time.monotonic() + 8.0

    while (
        time.monotonic() < deadline
        and not grandchild_pid_file.exists()
    ):
        time.sleep(0.05)

    assert grandchild_pid_file.is_file()

    grandchild_pid = int(
        grandchild_pid_file.read_text(
            encoding="utf-8"
        )
    )

    assert process_tree.pid_is_alive(
        grandchild_pid
    )

    proc.close()

    deadline = time.monotonic() + 5.0

    while (
        time.monotonic() < deadline
        and process_tree.pid_is_alive(
            grandchild_pid
        )
    ):
        time.sleep(0.05)

    assert not process_tree.pid_is_alive(
        grandchild_pid
    )



@pytest.mark.skipif(
    os.name != 'nt',
    reason='Windows suspended-root fail-closed cleanup contract',
)
def test_v0291_assignment_failure_terminates_suspended_root(
    monkeypatch,
    tmp_path,
):
    marker = tmp_path / 'must-not-run.txt'
    script = tmp_path / 'must_not_run.py'
    script.write_text(
        "from pathlib import Path\n"
        "import sys, time\n"
        "Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding='utf-8',
        newline='\n',
    )

    holder = {}

    def fail_assignment(self, process_handle):
        pid = int(
            process_tree.kernel32.GetProcessId(
                process_tree.wintypes.HANDLE(
                    int(process_handle)
                )
            )
        )
        holder['pid'] = pid
        raise process_tree.WindowsProcessTreeError(
            'forced_assignment_failure'
        )

    monkeypatch.setattr(
        process_tree.WindowsJob,
        'assign_process_handle',
        fail_assignment,
    )

    with pytest.raises(
        process_tree.WindowsProcessTreeError,
        match='forced_assignment_failure',
    ):
        process_tree.spawn_suspended_in_job(
            [sys.executable, str(script), str(marker)],
            cwd=tmp_path,
            env=os.environ.copy(),
        )

    assert 'pid' in holder
    assert not marker.exists()

    deadline = time.monotonic() + 5.0
    while (
        time.monotonic() < deadline
        and process_tree.pid_is_alive(holder['pid'])
    ):
        time.sleep(0.05)

    assert not process_tree.pid_is_alive(holder['pid'])


@pytest.mark.skipif(
    os.name != 'nt',
    reason='Windows Job Object synchronous capture contract',
)
def test_v0291_contained_capture_collects_output(tmp_path):
    script = tmp_path / 'capture.py'
    script.write_text(
        "import sys\nprint('stdout-ok')\nprint('stderr-ok', file=sys.stderr)\n",
        encoding='utf-8',
        newline='\n',
    )

    result = process_tree.run_contained_capture(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=5,
    )

    assert result.returncode == 0
    assert 'stdout-ok' in result.stdout
    assert 'stderr-ok' in result.stderr
    assert result.process_tree_contained is True


@pytest.mark.skipif(
    os.name != 'nt',
    reason='Windows Job Object synchronous descendant cleanup contract',
)
def test_v0291_sync_root_exit_kills_background_descendant(tmp_path):
    pid_file = tmp_path / 'background.pid'
    script = tmp_path / 'background_root.py'
    script.write_text(
        "from pathlib import Path\n"
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n",
        encoding='utf-8',
        newline='\n',
    )

    result = process_tree.run_contained_capture(
        [sys.executable, str(script), str(pid_file)],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout=5,
    )
    assert result.returncode == 0
    child_pid = int(pid_file.read_text(encoding='utf-8'))

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and process_tree.pid_is_alive(child_pid):
        time.sleep(0.05)
    assert not process_tree.pid_is_alive(child_pid)


@pytest.mark.skipif(
    os.name != 'nt',
    reason='Windows Job Object synchronous timeout containment contract',
)
def test_v0291_sync_timeout_kills_descendant_tree(tmp_path):
    pid_file = tmp_path / 'timeout-child.pid'
    script = tmp_path / 'timeout_root.py'
    script.write_text(
        "from pathlib import Path\n"
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding='utf-8',
        newline='\n',
    )

    with pytest.raises(subprocess.TimeoutExpired):
        process_tree.run_contained_capture(
            [sys.executable, str(script), str(pid_file)],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout=2,
        )

    child_pid = int(pid_file.read_text(encoding='utf-8'))
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and process_tree.pid_is_alive(child_pid):
        time.sleep(0.05)
    assert not process_tree.pid_is_alive(child_pid)



@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows zero-handle named Job lifetime characterization",
)
def test_v0291_zero_handle_named_job_is_not_reopenable(tmp_path):
    name = process_tree.async_job_object_name(
        "zerohandle"
    )

    job = process_tree.create_persistent_named_job(
        name=name
    )

    proc = process_tree.spawn_suspended_in_job(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(1)",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        job=job,
    )

    pid = proc.pid

    assert (
        process_tree.named_job_active_process_count(
            name
        )
        == 1
    )

    proc.close()

    assert (
        process_tree.named_job_active_process_count(
            name
        )
        is None
    )

    deadline = time.monotonic() + 5.0

    while (
        time.monotonic() < deadline
        and process_tree.pid_is_alive(pid)
    ):
        time.sleep(0.05)

    assert not process_tree.pid_is_alive(pid)


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows persistent named Job collision contract",
)
def test_v0291_persistent_named_job_collision_fails_closed():
    name = process_tree.async_job_object_name(
        "collision"
    )

    job = process_tree.create_persistent_named_job(
        name=name
    )

    try:
        with pytest.raises(
            process_tree.WindowsProcessTreeError,
            match="windows_named_job_already_exists",
        ):
            process_tree.create_persistent_named_job(
                name=name
            )
    finally:
        job.close()


def test_v0291_async_job_name_is_deterministic_and_local():
    name = process_tree.async_job_object_name(
        "abc123"
    )

    assert name == "Local\\AgentOS-v0291-abc123"

    with pytest.raises(
        ValueError,
        match="invalid_async_job_id",
    ):
        process_tree.async_job_object_name(
            "bad\\name"
        )
