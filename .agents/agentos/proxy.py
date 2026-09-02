"""
File: .agents/agentos/proxy.py

Purpose:
    Enforce AgentOS policy at the actual MCP/tool invocation boundary.

Responsibilities:
    - Normalize agent-facing tool names into stable capabilities.
    - Enforce approval, workflow, scope, process, and egress policy before execution.
    - Invoke bounded filesystem, process, and HTTP adapters.
    - Produce canonical execution evidence and signed external audit records.
"""
from __future__ import annotations

import ast
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import tempfile
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

from .core import check_write
from .cache import cache_lookup, cache_store
from .concurrency import acquire_resource, atomic_write, claim_task, file_hash, force_reclaim_task, handoff_task, heartbeat_resource, list_resources, release_resource, task_heartbeat, task_status
from .db import connect
from .drift import drift_check
from .external_audit import append_signed_event
from .policy import load_policy, local_override_status
from .secret_lineage import resolve_runtime_secret
from .tooling import append_audit_event, complete_tool, guard_tool, redact_value
from .tool_runtime_profiles import (
    build_runtime_environment,
    PROCESS_CREDENTIAL_CAPABILITY,
    credential_bindings_for_profile,
    cleanup_sandbox_workspace,
    create_sandbox_workspace,
    resolve_runtime_profile,
    resolve_runtime_profile_from_policy,
)
from .workflow import workflow_status

CAPABILITIES = {
    "agentos.read_file": "filesystem.read",
    "agentos.write_file": "filesystem.write",
    "agentos.run_command": "process.exec",
    "agentos.run_command_async": "process.exec",
    "agentos.http_request": "network.http",
    "agentos.acquire_resource": "coordination.resource.acquire",
    "agentos.heartbeat_resource": "coordination.resource.heartbeat",
    "agentos.release_resource": "coordination.resource.release",
    "agentos.list_resources": "coordination.resource.list",
    "agentos.claim_task": "coordination.task.claim",
    "agentos.handoff_task": "coordination.task.handoff",
    "agentos.task_heartbeat": "coordination.task.heartbeat",
    "agentos.task_status": "coordination.task.status",
    "agentos.force_reclaim_task": "coordination.task.reclaim",
}
TOOL_NAMES = {
    "filesystem.read": "filesystem_read",
    "filesystem.write": "filesystem_write",
    "process.exec": "shell_local",
    "network.http": "http",
    "coordination.resource.acquire": "coordination",
    "coordination.resource.heartbeat": "coordination",
    "coordination.resource.release": "coordination",
    "coordination.resource.list": "coordination",
    "coordination.task.claim": "coordination",
    "coordination.task.handoff": "coordination",
    "coordination.task.heartbeat": "coordination",
    "coordination.task.status": "coordination",
    "coordination.task.reclaim": "coordination",
}
SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "AUTH", "COOKIE", "CREDENTIAL")
NETWORK_EXECUTABLES = {"curl", "wget", "nc", "netcat", "ssh", "scp", "sftp", "ftp"}
SHELL_EXECUTABLES = {"bash", "sh", "zsh", "powershell", "pwsh", "cmd"}


def normalize_capability(tool_name: str) -> str:
    """Map an exposed proxy tool name to one stable capability."""
    if tool_name not in CAPABILITIES:
        raise RuntimeError(f"tool is not exposed by AgentOS proxy: {tool_name}")
    return CAPABILITIES[tool_name]


def _steps(root: Path, task_id: str) -> dict[str, str]:
    return {item["step_name"]: item["status"] for item in workflow_status(root, task_id)["steps"]}


def _inside(root: Path, value: str | None) -> Path:
    candidate = (root / (value or ".")).resolve() if not Path(value or ".").is_absolute() else Path(value or ".").resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _command_profile(command: list[str], policy: dict[str, Any]) -> str:
    if not command or not all(isinstance(x, str) and x for x in command):
        raise RuntimeError("command must be a non-empty JSON array of strings")
    # Parse executable identity independently of the host OS.
    # PureWindowsPath accepts both Windows backslashes and POSIX-style
    # forward slashes, so a Windows command transported to a Linux
    # governance runner still resolves to the same executable name.
    executable = PureWindowsPath(command[0]).name.lower()

    # Windows executable suffixes are transport details, not
    # different process-policy identities.
    if executable.endswith(".exe"):
        executable = executable[:-4]

    cfg = policy["proxy_policy"]["process_exec"]
    if executable in set(cfg.get("denied_executables", [])) | NETWORK_EXECUTABLES | SHELL_EXECUTABLES:
        raise RuntimeError(f"process blocked: executable is denied: {executable}")
    if executable not in set(cfg.get("allowed_executables", [])):
        raise RuntimeError(f"process blocked: executable is not allowlisted: {executable}")
    lowered = [x.lower() for x in command[1:]]
    joined = " ".join(command)
    if any(scheme in joined.lower() for scheme in ("http://", "https://", "ftp://")):
        raise RuntimeError("process blocked: network behavior must use agentos.http_request")
    if executable in {"python", "python3"}:
        if "-c" in lowered:
            raise RuntimeError("process blocked: inline Python is forbidden")
        if "-m" in lowered:
            index = lowered.index("-m")
            module = lowered[index + 1] if index + 1 < len(lowered) else ""
            if module not in set(cfg.get("allowed_python_modules", [])):
                raise RuntimeError(f"process blocked: Python module is not allowlisted: {module}")
            return "test" if module in {"pytest", "unittest"} else "inspect"
        raise RuntimeError("process blocked: Python execution requires an allowlisted -m module")
    if executable == "pytest":
        return "test"
    if executable in {"ruff", "mypy"}:
        return "inspect"
    if executable == "node" and "-e" in lowered:
        raise RuntimeError("process blocked: inline Node.js is forbidden")
    if executable == "npm":
        action = lowered[0] if lowered else ""
        if action not in set(cfg.get("allowed_npm_commands", [])):
            raise RuntimeError(f"process blocked: npm action is not allowlisted: {action}")
        return "test" if action == "test" else "build"
    if cfg.get("require_known_command_profile", True):
        raise RuntimeError("process blocked: no known command profile")
    return "custom"


def _filtered_env(extra: dict[str, Any] | None = None) -> dict[str, str]:
    allowed_names = {"PATH", "LANG", "LC_ALL", "TMP", "TEMP", "TMPDIR", "SYSTEMROOT", "WINDIR"}
    env = {k: v for k, v in os.environ.items() if k in allowed_names and not any(marker in k.upper() for marker in SECRET_ENV_MARKERS)}
    for key, value in (extra or {}).items():
        key = str(key)
        if any(marker in key.upper() for marker in SECRET_ENV_MARKERS) or key.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSH_AUTH_SOCK"}:
            continue
        env[key] = str(value)
    return env


def _validate_host(hostname: str, policy: dict[str, Any]) -> None:
    cfg = policy["proxy_policy"]["network_http"]
    host = hostname.rstrip(".").lower()
    allowed = [x.lower() for x in cfg.get("allowed_domains", [])]
    if cfg.get("default", "deny") == "deny" and not allowed:
        raise RuntimeError("network blocked: no domains are approved")
    exact = host in allowed
    subdomain = cfg.get("allow_subdomains", False) and any(host.endswith("." + item) for item in allowed)
    if allowed and not (exact or subdomain):
        raise RuntimeError(f"network blocked: domain is not allowlisted: {host}")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise RuntimeError(f"network blocked: DNS resolution failed for {host}") from exc
    for value in addresses:
        ip = ipaddress.ip_address(value)
        if cfg.get("blocked_loopback", True) and ip.is_loopback:
            raise RuntimeError("network blocked: loopback address")
        if cfg.get("blocked_private_networks", True) and ip.is_private:
            raise RuntimeError("network blocked: private address")
        if cfg.get("blocked_link_local", True) and ip.is_link_local:
            raise RuntimeError("network blocked: link-local address")


def _validate_url(url: str, policy: dict[str, Any]) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in set(policy["proxy_policy"]["network_http"].get("allowed_schemes", ["https"])):
        raise RuntimeError(f"network blocked: scheme is not allowed: {parsed.scheme}")
    if not parsed.hostname:
        raise RuntimeError("network blocked: URL has no hostname")
    _validate_host(parsed.hostname, policy)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self.count = 0
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        """Validate every redirect destination before following it."""
        self.count += 1
        if self.count > int(self.policy["proxy_policy"]["network_http"].get("max_redirects", 3)):
            raise urllib.error.HTTPError(newurl, code, "too many redirects", headers, fp)
        _validate_url(newurl, self.policy)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _scan_agentos_imports(root: Path, command: list[str], cwd: Path) -> None:
    """Reject test sources that attempt to import AgentOS enforcement internals."""
    candidates: list[Path] = []
    for item in command[1:]:
        candidate = (cwd / item).resolve()
        if candidate.is_file() and candidate.suffix == ".py": candidates.append(candidate)
        elif candidate.is_dir(): candidates.extend(candidate.rglob("*.py"))
    for path in candidates:
        try: tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError): continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(x.name == "agentos" or x.name.startswith("agentos.") for x in node.names):
                raise RuntimeError("agentos_internal_import_denied")
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("agentos"):
                raise RuntimeError("agentos_internal_import_denied")







def _preflight(root: Path, task_id: str, session_id: str, capability: str, args: dict[str, Any]) -> dict[str, Any]:
    drift = drift_check(root, task_id=task_id)
    override = local_override_status(root)
    policy = load_policy(root)
    if policy["proxy_policy"].get("block_on_uninitialized_baseline", True) and drift["baseline_state"] != "initialized":
        raise RuntimeError("proxy blocked: governance baseline is not initialized")
    if policy["proxy_policy"].get("block_on_drift", True) and drift["drift_detected"]:
        raise RuntimeError("proxy blocked: unacknowledged governance drift")
    if override.get("sensitive") and override.get("status") != "approved":
        raise RuntimeError("proxy blocked: sensitive local override is pending approval")
    steps = _steps(root, task_id)
    if (capability in {"filesystem.write", "process.exec", "network.http"} or capability.startswith("coordination.")) and steps.get("approve_task") != "done":
        raise RuntimeError("proxy blocked: task is not approved")
    if capability == "filesystem.write":
        if steps.get("prepare_change") != "done":
            raise RuntimeError("proxy blocked: prepare_change is incomplete")
        decision = check_write(root, task_id, str(args.get("path", "")))
        if not decision["allowed"]:
            raise RuntimeError(f"proxy blocked: {decision['reason']}")
    metadata: dict[str, Any] = {}
    execution_root = root.resolve()
    workspace_bound = False
    if capability in {"filesystem.read", "filesystem.write", "process.exec"}:
        from .multi_agent_workspace import workspace_binding, workspace_execution_root
        execution_root = workspace_execution_root(root, task_id, session_id, for_write=capability == "filesystem.write")
        workspace_bound = workspace_binding(root, task_id, session_id) is not None
        metadata["workspace_bound"] = workspace_bound
    if capability == "process.exec":
        if steps.get("prepare_change") != "done":
            raise RuntimeError(
                "proxy blocked: prepare_change is incomplete"
            )

        command_profile = _command_profile(
            args.get("command"),
            policy,
        )
        runtime_profile = resolve_runtime_profile_from_policy(
            command_profile,
            policy,
        )

        metadata["command_profile"] = command_profile
        metadata["runtime_profile"] = runtime_profile["name"]
        metadata["runtime_profile_hash"] = (
            runtime_profile["profile_hash"]
        )
        metadata["runtime_profile_version"] = (
            runtime_profile["profile_version"]
        )
        metadata["runtime_profile_scope"] = (
            runtime_profile["scope"]
        )
        if "configuration_hash" in runtime_profile:
            metadata["runtime_profile_configuration_hash"] = (
                runtime_profile["configuration_hash"]
            )
            metadata["runtime_profile_configuration_version"] = (
                runtime_profile["configuration_version"]
            )
            metadata["runtime_profile_configuration_source"] = (
                runtime_profile["configuration_source"]
            )
            metadata["credential_reference_hash"] = (
                runtime_profile["credential_reference_hash"]
            )
            metadata["credential_binding_hash"] = (
                runtime_profile["credential_binding_hash"]
            )
            metadata["credential_binding_count"] = (
                runtime_profile["credential_binding_count"]
            )

        resolved_cwd = _inside(
            execution_root,
            str(args.get("cwd", ".")),
        )
        _scan_agentos_imports(
            root,
            args.get("command", []),
            resolved_cwd,
        )

        metadata["cwd"] = (
            resolved_cwd
            .relative_to(execution_root)
            .as_posix()
            or "."
        )
        metadata["sandbox_profile"] = (
            "tool-runtime-profile-v1"
        )
        metadata[
            "host_filesystem_isolation_attested"
        ] = False
        metadata[
            "os_write_confinement_attested"
        ] = False
    if capability == "network.http":
        _validate_url(str(args.get("url", "")), policy)
    return metadata

def _is_windows_host() -> bool:
    return os.name == 'nt'






def _run_process_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> tuple[Any, dict[str, Any]]:
    """
    Run synchronous process.exec with host-appropriate containment.

    Windows successor semantics:
    v0.29.4 Restricted Token + Job Object are preserved and strengthened by
    v0.29.5 Low Mandatory Integrity. The local alias deliberately preserves
    the v0.29.4 canonical restricted-runner marker for predecessor structural
    attestation while executing the stronger successor primitive.
    """
    if _is_windows_host():
        from .windows_process_tree import (
            CONTAINMENT_PROFILE,
        )
        from .windows_restricted_execution import (
            RESTRICTED_EXECUTION_SCOPE,
            RESTRICTED_TOKEN_PROFILE,
        )
        from .windows_physical_isolation import (
            LOW_INTEGRITY_PROFILE,
            PHYSICAL_ISOLATION_SCOPE,
            run_low_integrity_restricted_contained_capture as run_restricted_contained_capture,
        )

        result = run_restricted_contained_capture(
            command,
            cwd=cwd,
            env=env,
            timeout=timeout,
        )

        return result, {
            "process_tree_contained": True,
            "process_tree_containment_profile": (
                CONTAINMENT_PROFILE
            ),
            "process_tree_containment_scope": (
                "agentos_mediated_process_execution"
            ),
            "restricted_execution": True,
            "restricted_execution_profile": (
                RESTRICTED_TOKEN_PROFILE
            ),
            "restricted_execution_scope": (
                RESTRICTED_EXECUTION_SCOPE
            ),
            "restricted_token_verified": True,
            "restricted_token_attested": False,
            "low_integrity_execution": True,
            "low_integrity_profile": (
                LOW_INTEGRITY_PROFILE
            ),
            "low_integrity_scope": (
                PHYSICAL_ISOLATION_SCOPE
            ),
            "low_integrity_token_verified": True,
            "sandbox_low_integrity_boundary_required": True,
            "low_integrity_attested": False,
            "host_filesystem_isolation_attested": False,
            "os_write_confinement_attested": False,
        }

    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
        env=env,
    )

    return result, {
        "process_tree_contained": False,
        "process_tree_containment_profile": None,
        "process_tree_containment_scope": None,
    }

def _credential_safe_environment_hash(
    env: dict[str, str],
    credential_targets: set[str],
) -> str:
    """
    Hash an execution-environment descriptor without deriving the persisted
    fingerprint from credential values.
    """
    safe = {
        key: (
            "<agentos-credential-projected>"
            if key in credential_targets
            else value
        )
        for key, value in sorted(env.items())
    }
    return hashlib.sha256(
        json.dumps(
            safe,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _redact_projected_secret_values(
    value: str,
    secret_values: list[str],
) -> str:
    """Redact exact projected secret values from captured process text."""
    text = str(value)
    unique = sorted(
        {
            item
            for item in secret_values
            if isinstance(item, str)
            and item
        },
        key=len,
        reverse=True,
    )
    for item in unique:
        text = text.replace(
            item,
            "<redacted-secret>",
        )
    return text


def _resolve_sync_credential_environment(
    root: Path,
    policy: dict[str, Any],
    runtime_profile: dict[str, Any],
    env: dict[str, str],
) -> tuple[
    dict[str, str],
    dict[str, Any],
    list[str],
]:
    """
    Resolve policy-bound process credentials only at the sync launch boundary.

    Returned evidence contains references/hashes/target names only. Secret
    values live only in the returned launch environment and transient list.
    """
    section = policy.get(
        "sandbox_workspace_runtime_profile_policy"
    )
    if not isinstance(section, dict):
        raise RuntimeError(
            "sync_credential_policy_section_missing"
        )

    if (
        section.get(
            "sync_credential_boundary_enabled"
        )
        is not True
    ):
        raise RuntimeError(
            "sync_credential_boundary_disabled"
        )

    if (
        section.get(
            "sync_credential_environment_projection_enabled"
        )
        is not True
    ):
        raise RuntimeError(
            "sync_credential_environment_projection_disabled"
        )

    # Phase 4 intentionally allows sync and async credential projection
    # to coexist. Async policy is validated by the async boundary itself.

    binding = credential_bindings_for_profile(
        runtime_profile["name"],
        policy,
    )

    for key, expected in (
        (
            "credential_reference_hash",
            binding[
                "credential_reference_hash"
            ],
        ),
        (
            "credential_binding_hash",
            binding[
                "binding_hash"
            ],
        ),
        (
            "credential_binding_count",
            binding[
                "binding_count"
            ],
        ),
    ):
        if runtime_profile.get(key) != expected:
            raise RuntimeError(
                "sync_credential_binding_drift:"
                + key
            )

    launch_env = dict(env)
    secret_values: list[str] = []
    projected: list[
        dict[str, Any]
    ] = []

    for item in binding["bindings"]:
        target = item["target_env"]

        if target in launch_env:
            raise RuntimeError(
                "credential_target_env_collision:"
                + target
            )

        secret = resolve_runtime_secret(
            root,
            item["credential_ref"],
            capability=PROCESS_CREDENTIAL_CAPABILITY,
        )

        field = item["secret_field"]
        if field not in secret:
            raise RuntimeError(
                "credential_secret_field_missing:"
                + item["binding_id"]
            )

        value = secret[field]
        if (
            not isinstance(value, str)
            or not value
        ):
            raise RuntimeError(
                "credential_secret_field_must_be_nonempty_string:"
                + item["binding_id"]
            )

        launch_env[target] = value
        secret_values.append(value)

        projected.append(
            {
                "binding_id": item[
                    "binding_id"
                ],
                "reference_hash": hashlib.sha256(
                    item[
                        "credential_ref"
                    ].encode(
                        "utf-8"
                    )
                ).hexdigest(),
                "target_env": target,
                "secret_field": field,
                "secret_included": False,
            }
        )

    evidence = {
        "credential_reference_version": binding[
            "credential_reference_version"
        ],
        "credential_reference_hash": binding[
            "credential_reference_hash"
        ],
        "credential_binding_hash": binding[
            "binding_hash"
        ],
        "credential_binding_count": binding[
            "binding_count"
        ],
        "credential_resolver_contract": binding[
            "credential_resolver_contract"
        ],
        "process_credential_capability": binding[
            "process_credential_capability"
        ],
        "projected": projected,
        "secret_values_included": False,
    }

    return (
        launch_env,
        evidence,
        secret_values,
    )

def _execute_adapter(root: Path, task_id: str, session_id: str, capability: str, args: dict[str, Any], metadata: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    policy = load_policy(root)
    if capability == "filesystem.read":
        from .multi_agent_workspace import workspace_binding, workspace_execution_root
        binding = workspace_binding(root, task_id, session_id)
        execution_root = workspace_execution_root(root, task_id, session_id)
        path = _inside(execution_root, str(args["path"]))
        logical_path = path.relative_to(execution_root).as_posix()
        start, end = int(args.get("start", 1)), int(args.get("end", 0))
        range_key = f"{start}:{end or 'EOF'}"
        if binding:
            content = path.read_text(encoding=str(args.get("encoding", "utf-8")))
            if end:
                content = "\n".join(content.splitlines()[start - 1:end])
            digest = hashlib.sha256(content.encode()).hexdigest()
            cache_hit = False
            with connect(root) as c:
                row = c.execute("SELECT COUNT(*) AS version FROM multi_agent_workspace_file_versions WHERE workspace_id=? AND path=?", (int(binding["workspace_id"]), logical_path)).fetchone()
        else:
            cached = cache_lookup(root, task_id, logical_path, range_key)
            if cached.get("hit"):
                content = cached["summary"]
                digest = hashlib.sha256(content.encode()).hexdigest()
                cache_hit = True
            else:
                content = path.read_text(encoding=str(args.get("encoding", "utf-8")))
                if end:
                    content = "\n".join(content.splitlines()[start - 1:end])
                cache_store(root, task_id, logical_path, range_key, content)
                digest = hashlib.sha256(content.encode()).hexdigest()
                cache_hit = False
            with connect(root) as c:
                row = c.execute("SELECT COALESCE(MAX(version),0) AS version FROM file_versions WHERE path=?", (logical_path,)).fetchone()
        return True, {"content": content, "sha256": digest, "content_hash": digest, "version": row[0], "cache_hit": cache_hit, "range_key": range_key, "workspace_bound": bool(binding)}
    if capability == "filesystem.write":
        from .multi_agent_workspace import workspace_binding, workspace_atomic_write, workspace_execution_root
        binding = workspace_binding(root, task_id, session_id)
        workspace_execution_root(root, task_id, session_id, for_write=True)
        if binding:
            result = workspace_atomic_write(root, task_id, session_id, str(args["path"]), str(args.get("content", "")), args.get("expected_hash"), str(args.get("encoding", "utf-8")))
        else:
            result = atomic_write(root, task_id, session_id, str(args["path"]), str(args.get("content", "")), args.get("expected_hash"), str(args.get("encoding", "utf-8")))
        return bool(result.get("allowed")), result
    if capability == "process.exec":
        cfg = policy["proxy_policy"]["process_exec"]
        timeout = min(
            int(args.get("timeout", 120)),
            int(
                cfg.get(
                    "max_timeout_seconds",
                    600,
                )
            ),
        )

        from .multi_agent_workspace import (
            workspace_execution_root,
        )

        execution_root = workspace_execution_root(
            root,
            task_id,
            session_id,
        )
        source_cwd = _inside(
            execution_root,
            str(args.get("cwd", ".")),
        )
        command = list(args["command"])

        runtime_profile = resolve_runtime_profile_from_policy(
            metadata["command_profile"],
            policy,
        )
        if (
            runtime_profile["profile_hash"]
            != metadata.get("runtime_profile_hash")
        ):
            raise RuntimeError(
                "runtime_profile_hash_drift"
            )
        runtime_configuration_bound = (
            "configuration_hash" in runtime_profile
        )
        metadata_configuration_bound = (
            metadata.get(
                "runtime_profile_configuration_hash"
            )
            is not None
        )
        if (
            runtime_configuration_bound
            != metadata_configuration_bound
        ):
            raise RuntimeError(
                "runtime_profile_configuration_drift"
            )
        if runtime_configuration_bound and (
            runtime_profile["configuration_hash"]
            != metadata.get(
                "runtime_profile_configuration_hash"
            )
            or int(
                metadata.get(
                    "runtime_profile_configuration_version",
                    0,
                )
            )
            != int(runtime_profile["configuration_version"])
            or metadata.get(
                "runtime_profile_configuration_source"
            )
            != runtime_profile["configuration_source"]
        ):
            raise RuntimeError(
                "runtime_profile_configuration_drift"
            )
        if runtime_configuration_bound and (
            runtime_profile.get("credential_reference_hash")
            != metadata.get("credential_reference_hash")
            or runtime_profile.get(
                "credential_binding_hash"
            )
            != metadata.get(
                "credential_binding_hash"
            )
            or int(
                runtime_profile.get(
                    "credential_binding_count",
                    0,
                )
            )
            != int(
                metadata.get(
                    "credential_binding_count",
                    0,
                )
            )
        ):
            raise RuntimeError(
                "runtime_profile_credential_binding_drift"
            )

        sandbox = create_sandbox_workspace(
            root,
            source_cwd,
            task_id,
            session_id,
            uuid.uuid4().hex,
            metadata["command_profile"],
            resolved_runtime_profile=runtime_profile,
        )

        cwd = Path(
            sandbox["workspace"]
        )

        env = _filtered_env(
            args.get("env")
        )
        env.pop(
            "PYTHONPATH",
            None,
        )
        env = build_runtime_environment(
            env,
            sandbox,
        )

        credential_evidence = {
            "credential_reference_version": None,
            "credential_reference_hash": None,
            "credential_binding_hash": None,
            "credential_binding_count": 0,
            "credential_resolver_contract": None,
            "process_credential_capability": None,
            "projected": [],
            "secret_values_included": False,
        }
        projected_secret_values: list[str] = []
        credential_targets: set[str] = set()

        if runtime_configuration_bound:
            (
                env,
                credential_evidence,
                projected_secret_values,
            ) = _resolve_sync_credential_environment(
                root,
                policy,
                runtime_profile,
                env,
            )
            credential_targets = {
                item["target_env"]
                for item in credential_evidence[
                    "projected"
                ]
            }

        try:
            proc, containment = _run_process_command(
                command,
                cwd=cwd,
                env=env,
                timeout=timeout,
            )

            command_hash = hashlib.sha256(
                json.dumps(
                    command,
                    sort_keys=True,
                ).encode()
            ).hexdigest()

            if credential_targets:
                environment_hash = (
                    _credential_safe_environment_hash(
                        env,
                        credential_targets,
                    )
                )
            else:
                # Preserve the exact v0.29.2 evidence algorithm when
                # no credential target was projected.
                environment_hash = hashlib.sha256(
                    json.dumps(
                        env,
                        sort_keys=True,
                    ).encode()
                ).hexdigest()

            with connect(root) as c:
                c.execute(
                    "INSERT INTO execution_manifests("
                    "task_id,session_id,command_hash,cwd,"
                    "sandbox_profile,workspace_path,"
                    "environment_hash,decision"
                    ") VALUES(?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        session_id,
                        command_hash,
                        metadata["cwd"],
                        metadata.get(
                            "sandbox_profile",
                            "tool-runtime-profile-v1",
                        ),
                        str(cwd),
                        environment_hash,
                        "allowed",
                    ),
                )

            limit = int(
                cfg.get(
                    "max_output_bytes",
                    65536,
                )
            )

            return proc.returncode == 0, {
                "exit_code": proc.returncode,
                "profile": metadata[
                    "command_profile"
                ],
                "runtime_profile": runtime_profile[
                    "name"
                ],
                "runtime_profile_hash": runtime_profile[
                    "profile_hash"
                ],
                "runtime_profile_version": runtime_profile[
                    "profile_version"
                ],
                "sandbox_scope": sandbox[
                    "scope"
                ],
                "sandbox_workspace_version": sandbox[
                    "sandbox_version"
                ],
                "host_filesystem_isolation_attested": False,
                "os_write_confinement_attested": False,
                "cwd": metadata["cwd"],
                "stdout": _redact_projected_secret_values(
                    proc.stdout[:limit],
                    projected_secret_values,
                ),
                "stderr": _redact_projected_secret_values(
                    proc.stderr[:limit],
                    projected_secret_values,
                ),
                **(
                    {
                        "credential_reference_hash": credential_evidence[
                            "credential_reference_hash"
                        ],
                        "credential_binding_hash": credential_evidence[
                            "credential_binding_hash"
                        ],
                        "credential_binding_count": credential_evidence[
                            "credential_binding_count"
                        ],
                        "credential_projection": credential_evidence[
                            "projected"
                        ],
                        "credential_values_included": False,
                    }
                    if runtime_configuration_bound
                    else {}
                ),
                **containment,
            }
        finally:
            cleanup_sandbox_workspace(
                root,
                Path(sandbox["root"]),
            )
    if capability == "network.http":
        url = str(args["url"]); _validate_url(url, policy)
        method = str(args.get("method", "GET")).upper()
        data = args.get("body"); body = data.encode() if isinstance(data, str) else None
        request = urllib.request.Request(url, data=body, method=method, headers={str(k): str(v) for k, v in args.get("headers", {}).items()})
        opener = urllib.request.build_opener(_SafeRedirect(policy))
        with opener.open(request, timeout=min(int(args.get("timeout", 30)), 120)) as response:
            final_url = response.geturl(); _validate_url(final_url, policy)
            payload = response.read(min(int(args.get("max_bytes", 1048576)), int(policy["proxy_policy"].get("http_max_response_bytes", 1048576))))
            return True, {"status": response.status, "url": final_url, "headers": dict(response.headers.items()), "body": payload.decode("utf-8", errors="replace")}
    if capability == "coordination.resource.acquire":
        result = acquire_resource(root, task_id, session_id, str(args["resource_type"]), str(args["resource"]), str(args.get("lease_mode", "exclusive_write")), args.get("ttl_seconds"), args.get("base_hash"))
        return bool(result.get("acquired")), result
    if capability == "coordination.resource.heartbeat": return True, heartbeat_resource(root, int(args["lease_id"]), task_id, session_id, args.get("ttl_seconds"))
    if capability == "coordination.resource.release": return True, release_resource(root, int(args["lease_id"]), task_id, session_id)
    if capability == "coordination.resource.list": return True, {"resources": list_resources(root, task_id if args.get("task_only", True) else None, bool(args.get("active_only", True)))}
    if capability == "coordination.task.claim":
        result=claim_task(root,task_id,session_id); return bool(result.get("claimed")),result
    if capability == "coordination.task.handoff": return True, handoff_task(root,task_id,session_id,str(args["to_session"]),str(args["note"]))
    if capability == "coordination.task.heartbeat": return True, task_heartbeat(root,task_id,session_id)
    if capability == "coordination.task.status": return True, task_status(root,task_id)
    if capability == "coordination.task.reclaim": return True, force_reclaim_task(root,task_id,session_id,str(args["reason"]))
    raise RuntimeError(f"unsupported capability: {capability}")

def proxy_submit_job(
    root: Path,
    task_id: str,
    session_id: str,
    command: list[str],
    cwd: str = ".",
    timeout_seconds: int = 900,
    env: dict[str, Any] | None = None,
    auto_start: bool = True,
    reason_code: str | None = None,
    justification: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Submit asynchronous process execution through the canonical proxy.

    The tool call represents governed job submission/launch.
    Terminal async-job lifecycle evidence remains owned by jobs.py.
    """
    tool_name = "agentos.run_command_async"
    capability = normalize_capability(tool_name)

    guarded_args = {
        "command": list(command),
        "cwd": cwd,
        "timeout": int(timeout_seconds),
        "env": env or {},
        "auto_start": bool(auto_start),
    }

    metadata = _preflight(
        root,
        task_id,
        session_id,
        capability,
        guarded_args,
    )
    if int(
        metadata.get(
            "credential_binding_count",
            0,
        )
    ):
        async_policy = load_policy(root).get(
            "sandbox_workspace_runtime_profile_policy",
            {},
        )
        if (
            async_policy.get(
                "async_credential_environment_projection_enabled"
            )
            is not True
        ):
            raise RuntimeError(
                "async_credential_projection_not_enabled"
            )

    metadata = {
        **metadata,
        "execution_mode": "async_job",
    }

    canonical_tool = TOOL_NAMES[capability]

    requested = {
        "tool": tool_name,
        "capability": capability,
        "args": redact_value(guarded_args),
        "metadata": metadata,
    }

    append_audit_event(
        root,
        "proxy.request",
        requested,
        task_id,
        session_id,
    )
    append_signed_event(
        root,
        "proxy.request",
        requested,
        task_id,
        session_id,
    )

    guard = guard_tool(
        root,
        task_id,
        session_id,
        canonical_tool,
        guarded_args,
        reason_code,
        justification,
        target,
    )

    if not guard["allowed"]:
        denied = {
            "allowed": False,
            "reason": guard["reason"],
            "capability": capability,
            "execution_mode": "async_job",
        }

        append_signed_event(
            root,
            "proxy.denied",
            denied,
            task_id,
            session_id,
        )
        return denied

    try:
        # Local import prevents the proxy/jobs module dependency
        # from becoming an import-time cycle.
        from .jobs import submit_job

        output = submit_job(
            root,
            task_id,
            session_id,
            list(command),
            cwd,
            int(timeout_seconds),
            env or {},
            bool(auto_start),
            execution_token=guard["execution_token"],
        )
        success = True
    except Exception as exc:
        output = {
            "error": type(exc).__name__,
            "message": str(exc),
        }
        success = False

    summary = json.dumps(
        redact_value(output),
        sort_keys=True,
        ensure_ascii=False,
    )

    canonical = complete_tool(
        root,
        guard["execution_token"],
        guarded_args,
        success,
        summary,
        session_id,
    )

    event = {
        "allowed": True,
        "success": success,
        "capability": capability,
        "tool_call_id": canonical["tool_call_id"],
        "output": redact_value(output),
        "metadata": metadata,
    }

    append_audit_event(
        root,
        "proxy.completed",
        event,
        task_id,
        session_id,
    )

    signed = append_signed_event(
        root,
        "proxy.completed",
        event,
        task_id,
        session_id,
    )

    with connect(root) as c:
        c.execute(
            "INSERT INTO proxy_executions("
            "task_id,session_id,tool_name,capability,"
            "decision,success,tool_call_id,external_event_hash"
            ") VALUES(?,?,?,?,?,?,?,?)",
            (
                task_id,
                session_id,
                tool_name,
                capability,
                "allowed",
                int(success),
                canonical["tool_call_id"],
                signed["event_hash"],
            ),
        )

        c.execute(
            "INSERT INTO process_exec_events("
            "task_id,session_id,command_json,cwd,"
            "command_profile,decision,success,exit_code"
            ") VALUES(?,?,?,?,?,?,?,?)",
            (
                task_id,
                session_id,
                json.dumps(redact_value(command)),
                metadata["cwd"],
                metadata["command_profile"],
                "allowed",
                int(success),
                output.get("exit_code")
                if isinstance(output, dict)
                else None,
            ),
        )

    return {
        **event,
        "external_audit": signed,
    }

def proxy_execute(root: Path, task_id: str, session_id: str, tool_name: str, args: dict[str, Any], reason_code: str | None = None, justification: str | None = None, target: str | None = None) -> dict[str, Any]:
    """Evaluate and execute one tool request through the enforced proxy."""
    capability = normalize_capability(tool_name)
    metadata = _preflight(root, task_id, session_id, capability, args)
    canonical_tool = TOOL_NAMES[capability]
    requested = {"tool": tool_name, "capability": capability, "args": redact_value(args), "metadata": metadata}
    append_audit_event(root, "proxy.request", requested, task_id, session_id)
    append_signed_event(root, "proxy.request", requested, task_id, session_id)
    if capability.startswith("coordination."):
        try:
            success, output = _execute_adapter(root, task_id, session_id, capability, args, metadata)
        except Exception as exc:
            success, output = False, {"error": type(exc).__name__, "message": str(exc)}
        event = {"allowed": success, "success": success, "capability": capability, "output": redact_value(output), "metadata": metadata}
        append_audit_event(root, "coordination.completed", event, task_id, session_id)
        signed = append_signed_event(root, "coordination.completed", event, task_id, session_id)
        resource_type=args.get("resource_type"); resource_key=args.get("resource"); lease_id=output.get("lease_id") if isinstance(output,dict) else None
        payload_hash=hashlib.sha256(json.dumps(redact_value(args),sort_keys=True).encode()).hexdigest()
        with connect(root) as c:
            c.execute("INSERT INTO coordination_events(task_id,session_id,event_type,resource_type,resource_key,lease_id,decision,reason,payload_hash,external_event_hash) VALUES(?,?,?,?,?,?,?,?,?,?)",(task_id,session_id,capability,resource_type,resource_key,lease_id,"allowed" if success else "denied",output.get("reason") if isinstance(output,dict) else None,payload_hash,signed["event_hash"]))
        return {**event, "external_audit": signed}
    guard = guard_tool(root, task_id, session_id, canonical_tool, args, reason_code, justification, target)
    if not guard["allowed"]:
        denied = {"allowed": False, "reason": guard["reason"], "capability": capability}
        append_signed_event(root, "proxy.denied", denied, task_id, session_id)
        return denied
    try:
        success, output = _execute_adapter(root, task_id, session_id, capability, args, metadata)
    except Exception as exc:
        success, output = False, {"error": type(exc).__name__, "message": str(exc)}
    summary = json.dumps(redact_value(output), sort_keys=True, ensure_ascii=False)
    canonical = complete_tool(root, guard["execution_token"], args, success, summary, session_id)
    event = {"allowed": True, "success": success, "capability": capability, "tool_call_id": canonical["tool_call_id"], "output": redact_value(output), "metadata": metadata}
    append_audit_event(root, "proxy.completed", event, task_id, session_id)
    signed = append_signed_event(root, "proxy.completed", event, task_id, session_id)
    with connect(root) as c:
        c.execute("INSERT INTO proxy_executions(task_id,session_id,tool_name,capability,decision,success,tool_call_id,external_event_hash) VALUES(?,?,?,?,?,?,?,?)", (task_id, session_id, tool_name, capability, "allowed", int(success), canonical["tool_call_id"], signed["event_hash"]))
        if capability == "process.exec":
            c.execute("INSERT INTO process_exec_events(task_id,session_id,command_json,cwd,command_profile,decision,success,exit_code) VALUES(?,?,?,?,?,?,?,?)", (task_id, session_id, json.dumps(redact_value(args["command"])), metadata["cwd"], metadata["command_profile"], "allowed", int(success), output.get("exit_code")))
    return {**event, "external_audit": signed}
