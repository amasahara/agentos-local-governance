"""
File: .agents/agentos/context_transport_cli.py

Purpose:
    Provide operator CLI commands for v0.23.1 adaptive Requirement-Preserving Context Compression.

Responsibilities:
    - Compile transport packs locally from canonical Context Packs.
    - Expose read-only inspection, expansion, requirement, token, and evaluation commands.
    - Keep transport compilation/evaluation mutation outside MCP authority.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .context_transport import (
    ContextTransportError,
    compile_transport_pack,
    context_expand,
    context_requirement_get,
    context_token_report,
    context_transport_explain,
    context_transport_get,
    evaluate_transport_pack,
    sync_schema,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _task_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))


def build_parser() -> argparse.ArgumentParser:
    """Build v0.23.0 context transport CLI parser."""
    p = argparse.ArgumentParser(prog="agentos context-transport")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)

    x = sub.add_parser("context-transport-compile")
    _task_arg(x)
    x.add_argument("--model-profile", default="generic-128k")
    x.add_argument("--reserved-output", type=int)
    x.add_argument("--system-tool-overhead", type=int)
    x.add_argument("--safety-margin", type=int)
    x.add_argument("--shadow", action="store_true")
    x.add_argument("--budget-mode", choices=("adaptive", "fixed"))

    x = sub.add_parser("context-transport-get"); _task_arg(x); x.add_argument("--revision", type=int)
    x = sub.add_parser("context-transport-explain"); _task_arg(x); x.add_argument("--revision", type=int)
    x = sub.add_parser("context-expand"); _task_arg(x); x.add_argument("--handle-id", required=True); x.add_argument("--revision", type=int); x.add_argument("--max-lines", type=int, default=240); x.add_argument("--line-start", type=int, default=1); x.add_argument("--max-tokens", type=int); x.add_argument("--reason-code", default="inspection"); x.add_argument("--requirement-id", action="append", default=[])
    x = sub.add_parser("context-requirement-get"); _task_arg(x); x.add_argument("--requirement-id"); x.add_argument("--context-revision", type=int)
    x = sub.add_parser("context-token-report"); _task_arg(x); x.add_argument("--revision", type=int)
    x = sub.add_parser("context-transport-evaluate"); _task_arg(x); x.add_argument("--revision", type=int); x.add_argument("--no-persist", action="store_true")
    sub.add_parser("context-transport-db-sync")
    return p


def _require_task(value: str | None) -> str:
    if not value:
        raise ContextTransportError("task_id_required")
    return value


def main(argv: list[str] | None = None) -> int:
    """Execute one v0.23.0 context transport CLI command."""
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        c = args.command
        if c == "context-transport-compile":
            return _emit(compile_transport_pack(root, _require_task(args.task_id), args.model_profile, args.reserved_output, args.system_tool_overhead, args.safety_margin, args.shadow, args.budget_mode))
        if c == "context-transport-get":
            return _emit(context_transport_get(root, _require_task(args.task_id), args.revision))
        if c == "context-transport-explain":
            return _emit(context_transport_explain(root, _require_task(args.task_id), args.revision))
        if c == "context-expand":
            return _emit(context_expand(root, _require_task(args.task_id), args.handle_id, args.revision, args.max_lines, line_start=args.line_start, max_tokens=args.max_tokens, requirement_ids=args.requirement_id, reason_code=args.reason_code))
        if c == "context-requirement-get":
            return _emit(context_requirement_get(root, _require_task(args.task_id), args.requirement_id, args.context_revision))
        if c == "context-token-report":
            return _emit(context_token_report(root, _require_task(args.task_id), args.revision))
        if c == "context-transport-evaluate":
            return _emit(evaluate_transport_pack(root, _require_task(args.task_id), args.revision, persist=not args.no_persist))
        if c == "context-transport-db-sync":
            return _emit(sync_schema(root))
    except ContextTransportError as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
