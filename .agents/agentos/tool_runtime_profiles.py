"""
File: .agents/agentos/tool_runtime_profiles.py

Purpose:
    Provide the v0.29.2 preactivation foundation for deterministic tool runtime
    profiles and Windows-oriented sandbox workspace layout.

Scope:
    This module prepares workspace/profile contracts only. It does not claim
    restricted-token execution, Low Integrity, arbitrary host containment, or
    general OS process isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

RUNTIME_PROFILE_VERSION = 1
SANDBOX_WORKSPACE_VERSION = 1
SANDBOX_CONFIGURATION_VERSION = 1
SANDBOX_SCOPE = "agentos_mediated_process_execution"

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_COPY_EXCLUDES = {".agents", ".git", "__pycache__"}

_DEFAULT_RUNTIME_PROFILES: dict[str, dict[str, Any]] = {
    "inspect": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "inspect",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
    "test": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "test",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
    "build": {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": "build",
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    },
}


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha(value: Any) -> str:
    payload = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_key(value: str, *, label: str) -> str:
    key = str(value or "").strip()
    if not _SAFE_KEY.fullmatch(key) or key in {".", ".."}:
        raise ValueError(f"unsafe_{label}")
    return key


def _reparse_kind(path: Path) -> str | None:
    """Return link/reparse kind without following the filesystem object."""
    if path.is_symlink():
        return "symlink"

    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return "junction"
        except OSError:
            pass

    try:
        info = os.lstat(path)
    except OSError:
        return None

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

    if attributes & reparse_flag:
        return "reparse_point"

    return None


def _assert_not_reparse(
    path: Path,
    *,
    label: str,
) -> None:
    kind = _reparse_kind(path)
    if kind is not None:
        raise RuntimeError(
            f"{label}_reparse_forbidden:"
            f"{kind}:"
            f"{path.name}"
        )


def _bounded_destination(
    root: Path,
    name: str,
) -> Path:
    """
    Build exactly one child path beneath the snapshot root.

    The helper is intentionally stricter than Path.relative_to(): paths such
    as ``root / "../escape"`` are lexically below ``root`` before
    normalization, so a relative_to-only check is insufficient.
    """
    child = Path(name)

    if (
        child.is_absolute()
        or len(child.parts) != 1
        or child.parts[0] in {"", ".", ".."}
    ):
        raise RuntimeError(
            "sandbox_snapshot_destination_escape"
        )

    destination = root / child

    base_resolved = root.resolve(
        strict=False
    )
    destination_resolved = destination.resolve(
        strict=False
    )

    try:
        destination_resolved.relative_to(
            base_resolved
        )
    except ValueError as exc:
        raise RuntimeError(
            "sandbox_snapshot_destination_escape"
        ) from exc

    return destination


def default_runtime_profiles() -> dict[str, dict[str, Any]]:
    """Return a deep data copy of the built-in v0.29.2 profile registry."""
    return json.loads(json.dumps(_DEFAULT_RUNTIME_PROFILES))


def _validate_profile(
    name: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise RuntimeError("tool_runtime_profile_must_be_object")

    expected = {
        "profile_version": RUNTIME_PROFILE_VERSION,
        "command_profile": name,
        "source_mode": "snapshot_copy",
        "writable_scope": "sandbox_only",
        "persistent_workspace_writes": False,
        "network_policy": "none",
        "sandbox_temp": True,
        "sandbox_cache": True,
        "sandbox_home": True,
        "package_cache_mode": "sandbox_local",
        "python_bytecode_cache": "sandbox_local",
    }

    unknown = sorted(set(profile) - set(expected))
    if unknown:
        raise RuntimeError(
            "tool_runtime_profile_unknown_fields:"
            + _canonical(unknown)
        )

    missing = sorted(set(expected) - set(profile))
    if missing:
        raise RuntimeError(
            "tool_runtime_profile_missing_fields:"
            + _canonical(missing)
        )

    mismatches = {
        key: {
            "expected": value,
            "actual": profile.get(key),
        }
        for key, value in expected.items()
        if profile.get(key) != value
    }

    if mismatches:
        raise RuntimeError(
            "tool_runtime_profile_invariant_mismatch:"
            + _canonical(mismatches)
        )

    return dict(profile)

CREDENTIAL_REFERENCE_VERSION = 1
CREDENTIAL_REFERENCE_SCHEME = "secret"
CREDENTIAL_RESOLVER_CONTRACT = "secret-resolver-v1"
PROCESS_CREDENTIAL_CAPABILITY = "process.exec.credential"

_CREDENTIAL_BINDING_FIELDS = {
    "binding_id",
    "credential_ref",
    "target_env",
    "secret_field",
}

_CREDENTIAL_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "AUTH",
    "COOKIE",
    "CREDENTIAL",
)

_CREDENTIAL_RESERVED_ENV = {
    "PATH",
    "PYTHONPATH",
    "HOME",
    "USERPROFILE",
    "TMP",
    "TEMP",
    "TMPDIR",
    "SYSTEMROOT",
    "WINDIR",
    "XDG_CACHE_HOME",
    "PIP_CACHE_DIR",
    "PYTHONPYCACHEPREFIX",
    "NPM_CONFIG_CACHE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSH_AUTH_SOCK",
}


def _validate_credential_alias_reference(value: Any) -> str:
    ref = str(value or "").strip()

    if not ref.startswith("secret://"):
        raise RuntimeError(
            "credential_reference_must_use_secret_alias"
        )

    alias = ref[len("secret://"):]
    if (
        not alias
        or "/" in alias
        or "\\" in alias
        or "?" in alias
        or "#" in alias
        or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
            alias,
        )
    ):
        raise RuntimeError(
            "credential_reference_alias_invalid"
        )

    return "secret://" + alias


def _validate_credential_target_env(value: Any) -> str:
    target = str(value or "").strip()

    if not re.fullmatch(
        r"[A-Z_][A-Z0-9_]{0,127}",
        target,
    ):
        raise RuntimeError(
            "credential_target_env_invalid"
        )

    if target.upper() in _CREDENTIAL_RESERVED_ENV:
        raise RuntimeError(
            "credential_target_env_reserved"
        )

    if not any(
        marker in target.upper()
        for marker in _CREDENTIAL_ENV_MARKERS
    ):
        raise RuntimeError(
            "credential_target_env_must_be_secret_classified"
        )

    return target


def _validate_credential_secret_field(value: Any) -> str:
    field = str(value or "").strip()

    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_.-]{0,127}",
        field,
    ):
        raise RuntimeError(
            "credential_secret_field_invalid"
        )

    return field


def _normalize_credential_binding(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RuntimeError(
            "credential_binding_must_be_object"
        )

    unknown = sorted(
        set(value)
        - _CREDENTIAL_BINDING_FIELDS
    )
    missing = sorted(
        _CREDENTIAL_BINDING_FIELDS
        - set(value)
    )

    if unknown:
        raise RuntimeError(
            "credential_binding_unknown_fields:"
            + _canonical(unknown)
        )

    if missing:
        raise RuntimeError(
            "credential_binding_missing_fields:"
            + _canonical(missing)
        )

    binding_id = str(
        value.get("binding_id")
        or ""
    ).strip()

    if not re.fullmatch(
        r"[a-z][a-z0-9._-]{0,63}",
        binding_id,
    ):
        raise RuntimeError(
            "credential_binding_id_invalid"
        )

    return {
        "binding_id": binding_id,
        "credential_ref": _validate_credential_alias_reference(
            value.get("credential_ref")
        ),
        "target_env": _validate_credential_target_env(
            value.get("target_env")
        ),
        "secret_field": _validate_credential_secret_field(
            value.get("secret_field")
        ),
    }


def credential_reference_contract_from_policy(
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate and canonicalize the v0.29.3 credential reference contract.

    Phase 2 is reference-only: it does not resolve secret material and does not
    project credential values into a child process.
    """
    if not isinstance(policy, dict):
        raise RuntimeError(
            "credential_reference_policy_must_be_object"
        )

    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        raise RuntimeError(
            "credential_reference_policy_section_missing"
        )

    required_true = [
        'credential_reference_contract_enabled',
        'credential_reference_secret_alias_only',
        'credential_reference_hash_required',
        'credential_raw_values_forbidden',
        'credential_values_persisted_forbidden',
    ]
    required_false = [
        'caller_credential_reference_override_allowed',
        'caller_raw_credential_override_allowed',
        'windows_file_secret_process_projection_attested',
    ]

    activated = (
        str(policy.get("version") or "").strip()
        == "0.29.3"
    )

    if activated:
        required_true.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_attested',
                'credential_boundary_enabled',
            )
        )
    else:
        required_false.extend(
            (
                'credential_environment_projection_enabled',
                'credential_boundary_attested',
                'credential_boundary_enabled',
            )
        )


    bad_true = [
        key
        for key in required_true
        if section.get(key) is not True
    ]
    bad_false = [
        key
        for key in required_false
        if section.get(key) is not False
    ]

    if bad_true or bad_false:
        raise RuntimeError(
            "credential_reference_contract_invalid:"
            + _canonical(
                {
                    "required_true": bad_true,
                    "required_false": bad_false,
                }
            )
        )

    if int(
        section.get(
            "credential_reference_version",
            0,
        )
    ) != CREDENTIAL_REFERENCE_VERSION:
        raise RuntimeError(
            "credential_reference_version_invalid"
        )

    if (
        section.get(
            "credential_reference_scheme"
        )
        != CREDENTIAL_REFERENCE_SCHEME
    ):
        raise RuntimeError(
            "credential_reference_scheme_invalid"
        )

    if (
        section.get(
            "credential_resolver_contract"
        )
        != CREDENTIAL_RESOLVER_CONTRACT
    ):
        raise RuntimeError(
            "credential_resolver_contract_invalid"
        )

    if (
        section.get(
            "process_credential_capability"
        )
        != PROCESS_CREDENTIAL_CAPABILITY
    ):
        raise RuntimeError(
            "process_credential_capability_invalid"
        )

    configured = section.get(
        "credential_bindings"
    )
    if not isinstance(configured, dict):
        raise RuntimeError(
            "credential_bindings_must_be_object"
        )

    known = set(
        section.get(
            "known_profiles",
            [],
        )
    )

    if set(configured) != known:
        raise RuntimeError(
            "credential_binding_profile_set_mismatch"
        )

    normalized: dict[str, list[dict[str, str]]] = {}

    for profile in sorted(known):
        bindings = configured.get(profile)

        if not isinstance(bindings, list):
            raise RuntimeError(
                "credential_profile_bindings_must_be_list"
            )

        items = [
            _normalize_credential_binding(
                item
            )
            for item in bindings
        ]

        ids = [
            item["binding_id"]
            for item in items
        ]
        targets = [
            item["target_env"]
            for item in items
        ]

        if len(ids) != len(set(ids)):
            raise RuntimeError(
                "credential_binding_id_duplicate"
            )

        if len(targets) != len(set(targets)):
            raise RuntimeError(
                "credential_target_env_duplicate"
            )

        normalized[profile] = sorted(
            items,
            key=lambda item: (
                item["binding_id"],
                item["target_env"],
            ),
        )

    payload = {
        "credential_reference_version": (
            CREDENTIAL_REFERENCE_VERSION
        ),
        "credential_reference_scheme": (
            CREDENTIAL_REFERENCE_SCHEME
        ),
        "credential_resolver_contract": (
            CREDENTIAL_RESOLVER_CONTRACT
        ),
        "process_credential_capability": (
            PROCESS_CREDENTIAL_CAPABILITY
        ),
        "credential_bindings": normalized,
    }

    return {
        **payload,
        "credential_reference_hash": _sha(
            payload
        ),
    }


def credential_bindings_for_profile(
    command_profile: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    contract = (
        credential_reference_contract_from_policy(
            policy
        )
    )
    name = str(
        command_profile
        or ""
    ).strip().lower()

    if name not in contract[
        "credential_bindings"
    ]:
        raise RuntimeError(
            "credential_binding_profile_unknown"
        )

    bindings = contract[
        "credential_bindings"
    ][name]

    binding_payload = {
        "profile": name,
        "bindings": bindings,
        "credential_reference_hash": contract[
            "credential_reference_hash"
        ],
    }

    return {
        "profile": name,
        "bindings": bindings,
        "binding_count": len(bindings),
        "binding_hash": _sha(
            binding_payload
        ),
        "credential_reference_hash": contract[
            "credential_reference_hash"
        ],
        "credential_reference_version": contract[
            "credential_reference_version"
        ],
        "credential_resolver_contract": contract[
            "credential_resolver_contract"
        ],
        "process_credential_capability": contract[
            "process_credential_capability"
        ],
        "secret_values_included": False,
    }

def sandbox_configuration_from_policy(
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the governed v0.29.3 sandbox configuration contract."""
    if not isinstance(policy, dict):
        raise RuntimeError(
            "sandbox_configuration_policy_must_be_object"
        )

    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        raise RuntimeError(
            "sandbox_configuration_policy_section_missing"
        )

    required_true = [
        'sandbox_configuration_contract_enabled',
        'sandbox_configuration_hash_required',
        'configured_profiles_must_match_known_profiles',
        'security_invariants_runtime_enforced',
    ]
    required_false = [
        'unknown_profile_fields_allowed',
        'caller_configuration_override_allowed',
    ]

    activated = (
        str(policy.get("version") or "").strip()
        == "0.29.3"
    )

    if activated:
        required_true.extend(
            (
                'sandbox_configuration_attested',
                'credential_boundary_enabled',
            )
        )
    else:
        required_false.extend(
            (
                'sandbox_configuration_attested',
                'credential_boundary_enabled',
            )
        )


    bad_true = [
        key
        for key in required_true
        if section.get(key) is not True
    ]
    bad_false = [
        key
        for key in required_false
        if section.get(key) is not False
    ]

    if bad_true or bad_false:
        raise RuntimeError(
            "sandbox_configuration_contract_invalid:"
            + _canonical(
                {
                    "required_true": bad_true,
                    "required_false": bad_false,
                }
            )
        )

    if int(
        section.get(
            "sandbox_configuration_version",
            0,
        )
    ) != SANDBOX_CONFIGURATION_VERSION:
        raise RuntimeError(
            "sandbox_configuration_version_invalid"
        )

    if (
        section.get("sandbox_configuration_source")
        != "effective_policy"
    ):
        raise RuntimeError(
            "sandbox_configuration_source_invalid"
        )

    configured = section.get(
        "configured_profiles"
    )
    if not isinstance(configured, dict):
        raise RuntimeError(
            "sandbox_configuration_profiles_must_be_object"
        )

    known = set(
        section.get(
            "known_profiles",
            [],
        )
    )
    if known != set(_DEFAULT_RUNTIME_PROFILES):
        raise RuntimeError(
            "sandbox_configuration_known_profiles_invalid"
        )

    if set(configured) != known:
        raise RuntimeError(
            "sandbox_configuration_profile_set_mismatch"
        )

    validated = {
        name: _validate_profile(
            name,
            configured[name],
        )
        for name in sorted(known)
    }

    credential_contract = (
        credential_reference_contract_from_policy(
            policy
        )
    )

    payload = {
        "configuration_version": (
            SANDBOX_CONFIGURATION_VERSION
        ),
        "configuration_source": (
            "effective_policy"
        ),
        "profiles": validated,
        "credential_reference_version": (
            credential_contract[
                "credential_reference_version"
            ]
        ),
        "credential_reference_hash": (
            credential_contract[
                "credential_reference_hash"
            ]
        ),
        "credential_bindings": (
            credential_contract[
                "credential_bindings"
            ]
        ),
    }

    return {
        **payload,
        "configuration_hash": _sha(
            payload
        ),
    }

def resolve_runtime_profile_from_policy(
    command_profile: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Resolve a policy-bound profile.

    Historical internal tests may provide a minimal synthetic policy without
    the v0.29.3 configuration section. That compatibility path returns the
    v0.29.2 built-in profile. Real AgentOS execution uses load_policy(root),
    which contains and validates the governed configuration contract.
    """
    section = (
        policy.get(
            "sandbox_workspace_runtime_profile_policy"
        )
        if isinstance(policy, dict)
        else None
    )

    if (
        not isinstance(section, dict)
        or "sandbox_configuration_contract_enabled"
        not in section
    ):
        return resolve_runtime_profile(
            command_profile
        )

    configuration = (
        sandbox_configuration_from_policy(
            policy
        )
    )

    resolved = resolve_runtime_profile(
        command_profile,
        configuration["profiles"],
    )

    credential_binding = (
        credential_bindings_for_profile(
            command_profile,
            policy,
        )
    )

    return {
        **resolved,
        "configuration_version": (
            configuration[
                "configuration_version"
            ]
        ),
        "configuration_source": (
            configuration[
                "configuration_source"
            ]
        ),
        "configuration_hash": (
            configuration[
                "configuration_hash"
            ]
        ),
        "credential_reference_version": (
            credential_binding[
                "credential_reference_version"
            ]
        ),
        "credential_reference_hash": (
            credential_binding[
                "credential_reference_hash"
            ]
        ),
        "credential_binding_hash": (
            credential_binding[
                "binding_hash"
            ]
        ),
        "credential_binding_count": (
            credential_binding[
                "binding_count"
            ]
        ),
        "credential_resolver_contract": (
            credential_binding[
                "credential_resolver_contract"
            ]
        ),
        "process_credential_capability": (
            credential_binding[
                "process_credential_capability"
            ]
        ),
        "credential_values_included": False,
    }

def _validate_resolved_runtime_profile(
    command_profile: str,
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Reject forged internal resolved-profile objects."""
    if not isinstance(resolved, dict):
        raise RuntimeError(
            "resolved_runtime_profile_must_be_object"
        )

    name = str(command_profile or "").strip().lower()
    profile = resolved.get("profile")
    if not isinstance(profile, dict):
        raise RuntimeError(
            "resolved_runtime_profile_data_missing"
        )

    expected = resolve_runtime_profile(
        name,
        {
            name: profile,
        },
    )

    for key in (
        "name",
        "profile_version",
        "profile_hash",
        "scope",
    ):
        if resolved.get(key) != expected.get(key):
            raise RuntimeError(
                "resolved_runtime_profile_contract_mismatch:"
                + key
            )

    result = dict(resolved)
    config_fields = (
        "configuration_version",
        "configuration_source",
        "configuration_hash",
    )
    present = [
        key
        for key in config_fields
        if key in result
    ]

    if present and len(present) != len(config_fields):
        raise RuntimeError(
            "resolved_runtime_profile_configuration_incomplete"
        )

    if present:
        if int(
            result.get(
                "configuration_version",
                0,
            )
        ) != SANDBOX_CONFIGURATION_VERSION:
            raise RuntimeError(
                "resolved_runtime_profile_configuration_version_invalid"
            )
        if (
            result.get("configuration_source")
            != "effective_policy"
        ):
            raise RuntimeError(
                "resolved_runtime_profile_configuration_source_invalid"
            )
        config_hash = str(
            result.get(
                "configuration_hash",
                "",
            )
        )
        if not re.fullmatch(
            r"[0-9a-f]{64}",
            config_hash,
        ):
            raise RuntimeError(
                "resolved_runtime_profile_configuration_hash_invalid"
            )

    return result

def resolve_runtime_profile(
    command_profile: str,
    configured_profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Resolve one runtime profile from the internally selected command profile.

    Caller-supplied runtime-profile override is intentionally not accepted.
    """
    name = str(command_profile or "").strip().lower()
    if name not in _DEFAULT_RUNTIME_PROFILES:
        raise RuntimeError(
            "tool_runtime_profile_unknown_command_profile:"
            + name
        )

    registry = default_runtime_profiles()

    if configured_profiles is not None:
        if not isinstance(configured_profiles, dict):
            raise RuntimeError(
                "tool_runtime_profile_registry_must_be_object"
            )
        for key, value in configured_profiles.items():
            if key not in registry:
                raise RuntimeError(
                    "tool_runtime_profile_unknown_configured_profile:"
                    + str(key)
                )
            if not isinstance(value, dict):
                raise RuntimeError(
                    "tool_runtime_profile_must_be_object"
                )
            merged = dict(registry[key])
            merged.update(value)
            registry[key] = merged

    profile = _validate_profile(
        name,
        registry[name],
    )

    return {
        "name": name,
        "profile_version": RUNTIME_PROFILE_VERSION,
        "profile": profile,
        "profile_hash": _sha(
            {
                "name": name,
                "profile": profile,
            }
        ),
        "scope": SANDBOX_SCOPE,
    }


def sandbox_base(primary_root: Path) -> Path:
    """
    Return the project-specific sandbox base outside the governed repository.

    The physical separation is a workspace boundary only. It is not an OS ACL
    or token isolation claim.
    """
    root = primary_root.resolve()
    digest = _sha(str(root))[:12]
    return (
        root.parent
        / f".{root.name}.agentos-sandboxes"
        / digest
    ).resolve()


def sandbox_layout(
    primary_root: Path,
    task_id: str,
    session_id: str,
    execution_id: str,
    command_profile: str,
) -> dict[str, Path | str]:
    task = _safe_key(task_id, label="task_id")
    session = _safe_key(session_id, label="session_id")
    execution = _safe_key(
        execution_id,
        label="execution_id",
    )
    profile = _safe_key(
        command_profile,
        label="command_profile",
    )

    root = (
        sandbox_base(primary_root)
        / task
        / session
        / execution
    ).resolve()

    return {
        "root": root,
        "workspace": root / "workspace",
        "home": root / "home",
        "temp": root / "temp",
        "cache": root / "cache",
        "logs": root / "logs",
        "command_profile": profile,
    }


def _copy_snapshot_tree(
    source: Path,
    target: Path,
) -> None:
    """
    Copy one source tree without following symlinks, junctions, or reparse
    points.
    """
    _assert_not_reparse(
        source,
        label="sandbox_source",
    )

    target.mkdir(
        parents=True,
        exist_ok=False,
    )

    for entry in source.iterdir():
        if entry.name in _COPY_EXCLUDES:
            continue

        _assert_not_reparse(
            entry,
            label="sandbox_source_entry",
        )

        destination = _bounded_destination(
            target,
            entry.name,
        )

        if entry.is_dir():
            _copy_snapshot_tree(
                entry,
                destination,
            )
        elif entry.is_file():
            shutil.copy2(
                entry,
                destination,
            )


def create_sandbox_workspace(
    primary_root: Path,
    source_root: Path,
    task_id: str,
    session_id: str,
    execution_id: str,
    command_profile: str,
    *,
    resolved_runtime_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialize a sandbox bound to a validated runtime profile."""
    primary = primary_root.resolve()
    _assert_not_reparse(
        source_root,
        label="sandbox_source_root",
    )

    source = source_root.resolve()

    if not source.is_dir():
        raise RuntimeError(
            "sandbox_source_root_missing"
        )

    primary_agents = (
        primary
        / ".agents"
    ).resolve()
    try:
        source.relative_to(
            primary_agents
        )
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "sandbox_source_must_not_be_agentos_managed_root"
        )

    resolved = (
        _validate_resolved_runtime_profile(
            command_profile,
            resolved_runtime_profile,
        )
        if resolved_runtime_profile is not None
        else resolve_runtime_profile(
            command_profile
        )
    )

    layout = sandbox_layout(
        primary,
        task_id,
        session_id,
        execution_id,
        command_profile,
    )

    root = Path(layout["root"])
    if root.exists():
        raise FileExistsError(
            "sandbox_workspace_already_exists"
        )

    root.mkdir(
        parents=True,
        exist_ok=False,
    )

    try:
        for name in (
            "home",
            "temp",
            "cache",
            "logs",
        ):
            Path(layout[name]).mkdir(
                parents=True,
                exist_ok=False,
            )
        _copy_snapshot_tree(
            source,
            Path(layout["workspace"]),
        )
    except Exception:
        shutil.rmtree(
            root,
            ignore_errors=True,
        )
        raise

    snapshot_hash = sandbox_workspace_hash(
        Path(layout["workspace"])
    )

    result = {
        "sandbox_version": SANDBOX_WORKSPACE_VERSION,
        "scope": SANDBOX_SCOPE,
        "profile_name": resolved["name"],
        "profile_hash": resolved["profile_hash"],
        "profile_version": resolved["profile_version"],
        "root": str(root),
        "workspace": str(layout["workspace"]),
        "home": str(layout["home"]),
        "temp": str(layout["temp"]),
        "cache": str(layout["cache"]),
        "logs": str(layout["logs"]),
        "snapshot_hash": snapshot_hash,
        "source_root_hash": _sha(
            str(source)
        ),
        "primary_root_hash": _sha(
            str(primary)
        ),
    }

    if "configuration_hash" in resolved:
        result.update(
            {
                "configuration_version": resolved[
                    "configuration_version"
                ],
                "configuration_source": resolved[
                    "configuration_source"
                ],
                "configuration_hash": resolved[
                    "configuration_hash"
                ],
            }
        )

    return result

def _snapshot_hash_tree(
    root: Path,
    current: Path,
    digest,
) -> None:
    for entry in sorted(
        current.iterdir(),
        key=lambda item: item.name,
    ):
        _assert_not_reparse(
            entry,
            label="sandbox_snapshot_entry",
        )

        relative = entry.relative_to(
            root
        ).as_posix()

        if entry.is_dir():
            digest.update(
                b"D\0"
            )
            digest.update(
                relative.encode(
                    "utf-8"
                )
            )
            digest.update(
                b"\0"
            )
            _snapshot_hash_tree(
                root,
                entry,
                digest,
            )
        elif entry.is_file():
            digest.update(
                b"F\0"
            )
            digest.update(
                relative.encode(
                    "utf-8"
                )
            )
            digest.update(
                b"\0"
            )

            with entry.open(
                "rb"
            ) as handle:
                while True:
                    chunk = handle.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    digest.update(
                        chunk
                    )

            digest.update(
                b"\0"
            )


def sandbox_workspace_hash(
    workspace_root: Path,
) -> str:
    """
    Hash the materialized sandbox snapshot deterministically.

    The hash binds relative paths, entry types, and exact file bytes. Reparse
    points are rejected before traversal.
    """
    root = workspace_root.resolve()

    if not root.is_dir():
        raise RuntimeError(
            "sandbox_workspace_missing"
        )

    _assert_not_reparse(
        workspace_root,
        label="sandbox_workspace_root",
    )

    digest = hashlib.sha256()
    _snapshot_hash_tree(
        root,
        root,
        digest,
    )
    return digest.hexdigest()


def build_runtime_environment(
    base_env: dict[str, str],
    sandbox: dict[str, Any],
) -> dict[str, str]:
    """
    Redirect tool-local mutable runtime paths into the sandbox.

    Credential filtering remains the responsibility of the existing AgentOS
    environment filter until the dedicated credential-boundary release.
    """
    env = {
        str(key): str(value)
        for key, value in base_env.items()
    }

    home = str(sandbox["home"])
    temp = str(sandbox["temp"])
    cache = str(sandbox["cache"])

    env.update(
        {
            "HOME": home,
            "USERPROFILE": home,
            "TMP": temp,
            "TEMP": temp,
            "TMPDIR": temp,
            "XDG_CACHE_HOME": cache,
            "PIP_CACHE_DIR": str(
                Path(cache)
                / "pip"
            ),
            "npm_config_cache": str(
                Path(cache)
                / "npm"
            ),
            "PYTHONPYCACHEPREFIX": str(
                Path(cache)
                / "pycache"
            ),
        }
    )

    return env


def cleanup_sandbox_workspace(
    primary_root: Path,
    sandbox_root: Path,
) -> None:
    """
    Remove one sandbox only when it is inside the project-specific sandbox base.
    """
    base = sandbox_base(
        primary_root
    )
    target = sandbox_root.resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise RuntimeError(
            "sandbox_cleanup_path_escape"
        ) from exc

    if target == base:
        raise RuntimeError(
            "sandbox_cleanup_base_forbidden"
        )

    shutil.rmtree(
        target,
        ignore_errors=False,
    )

    # Prune empty execution scaffolding without touching active sibling
    # sandboxes. rmdir() fails safely when a directory is not empty.
    container = base.parent
    candidate = target.parent

    while True:
        if candidate == container.parent:
            break

        try:
            candidate.relative_to(
                container
            )
        except ValueError:
            break

        try:
            candidate.rmdir()
        except OSError:
            break

        if candidate == container:
            break

        candidate = candidate.parent
