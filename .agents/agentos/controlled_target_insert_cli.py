"""
File: .agents/agentos/controlled_target_insert_cli.py

Purpose:
    Provide human/operator CLI commands for AgentOS v0.22.0 controlled TARGET INSERT.

Responsibilities:
    - Create, review, approve, inspect, and execute controlled insert plans.
    - Keep approval and execution outside MCP/LLM mutation capabilities.
    - Emit JSON-only privacy-safe command results.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .controlled_target_insert import (
    ControlledTargetInsertError,
    approve_target_insert_plan,
    build_insert_spec,
    create_target_insert_plan,
    docs_check_v0220,
    execute_target_insert,
    get_target_insert_plan,
    get_target_insert_readiness,
    get_target_insert_receipt,
    sync_controlled_target_insert_schema,
)


def _emit(value: Any) -> int:
    """Print JSON result and return a conventional process code."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build v0.22.0 controlled-insert CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos controlled-target-insert")
    parser.add_argument("--root", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("db-target-insert-plan-create")
    p.add_argument("--extraction-batch-id", type=int, required=True)
    p.add_argument("--created-by", required=True)
    p.add_argument("--chunk-size", type=int, default=500)

    for name in ("db-target-insert-plan-show", "db-target-insert-readiness", "db-target-insert-spec", "db-target-insert-receipt"):
        p = sub.add_parser(name)
        p.add_argument("--insert-run-id", type=int, required=True)

    p = sub.add_parser("db-target-insert-plan-review")
    p.add_argument("--insert-run-id", type=int, required=True)
    p.add_argument("--reviewed-by", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("db-target-insert-plan-approve")
    p.add_argument("--insert-run-id", type=int, required=True)
    p.add_argument("--approved-by", required=True)
    p.add_argument("--human-confirmed", action="store_true")

    p = sub.add_parser("db-target-insert-execute")
    p.add_argument("--insert-run-id", type=int, required=True)

    sub.add_parser("db-controlled-target-insert-db-sync")
    sub.add_parser("docs-check-v0220")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute a v0.22.0 operator command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "db-target-insert-plan-create":
            return _emit(create_target_insert_plan(root, extraction_batch_id=args.extraction_batch_id, created_by=args.created_by, chunk_size=args.chunk_size))
        if args.command == "db-target-insert-plan-show":
            return _emit(get_target_insert_plan(root, args.insert_run_id))
        if args.command == "db-target-insert-readiness":
            return _emit(get_target_insert_readiness(root, args.insert_run_id))
        if args.command == "db-target-insert-spec":
            return _emit(build_insert_spec(root, args.insert_run_id))
        if args.command == "db-target-insert-plan-review":
            from .controlled_target_insert import review_target_insert_plan
            return _emit(review_target_insert_plan(root, args.insert_run_id, reviewed_by=args.reviewed_by, human_confirmed=args.human_confirmed))
        if args.command == "db-target-insert-plan-approve":
            return _emit(approve_target_insert_plan(root, args.insert_run_id, approved_by=args.approved_by, human_confirmed=args.human_confirmed))
        if args.command == "db-target-insert-execute":
            return _emit(execute_target_insert(root, args.insert_run_id))
        if args.command == "db-target-insert-receipt":
            return _emit(get_target_insert_receipt(root, args.insert_run_id))
        if args.command == "db-controlled-target-insert-db-sync":
            return _emit(sync_controlled_target_insert_schema(root))
        if args.command == "docs-check-v0220":
            return _emit(docs_check_v0220(root))
    except ControlledTargetInsertError as exc:
        return _emit({"ok": False, "error": str(exc)})
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
