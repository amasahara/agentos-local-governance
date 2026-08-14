"""
File: .agents/agentos/db_aware_context_projection_cli.py

Purpose:
    Expose read-only v0.24.2 DB-aware context projection inspection commands.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .db_aware_context_projection import DBAwareProjectionError, preview_file, projection_status


def _emit(value: object) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("context-db-projection-preview")
    p.add_argument("--path", required=True)

    p = sub.add_parser("context-db-projection-status")
    p.add_argument("--task-id", required=True)
    p.add_argument("--revision", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.command == "context-db-projection-preview":
            return _emit(preview_file(root, args.path))
        if args.command == "context-db-projection-status":
            return _emit(projection_status(root, args.task_id, args.revision))
        raise AssertionError(args.command)
    except DBAwareProjectionError as exc:
        return _emit({"ok": False, "error": str(exc), "command": args.command})


if __name__ == "__main__":
    raise SystemExit(main())
