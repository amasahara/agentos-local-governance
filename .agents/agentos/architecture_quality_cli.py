"""Path: .agents/agentos/architecture_quality_cli.py
Purpose: CLI inspection and explicit quality/operational enforcement for AgentOS v0.26.3.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .architecture_quality import architecture_quality_check, architecture_quality_findings, architecture_quality_status


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("architecture-quality-check")
    p.add_argument("--task-id")
    p.add_argument("--plan-id", type=int)
    p.add_argument("--changed-file", action="append", default=[])
    p.add_argument("--mode", default="manual")
    sub.add_parser("architecture-quality-status")
    p = sub.add_parser("architecture-quality-findings")
    p.add_argument("--run-id", type=int)
    p.add_argument("--task-id")
    p.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "architecture-quality-check":
            value = architecture_quality_check(root, task_id=args.task_id, plan_id=args.plan_id, changed_files=args.changed_file, mode=args.mode, created_by="cli:architecture-quality")
        elif args.command == "architecture-quality-status":
            value = architecture_quality_status(root)
        elif args.command == "architecture-quality-findings":
            value = architecture_quality_findings(root, run_id=args.run_id, task_id=args.task_id, limit=args.limit)
        else:
            raise RuntimeError("unknown architecture quality command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
