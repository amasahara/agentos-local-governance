"""
File: .agents/agentos/context_evaluation_cli.py

Purpose:
    Provide operator CLI access to v0.23.2 bounded context expansion and
    deterministic compression evaluation.

Responsibilities:
    - Execute bounded batch expansion without persisting expanded content.
    - Persist deterministic compression evaluations and optional shadow comparisons.
    - Expose metadata-only expansion/evaluation history.
    - Keep all LLM-facing MCP operations read-only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .context_evaluation import (
    ContextEvaluationError,
    compare_compression,
    compression_evaluation_get,
    compression_evaluation_history_get,
    evaluate_compression,
    expansion_history_get,
    sync_schema,
)
from .context_transport import ContextTransportError, context_expand_batch, context_expansion_explain


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _task_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))


def _require_task(value: str | None) -> str:
    if not value:
        raise ContextEvaluationError("task_id_required")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.23.2 context expansion/evaluation CLI parser."""
    p = argparse.ArgumentParser(prog="agentos context-evaluation")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)

    x = sub.add_parser("context-expansion-explain")
    _task_arg(x); x.add_argument("--revision", type=int)

    x = sub.add_parser("context-expand-batch")
    _task_arg(x); x.add_argument("--revision", type=int)
    x.add_argument("--requests-json", required=True, help="JSON array of handle expansion requests")
    x.add_argument("--max-total-tokens", type=int)
    x.add_argument("--reason-code", default="inspection")
    x.add_argument("--requirement-id", action="append", default=[])

    x = sub.add_parser("context-expansion-history")
    _task_arg(x); x.add_argument("--revision", type=int); x.add_argument("--limit", type=int, default=50)

    x = sub.add_parser("context-compression-evaluate")
    _task_arg(x); x.add_argument("--revision", type=int); x.add_argument("--no-persist", action="store_true")

    x = sub.add_parser("context-compression-evaluation-get")
    _task_arg(x); x.add_argument("--revision", type=int)

    x = sub.add_parser("context-compression-evaluation-history")
    _task_arg(x); x.add_argument("--limit", type=int, default=20)

    x = sub.add_parser("context-compression-compare")
    _task_arg(x); x.add_argument("--baseline-revision", type=int, required=True)
    x.add_argument("--candidate-revision", type=int, required=True); x.add_argument("--persist", action="store_true")

    sub.add_parser("context-expansion-evaluation-db-sync")
    return p


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.23.2 context expansion/evaluation CLI operation."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        command = args.command
        if command == "context-expansion-explain":
            return _emit(context_expansion_explain(root, _require_task(args.task_id), args.revision))
        if command == "context-expand-batch":
            requests = json.loads(args.requests_json)
            if not isinstance(requests, list):
                raise ContextEvaluationError("requests_json_must_be_array")
            return _emit(context_expand_batch(
                root, _require_task(args.task_id), requests, args.revision,
                args.max_total_tokens, args.reason_code, args.requirement_id, record_event=True,
            ))
        if command == "context-expansion-history":
            return _emit(expansion_history_get(root, _require_task(args.task_id), args.revision, args.limit))
        if command == "context-compression-evaluate":
            return _emit(evaluate_compression(root, _require_task(args.task_id), args.revision, persist=not args.no_persist))
        if command == "context-compression-evaluation-get":
            return _emit(compression_evaluation_get(root, _require_task(args.task_id), args.revision))
        if command == "context-compression-evaluation-history":
            return _emit(compression_evaluation_history_get(root, _require_task(args.task_id), args.limit))
        if command == "context-compression-compare":
            return _emit(compare_compression(
                root, _require_task(args.task_id), args.baseline_revision, args.candidate_revision, persist=args.persist,
            ))
        if command == "context-expansion-evaluation-db-sync":
            return _emit(sync_schema(root))
    except (ContextEvaluationError, ContextTransportError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
