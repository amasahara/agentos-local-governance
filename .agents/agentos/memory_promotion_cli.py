"""
File: .agents/agentos/memory_promotion_cli.py

Purpose:
    Expose v0.31.1 governed memory-promotion operations through the unified CLI.

Responsibilities:
    - Read promotion status and eligibility.
    - Create/reuse non-active memory candidates.
    - Finalize approve/reject only through the control-plane-only command.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .memory_promotion import (
    create_memory_promotion_candidate,
    evaluate_memory_promotion,
    finalize_memory_promotion_candidate,
    memory_promotion_status,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.31.1 memory-promotion CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos memory-promotion")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("memory-promotion-status")
    status.add_argument("--finding-id", type=int)

    evaluate = sub.add_parser("memory-promotion-evaluate")
    evaluate.add_argument("--finding-id", type=int, required=True)

    create = sub.add_parser("memory-promotion-candidate-create")
    create.add_argument("--finding-id", type=int, required=True)

    finalize = sub.add_parser("memory-promotion-finalize")
    finalize.add_argument("--memory-id", type=int, required=True)
    finalize.add_argument("--decision-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.31.1 memory-promotion CLI command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "memory-promotion-status":
            value = memory_promotion_status(root, finding_id=args.finding_id)
        elif args.command == "memory-promotion-evaluate":
            value = evaluate_memory_promotion(root, args.finding_id)
        elif args.command == "memory-promotion-candidate-create":
            value = create_memory_promotion_candidate(
                root,
                args.finding_id,
                raised_by_session=os.environ.get("AGENTOS_SESSION_ID"),
            )
        elif args.command == "memory-promotion-finalize":
            value = finalize_memory_promotion_candidate(
                root,
                args.memory_id,
                args.decision_id,
                expected_task_id=os.environ.get("AGENTOS_TASK_ID"),
            )
        else:
            raise RuntimeError("unknown_memory_promotion_command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
