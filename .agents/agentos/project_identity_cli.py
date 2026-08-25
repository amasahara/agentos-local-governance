"""
File: .agents/agentos/project_identity_cli.py
Purpose: Provide current project bootstrap, adoption, policy compilation, repository-role validation, and identity CLI operations.
Responsibilities:
- Initialize or adopt projects without overwriting application-root metadata.
- Separate distribution metadata from installed-project metadata.
- Compile current governance plus modular policy fragments deterministically.
- Validate distribution and governed-project repository roles.
- Preserve historical identity commands required by regression coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any
from uuid import uuid4

from . import __version__
from .project_identity import (
    ProjectIdentityError,
    ROLE_VALUES,
    ensure_instance_id,
    ensure_project_id,
    fork_project_identity,
    load_purpose,
    set_purpose,
    sync_identity_to_database,
    verify_identity,
)
from .schema_version import CURRENT_SCHEMA_VERSION

REPOSITORY_ROLES = ("agentos_distribution", "governed_project")
CURRENT_LAUNCHERS = {
    "agentos",
    "agentos.cmd",
    "agentos-admin",
    "agentos-admin.cmd",
    "agentos-mcp",
    "agentos-mcp.cmd",
    "agentos-gatewayd",
    "agentos-gatewayd.cmd",
}
CURRENT_DOCS = {
    "QUICKSTART.md",
    "NEW_PROJECT.md",
    "EXISTING_PROJECT.md",
    "WINDOWS.md",
    "REFERENCE.md",
}


def _root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProjectIdentityError(f"JSON document must contain an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key in sorted(override):
        left = result.get(key)
        right = override[key]
        result[key] = (
            _merge(left, right)
            if isinstance(left, dict) and isinstance(right, dict)
            else right
        )
    return result


def compile_effective_policy(root: Path) -> dict[str, Any]:
    """Compile the current baseline, modular fragments, and local override.

    Args:
        root: Governed project root.
    Returns:
        Output path, source hashes, release identity, and effective policy hash.
    Raises:
        ProjectIdentityError: If a required policy source is missing or invalid.
        OSError: If a policy source or generated output cannot be accessed.
    Side effects:
        Atomically replaces the generated effective policy document.
    """
    base = root / ".agents/config/governance.json"
    sources = sorted((root / ".agents/config/policy").glob("*.json"))
    if not base.is_file():
        raise ProjectIdentityError("missing current governance baseline")
    if not sources:
        raise ProjectIdentityError("no modular policy fragments found")

    effective = _load_object(base)
    evidence = [{
        "path": base.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
    }]
    for source in sources:
        effective = _merge(effective, _load_object(source))
        evidence.append({
            "path": source.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        })

    local = root / ".agents/config/governance.local.json"
    if local.exists():
        effective = _merge(effective, _load_object(local))
        evidence.append({
            "path": local.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
        })

    effective["version"] = __version__
    effective["schema_version"] = CURRENT_SCHEMA_VERSION
    effective["repository_role"] = "governed_project"
    effective["policy_compilation"] = {
        "format": 1,
        "source_order": [item["path"] for item in evidence],
    }
    digest = hashlib.sha256(_canonical(effective).encode("utf-8")).hexdigest()
    output = root / ".agents/config/generated/governance.effective.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    _write_json(temporary, effective)
    temporary.replace(output)
    return {
        "ok": True,
        "version": __version__,
        "schema": CURRENT_SCHEMA_VERSION,
        "output": output.relative_to(root).as_posix(),
        "effective_policy_hash": digest,
        "sources": evidence,
    }


def validate_repository(root: Path, role: str) -> dict[str, Any]:
    """Validate a repository against an explicit repository role.

    Args:
        root: Repository root.
        role: agentos_distribution or governed_project.
    Returns:
        Machine-readable validation findings and current release identity.
    Raises:
        ProjectIdentityError: If the role or metadata is invalid.
        OSError: If repository metadata cannot be read.
    Side effects:
        None.
    """
    if role not in REPOSITORY_ROLES:
        raise ProjectIdentityError(f"unsupported repository role: {role}")

    required = (
        (
            "VERSION",
            "README.md",
            "README.en.md",
            ".agents/distribution/metadata.json",
            ".agents/agentos",
            ".agents/bin",
            ".agents/config/governance.json",
            ".agents/config/policy",
        )
        if role == "agentos_distribution"
        else (
            ".agents/release/VERSION",
            ".agents/release/install-manifest.json",
            ".agents/project/identity.json",
            ".agents/project/purpose.json",
            ".agents/config/generated/governance.effective.json",
        )
    )
    findings = [
        {"code": "missing_required_path", "path": rel}
        for rel in required
        if not (root / rel).exists()
    ]

    if role == "agentos_distribution":
        metadata_path = root / ".agents/distribution/metadata.json"
        if metadata_path.is_file():
            metadata = _load_object(metadata_path)
            expected = {
                "repository_role": "agentos_distribution",
                "agentos_version": __version__,
                "schema_version": CURRENT_SCHEMA_VERSION,
            }
            for key, value in expected.items():
                if metadata.get(key) != value:
                    findings.append({
                        "code": "distribution_metadata_mismatch",
                        "field": key,
                        "expected": value,
                        "actual": metadata.get(key),
                    })
        version_path = root / "VERSION"
        if version_path.is_file():
            actual_version = version_path.read_text(encoding="utf-8").strip()
            if actual_version != __version__:
                findings.append({
                    "code": "release_version_mismatch",
                    "path": "VERSION",
                    "expected": __version__,
                    "actual": actual_version,
                })
    else:
        manifest = root / ".agents/release/install-manifest.json"
        if manifest.is_file():
            installed = _load_object(manifest).get("installed_paths", [])
            if not isinstance(installed, list):
                findings.append({
                    "code": "invalid_installed_paths",
                    "path": ".agents/release/install-manifest.json",
                })
            else:
                findings.extend(
                    {
                        "code": "application_root_metadata_owned_by_agentos",
                        "path": rel,
                    }
                    for rel in ("README.md", "README.en.md", "VERSION", "huong_dan.md")
                    if rel in installed
                )

    return {
        "ok": not findings,
        "role": role,
        "release": __version__,
        "schema": CURRENT_SCHEMA_VERSION,
        "findings": findings,
    }


def _copy_payload(distribution: Path, target: Path) -> list[str]:
    installed: list[str] = []
    for rel in ("agentos", "schema"):
        source = distribution / ".agents" / rel
        if source.exists():
            shutil.copytree(
                source,
                target / ".agents" / rel,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
            )
            installed.append(f".agents/{rel}")

    source_bin = distribution / ".agents/bin"
    target_bin = target / ".agents/bin"
    target_bin.mkdir(parents=True, exist_ok=True)
    for name in sorted(CURRENT_LAUNCHERS):
        source = source_bin / name
        if source.is_file():
            shutil.copy2(source, target_bin / name)
            installed.append(f".agents/bin/{name}")

    baseline = distribution / ".agents/config/governance.json"
    if not baseline.is_file():
        raise ProjectIdentityError("distribution is missing current governance baseline")
    target_baseline = target / ".agents/config/governance.json"
    target_baseline.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(baseline, target_baseline)
    installed.append(".agents/config/governance.json")

    source_policy = distribution / ".agents/config/policy"
    if not source_policy.is_dir():
        raise ProjectIdentityError("distribution is missing modular policy sources")
    shutil.copytree(
        source_policy,
        target / ".agents/config/policy",
        dirs_exist_ok=True,
    )
    installed.append(".agents/config/policy")

    docs = target / ".agents/docs"
    docs.mkdir(parents=True, exist_ok=True)
    for name in sorted(CURRENT_DOCS):
        source = distribution / ".agents/docs" / name
        if source.is_file():
            shutil.copy2(source, docs / name)
            installed.append(f".agents/docs/{name}")
    return installed


def _bootstrap(distribution: Path, target: Path, mode: str) -> dict[str, Any]:
    installed = _copy_payload(distribution, target)
    project_uuid = str(uuid4())
    _write_json(
        target / ".agents/project/identity.json",
        {
            "identity_version": 1,
            "project_uuid": project_uuid,
            "created_by": f"agentos_{mode}",
        },
    )
    _write_json(
        target / ".agents/project/purpose.json",
        {
            "status": "UNCONFIRMED",
            "domain": None,
            "purpose": None,
            "role": None,
            "capabilities": [],
        },
    )
    installed.extend([
        ".agents/project/identity.json",
        ".agents/project/purpose.json",
    ])

    release = target / ".agents/release"
    release.mkdir(parents=True, exist_ok=True)
    (release / "VERSION").write_text(__version__ + "\n", encoding="utf-8")
    installed.append(".agents/release/VERSION")
    policy = compile_effective_policy(target)
    installed.append(policy["output"])
    _write_json(
        release / "install-manifest.json",
        {
            "format": 1,
            "role": "governed_project",
            "agentos_version": __version__,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "mode": mode,
            "installed_paths": sorted(installed),
            "application_root_paths_written": [],
        },
    )
    return {
        "ok": True,
        "mode": mode,
        "target": str(target),
        "project_uuid": project_uuid,
        "purpose_status": "UNCONFIRMED",
        "application_root_paths_written": [],
        "policy": policy,
    }


def project_init(distribution: Path, target: Path) -> dict[str, Any]:
    """Initialize a new governed project.

    Args:
        distribution: AgentOS distribution root.
        target: New application project root.
    Returns:
        Bootstrap metadata including the generated project UUID.
    Raises:
        ProjectIdentityError: If the target is already governed.
        OSError: If the target payload cannot be written.
    Side effects:
        Creates the target when needed and writes only below target/.agents.
    """
    if (target / ".agents/release/install-manifest.json").exists():
        raise ProjectIdentityError("target is already governed")
    target.mkdir(parents=True, exist_ok=True)
    return _bootstrap(distribution, target, "project-init")


def project_adopt(
    distribution: Path,
    target: Path,
    apply: bool,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Inspect or adopt an existing application project.

    Args:
        distribution: AgentOS distribution root.
        target: Existing application project root.
        apply: Apply the adoption plan when true.
        human_confirmed: Human confirmation for mutation.
    Returns:
        A read-only plan or adoption metadata.
    Raises:
        ProjectIdentityError: If apply lacks confirmation.
        OSError: If discovery or the approved target write fails.
    Side effects:
        The default is read-only; apply writes only below target/.agents.
    """
    signals = {
        "git": (target / ".git").exists(),
        "readme": (target / "README.md").exists(),
        "version": (target / "VERSION").exists(),
        "tests": (target / "tests").exists(),
        "source_roots": [
            name
            for name in ("src", "app", "apps", "lib")
            if (target / name).is_dir()
        ],
    }
    if not apply:
        return {
            "ok": True,
            "mode": "read_only_plan",
            "target": str(target),
            "signals": signals,
            "writes": [".agents/**"],
            "preserved": [
                "README.md",
                "VERSION",
                "application source",
                "tests",
            ],
        }
    if not human_confirmed:
        raise ProjectIdentityError("--apply requires --human-confirmed")
    result = _bootstrap(distribution, target, "project-adopt")
    result["signals"] = signals
    return result


def docs_check_v0200(root: Path) -> dict[str, Any]:
    """Run the historical v0.20.0 file-presence compatibility check.

    Args:
        root: Distribution repository root.
    Returns:
        Compatibility findings for the historical documentation contract.
    Raises:
        OSError: If VERSION cannot be read.
    Side effects:
        None.
    """
    required = (
        "README.md",
        "README.vi.md",
        "README.en.md",
        "huong_dan.md",
        "huong_dan.vi.md",
        "huong_dan.en.md",
        "AGENTS.md",
        "VERSION",
        ".agents/config/governance.json",
        ".agents/config/project.id",
        ".agents/config/project.purpose.json",
        ".agents/docs/PROJECT_IDENTITY.md",
        ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
        ".agents/agentos/__init__.py",
    )
    missing = [item for item in required if not (root / item).exists()]
    version = (
        (root / "VERSION").read_text(encoding="utf-8").strip()
        if (root / "VERSION").exists()
        else None
    )
    return {
        "ok": not missing,
        "version": {"VERSION": version},
        "required_version": "0.20.0",
        "schema": CURRENT_SCHEMA_VERSION,
        "missing_documents": missing,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the project lifecycle and historical identity parser.

    Args:
        None.
    Returns:
        Configured argument parser.
    Raises:
        None.
    Side effects:
        None.
    """
    program = (
        "agentos-admin"
        if os.environ.get("AGENTOS_EXECUTION_PLANE") == "control"
        else "agentos"
    )
    parser = argparse.ArgumentParser(prog=program)
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    item = sub.add_parser("project-init")
    item.add_argument("--project-root", "--target", dest="target", required=True)
    item.add_argument("--distribution-root")

    item = sub.add_parser("project-adopt")
    item.add_argument("--project-root", "--target", dest="target", required=True)
    item.add_argument("--distribution-root")
    item.add_argument("--apply", action="store_true")
    item.add_argument("--human-confirmed", action="store_true")

    item = sub.add_parser("repository-validate")
    item.add_argument("--role", required=True, choices=REPOSITORY_ROLES)

    item = sub.add_parser("policy-compile")
    item.add_argument("--project-root")

    sub.add_parser("project-identity-init")
    sub.add_parser("project-identity-show")

    item = sub.add_parser("project-identity-verify")
    item.add_argument("--allow-missing-purpose", action="store_true")

    item = sub.add_parser("project-purpose-set")
    item.add_argument("--name", required=True)
    item.add_argument("--domain-id", required=True)
    item.add_argument("--domain-name", required=True)
    item.add_argument("--purpose-id", required=True)
    item.add_argument("--description", required=True)
    item.add_argument("--role", required=True, choices=sorted(ROLE_VALUES))
    item.add_argument("--capability", action="append", default=[], required=True)
    item.add_argument("--confirmed-by", required=True)
    item.add_argument("--human-confirmed", action="store_true", required=True)

    sub.add_parser("project-purpose-show")

    item = sub.add_parser("project-fork")
    item.add_argument("--confirmed-by", required=True)
    item.add_argument("--human-confirmed", action="store_true", required=True)
    item.add_argument("--new-name")

    sub.add_parser("project-identity-db-sync")
    sub.add_parser("docs-check-v0200")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one project lifecycle or identity command.

    Args:
        argv: Optional command arguments; process arguments are used when absent.
    Returns:
        Zero for successful results, otherwise one.
    Raises:
        None; supported operational failures are emitted as JSON.
    Side effects:
        Depends on the selected command; inspection commands remain read-only.
    """
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    try:
        if args.command == "project-init":
            distribution = (
                _root(args.distribution_root)
                if args.distribution_root
                else root
            )
            return _emit(project_init(distribution, Path(args.target).resolve()))
        if args.command == "project-adopt":
            distribution = (
                _root(args.distribution_root)
                if args.distribution_root
                else root
            )
            return _emit(project_adopt(
                distribution,
                Path(args.target).resolve(),
                args.apply,
                args.human_confirmed,
            ))
        if args.command == "repository-validate":
            return _emit(validate_repository(root, args.role))
        if args.command == "policy-compile":
            project_root = (
                Path(args.project_root).resolve()
                if args.project_root
                else root
            )
            return _emit(compile_effective_policy(project_root))
        if args.command == "project-identity-init":
            return _emit({
                "ok": True,
                "project": ensure_project_id(
                    root,
                    created_by="agentos_v0.20.0",
                ),
                "instance": ensure_instance_id(root),
            })
        if args.command == "project-identity-show":
            return _emit({
                "ok": True,
                "project": ensure_project_id(root),
                "instance": ensure_instance_id(root),
                "purpose": load_purpose(root),
            })
        if args.command == "project-identity-verify":
            return _emit(verify_identity(
                root,
                require_purpose=not args.allow_missing_purpose,
            ))
        if args.command == "project-purpose-set":
            value = set_purpose(
                root,
                name=args.name,
                domain_id=args.domain_id,
                domain_name=args.domain_name,
                purpose_id=args.purpose_id,
                purpose_description=args.description,
                capabilities=args.capability,
                role=args.role,
                confirmed_by=args.confirmed_by,
                human_confirmed=args.human_confirmed,
            )
            try:
                sync_identity_to_database(root)
            except ProjectIdentityError:
                pass
            return _emit({"ok": True, "purpose": value})
        if args.command == "project-purpose-show":
            return _emit({"ok": True, "purpose": load_purpose(root)})
        if args.command == "project-fork":
            value = fork_project_identity(
                root,
                confirmed_by=args.confirmed_by,
                human_confirmed=args.human_confirmed,
                new_name=args.new_name,
            )
            try:
                sync_identity_to_database(root)
            except ProjectIdentityError:
                pass
            return _emit({"ok": True, "project": value})
        if args.command == "project-identity-db-sync":
            return _emit(sync_identity_to_database(root))
        if args.command == "docs-check-v0200":
            return _emit(docs_check_v0200(root))
        raise AssertionError(args.command)
    except (ProjectIdentityError, OSError, json.JSONDecodeError) as exc:
        return _emit({
            "ok": False,
            "error": str(exc),
            "command": args.command,
        })


if __name__ == "__main__":
    sys.exit(main())
