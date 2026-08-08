"""
File: .agents/agentos/project_identity_cli.py

Purpose:
    Expose v0.20.0 project identity and purpose operations without requiring
    assumptions about the internal v0.19.5 CLI parser implementation.

Responsibilities:
    - Dispatch additive identity commands from the AgentOS launcher wrapper.
    - Keep mutations human-confirmed and MCP read-only.
    - Provide split-documentation checks for the v0.20.0 GitHub layout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .project_identity import (
    ProjectIdentityError,
    ROLE_VALUES,
    SCHEMA_VERSION,
    ensure_instance_id,
    ensure_project_id,
    fork_project_identity,
    load_purpose,
    set_purpose,
    sync_identity_to_database,
    verify_identity,
)


def _root(value: str | None) -> Path:
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def docs_check_v0200(root: Path) -> dict[str, Any]:
    """Validate the split VI/EN documentation and release synchronization.

    Args:
        root: AgentOS project root.

    Returns:
        Machine-readable documentation/version synchronization report.
    """
    required = [
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
    ]
    missing = [item for item in required if not (root / item).exists()]
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None

    links: dict[str, dict[str, bool]] = {}
    for name in ("README.md", "huong_dan.md"):
        p = root / name
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        prefix = "README" if name == "README.md" else "huong_dan"
        links[name] = {
            "vi": f"{prefix}.vi.md" in text,
            "en": f"{prefix}.en.md" in text,
        }

    language_switchers: dict[str, bool] = {}
    for name in ("README.vi.md", "README.en.md", "huong_dan.vi.md", "huong_dan.en.md"):
        p = root / name
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        if name.startswith("README"):
            language_switchers[name] = "README.vi.md" in text and "README.en.md" in text
        else:
            language_switchers[name] = "huong_dan.vi.md" in text and "huong_dan.en.md" in text

    governance_version = None
    identity_policy_present = False
    gov = root / ".agents/config/governance.json"
    if gov.exists():
        try:
            parsed = json.loads(gov.read_text(encoding="utf-8"))
            governance_version = parsed.get("version") or parsed.get("governance_version")
            identity_policy_present = isinstance(parsed.get("project_identity_policy"), dict)
        except Exception:
            pass

    package_version = None
    package = root / ".agents/agentos/__init__.py"
    if package.exists():
        text = package.read_text(encoding="utf-8")
        import re
        match = re.search(r'(?m)^\s*__version__\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            package_version = match.group(1)

    changelog_has_current_version = False
    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    if changelog.exists():
        changelog_has_current_version = "v0.20.0" in changelog.read_text(encoding="utf-8")

    identity_documents_valid = False
    if (root / ".agents/config/project.id").exists() and (root / ".agents/config/project.purpose.json").exists():
        try:
            ensure_project_id(root)
            load_purpose(root, required=True)
            identity_documents_valid = True
        except ProjectIdentityError:
            identity_documents_valid = False

    version_consistent = (
        version == "0.20.0"
        and governance_version == "0.20.0"
        and package_version == "0.20.0"
    )
    ok = (
        not missing
        and version_consistent
        and all(item["vi"] and item["en"] for item in links.values())
        and all(language_switchers.values())
        and changelog_has_current_version
        and identity_policy_present
        and identity_documents_valid
    )
    return {
        "ok": ok,
        "version": {
            "VERSION": version,
            "governance.json": governance_version,
            "__init__.py": package_version,
            "consistent": version_consistent,
        },
        "required_version": "0.20.0",
        "schema": SCHEMA_VERSION,
        "missing_documents": missing,
        "landing_links": links,
        "language_switchers": language_switchers,
        "changelog_has_current_version": changelog_has_current_version,
        "project_identity_policy_present": identity_policy_present,
        "identity_documents_valid": identity_documents_valid,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("project-identity-init")
    sub.add_parser("project-identity-show")
    verify = sub.add_parser("project-identity-verify")
    verify.add_argument("--allow-missing-purpose", action="store_true")

    purpose = sub.add_parser("project-purpose-set")
    purpose.add_argument("--name", required=True)
    purpose.add_argument("--domain-id", required=True)
    purpose.add_argument("--domain-name", required=True)
    purpose.add_argument("--purpose-id", required=True)
    purpose.add_argument("--description", required=True)
    purpose.add_argument("--role", required=True, choices=sorted(ROLE_VALUES))
    purpose.add_argument("--capability", action="append", default=[], required=True)
    purpose.add_argument("--confirmed-by", required=True)
    purpose.add_argument("--human-confirmed", action="store_true", required=True)

    sub.add_parser("project-purpose-show")
    fork = sub.add_parser("project-fork")
    fork.add_argument("--confirmed-by", required=True)
    fork.add_argument("--human-confirmed", action="store_true", required=True)
    fork.add_argument("--new-name")
    sub.add_parser("project-identity-db-sync")
    sub.add_parser("docs-check-v0200")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    try:
        if args.command == "project-identity-init":
            project = ensure_project_id(root, created_by="agentos_v0.20.0")
            instance = ensure_instance_id(root)
            return _emit({"ok": True, "project": project, "instance": instance})
        if args.command == "project-identity-show":
            return _emit(
                {
                    "ok": True,
                    "project": ensure_project_id(root),
                    "instance": ensure_instance_id(root),
                    "purpose": load_purpose(root),
                }
            )
        if args.command == "project-identity-verify":
            return _emit(
                verify_identity(root, require_purpose=not args.allow_missing_purpose)
            )
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
    except ProjectIdentityError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    sys.exit(main())
