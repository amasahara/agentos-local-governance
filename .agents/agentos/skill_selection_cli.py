"""Path: .agents/agentos/skill_selection_cli.py
Purpose: Explicit CLI selection/evaluation and read-only inspection for AgentOS v0.27.1.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .skill_selection import (
    run_skill_evaluation,
    run_skill_selection,
    skill_evaluation_get,
    skill_selection_candidates_get,
    skill_selection_status,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _list_json(value: str | None, field: str) -> list[str] | None:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise RuntimeError(f"{field}_must_be_json_string_array")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("skill-selection-run")
    p.add_argument("--task-id", required=True)
    p.add_argument("--available-tools")
    p.add_argument("--available-capabilities")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("skill-selection-status")
    p.add_argument("--task-id")
    p.add_argument("--run-id", type=int)

    p = sub.add_parser("skill-selection-candidates")
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--eligible-only", action="store_true")

    p = sub.add_parser("skill-evaluation-run")
    p.add_argument("--selection-run-id", type=int, required=True)
    p.add_argument("--skill-id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "skill-selection-run":
            value = run_skill_selection(
                root,
                args.task_id,
                available_tools=_list_json(args.available_tools, "available_tools"),
                available_capabilities=_list_json(args.available_capabilities, "available_capabilities"),
                limit=args.limit,
            )
        elif args.command == "skill-selection-status":
            value = skill_selection_status(root, task_id=args.task_id, run_id=args.run_id)
        elif args.command == "skill-selection-candidates":
            value = skill_selection_candidates_get(root, args.run_id, eligible_only=args.eligible_only)
        elif args.command == "skill-evaluation-run":
            value = run_skill_evaluation(root, args.selection_run_id, skill_id=args.skill_id)
        else:
            raise RuntimeError("unknown skill selection command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
