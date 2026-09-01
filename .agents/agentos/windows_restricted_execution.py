"""
Windows restricted-token primitives for AgentOS v0.29.4 Phase 1.

Foundation only: token creation/verification + CreateProcessAsUserW ABI binding.
No sync/async production path is switched in this phase.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

RESTRICTED_EXECUTION_VERSION = 1
RESTRICTED_EXECUTION_SCOPE = "agentos_mediated_process_execution"
RESTRICTED_TOKEN_PROFILE = "disable_max_privilege_lua_v1"

DISABLE_MAX_PRIVILEGE = 0x00000001
SANDBOX_INERT = 0x00000002
LUA_TOKEN = 0x00000004
RESTRICTED_TOKEN_FLAGS = DISABLE_MAX_PRIVILEGE | LUA_TOKEN

TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
RESTRICTED_SOURCE_TOKEN_ACCESS = TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY

TokenPrivileges = 3
TokenType = 8
TokenSandBoxInert = 15
TokenHasRestrictions = 21
TokenPrimary = 1
SE_PRIVILEGE_ENABLED = 0x00000002
CREATE_SUSPENDED = 0x00000004
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
ALLOWED_ENABLED_PRIVILEGES = frozenset({"SeChangeNotifyPrivilege"})


class WindowsRestrictedExecutionUnavailable(RuntimeError):
    pass


class WindowsRestrictedExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RestrictedExecutionDescriptor:
    version: int = RESTRICTED_EXECUTION_VERSION
    scope: str = RESTRICTED_EXECUTION_SCOPE
    profile: str = RESTRICTED_TOKEN_PROFILE
    current_process_primary_token_only: bool = True
    disable_max_privilege: bool = True
    lua_token: bool = True
    sandbox_inert: bool = False
    token_has_restrictions_verified: bool = True
    primary_token_verified: bool = True
    privilege_allowlist_verified: bool = True
    create_process_as_user_bound: bool = True
    sync_execution_enforced: bool = True
    async_execution_enforced: bool = True
    restricted_token_attested: bool = True
    low_integrity_attested: bool = False
    host_filesystem_isolation_attested: bool = False
    os_write_confinement_attested: bool = False
    same_user_host_bypass_resistance_claimed: bool = False


DESCRIPTOR = RestrictedExecutionDescriptor()


@dataclass(frozen=True)
class RestrictedTokenEvidence:
    token_type: int
    token_has_restrictions: bool
    sandbox_inert: bool
    enabled_privileges: tuple[str, ...]
    unexpected_enabled_privileges: tuple[str, ...]

    @property
    def primary_token(self) -> bool:
        return self.token_type == TokenPrimary

    @property
    def verified(self) -> bool:
        return (
            self.primary_token
            and self.token_has_restrictions
            and not self.sandbox_inert
            and not self.unexpected_enabled_privileges
        )


@dataclass
class RestrictedPrimaryToken:
    _handle: int
    evidence: RestrictedTokenEvidence
    _closed: bool = False

    @property
    def handle(self) -> int:
        if self._closed:
            raise WindowsRestrictedExecutionError("restricted_token_handle_closed")
        return self._handle

    def close(self) -> None:
        if self._closed:
            return
        handle = self._handle
        self._handle = 0
        self._closed = True
        _close_handle(handle)

    def __enter__(self) -> "RestrictedPrimaryToken":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def is_supported_host() -> bool:
    return os.name == "nt"


if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD),
        ]

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.CreateRestrictedToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.CreateRestrictedToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.LookupPrivilegeNameW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(LUID), wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.LookupPrivilegeNameW.restype = wintypes.BOOL

    # Phase 1 binding only. Phase 2 will use this launch primitive.
    advapi32.CreateProcessAsUserW.argtypes = [
        wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID,
        wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID,
        wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOW),
        ctypes.POINTER(PROCESS_INFORMATION),
    ]
    advapi32.CreateProcessAsUserW.restype = wintypes.BOOL


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsRestrictedExecutionUnavailable(
            "windows_restricted_execution_requires_windows"
        )


def _win_error(operation: str) -> WindowsRestrictedExecutionError:
    return WindowsRestrictedExecutionError(
        f"{operation}_failed_winerror_{ctypes.get_last_error()}"
    )


def _close_handle(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    if not kernel32.CloseHandle(wintypes.HANDLE(int(handle))):
        raise _win_error("CloseHandle")


def _query_token_dword(token_handle: int, information_class: int) -> int:
    _require_windows()
    value = wintypes.DWORD()
    returned = wintypes.DWORD()
    ok = advapi32.GetTokenInformation(
        wintypes.HANDLE(int(token_handle)), int(information_class),
        ctypes.byref(value), ctypes.sizeof(value), ctypes.byref(returned),
    )
    if not ok:
        raise _win_error("GetTokenInformation")
    return int(value.value)


def _query_token_buffer(token_handle: int, information_class: int):
    _require_windows()
    required = wintypes.DWORD()
    ctypes.set_last_error(0)
    advapi32.GetTokenInformation(
        wintypes.HANDLE(int(token_handle)), int(information_class),
        None, 0, ctypes.byref(required),
    )
    if int(required.value) <= 0:
        raise _win_error("GetTokenInformationSize")
    buffer = ctypes.create_string_buffer(int(required.value))
    returned = wintypes.DWORD()
    ok = advapi32.GetTokenInformation(
        wintypes.HANDLE(int(token_handle)), int(information_class),
        ctypes.cast(buffer, wintypes.LPVOID), int(required.value),
        ctypes.byref(returned),
    )
    if not ok:
        raise _win_error("GetTokenInformation")
    return buffer


def _privilege_name(luid: "LUID") -> str:
    capacity = wintypes.DWORD(256)
    name = ctypes.create_unicode_buffer(int(capacity.value))
    ok = advapi32.LookupPrivilegeNameW(
        None, ctypes.byref(luid), name, ctypes.byref(capacity)
    )
    if not ok:
        raise _win_error("LookupPrivilegeNameW")
    return str(name.value)


def _enabled_privilege_names(token_handle: int) -> tuple[str, ...]:
    buffer = _query_token_buffer(token_handle, TokenPrivileges)
    count = ctypes.cast(
        ctypes.addressof(buffer), ctypes.POINTER(wintypes.DWORD)
    ).contents.value
    offset = ctypes.sizeof(wintypes.DWORD)
    size = ctypes.sizeof(LUID_AND_ATTRIBUTES)
    enabled: list[str] = []
    for index in range(int(count)):
        address = ctypes.addressof(buffer) + offset + index * size
        entry = ctypes.cast(
            address, ctypes.POINTER(LUID_AND_ATTRIBUTES)
        ).contents
        if int(entry.Attributes) & SE_PRIVILEGE_ENABLED:
            enabled.append(_privilege_name(entry.Luid))
    return tuple(sorted(set(enabled), key=str.casefold))


def inspect_restricted_token(token_handle: int) -> RestrictedTokenEvidence:
    token_type = _query_token_dword(token_handle, TokenType)
    has_restrictions = bool(_query_token_dword(token_handle, TokenHasRestrictions))
    sandbox_inert = bool(_query_token_dword(token_handle, TokenSandBoxInert))
    enabled = _enabled_privilege_names(token_handle)
    unexpected = tuple(
        name for name in enabled if name not in ALLOWED_ENABLED_PRIVILEGES
    )
    return RestrictedTokenEvidence(
        token_type=token_type,
        token_has_restrictions=has_restrictions,
        sandbox_inert=sandbox_inert,
        enabled_privileges=enabled,
        unexpected_enabled_privileges=unexpected,
    )


def verify_restricted_primary_token(token_handle: int) -> RestrictedTokenEvidence:
    evidence = inspect_restricted_token(token_handle)
    if not evidence.primary_token:
        raise WindowsRestrictedExecutionError("restricted_token_not_primary")
    if not evidence.token_has_restrictions:
        raise WindowsRestrictedExecutionError("restricted_token_not_filtered")
    if evidence.sandbox_inert:
        raise WindowsRestrictedExecutionError("restricted_token_sandbox_inert_forbidden")
    if evidence.unexpected_enabled_privileges:
        raise WindowsRestrictedExecutionError(
            "restricted_token_unexpected_enabled_privileges:"
            + ",".join(evidence.unexpected_enabled_privileges)
        )
    return evidence


def create_restricted_primary_token() -> RestrictedPrimaryToken:
    """Create and verify a restricted version of the current primary token."""
    _require_windows()
    if RESTRICTED_TOKEN_FLAGS & SANDBOX_INERT:
        raise WindowsRestrictedExecutionError("sandbox_inert_must_never_be_enabled")

    source = wintypes.HANDLE()
    restricted = wintypes.HANDLE()
    ok = advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), RESTRICTED_SOURCE_TOKEN_ACCESS,
        ctypes.byref(source),
    )
    if not ok:
        raise _win_error("OpenProcessToken")

    try:
        ok = advapi32.CreateRestrictedToken(
            source, RESTRICTED_TOKEN_FLAGS, 0, None, 0, None, 0, None,
            ctypes.byref(restricted),
        )
        if not ok:
            raise _win_error("CreateRestrictedToken")
    finally:
        if source.value:
            _close_handle(int(source.value))

    handle = int(restricted.value or 0)
    if not handle:
        raise WindowsRestrictedExecutionError("restricted_token_handle_missing")
    try:
        evidence = verify_restricted_primary_token(handle)
    except Exception:
        _close_handle(handle)
        raise
    return RestrictedPrimaryToken(_handle=handle, evidence=evidence)

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


def _verify_child_process_token(
    process_handle: int,
) -> RestrictedTokenEvidence:
    _require_windows()

    child_token = wintypes.HANDLE()
    ok = advapi32.OpenProcessToken(
        wintypes.HANDLE(int(process_handle)),
        TOKEN_QUERY,
        ctypes.byref(child_token),
    )
    if not ok:
        raise _win_error("OpenProcessTokenChild")

    try:
        return verify_restricted_primary_token(
            int(child_token.value)
        )
    finally:
        if child_token:
            _close_handle(
                int(child_token.value)
            )


def spawn_restricted_suspended_in_job(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    job_name: str | None = None,
    job: Any | None = None,
    stdin_handle: int | None = None,
    stdout_handle: int | None = None,
    stderr_handle: int | None = None,
):
    """
    Create a restricted child suspended, verify its actual child token,
    assign it to the v0.29.1 Job Object boundary, then resume it.

    There is deliberately no unrestricted CreateProcessW fallback.
    """
    _require_windows()

    from .windows_process_tree import (
        SpawnedWindowsProcess,
        create_kill_on_close_job,
    )

    argv = [str(item) for item in command]
    if not argv or not all(argv):
        raise ValueError(
            "command_must_be_non_empty_strings"
        )

    if job is not None and job_name is not None:
        raise ValueError(
            "job_and_job_name_are_mutually_exclusive"
        )

    owns_job = job is None
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
            if owns_job:
                job.close()
            raise ValueError(
                "all_standard_handles_must_be_supplied"
            )

        startup.dwFlags |= STARTF_USESTDHANDLES
        startup.hStdInput = wintypes.HANDLE(
            int(stdin_handle)
        )
        startup.hStdOutput = wintypes.HANDLE(
            int(stdout_handle)
        )
        startup.hStdError = wintypes.HANDLE(
            int(stderr_handle)
        )

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
        with create_restricted_primary_token() as restricted:
            ok = advapi32.CreateProcessAsUserW(
                wintypes.HANDLE(
                    restricted.handle
                ),
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
                raise _win_error(
                    "CreateProcessAsUserW"
                )

        process_created = True

        # The child is still suspended here.
        _verify_child_process_token(
            int(process.hProcess)
        )

        job.assign_process_handle(
            int(process.hProcess)
        )
        assigned_to_job = True

        resume_result = kernel32.ResumeThread(
            process.hThread
        )
        if resume_result == 0xFFFFFFFF:
            raise _win_error("ResumeThread")

        _close_handle(
            int(process.hThread)
        )
        process.hThread = None

        return SpawnedWindowsProcess(
            job=job,
            process_handle=int(
                process.hProcess
            ),
            pid=int(
                process.dwProcessId
            ),
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
                        "TerminateProcess"
                    )
                else:
                    kernel32.WaitForSingleObject(
                        process.hProcess,
                        5000,
                    )

        if process.hThread:
            _close_handle(
                int(process.hThread)
            )

        if process.hProcess:
            _close_handle(
                int(process.hProcess)
            )

        if owns_job:
            try:
                job.close()
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc

        if cleanup_error is not None:
            raise WindowsRestrictedExecutionError(
                "restricted_process_cleanup_failed"
            ) from cleanup_error

        raise original_exc

def run_restricted_contained_capture(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
):
    """
    Run one synchronous v0.29.4 AgentOS process.exec command with both
    Restricted Token and v0.29.1 Job Object containment.

    No caller-selectable unrestricted mode and no CreateProcessW fallback.
    """
    _require_windows()

    from .windows_process_tree import (
        ContainedCompletedProcess,
        _os_handle,
        _read_capture,
    )

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
            proc = spawn_restricted_suspended_in_job(
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
