"""
File: .agents/agentos/project_consolidation_cli.py

Purpose:
    Expose v0.20.2 Primary-Project Consolidation operator commands while
    forwarding older commands to the v0.20.1 CLI wrapper.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .project_consolidation import (
    ProjectConsolidationError,
    add_component_mapping,
    approve_consolidation,
    complete_consolidation,
    create_consolidation,
    docs_check_v0202,
    execute_mapping,
    get_consolidation,
    review_consolidation,
    remove_component_mapping,
    rollback_mapping,
    sync_consolidation_schema,
)


def _emit(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("project-consolidation-create")
    create.add_argument("--candidate-set-id", type=int, required=True)
    create.add_argument("--created-by", required=True)

    show = sub.add_parser("project-consolidation-show")
    show.add_argument("--consolidation-id", type=int, required=True)

    add = sub.add_parser("project-consolidation-add")
    add.add_argument("--consolidation-id", type=int, required=True)
    add.add_argument("--source-project-uuid", required=True)
    add.add_argument("--source-path", required=True)
    add.add_argument("--target-path")
    add.add_argument("--action", choices=["REUSE", "MOVE", "ADAPT", "REIMPLEMENT", "IGNORE", "CONFLICT"], required=True)
    add.add_argument("--reason", required=True)
    add.add_argument("--created-by", required=True)

    remove = sub.add_parser("project-consolidation-remove")
    remove.add_argument("--consolidation-id", type=int, required=True)
    remove.add_argument("--mapping-id", type=int, required=True)
    remove.add_argument("--removed-by", required=True)
    remove.add_argument("--reason", required=True)

    review = sub.add_parser("project-consolidation-review")
    review.add_argument("--consolidation-id", type=int, required=True)
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--reason", required=True)
    review.add_argument("--human-confirmed", action="store_true", required=True)

    approve = sub.add_parser("project-consolidation-approve")
    approve.add_argument("--consolidation-id", type=int, required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--human-confirmed", action="store_true", required=True)

    execute = sub.add_parser("project-consolidation-execute")
    execute.add_argument("--consolidation-id", type=int, required=True)
    execute.add_argument("--mapping-id", type=int, required=True)
    execute.add_argument("--executed-by", required=True)
    execute.add_argument("--prepared-content-file")

    complete = sub.add_parser("project-consolidation-complete")
    complete.add_argument("--consolidation-id", type=int, required=True)
    complete.add_argument("--completed-by", required=True)

    rollback = sub.add_parser("project-consolidation-rollback")
    rollback.add_argument("--consolidation-id", type=int, required=True)
    rollback.add_argument("--mapping-id", type=int, required=True)
    rollback.add_argument("--confirmed-by", required=True)
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--human-confirmed", action="store_true", required=True)

    sub.add_parser("project-consolidation-db-sync")
    sub.add_parser("docs-check-v0202")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "project-consolidation-create":
            return _emit(create_consolidation(root, args.candidate_set_id, created_by=args.created_by))
        if args.command == "project-consolidation-show":
            return _emit(get_consolidation(root, args.consolidation_id))
        if args.command == "project-consolidation-add":
            return _emit(add_component_mapping(
                root, args.consolidation_id,
                source_project_uuid=args.source_project_uuid,
                source_path=args.source_path,
                target_path=args.target_path,
                action=args.action,
                rationale=args.reason,
                created_by=args.created_by,
            ))
        if args.command == "project-consolidation-remove":
            return _emit(remove_component_mapping(root, args.consolidation_id, args.mapping_id, removed_by=args.removed_by, reason=args.reason))
        if args.command == "project-consolidation-review":
            return _emit(review_consolidation(root, args.consolidation_id, reviewed_by=args.reviewed_by, reason=args.reason, human_confirmed=args.human_confirmed))
        if args.command == "project-consolidation-approve":
            return _emit(approve_consolidation(root, args.consolidation_id, approved_by=args.approved_by, reason=args.reason, human_confirmed=args.human_confirmed))
        if args.command == "project-consolidation-execute":
            return _emit(execute_mapping(root, args.consolidation_id, args.mapping_id, executed_by=args.executed_by, prepared_content_file=args.prepared_content_file))
        if args.command == "project-consolidation-complete":
            return _emit(complete_consolidation(root, args.consolidation_id, completed_by=args.completed_by))
        if args.command == "project-consolidation-rollback":
            return _emit(rollback_mapping(root, args.consolidation_id, args.mapping_id, confirmed_by=args.confirmed_by, reason=args.reason, human_confirmed=args.human_confirmed))
        if args.command == "project-consolidation-db-sync":
            return _emit(sync_consolidation_schema(root))
        if args.command == "docs-check-v0202":
            return _emit(docs_check_v0202(root))
        raise AssertionError(args.command)
    except ProjectConsolidationError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
