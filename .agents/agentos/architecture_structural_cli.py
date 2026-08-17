"""Path: .agents/agentos/architecture_structural_cli.py
Purpose: CLI inspection and explicit structural enforcement for AgentOS v0.26.1.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .architecture_structural import (
    architecture_structural_check,
    architecture_structural_findings,
    architecture_structural_status,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("architecture-structural-check")
    p.add_argument("--task-id")
    p.add_argument("--changed-file", action="append", default=[])
    p.add_argument("--mode", default="manual")
    p = sub.add_parser("architecture-structural-status")
    p = sub.add_parser("architecture-structural-findings")
    p.add_argument("--run-id", type=int)
    p.add_argument("--task-id")
    p.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "architecture-structural-check":
            value = architecture_structural_check(root, task_id=args.task_id, changed_files=args.changed_file, mode=args.mode, created_by="cli:architecture-structural")
        elif args.command == "architecture-structural-status":
            value = architecture_structural_status(root)
        elif args.command == "architecture-structural-findings":
            value = architecture_structural_findings(root, run_id=args.run_id, task_id=args.task_id, limit=args.limit)
        else:
            raise RuntimeError("unknown architecture structural command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
