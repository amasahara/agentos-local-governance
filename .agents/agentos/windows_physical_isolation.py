
"""Windows Native Physical Isolation primitives for AgentOS v0.29.5 Phase 1.

Foundation only. Production sync/async launchers are not switched here.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass

from .windows_restricted_execution import (
    DISABLE_MAX_PRIVILEGE,
    LUA_TOKEN,
    RESTRICTED_TOKEN_FLAGS,
    RestrictedTokenEvidence,
    verify_restricted_primary_token,
)

PHYSICAL_ISOLATION_VERSION = 1
PHYSICAL_ISOLATION_SCOPE = "agentos_mediated_process_execution"
LOW_INTEGRITY_PROFILE = "restricted_low_integrity_v1"

TOKEN_ASSIGN_PRIMARY = 0x0001
TOKEN_DUPLICATE = 0x0002
TOKEN_QUERY = 0x0008
TOKEN_ADJUST_DEFAULT = 0x0080
LOW_INTEGRITY_SOURCE_TOKEN_ACCESS = (
    TOKEN_ASSIGN_PRIMARY | TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ADJUST_DEFAULT
)

TokenIntegrityLevel = 25
SE_GROUP_INTEGRITY = 0x00000020
SECURITY_MANDATORY_LOW_RID = 0x00001000
LOW_INTEGRITY_SID = "S-1-16-4096"


class WindowsPhysicalIsolationUnavailable(RuntimeError):
    pass


class WindowsPhysicalIsolationError(RuntimeError):
    pass


@dataclass(frozen=True)
class IntegrityLevelEvidence:
    sid: str
    rid: int

    @property
    def low_integrity(self) -> bool:
        return self.sid == LOW_INTEGRITY_SID and self.rid == SECURITY_MANDATORY_LOW_RID

    @property
    def verified(self) -> bool:
        return self.low_integrity


@dataclass(frozen=True)
class PhysicalIsolationDescriptor:
    version: int = PHYSICAL_ISOLATION_VERSION
    scope: str = PHYSICAL_ISOLATION_SCOPE
    profile: str = LOW_INTEGRITY_PROFILE
    restricted_token_preserved: bool = True
    low_integrity_token_primitive_present: bool = True
    token_integrity_level_verified: bool = True
    sandbox_mandatory_label_enforced: bool = True
    sync_execution_enforced: bool = True
    async_execution_enforced: bool = True
    low_integrity_attested: bool = True
    host_filesystem_isolation_attested: bool = False
    os_write_confinement_attested: bool = False
    same_user_host_bypass_resistance_claimed: bool = False
    desktop_isolation_attested: bool = False


DESCRIPTOR = PhysicalIsolationDescriptor()


@dataclass
class LowIntegrityRestrictedPrimaryToken:
    _handle: int
    restricted_evidence: RestrictedTokenEvidence
    integrity_evidence: IntegrityLevelEvidence
    _closed: bool = False

    @property
    def handle(self) -> int:
        if self._closed:
            raise WindowsPhysicalIsolationError("low_integrity_token_handle_closed")
        return self._handle

    def close(self) -> None:
        if self._closed:
            return
        handle = self._handle
        self._handle = 0
        self._closed = True
        _close_handle(handle)

    def __enter__(self) -> "LowIntegrityRestrictedPrimaryToken":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def is_supported_host() -> bool:
    return os.name == "nt"


if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("Sid", wintypes.LPVOID),
            ("Attributes", wintypes.DWORD),
        ]

    class TOKEN_MANDATORY_LABEL(ctypes.Structure):
        _fields_ = [("Label", SID_AND_ATTRIBUTES)]

    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

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
    advapi32.SetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD
    ]
    advapi32.SetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID)
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [
        wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    advapi32.GetLengthSid.argtypes = [wintypes.LPVOID]
    advapi32.GetLengthSid.restype = wintypes.DWORD
    advapi32.IsValidSid.argtypes = [wintypes.LPVOID]
    advapi32.IsValidSid.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.argtypes = [wintypes.LPVOID]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [wintypes.LPVOID, wintypes.DWORD]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsPhysicalIsolationUnavailable(
            "windows_physical_isolation_requires_windows"
        )


def _win_error(operation: str) -> WindowsPhysicalIsolationError:
    return WindowsPhysicalIsolationError(
        f"{operation}_failed_winerror_{ctypes.get_last_error()}"
    )


def _close_handle(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    if not kernel32.CloseHandle(wintypes.HANDLE(int(handle))):
        raise _win_error("CloseHandle")


def _local_free(pointer: int | None) -> None:
    if os.name != "nt" or not pointer:
        return
    result = kernel32.LocalFree(wintypes.HLOCAL(int(pointer)))
    if result:
        raise _win_error("LocalFree")


def _query_token_buffer(token_handle: int, information_class: int):
    _require_windows()
    required = wintypes.DWORD()
    ctypes.set_last_error(0)
    advapi32.GetTokenInformation(
        wintypes.HANDLE(int(token_handle)),
        int(information_class),
        None,
        0,
        ctypes.byref(required),
    )
    if int(required.value) <= 0:
        raise _win_error("GetTokenInformationSize")

    buffer = ctypes.create_string_buffer(int(required.value))
    returned = wintypes.DWORD()
    ok = advapi32.GetTokenInformation(
        wintypes.HANDLE(int(token_handle)),
        int(information_class),
        ctypes.cast(buffer, wintypes.LPVOID),
        int(required.value),
        ctypes.byref(returned),
    )
    if not ok:
        raise _win_error("GetTokenInformation")
    return buffer


def _sid_to_string(sid) -> str:
    _require_windows()
    if not sid or not advapi32.IsValidSid(sid):
        raise WindowsPhysicalIsolationError("integrity_sid_invalid")

    value = wintypes.LPWSTR()
    ok = advapi32.ConvertSidToStringSidW(sid, ctypes.byref(value))
    if not ok:
        raise _win_error("ConvertSidToStringSidW")
    try:
        return str(value.value)
    finally:
        if value:
            _local_free(ctypes.cast(value, wintypes.LPVOID).value)


def _sid_integrity_rid(sid) -> int:
    _require_windows()
    if not sid or not advapi32.IsValidSid(sid):
        raise WindowsPhysicalIsolationError("integrity_sid_invalid")

    count_pointer = advapi32.GetSidSubAuthorityCount(sid)
    if not count_pointer:
        raise _win_error("GetSidSubAuthorityCount")
    count = int(count_pointer.contents.value)
    if count <= 0:
        raise WindowsPhysicalIsolationError("integrity_sid_subauthority_missing")

    rid_pointer = advapi32.GetSidSubAuthority(sid, count - 1)
    if not rid_pointer:
        raise _win_error("GetSidSubAuthority")
    return int(rid_pointer.contents.value)


def inspect_token_integrity(token_handle: int) -> IntegrityLevelEvidence:
    buffer = _query_token_buffer(token_handle, TokenIntegrityLevel)
    label = ctypes.cast(
        ctypes.addressof(buffer),
        ctypes.POINTER(TOKEN_MANDATORY_LABEL),
    ).contents
    sid = label.Label.Sid
    return IntegrityLevelEvidence(
        sid=_sid_to_string(sid),
        rid=_sid_integrity_rid(sid),
    )


def verify_low_integrity_token(token_handle: int) -> IntegrityLevelEvidence:
    evidence = inspect_token_integrity(token_handle)
    if evidence.sid != LOW_INTEGRITY_SID:
        raise WindowsPhysicalIsolationError(
            "token_integrity_sid_not_low:" + evidence.sid
        )
    if evidence.rid != SECURITY_MANDATORY_LOW_RID:
        raise WindowsPhysicalIsolationError(
            "token_integrity_rid_not_low:" + str(evidence.rid)
        )
    return evidence


def set_low_integrity_token(token_handle: int) -> IntegrityLevelEvidence:
    _require_windows()
    sid = wintypes.LPVOID()
    ok = advapi32.ConvertStringSidToSidW(
        LOW_INTEGRITY_SID,
        ctypes.byref(sid),
    )
    if not ok:
        raise _win_error("ConvertStringSidToSidW")

    try:
        if not advapi32.IsValidSid(sid):
            raise WindowsPhysicalIsolationError("low_integrity_sid_invalid")

        label = TOKEN_MANDATORY_LABEL()
        label.Label.Sid = sid
        label.Label.Attributes = SE_GROUP_INTEGRITY

        sid_length = int(advapi32.GetLengthSid(sid))
        if sid_length <= 0:
            raise _win_error("GetLengthSid")

        ok = advapi32.SetTokenInformation(
            wintypes.HANDLE(int(token_handle)),
            TokenIntegrityLevel,
            ctypes.byref(label),
            ctypes.sizeof(TOKEN_MANDATORY_LABEL) + sid_length,
        )
        if not ok:
            raise _win_error("SetTokenInformationTokenIntegrityLevel")
    finally:
        if sid.value:
            _local_free(sid.value)

    return verify_low_integrity_token(token_handle)


def create_low_integrity_restricted_primary_token(
) -> LowIntegrityRestrictedPrimaryToken:
    _require_windows()

    if RESTRICTED_TOKEN_FLAGS != (DISABLE_MAX_PRIVILEGE | LUA_TOKEN):
        raise WindowsPhysicalIsolationError("restricted_token_profile_changed")

    source = wintypes.HANDLE()
    restricted = wintypes.HANDLE()

    ok = advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        LOW_INTEGRITY_SOURCE_TOKEN_ACCESS,
        ctypes.byref(source),
    )
    if not ok:
        raise _win_error("OpenProcessTokenLowIntegritySource")

    try:
        ok = advapi32.CreateRestrictedToken(
            source,
            RESTRICTED_TOKEN_FLAGS,
            0,
            None,
            0,
            None,
            0,
            None,
            ctypes.byref(restricted),
        )
        if not ok:
            raise _win_error("CreateRestrictedTokenLowIntegrity")
    finally:
        if source.value:
            _close_handle(int(source.value))

    handle = int(restricted.value or 0)
    if not handle:
        raise WindowsPhysicalIsolationError(
            "low_integrity_restricted_token_handle_missing"
        )

    try:
        restricted_evidence = verify_restricted_primary_token(handle)
        integrity_evidence = set_low_integrity_token(handle)
        restricted_evidence = verify_restricted_primary_token(handle)
    except Exception:
        _close_handle(handle)
        raise

    return LowIntegrityRestrictedPrimaryToken(
        _handle=handle,
        restricted_evidence=restricted_evidence,
        integrity_evidence=integrity_evidence,
    )

# ---------------------------------------------------------------------------
# v0.29.5 Phase 2 — Sandbox Mandatory Integrity Label Boundary
# ---------------------------------------------------------------------------

LABEL_SECURITY_INFORMATION = 0x00000010
SE_FILE_OBJECT = 1
SDDL_REVISION_1 = 1
SYSTEM_MANDATORY_LABEL_ACE_TYPE = 0x11
SYSTEM_MANDATORY_LABEL_NO_WRITE_UP = 0x00000001
OBJECT_INHERIT_ACE = 0x01
CONTAINER_INHERIT_ACE = 0x02
SECURITY_MANDATORY_MEDIUM_RID = 0x00002000
MEDIUM_INTEGRITY_SID = "S-1-16-8192"

LOW_DIRECTORY_LABEL_SDDL = "S:(ML;OICI;NW;;;LW)"
LOW_FILE_LABEL_SDDL = "S:(ML;;NW;;;LW)"


@dataclass(frozen=True)
class MandatoryLabelEvidence:
    path: str
    explicit_label: bool
    sid: str | None
    rid: int
    no_write_up: bool
    ace_flags: int

    @property
    def low_integrity(self) -> bool:
        return (
            self.sid == LOW_INTEGRITY_SID
            and self.rid == SECURITY_MANDATORY_LOW_RID
        )

    @property
    def medium_or_higher(self) -> bool:
        return self.rid >= SECURITY_MANDATORY_MEDIUM_RID

    @property
    def verified_low_no_write_up(self) -> bool:
        return self.low_integrity and self.no_write_up



@dataclass(frozen=True)
class SandboxMandatoryLabelBoundaryEvidence:
    root: str
    labeled_path_count: int
    verified_path_count: int
    root_label: MandatoryLabelEvidence
    low_integrity: bool
    no_write_up: bool
    dacl_verified_path_count: int
    ancestry_traverse_verified_count: int
    current_user_access_verified: bool

if os.name == "nt":
    class ACL(ctypes.Structure):
        _fields_ = [
            ("AclRevision", ctypes.c_ubyte),
            ("Sbz1", ctypes.c_ubyte),
            ("AclSize", ctypes.c_ushort),
            ("AceCount", ctypes.c_ushort),
            ("Sbz2", ctypes.c_ushort),
        ]

    class ACE_HEADER(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", ctypes.c_ushort),
        ]

    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = (
        wintypes.BOOL
    )

    advapi32.GetSecurityDescriptorSacl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorSacl.restype = wintypes.BOOL

    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD

    advapi32.GetAce.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi32.GetAce.restype = wintypes.BOOL


def _security_api_error(
    operation: str,
    code: int,
) -> WindowsPhysicalIsolationError:
    return WindowsPhysicalIsolationError(
        f"{operation}_failed_winerror_{int(code)}"
    )


def _assert_path_not_reparse(
    path: Path,
) -> None:
    import stat

    target = Path(path)

    try:
        info = os.lstat(target)
    except OSError as exc:
        raise WindowsPhysicalIsolationError(
            "mandatory_label_path_missing:"
            + str(target)
        ) from exc

    attributes = int(
        getattr(
            info,
            "st_file_attributes",
            0,
        )
        or 0
    )
    reparse_flag = int(
        getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
    )

    if target.is_symlink() or (
        attributes & reparse_flag
    ):
        raise WindowsPhysicalIsolationError(
            "mandatory_label_reparse_forbidden:"
            + str(target)
        )


def _mandatory_label_sddl_for_path(
    path: Path,
) -> str:
    return (
        LOW_DIRECTORY_LABEL_SDDL
        if Path(path).is_dir()
        else LOW_FILE_LABEL_SDDL
    )


def _set_named_low_mandatory_label(
    path: Path,
) -> None:
    _require_windows()

    target = Path(path)
    _assert_path_not_reparse(target)

    security_descriptor = wintypes.LPVOID()
    descriptor_length = wintypes.DWORD()

    ok = (
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            _mandatory_label_sddl_for_path(target),
            SDDL_REVISION_1,
            ctypes.byref(security_descriptor),
            ctypes.byref(descriptor_length),
        )
    )

    if not ok:
        raise _win_error(
            "ConvertStringSecurityDescriptorToSecurityDescriptorW"
        )

    try:
        present = wintypes.BOOL()
        defaulted = wintypes.BOOL()
        sacl = wintypes.LPVOID()

        ok = advapi32.GetSecurityDescriptorSacl(
            security_descriptor,
            ctypes.byref(present),
            ctypes.byref(sacl),
            ctypes.byref(defaulted),
        )

        if not ok:
            raise _win_error(
                "GetSecurityDescriptorSacl"
            )

        if (
            not present.value
            or not sacl.value
        ):
            raise WindowsPhysicalIsolationError(
                "low_mandatory_label_sacl_missing"
            )

        result = advapi32.SetNamedSecurityInfoW(
            str(target),
            SE_FILE_OBJECT,
            LABEL_SECURITY_INFORMATION,
            None,
            None,
            None,
            sacl,
        )

        if result != 0:
            raise _security_api_error(
                "SetNamedSecurityInfoWLabel",
                int(result),
            )
    finally:
        if security_descriptor.value:
            _local_free(
                security_descriptor.value
            )


def inspect_path_mandatory_label(
    path: Path,
) -> MandatoryLabelEvidence:
    """
    Query one filesystem mandatory integrity label.

    An object without an explicit integrity label is reported as effective
    Medium, matching Windows MIC semantics.
    """
    _require_windows()

    target = Path(path)
    _assert_path_not_reparse(target)
    target = target.absolute()

    sacl = wintypes.LPVOID()
    security_descriptor = wintypes.LPVOID()

    result = advapi32.GetNamedSecurityInfoW(
        str(target),
        SE_FILE_OBJECT,
        LABEL_SECURITY_INFORMATION,
        None,
        None,
        None,
        ctypes.byref(sacl),
        ctypes.byref(security_descriptor),
    )

    if result != 0:
        raise _security_api_error(
            "GetNamedSecurityInfoWLabel",
            int(result),
        )

    try:
        if not sacl.value:
            return MandatoryLabelEvidence(
                path=str(target),
                explicit_label=False,
                sid=None,
                rid=SECURITY_MANDATORY_MEDIUM_RID,
                no_write_up=True,
                ace_flags=0,
            )

        acl = ctypes.cast(
            sacl,
            ctypes.POINTER(ACL),
        ).contents

        for index in range(int(acl.AceCount)):
            ace_pointer = wintypes.LPVOID()

            ok = advapi32.GetAce(
                sacl,
                index,
                ctypes.byref(ace_pointer),
            )

            if not ok:
                raise _win_error("GetAce")

            if not ace_pointer.value:
                continue

            header = ctypes.cast(
                ace_pointer,
                ctypes.POINTER(ACE_HEADER),
            ).contents

            if (
                int(header.AceType)
                != SYSTEM_MANDATORY_LABEL_ACE_TYPE
            ):
                continue

            base = int(ace_pointer.value)
            mask = int(
                ctypes.c_uint32.from_address(
                    base
                    + ctypes.sizeof(ACE_HEADER)
                ).value
            )

            sid_pointer = wintypes.LPVOID(
                base
                + ctypes.sizeof(ACE_HEADER)
                + ctypes.sizeof(wintypes.DWORD)
            )

            return MandatoryLabelEvidence(
                path=str(target),
                explicit_label=True,
                sid=_sid_to_string(
                    sid_pointer
                ),
                rid=_sid_integrity_rid(
                    sid_pointer
                ),
                no_write_up=bool(
                    mask
                    & SYSTEM_MANDATORY_LABEL_NO_WRITE_UP
                ),
                ace_flags=int(
                    header.AceFlags
                ),
            )

        return MandatoryLabelEvidence(
            path=str(target),
            explicit_label=False,
            sid=None,
            rid=SECURITY_MANDATORY_MEDIUM_RID,
            no_write_up=True,
            ace_flags=0,
        )
    finally:
        if security_descriptor.value:
            _local_free(
                security_descriptor.value
            )


def verify_low_mandatory_label(
    path: Path,
) -> MandatoryLabelEvidence:
    evidence = inspect_path_mandatory_label(
        path
    )

    if not evidence.explicit_label:
        raise WindowsPhysicalIsolationError(
            "mandatory_label_not_explicit:"
            + evidence.path
        )

    if not evidence.low_integrity:
        raise WindowsPhysicalIsolationError(
            "mandatory_label_not_low:"
            + evidence.path
        )

    if not evidence.no_write_up:
        raise WindowsPhysicalIsolationError(
            "mandatory_label_no_write_up_missing:"
            + evidence.path
        )

    return evidence


def _sandbox_tree_paths(
    root: Path,
) -> list[Path]:
    root = Path(root)
    _assert_path_not_reparse(root)

    paths = [root]
    stack = [root]

    while stack:
        current = stack.pop()

        if not current.is_dir():
            continue

        for child in current.iterdir():
            _assert_path_not_reparse(child)
            paths.append(child)

            if child.is_dir():
                stack.append(child)

    return paths



def apply_low_integrity_sandbox_boundary(
    sandbox_root: Path,
    *,
    require_controlled_ancestry: bool = False,
) -> SandboxMandatoryLabelBoundaryEvidence:
    """
    Apply the complete Phase 2/3 Windows sandbox boundary.

    Order is deliberate:
    1. establish a current-user DACL path usable by the Restricted/LUA token;
    2. explicitly Low-label every object in the execution sandbox;
    3. verify both DACL and MIC evidence before returning.

    The controlled ancestry receives traverse/read only. It is not Low-labeled.
    The primary project and parents outside *.agentos-sandboxes are untouched.
    """
    _require_windows()

    root = Path(
        sandbox_root
    )
    _assert_path_not_reparse(
        root
    )
    root = root.absolute()

    if not root.is_dir():
        raise WindowsPhysicalIsolationError(
            "sandbox_mandatory_label_root_missing"
        )

    (
        ancestry_count,
        dacl_verified_count,
    ) = ensure_restricted_user_sandbox_dacl(
        root,
        require_controlled_ancestry=(
            require_controlled_ancestry
        ),
    )

    paths = _sandbox_tree_paths(
        root
    )

    for path in reversed(
        paths
    ):
        _set_named_low_mandatory_label(
            path
        )

    verified = [
        verify_low_mandatory_label(
            path
        )
        for path in paths
    ]

    # Re-verify DACL after SACL/MIC updates.
    for path in paths:
        verify_current_user_access_ace(
            path,
            SANDBOX_CURRENT_USER_ACCESS_MASK,
        )

    root_label = next(
        item
        for item in verified
        if Path(
            item.path
        ).absolute()
        == root
    )

    return SandboxMandatoryLabelBoundaryEvidence(
        root=str(
            root
        ),
        labeled_path_count=len(
            paths
        ),
        verified_path_count=len(
            verified
        ),
        root_label=root_label,
        low_integrity=all(
            item.low_integrity
            for item in verified
        ),
        no_write_up=all(
            item.no_write_up
            for item in verified
        ),
        dacl_verified_path_count=(
            dacl_verified_count
        ),
        ancestry_traverse_verified_count=(
            ancestry_count
        ),
        current_user_access_verified=True,
    )

# ---------------------------------------------------------------------------
# v0.29.5 Phase 3 — Synchronous Restricted + Low Integrity Execution
# ---------------------------------------------------------------------------


def _verify_child_process_low_integrity(
    process_handle: int,
) -> IntegrityLevelEvidence:
    _require_windows()

    child_token = wintypes.HANDLE()

    ok = advapi32.OpenProcessToken(
        wintypes.HANDLE(
            int(process_handle)
        ),
        TOKEN_QUERY,
        ctypes.byref(
            child_token
        ),
    )

    if not ok:
        raise _win_error(
            "OpenProcessTokenLowIntegrityChild"
        )

    try:
        return verify_low_integrity_token(
            int(
                child_token.value
            )
        )
    finally:
        if child_token.value:
            _close_handle(
                int(
                    child_token.value
                )
            )


def spawn_low_integrity_restricted_suspended_in_job(
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
    Create a Restricted + Low-IL child suspended, verify the actual child
    token for both contracts, assign it to the Job Object, then resume.

    No unrestricted or Medium-IL fallback exists in this primitive.
    """
    _require_windows()

    from . import windows_restricted_execution as _restricted
    from .windows_process_tree import (
        SpawnedWindowsProcess,
        create_kill_on_close_job,
    )

    argv = tuple(
        str(item)
        for item in command
    )

    if (
        not argv
        or not all(
            argv
        )
    ):
        raise ValueError(
            "command_must_be_non_empty_strings"
        )

    if (
        job is not None
        and job_name is not None
    ):
        raise ValueError(
            "job_and_job_name_are_mutually_exclusive"
        )

    owns_job = job is None

    if job is None:
        job = create_kill_on_close_job(
            name=job_name
        )

    startup = (
        _restricted.STARTUPINFOW()
    )
    startup.cb = ctypes.sizeof(
        startup
    )

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

        startup.dwFlags |= (
            _restricted.STARTF_USESTDHANDLES
        )
        startup.hStdInput = (
            wintypes.HANDLE(
                int(
                    stdin_handle
                )
            )
        )
        startup.hStdOutput = (
            wintypes.HANDLE(
                int(
                    stdout_handle
                )
            )
        )
        startup.hStdError = (
            wintypes.HANDLE(
                int(
                    stderr_handle
                )
            )
        )

    process = (
        _restricted.PROCESS_INFORMATION()
    )

    command_line = (
        ctypes.create_unicode_buffer(
            subprocess.list2cmdline(
                list(
                    argv
                )
            )
        )
    )

    env_block = (
        _restricted._environment_block(
            env
        )
    )

    creation_flags = (
        _restricted.CREATE_SUSPENDED
        | (
            _restricted.CREATE_UNICODE_ENVIRONMENT
            if env_block is not None
            else 0
        )
    )

    process_created = False
    assigned_to_job = False

    try:
        with create_low_integrity_restricted_primary_token() as token:
            ok = (
                _restricted.advapi32.CreateProcessAsUserW(
                    wintypes.HANDLE(
                        token.handle
                    ),
                    None,
                    command_line,
                    None,
                    None,
                    bool(
                        inherit_std_handles
                    ),
                    creation_flags,
                    (
                        ctypes.cast(
                            env_block,
                            wintypes.LPVOID,
                        )
                        if env_block
                        is not None
                        else None
                    ),
                    (
                        str(
                            Path(
                                cwd
                            ).resolve()
                        )
                        if cwd
                        is not None
                        else None
                    ),
                    ctypes.byref(
                        startup
                    ),
                    ctypes.byref(
                        process
                    ),
                )
            )

            if not ok:
                raise _restricted._win_error(
                    "CreateProcessAsUserWLowIntegrity"
                )

        process_created = True

        # The child remains suspended through both token verifications.
        _restricted._verify_child_process_token(
            int(
                process.hProcess
            )
        )

        _verify_child_process_low_integrity(
            int(
                process.hProcess
            )
        )

        job.assign_process_handle(
            int(
                process.hProcess
            )
        )
        assigned_to_job = True

        resume_result = (
            _restricted.kernel32.ResumeThread(
                process.hThread
            )
        )

        if (
            resume_result
            == 0xFFFFFFFF
        ):
            raise _restricted._win_error(
                "ResumeThreadLowIntegrity"
            )

        _restricted._close_handle(
            int(
                process.hThread
            )
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

        if (
            process_created
            and process.hProcess
        ):
            terminated = False

            if assigned_to_job:
                try:
                    job.terminate(
                        1
                    )
                    terminated = True
                except Exception:
                    pass

            if not terminated:
                if not (
                    _restricted.kernel32.TerminateProcess(
                        process.hProcess,
                        1,
                    )
                ):
                    cleanup_error = (
                        _restricted._win_error(
                            "TerminateProcessLowIntegrity"
                        )
                    )
                else:
                    _restricted.kernel32.WaitForSingleObject(
                        process.hProcess,
                        5000,
                    )

        if process.hThread:
            _restricted._close_handle(
                int(
                    process.hThread
                )
            )

        if process.hProcess:
            _restricted._close_handle(
                int(
                    process.hProcess
                )
            )

        if owns_job:
            try:
                job.close()
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc

        if cleanup_error is not None:
            raise WindowsPhysicalIsolationError(
                "low_integrity_process_cleanup_failed"
            ) from cleanup_error

        raise original_exc


def run_low_integrity_restricted_contained_capture(
    command: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
):
    """
    Run one synchronous AgentOS process with Restricted Token + Low IL +
    Job Object containment.

    Standard streams are explicit trusted inherited capture handles opened by
    the AgentOS parent. This does not broaden filesystem-isolation claims.
    """
    _require_windows()

    from .windows_process_tree import (
        ContainedCompletedProcess,
        _os_handle,
        _read_capture,
    )

    argv = tuple(
        str(item)
        for item in command
    )

    if (
        not argv
        or not all(
            argv
        )
    ):
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
            _os_handle(
                stdin_file
            ),
            _os_handle(
                stdout_file
            ),
            _os_handle(
                stderr_file
            ),
        )

        proc = None

        try:
            proc = (
                spawn_low_integrity_restricted_suspended_in_job(
                    argv,
                    cwd=cwd,
                    env=env,
                    stdin_handle=handles[
                        0
                    ],
                    stdout_handle=handles[
                        1
                    ],
                    stderr_handle=handles[
                        2
                    ],
                )
            )

            try:
                returncode = (
                    proc.wait(
                        timeout=timeout
                    )
                )
            except TimeoutError as exc:
                proc.terminate_tree(
                    124
                )

                try:
                    proc.wait(
                        timeout=5.0
                    )
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
                    list(
                        argv
                    ),
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

# ---------------------------------------------------------------------------
# v0.29.5 Phase 3 repair — Restricted/LUA sandbox DACL accessibility
# ---------------------------------------------------------------------------

TokenUser = 1

DACL_SECURITY_INFORMATION = 0x00000004

ACCESS_ALLOWED_ACE_TYPE = 0x00

GRANT_ACCESS = 1
NO_MULTIPLE_TRUSTEE = 0
TRUSTEE_IS_SID = 0
TRUSTEE_IS_USER = 1

NO_INHERITANCE = 0x0
SUB_CONTAINERS_AND_OBJECTS_INHERIT = 0x3

FILE_READ_DATA = 0x0001
FILE_WRITE_DATA = 0x0002
FILE_APPEND_DATA = 0x0004
FILE_READ_EA = 0x0008
FILE_WRITE_EA = 0x0010
FILE_EXECUTE = 0x0020
FILE_DELETE_CHILD = 0x0040
FILE_READ_ATTRIBUTES = 0x0080
FILE_WRITE_ATTRIBUTES = 0x0100

DELETE = 0x00010000
READ_CONTROL = 0x00020000
SYNCHRONIZE = 0x00100000

SANDBOX_CURRENT_USER_ACCESS_MASK = (
    FILE_READ_DATA
    | FILE_WRITE_DATA
    | FILE_APPEND_DATA
    | FILE_READ_EA
    | FILE_WRITE_EA
    | FILE_EXECUTE
    | FILE_DELETE_CHILD
    | FILE_READ_ATTRIBUTES
    | FILE_WRITE_ATTRIBUTES
    | DELETE
    | READ_CONTROL
    | SYNCHRONIZE
)

SANDBOX_ANCESTRY_TRAVERSE_MASK = (
    FILE_READ_DATA
    | FILE_READ_EA
    | FILE_EXECUTE
    | FILE_READ_ATTRIBUTES
    | READ_CONTROL
    | SYNCHRONIZE
)


if os.name == "nt":
    class TOKEN_USER(
        ctypes.Structure
    ):
        _fields_ = [
            (
                "User",
                SID_AND_ATTRIBUTES,
            ),
        ]

    class TRUSTEE_W(
        ctypes.Structure
    ):
        pass

    TRUSTEE_W._fields_ = [
        (
            "pMultipleTrustee",
            ctypes.POINTER(
                TRUSTEE_W
            ),
        ),
        (
            "MultipleTrusteeOperation",
            ctypes.c_int,
        ),
        (
            "TrusteeForm",
            ctypes.c_int,
        ),
        (
            "TrusteeType",
            ctypes.c_int,
        ),
        (
            "ptstrName",
            wintypes.LPWSTR,
        ),
    ]

    class EXPLICIT_ACCESS_W(
        ctypes.Structure
    ):
        _fields_ = [
            (
                "grfAccessPermissions",
                wintypes.DWORD,
            ),
            (
                "grfAccessMode",
                ctypes.c_int,
            ),
            (
                "grfInheritance",
                wintypes.DWORD,
            ),
            (
                "Trustee",
                TRUSTEE_W,
            ),
        ]

    advapi32.SetEntriesInAclW.argtypes = [
        wintypes.ULONG,
        ctypes.POINTER(
            EXPLICIT_ACCESS_W
        ),
        wintypes.LPVOID,
        ctypes.POINTER(
            wintypes.LPVOID
        ),
    ]
    advapi32.SetEntriesInAclW.restype = (
        wintypes.DWORD
    )

    advapi32.EqualSid.argtypes = [
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    advapi32.EqualSid.restype = (
        wintypes.BOOL
    )


def _current_process_user_sid():
    _require_windows()

    token = wintypes.HANDLE()

    ok = advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_QUERY,
        ctypes.byref(
            token
        ),
    )

    if not ok:
        raise _win_error(
            "OpenProcessTokenCurrentUser"
        )

    try:
        buffer = _query_token_buffer(
            int(
                token.value
            ),
            TokenUser,
        )
    finally:
        if token.value:
            _close_handle(
                int(
                    token.value
                )
            )

    user = ctypes.cast(
        ctypes.addressof(
            buffer
        ),
        ctypes.POINTER(
            TOKEN_USER
        ),
    ).contents

    sid = user.User.Sid

    if not sid:
        raise WindowsPhysicalIsolationError(
            "current_user_sid_missing"
        )

    if not advapi32.IsValidSid(
        sid
    ):
        raise WindowsPhysicalIsolationError(
            "current_user_sid_invalid"
        )

    return (
        buffer,
        sid,
    )


def _get_named_dacl(
    path: Path,
):
    _require_windows()

    dacl = wintypes.LPVOID()
    security_descriptor = (
        wintypes.LPVOID()
    )

    result = (
        advapi32.GetNamedSecurityInfoW(
            str(
                Path(
                    path
                ).absolute()
            ),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(
                dacl
            ),
            None,
            ctypes.byref(
                security_descriptor
            ),
        )
    )

    if result != 0:
        raise _security_api_error(
            "GetNamedSecurityInfoWDacl",
            int(
                result
            ),
        )

    return (
        dacl,
        security_descriptor,
    )


def _grant_current_user_access(
    path: Path,
    access_mask: int,
    *,
    inherit: bool,
) -> None:
    """
    Add one current-user allow ACE while preserving the existing DACL.

    WRITE_DAC, WRITE_OWNER and ACCESS_SYSTEM_SECURITY are deliberately not
    granted to the Low worker.
    """
    _require_windows()

    target = Path(
        path
    ).absolute()

    _assert_path_not_reparse(
        target
    )

    sid_buffer, sid = (
        _current_process_user_sid()
    )

    dacl = wintypes.LPVOID()
    security_descriptor = (
        wintypes.LPVOID()
    )
    new_acl = wintypes.LPVOID()

    try:
        (
            dacl,
            security_descriptor,
        ) = _get_named_dacl(
            target
        )

        trustee = TRUSTEE_W()
        trustee.pMultipleTrustee = None
        trustee.MultipleTrusteeOperation = (
            NO_MULTIPLE_TRUSTEE
        )
        trustee.TrusteeForm = (
            TRUSTEE_IS_SID
        )
        trustee.TrusteeType = (
            TRUSTEE_IS_USER
        )
        trustee.ptstrName = ctypes.cast(
            sid,
            wintypes.LPWSTR,
        )

        entry = EXPLICIT_ACCESS_W()
        entry.grfAccessPermissions = (
            int(
                access_mask
            )
        )
        entry.grfAccessMode = (
            GRANT_ACCESS
        )
        entry.grfInheritance = (
            SUB_CONTAINERS_AND_OBJECTS_INHERIT
            if inherit
            else NO_INHERITANCE
        )
        entry.Trustee = trustee

        result = (
            advapi32.SetEntriesInAclW(
                1,
                ctypes.byref(
                    entry
                ),
                dacl,
                ctypes.byref(
                    new_acl
                ),
            )
        )

        if result != 0:
            raise _security_api_error(
                "SetEntriesInAclWCurrentUser",
                int(
                    result
                ),
            )

        if not new_acl.value:
            raise WindowsPhysicalIsolationError(
                "current_user_dacl_new_acl_missing"
            )

        result = (
            advapi32.SetNamedSecurityInfoW(
                str(
                    target
                ),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION,
                None,
                None,
                new_acl,
                None,
            )
        )

        if result != 0:
            raise _security_api_error(
                "SetNamedSecurityInfoWCurrentUserDacl",
                int(
                    result
                ),
            )

    finally:
        # Keep sid_buffer alive through SetEntriesInAclW / SetNamedSecurityInfoW.
        _ = sid_buffer

        if new_acl.value:
            _local_free(
                new_acl.value
            )

        if security_descriptor.value:
            _local_free(
                security_descriptor.value
            )


def verify_current_user_access_ace(
    path: Path,
    required_mask: int,
) -> bool:
    _require_windows()

    target = Path(
        path
    ).absolute()

    sid_buffer, user_sid = (
        _current_process_user_sid()
    )

    dacl = wintypes.LPVOID()
    security_descriptor = (
        wintypes.LPVOID()
    )

    try:
        (
            dacl,
            security_descriptor,
        ) = _get_named_dacl(
            target
        )

        if not dacl.value:
            raise WindowsPhysicalIsolationError(
                "sandbox_dacl_missing:"
                + str(
                    target
                )
            )

        acl = ctypes.cast(
            dacl,
            ctypes.POINTER(
                ACL
            ),
        ).contents

        for index in range(
            int(
                acl.AceCount
            )
        ):
            ace_pointer = (
                wintypes.LPVOID()
            )

            ok = advapi32.GetAce(
                dacl,
                index,
                ctypes.byref(
                    ace_pointer
                ),
            )

            if not ok:
                raise _win_error(
                    "GetAceDacl"
                )

            if not ace_pointer.value:
                continue

            header = ctypes.cast(
                ace_pointer,
                ctypes.POINTER(
                    ACE_HEADER
                ),
            ).contents

            if (
                int(
                    header.AceType
                )
                != ACCESS_ALLOWED_ACE_TYPE
            ):
                continue

            base = int(
                ace_pointer.value
            )

            mask = int(
                ctypes.c_uint32.from_address(
                    base
                    + ctypes.sizeof(
                        ACE_HEADER
                    )
                ).value
            )

            ace_sid = wintypes.LPVOID(
                base
                + ctypes.sizeof(
                    ACE_HEADER
                )
                + ctypes.sizeof(
                    wintypes.DWORD
                )
            )

            if not advapi32.EqualSid(
                user_sid,
                ace_sid,
            ):
                continue

            if (
                mask
                & int(
                    required_mask
                )
            ) == int(
                required_mask
            ):
                return True

        raise WindowsPhysicalIsolationError(
            "sandbox_current_user_access_ace_missing:"
            + str(
                target
            )
        )

    finally:
        _ = sid_buffer

        if security_descriptor.value:
            _local_free(
                security_descriptor.value
            )


def _sandbox_controlled_ancestry(
    root: Path,
) -> list[Path]:
    """
    Return only the AgentOS-owned sandbox hierarchy above one execution root.

    The first ancestor must be the *.agentos-sandboxes directory. No parent
    outside that controlled hierarchy is modified.
    """
    target = Path(
        root
    ).absolute()

    ancestors = list(
        target.parents
    )

    anchor = None

    for candidate in ancestors:
        if (
            candidate.name.startswith(
                "."
            )
            and candidate.name.endswith(
                ".agentos-sandboxes"
            )
        ):
            anchor = candidate
            break

    if anchor is None:
        raise WindowsPhysicalIsolationError(
            "sandbox_controlled_ancestry_anchor_missing"
        )

    chain = []
    current = target.parent

    while True:
        chain.append(
            current
        )

        if current == anchor:
            break

        if current.parent == current:
            raise WindowsPhysicalIsolationError(
                "sandbox_controlled_ancestry_escape"
            )

        current = current.parent

    chain.reverse()

    return chain


def ensure_restricted_user_sandbox_dacl(
    sandbox_root: Path,
    *,
    require_controlled_ancestry: bool = False,
) -> tuple[int, int]:
    """
    Make the AgentOS-owned sandbox traversable by the Restricted/LUA user SID,
    and make all execution-root objects readable/writable/executable by that
    same user SID.

    This preserves all existing DACL ACEs and never grants Everyone/Users.
    """
    _require_windows()

    root = Path(
        sandbox_root
    ).absolute()

    ancestry: list[Path] = []

    if require_controlled_ancestry:
        ancestry = (
            _sandbox_controlled_ancestry(
                root
            )
        )

    for directory in ancestry:
        _assert_path_not_reparse(
            directory
        )
        _grant_current_user_access(
            directory,
            SANDBOX_ANCESTRY_TRAVERSE_MASK,
            inherit=False,
        )
        verify_current_user_access_ace(
            directory,
            SANDBOX_ANCESTRY_TRAVERSE_MASK,
        )

    paths = _sandbox_tree_paths(
        root
    )

    for path in paths:
        _grant_current_user_access(
            path,
            SANDBOX_CURRENT_USER_ACCESS_MASK,
            inherit=path.is_dir(),
        )

    for path in paths:
        verify_current_user_access_ace(
            path,
            SANDBOX_CURRENT_USER_ACCESS_MASK,
        )

    return (
        len(
            ancestry
        ),
        len(
            paths
        ),
    )
