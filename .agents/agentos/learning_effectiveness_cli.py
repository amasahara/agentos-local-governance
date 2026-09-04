"""
File: .agents/agentos/learning_effectiveness_cli.py

Purpose:
    Expose v0.31.3 comparative effectiveness, drift, and explicit review requests.

Responsibilities:
    - Inspect effectiveness/drift status without mutating knowledge.
    - Evaluate one actually-used knowledge artifact against deterministic controls.
    - Evaluate architecture/scope drift conservatively.
    - Open an existing Human Decision only from an explicit assessment-hash request.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .learning_effectiveness import (
    comparative_effectiveness,
    effectiveness_status,
    knowledge_drift,
    request_learning_review,
)


def _emit(value: Any) -> int:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _kind(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--knowledge-kind",
        choices=("skill", "memory", "finding"),
        required=True,
    )
    parser.add_argument("--knowledge-id", required=True)


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.31.3 effectiveness/drift CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos learning-effectiveness")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("learning-effectiveness-status")

    evaluate = sub.add_parser("learning-effectiveness-evaluate")
    _kind(evaluate)

    drift = sub.add_parser("learning-drift-evaluate")
    _kind(drift)

    review = sub.add_parser("learning-effectiveness-review-request")
    _kind(review)
    review.add_argument("--assessment-hash", required=True)
    review.add_argument("--task-id", required=True)
    review.add_argument("--raised-by-session")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.31.3 effectiveness/drift operation."""
    args = build_parser().parse_args(argv)
    root = Path(
        args.root
        or os.environ.get("AGENTOS_PROJECT_ROOT", ".")
    ).resolve()
    try:
        if args.command == "learning-effectiveness-status":
            value = effectiveness_status(root)
        elif args.command == "learning-effectiveness-evaluate":
            value = comparative_effectiveness(
                root,
                args.knowledge_kind,
                args.knowledge_id,
            )
        elif args.command == "learning-drift-evaluate":
            value = knowledge_drift(
                root,
                args.knowledge_kind,
                args.knowledge_id,
            )
        elif args.command == "learning-effectiveness-review-request":
            value = request_learning_review(
                root,
                knowledge_kind=args.knowledge_kind,
                knowledge_id=args.knowledge_id,
                expected_assessment_hash=args.assessment_hash,
                task_id=args.task_id,
                raised_by_session=args.raised_by_session,
            )
        else:
            raise RuntimeError("unknown_learning_effectiveness_command")
        return _emit(value)
    except Exception as exc:
        return _emit(
            {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            }
        )


if __name__ == "__main__":
    raise SystemExit(main())
