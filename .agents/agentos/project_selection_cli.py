"""
File: .agents/agentos/project_selection_cli.py

Purpose:
    Expose AgentOS v0.20.1 primary-project selection and compatibility operations
    while preserving v0.20.0 identity commands as the fallback CLI backend.

Responsibilities:
    - Create read-only multi-project candidate sets.
    - Show deterministic domain/purpose compatibility evidence.
    - Require human confirmation for conditional purpose compatibility.
    - Produce advisory primary recommendations.
    - Commit a human-selected primary only when it is the active project root.
    - Validate v0.20.1 bilingual documentation and release synchronization.
"""
from __future__ import annotations

from .cli_identity import cli_program

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from .project_selection import (
    ProjectSelectionError,
    MIGRATION_VERSION,
    confirm_conditional_compatibility,
    create_candidate_set,
    get_candidate_set,
    get_primary_selection,
    recommend_primary,
    select_primary,
    sync_selection_schema,
)


def _root(value: str | None) -> Path:
    """Resolve an explicit or nearest AgentOS project root."""
    if value:
        return Path(value).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return current


def _emit(value: Any) -> int:
    """Print machine-readable JSON and map `ok` to process status."""
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def docs_check_v0201(root: Path) -> dict[str, Any]:
    """Validate v0.20.1 split VI/EN docs, policy, version, and selection module."""
    required = [
        "README.md",
        "README.vi.md",
        "README.en.md",
        "huong_dan.md",
        "huong_dan.vi.md",
        "huong_dan.en.md",
        "UPGRADE_FROM_0.20.0.md",
        "RELEASE_NOTES.md",
        "AGENTS.md",
        "VERSION",
        ".agents/config/governance.json",
        ".agents/config/project.id",
        ".agents/config/project.purpose.json",
        ".agents/docs/PROJECT_IDENTITY.md",
        ".agents/docs/PRIMARY_PROJECT_SELECTION.md",
        ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
        ".agents/agentos/project_identity.py",
        ".agents/agentos/project_selection.py",
        ".agents/agentos/__init__.py",
    ]
    missing = [item for item in required if not (root / item).exists()]
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None

    links: dict[str, dict[str, bool]] = {}
    for name in ("README.md", "huong_dan.md"):
        path = root / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        prefix = "README" if name == "README.md" else "huong_dan"
        links[name] = {"vi": f"{prefix}.vi.md" in text, "en": f"{prefix}.en.md" in text}

    language_switchers: dict[str, bool] = {}
    for name in ("README.vi.md", "README.en.md", "huong_dan.vi.md", "huong_dan.en.md"):
        path = root / name
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if name.startswith("README"):
            language_switchers[name] = "README.vi.md" in text and "README.en.md" in text
        else:
            language_switchers[name] = "huong_dan.vi.md" in text and "huong_dan.en.md" in text

    governance_version = None
    selection_policy_present = False
    identity_policy_present = False
    governance = root / ".agents/config/governance.json"
    if governance.exists():
        try:
            parsed = json.loads(governance.read_text(encoding="utf-8"))
            governance_version = parsed.get("version") or parsed.get("governance_version")
            selection_policy_present = isinstance(parsed.get("primary_project_selection_policy"), dict)
            identity_policy_present = isinstance(parsed.get("project_identity_policy"), dict)
        except Exception:
            pass

    package_version = None
    package = root / ".agents/agentos/__init__.py"
    if package.exists():
        match = re.search(
            r'(?m)^\s*__version__\s*=\s*["\']([^"\']+)["\']',
            package.read_text(encoding="utf-8"),
        )
        if match:
            package_version = match.group(1)

    changelog_has_current_version = False
    changelog = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    if changelog.exists():
        changelog_has_current_version = "v0.20.1" in changelog.read_text(encoding="utf-8")

    version_consistent = (
        version == "0.20.1"
        and governance_version == "0.20.1"
        and package_version == "0.20.1"
    )
    ok = (
        not missing
        and version_consistent
        and all(item["vi"] and item["en"] for item in links.values())
        and all(language_switchers.values())
        and changelog_has_current_version
        and selection_policy_present
        and identity_policy_present
    )
    return {
        "ok": ok,
        "version": {
            "VERSION": version,
            "governance.json": governance_version,
            "__init__.py": package_version,
            "consistent": version_consistent,
        },
        "required_version": "0.20.1",
        "schema": MIGRATION_VERSION,
        "missing_documents": missing,
        "landing_links": links,
        "language_switchers": language_switchers,
        "changelog_has_current_version": changelog_has_current_version,
        "project_identity_policy_present": identity_policy_present,
        "primary_project_selection_policy_present": selection_policy_present,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the additive v0.20.1 CLI parser."""
    parser = argparse.ArgumentParser(prog=cli_program())
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("project-candidate-set-create")
    create.add_argument("--source-root", action="append", default=[], required=True)
    create.add_argument("--created-by", required=True)

    show = sub.add_parser("project-candidate-set-show")
    show.add_argument("--candidate-set-id", type=int, required=True)

    compat = sub.add_parser("project-compatibility-show")
    compat.add_argument("--candidate-set-id", type=int, required=True)

    confirm = sub.add_parser("project-compatibility-confirm")
    confirm.add_argument("--candidate-set-id", type=int, required=True)
    confirm.add_argument("--project-a", required=True)
    confirm.add_argument("--project-b", required=True)
    confirm.add_argument("--confirmed-by", required=True)
    confirm.add_argument("--reason", required=True)
    confirm.add_argument("--human-confirmed", action="store_true", required=True)

    recommend = sub.add_parser("project-primary-recommend")
    recommend.add_argument("--candidate-set-id", type=int, required=True)

    select = sub.add_parser("project-primary-select")
    select.add_argument("--candidate-set-id", type=int, required=True)
    select.add_argument("--project-uuid", required=True)
    select.add_argument("--confirmed-by", required=True)
    select.add_argument("--reason", required=True)
    select.add_argument("--human-confirmed", action="store_true", required=True)

    status = sub.add_parser("project-primary-status")
    status.add_argument("--candidate-set-id", type=int, required=True)

    sub.add_parser("project-selection-db-sync")
    sub.add_parser("docs-check-v0201")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch v0.20.1 commands and return a shell status code."""
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    try:
        if args.command == "project-candidate-set-create":
            return _emit(
                create_candidate_set(root, args.source_root, created_by=args.created_by)
            )
        if args.command == "project-candidate-set-show":
            return _emit(get_candidate_set(root, args.candidate_set_id))
        if args.command == "project-compatibility-show":
            state = get_candidate_set(root, args.candidate_set_id)
            return _emit(
                {
                    "ok": True,
                    "candidate_set_id": args.candidate_set_id,
                    "compatibility": state["compatibility"],
                }
            )
        if args.command == "project-compatibility-confirm":
            return _emit(
                confirm_conditional_compatibility(
                    root,
                    args.candidate_set_id,
                    args.project_a,
                    args.project_b,
                    confirmed_by=args.confirmed_by,
                    reason=args.reason,
                    human_confirmed=args.human_confirmed,
                )
            )
        if args.command == "project-primary-recommend":
            return _emit(recommend_primary(root, args.candidate_set_id))
        if args.command == "project-primary-select":
            return _emit(
                select_primary(
                    root,
                    args.candidate_set_id,
                    args.project_uuid,
                    selected_by=args.confirmed_by,
                    reason=args.reason,
                    human_confirmed=args.human_confirmed,
                )
            )
        if args.command == "project-primary-status":
            return _emit(get_primary_selection(root, args.candidate_set_id))
        if args.command == "project-selection-db-sync":
            return _emit(sync_selection_schema(root))
        if args.command == "docs-check-v0201":
            return _emit(docs_check_v0201(root))
        raise AssertionError(args.command)
    except ProjectSelectionError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    sys.exit(main())
