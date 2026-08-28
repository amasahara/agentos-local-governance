"""Path: .agents/agentos/completion_cli.py
Purpose: Unified agent-plane CLI for v0.29.0 completion verification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .completion_surface import (
    SUBJECT_WORKFLOW,
    SUBJECT_WORKER,
    completion_public_status,
    completion_request,
    completion_verify,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _json_object(value: str, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}_must_be_valid_json") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label}_must_be_json_object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentos")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("completion-request")
    p.add_argument("--subject-type", required=True, choices=[SUBJECT_WORKFLOW, SUBJECT_WORKER])
    p.add_argument("--workflow-name", default="default")
    p.add_argument("--supervisor-id", type=int)
    p.add_argument("--worker-key")

    p = sub.add_parser("completion-verify")
    p.add_argument("--request-id", required=True)
    p.add_argument("--verdict", required=True, choices=["pass", "fail", "inconclusive"])
    p.add_argument("--checks", required=True)
    p.add_argument("--evidence", required=True)

    p = sub.add_parser("completion-status")
    p.add_argument("--request-id")
    p.add_argument("--subject-type", choices=[SUBJECT_WORKFLOW, SUBJECT_WORKER])
    p.add_argument("--task-id")
    p.add_argument("--workflow-name", default="default")
    p.add_argument("--supervisor-id", type=int)
    p.add_argument("--worker-key")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "completion-request":
            value = completion_request(
                root,
                subject_type=args.subject_type,
                workflow_name=args.workflow_name,
                supervisor_id=args.supervisor_id,
                worker_key=args.worker_key,
            )
        elif args.command == "completion-verify":
            value = completion_verify(
                root,
                request_id=args.request_id,
                verdict=args.verdict,
                checks=_json_object(args.checks, "checks"),
                evidence=_json_object(args.evidence, "evidence"),
            )
        elif args.command == "completion-status":
            value = completion_public_status(
                root,
                request_id=args.request_id,
                subject_type=args.subject_type,
                task_id=args.task_id,
                workflow_name=args.workflow_name,
                supervisor_id=args.supervisor_id,
                worker_key=args.worker_key,
            )
        else:
            raise RuntimeError("unknown completion command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
