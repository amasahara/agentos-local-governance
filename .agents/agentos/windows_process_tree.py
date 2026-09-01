"""
File: .agents/agentos/windows_process_tree.py

Purpose:
    Provide Windows-native Job Object primitives for AgentOS-managed
    process-tree containment.

Scope:
    This module is intentionally narrower than arbitrary host-process
    containment. It governs only process trees launched through an
    AgentOS-mediated process execution path.

Release target:
    v0.29.1 -- Windows Process-Tree Containment.

Phase:
    Foundation only. Runtime proxy/jobs integration is activated in later
    phases after focused Windows regression coverage is green.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

if os.name == "nt":
    import msvcrt


PROCESS_TREE_CONTAINMENT_VERSION = 1
CONTAINMENT_SCOPE = "agentos_mediated_process_execution"
CONTAINMENT_PROFILE = "windows_job_object_kill_on_close_v1"

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
JOB_OBJECT_ASSIGN_PROCESS = 0x0001
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183

# The v0.29.1 containment contract deliberately does not enable either
# breakaway flag. Descendants therefore inherit the immediate Job Object
# by default unless an enclosing host job imposes stricter constraints.
JOB_LIMIT_FLAGS = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
INFINITE = 0xFFFFFFFF

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

JobObjectBasicAccountingInformation = 1
JobObjectExtendedLimitInformation = 9


class WindowsProcessTreeUnavailable(RuntimeError):
    """Raised when Windows-native process-tree containment is unavailable."""


class WindowsProcessTreeError(RuntimeError):
    """Raised when a Windows Job Object containment operation fails."""


@dataclass(frozen=True)
class ContainmentDescriptor:
    version: int = PROCESS_TREE_CONTAINMENT_VERSION
    scope: str = CONTAINMENT_SCOPE
    profile: str = CONTAINMENT_PROFILE
    kill_on_job_close: bool = True
    breakaway_allowed: bool = False
    silent_breakaway_allowed: bool = False
    root_created_suspended: bool = True
    assigned_before_resume: bool = True


DESCRIPTOR = ContainmentDescriptor()


def is_supported_host() -> bool:
    """Return whether Win32 Job Object containment can execute on this host."""
    return os.name == "nt"


if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    ULONG_PTR = wintypes.WPARAM
    SIZE_T = ctypes.c_size_t

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", SIZE_T),
            ("MaximumWorkingSetSize", SIZE_T),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ULONG_PTR),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", SIZE_T),
            ("JobMemoryLimit", SIZE_T),
            ("PeakProcessMemoryUsed", SIZE_T),
            ("PeakJobMemoryUsed", SIZE_T),
        ]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    kernel32.CreateJobObjectW.argtypes = [
        wintypes.LPVOID,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE

    kernel32.OpenJobObjectW.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.OpenJobObjectW.restype = wintypes.HANDLE

    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryInformationJobObject.restype = wintypes.BOOL

    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    kernel32.AssignProcessToJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.HANDLE,
    ]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    kernel32.TerminateJobObject.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    kernel32.TerminateJobObject.restype = wintypes.BOOL

    kernel32.TerminateProcess.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
    kernel32.GetProcessId.restype = wintypes.DWORD

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD

    kernel32.WaitForSingleObject.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    kernel32.CreateProcessW.restype = wintypes.BOOL


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsProcessTreeUnavailable(
            "windows_process_tree_requires_windows"
        )


def _win_error(operation: str) -> WindowsProcessTreeError:
    code = ctypes.get_last_error()
    return WindowsProcessTreeError(
        f"{operation}_failed_winerror_{code}"
    )


def _close_handle(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _environment_block(
    env: Mapping[str, str] | None,
) -> ctypes.Array[ctypes.c_wchar] | None:
    if env is None:
        return None

    normalized = {
        str(key): str(value)
        for key, value in env.items()
    }

    payload = "\0".join(
        f"{key}={normalized[key]}"
        for key in sorted(
            normalized,
            key=str.upper,
        )
    ) + "\0\0"

    return ctypes.create_unicode_buffer(payload)


class WindowsJob:
    """Own one kill-on-close Win32 Job Object handle."""

    def __init__(self, handle: int):
        self._handle = int(handle)
        self._closed = False

    @property
    def handle(self) -> int:
        if self._closed:
            raise WindowsProcessTreeError(
                "windows_job_handle_closed"
            )
        return self._handle

    def assign_process_handle(self, process_handle: int) -> None:
        _require_windows()

        ok = kernel32.AssignProcessToJobObject(
            wintypes.HANDLE(self.handle),
            wintypes.HANDLE(int(process_handle)),
        )

        if not ok:
            raise _win_error("AssignProcessToJobObject")

    def terminate(self, exit_code: int = 1) -> None:
        _require_windows()

        ok = kernel32.TerminateJobObject(
            wintypes.HANDLE(self.handle),
            wintypes.UINT(int(exit_code) & 0xFFFFFFFF),
        )

        if not ok:
            raise _win_error("TerminateJobObject")

    def close(self) -> None:
        if self._closed:
            return

        handle = self._handle
        self._closed = True

        if os.name == "nt" and handle:
            if not kernel32.CloseHandle(
                wintypes.HANDLE(handle)
            ):
                raise _win_error("CloseHandle")

    def __enter__(self) -> "WindowsJob":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def create_kill_on_close_job(
    *,
    name: str | None = None,
) -> WindowsJob:
    """Create a Job Object with descendant kill-on-last-handle-close."""
    _require_windows()

    handle = kernel32.CreateJobObjectW(
        None,
        name,
    )

    if not handle:
        raise _win_error("CreateJobObjectW")

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_LIMIT_FLAGS

    ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )

    if not ok:
        kernel32.CloseHandle(handle)
        raise _win_error("SetInformationJobObject")

    return WindowsJob(int(handle))


class SpawnedWindowsProcess:
    """A suspended-before-assignment process governed by a Job Object."""

    def __init__(
        self,
        *,
        job: WindowsJob,
        process_handle: int,
        pid: int,
    ):
        self.job = job
        self._process_handle = int(process_handle)
        self.pid = int(pid)
        self._closed = False

    def poll(self) -> int | None:
        _require_windows()

        wait = kernel32.WaitForSingleObject(
            wintypes.HANDLE(self._process_handle),
            0,
        )

        if wait == WAIT_TIMEOUT:
            return None

        if wait != WAIT_OBJECT_0:
            raise _win_error("WaitForSingleObject")

        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(
            wintypes.HANDLE(self._process_handle),
            ctypes.byref(code),
        ):
            raise _win_error("GetExitCodeProcess")

        return int(code.value)

    def wait(self, timeout: float | None = None) -> int:
        _require_windows()

        milliseconds = (
            INFINITE
            if timeout is None
            else max(
                0,
                min(
                    int(float(timeout) * 1000),
                    0xFFFFFFFE,
                ),
            )
        )

        wait = kernel32.WaitForSingleObject(
            wintypes.HANDLE(self._process_handle),
            milliseconds,
        )

        if wait == WAIT_TIMEOUT:
            raise TimeoutError(
                "windows_process_tree_wait_timeout"
            )

        if wait != WAIT_OBJECT_0:
            raise _win_error("WaitForSingleObject")

        code = self.poll()

        if code is None:
            raise WindowsProcessTreeError(
                "process_signaled_without_exit_code"
            )

        return code

    def terminate_tree(self, exit_code: int = 1) -> None:
        self.job.terminate(exit_code)

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True

        process_handle = self._process_handle
        self._process_handle = 0

        _close_handle(process_handle)
        self.job.close()

    def __enter__(self) -> "SpawnedWindowsProcess":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def spawn_suspended_in_job(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    job_name: str | None = None,
    job: WindowsJob | None = None,
    stdin_handle: int | None = None,
    stdout_handle: int | None = None,
    stderr_handle: int | None = None,
) -> SpawnedWindowsProcess:
    """Create the root suspended, assign it to a Job Object, then resume."""
    _require_windows()

    argv = [str(item) for item in command]

    if not argv or not all(argv):
        raise ValueError(
            "command_must_be_non_empty_strings"
        )

    if job is not None and job_name is not None:
        raise ValueError(
            "job_and_job_name_are_mutually_exclusive"
        )

    if job is None:
        job = create_kill_on_close_job(
            name=job_name,
        )

    startup = STARTUPINFOW()
    startup.cb = ctypes.sizeof(startup)

    std_handles = (
        stdin_handle,
        stdout_handle,
        stderr_handle,
    )
    inherit_std_handles = any(
        handle is not None
        for handle in std_handles
    )

    if inherit_std_handles:
        if not all(
            handle is not None
            for handle in std_handles
        ):
            job.close()
            raise ValueError(
                'all_standard_handles_must_be_supplied'
            )

        startup.dwFlags |= STARTF_USESTDHANDLES
        startup.hStdInput = wintypes.HANDLE(int(stdin_handle))
        startup.hStdOutput = wintypes.HANDLE(int(stdout_handle))
        startup.hStdError = wintypes.HANDLE(int(stderr_handle))

    process = PROCESS_INFORMATION()
    command_line = ctypes.create_unicode_buffer(
        subprocess.list2cmdline(argv)
    )

    env_block = _environment_block(env)

    creation_flags = (
        CREATE_SUSPENDED
        | (
            CREATE_UNICODE_ENVIRONMENT
            if env_block is not None
            else 0
        )
    )

    process_created = False
    assigned_to_job = False

    try:
        ok = kernel32.CreateProcessW(
            None,
            command_line,
            None,
            None,
            bool(inherit_std_handles),
            creation_flags,
            (
                ctypes.cast(
                    env_block,
                    wintypes.LPVOID,
                )
                if env_block is not None
                else None
            ),
            (
                str(Path(cwd).resolve())
                if cwd is not None
                else None
            ),
            ctypes.byref(startup),
            ctypes.byref(process),
        )

        if not ok:
            raise _win_error("CreateProcessW")

        process_created = True

        job.assign_process_handle(
            int(process.hProcess)
        )
        assigned_to_job = True

        resume_result = kernel32.ResumeThread(
            process.hThread
        )

        if resume_result == 0xFFFFFFFF:
            raise _win_error("ResumeThread")

        kernel32.CloseHandle(process.hThread)
        process.hThread = None

        return SpawnedWindowsProcess(
            job=job,
            process_handle=int(process.hProcess),
            pid=int(process.dwProcessId),
        )

    except Exception as original_exc:
        cleanup_error = None

        if process_created and process.hProcess:
            terminated = False

            if assigned_to_job:
                try:
                    job.terminate(1)
                    terminated = True
                except Exception:
                    pass

            if not terminated:
                if not kernel32.TerminateProcess(
                    process.hProcess,
                    1,
                ):
                    cleanup_error = _win_error(
                        'TerminateProcess'
                    )
                else:
                    kernel32.WaitForSingleObject(
                        process.hProcess,
                        5000,
                    )

        if process.hThread:
            _close_handle(int(process.hThread))

        if process.hProcess:
            _close_handle(int(process.hProcess))

        try:
            job.close()
        except Exception as exc:
            if cleanup_error is None:
                cleanup_error = exc

        if cleanup_error is not None:
            raise WindowsProcessTreeError(
                'windows_process_tree_cleanup_failed'
            ) from cleanup_error

        raise original_exc


def pid_is_alive(pid: int) -> bool:
    """Best-effort Win32 liveness probe used by containment regression tests."""
    _require_windows()

    handle = kernel32.OpenProcess(
        SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        int(pid),
    )

    if not handle:
        return False

    try:
        wait = kernel32.WaitForSingleObject(
            handle,
            0,
        )

        return wait == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)



@dataclass(frozen=True)
class ContainedCompletedProcess:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    pid: int
    containment_profile: str = CONTAINMENT_PROFILE
    process_tree_contained: bool = True


def _os_handle(file_object) -> int:
    _require_windows()
    handle = int(msvcrt.get_osfhandle(file_object.fileno()))
    os.set_handle_inheritable(handle, True)
    return handle


def _read_capture(file_object, *, encoding: str, errors: str) -> str:
    file_object.flush()
    file_object.seek(0)
    return file_object.read().decode(encoding, errors=errors)





def run_contained_capture(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> ContainedCompletedProcess:
    """
    Run one synchronous command inside the v0.29.1 Job Object boundary.

    This remains the generic process-tree primitive. v0.29.4 production
    process.exec uses run_restricted_contained_capture() instead.
    """
    _require_windows()

    argv = tuple(str(item) for item in command)
    if not argv or not all(argv):
        raise ValueError(
            "command_must_be_non_empty_strings"
        )

    with open(
        os.devnull,
        "rb",
        buffering=0,
    ) as stdin_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stdout_file, tempfile.TemporaryFile(
        mode="w+b"
    ) as stderr_file:
        handles = (
            _os_handle(stdin_file),
            _os_handle(stdout_file),
            _os_handle(stderr_file),
        )
        proc = None

        try:
            proc = spawn_suspended_in_job(
                argv,
                cwd=cwd,
                env=env,
                stdin_handle=handles[0],
                stdout_handle=handles[1],
                stderr_handle=handles[2],
            )

            try:
                returncode = proc.wait(
                    timeout=timeout
                )
            except TimeoutError as exc:
                proc.terminate_tree(124)
                try:
                    proc.wait(timeout=5.0)
                except Exception:
                    pass

                stdout = _read_capture(
                    stdout_file,
                    encoding=encoding,
                    errors=errors,
                )
                stderr = _read_capture(
                    stderr_file,
                    encoding=encoding,
                    errors=errors,
                )

                raise subprocess.TimeoutExpired(
                    list(argv),
                    timeout,
                    output=stdout,
                    stderr=stderr,
                ) from exc

            stdout = _read_capture(
                stdout_file,
                encoding=encoding,
                errors=errors,
            )
            stderr = _read_capture(
                stderr_file,
                encoding=encoding,
                errors=errors,
            )

            return ContainedCompletedProcess(
                args=argv,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                pid=proc.pid,
            )

        finally:
            if proc is not None:
                proc.close()

            for handle in handles:
                try:
                    os.set_handle_inheritable(
                        handle,
                        False,
                    )
                except OSError:
                    pass

def async_job_object_name(job_id: str) -> str:
    value = str(job_id).strip()

    if not value or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for ch in value
    ):
        raise ValueError(
            "invalid_async_job_id_for_windows_job_object"
        )

    return "Local\\AgentOS-v0291-" + value


def create_persistent_named_job(
    *,
    name: str,
) -> WindowsJob:
    _require_windows()

    if not name:
        raise ValueError(
            "windows_named_job_requires_name"
        )

    ctypes.set_last_error(0)

    handle = kernel32.CreateJobObjectW(
        None,
        name,
    )

    if not handle:
        raise _win_error("CreateJobObjectW")

    last_error = ctypes.get_last_error()

    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise WindowsProcessTreeError(
            "windows_named_job_already_exists"
        )

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0

    ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )

    if not ok:
        kernel32.CloseHandle(handle)
        raise _win_error("SetInformationJobObject")

    return WindowsJob(int(handle))


def _open_named_job_handle(
    name: str,
    access: int,
) -> int | None:
    _require_windows()

    ctypes.set_last_error(0)

    handle = kernel32.OpenJobObjectW(
        wintypes.DWORD(int(access)),
        False,
        name,
    )

    if handle:
        return int(handle)

    code = ctypes.get_last_error()

    if code == ERROR_FILE_NOT_FOUND:
        return None

    raise WindowsProcessTreeError(
        f"OpenJobObjectW_failed_winerror_{code}"
    )


def named_job_active_process_count(
    name: str,
) -> int | None:
    handle = _open_named_job_handle(
        name,
        JOB_OBJECT_QUERY,
    )

    if handle is None:
        return None

    try:
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        returned = wintypes.DWORD()

        ok = kernel32.QueryInformationJobObject(
            wintypes.HANDLE(handle),
            JobObjectBasicAccountingInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(returned),
        )

        if not ok:
            raise _win_error(
                "QueryInformationJobObject"
            )

        return int(info.ActiveProcesses)
    finally:
        kernel32.CloseHandle(
            wintypes.HANDLE(handle)
        )


def terminate_named_job(
    name: str,
    exit_code: int = 1,
) -> bool:
    handle = _open_named_job_handle(
        name,
        JOB_OBJECT_TERMINATE,
    )

    if handle is None:
        return False

    try:
        ok = kernel32.TerminateJobObject(
            wintypes.HANDLE(handle),
            wintypes.UINT(
                int(exit_code) & 0xFFFFFFFF
            ),
        )

        if not ok:
            raise _win_error(
                "TerminateJobObject"
            )

        return True
    finally:
        kernel32.CloseHandle(
            wintypes.HANDLE(handle)
        )


@dataclass(frozen=True)
class DetachedWindowsProcess:
    pid: int
    job_name: str
    containment_profile: str = (
        "windows_named_job_object_v1"
    )
    process_tree_contained: bool = True


def spawn_detached_persistent_job(
    command: Sequence[str],
    *,
    cwd: Path | str | None,
    env: Mapping[str, str] | None,
    job_name: str,
    stdout_file,
    stderr_file,
) -> DetachedWindowsProcess:
    _require_windows()

    job = create_persistent_named_job(
        name=job_name,
    )

    proc = None

    with open(
        os.devnull,
        "rb",
        buffering=0,
    ) as stdin_file:
        handles = (
            _os_handle(stdin_file),
            _os_handle(stdout_file),
            _os_handle(stderr_file),
        )

        try:
            proc = spawn_suspended_in_job(
                command,
                cwd=cwd,
                env=env,
                job=job,
                stdin_handle=handles[0],
                stdout_handle=handles[1],
                stderr_handle=handles[2],
            )

            result = DetachedWindowsProcess(
                pid=proc.pid,
                job_name=job_name,
            )

            # No KILL_ON_JOB_CLOSE here. Associated processes keep the
            # named object alive after launcher handles are closed.
            proc.close()
            proc = None

            return result
        finally:
            if proc is not None:
                proc.close()

            for handle in handles:
                try:
                    os.set_handle_inheritable(
                        handle,
                        False,
                    )
                except OSError:
                    pass


def create_named_kill_on_close_job(
    *,
    name: str,
) -> WindowsJob:
    """Create a unique named Job Object with fail-closed kill-on-close."""
    _require_windows()

    if not name:
        raise ValueError(
            "windows_named_job_requires_name"
        )

    ctypes.set_last_error(0)

    handle = kernel32.CreateJobObjectW(
        None,
        name,
    )

    if not handle:
        raise _win_error("CreateJobObjectW")

    last_error = ctypes.get_last_error()

    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        raise WindowsProcessTreeError(
            "windows_named_job_already_exists"
        )

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    )

    ok = kernel32.SetInformationJobObject(
        handle,
        JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )

    if not ok:
        kernel32.CloseHandle(handle)
        raise _win_error("SetInformationJobObject")

    return WindowsJob(int(handle))
