"""
File: .agents/agentos/cli.py

Purpose:
    Provide the command-line interface for AgentOS governance operations.

Responsibilities:
    - Parse commands and structured arguments.
    - Call runtime contracts.
    - Emit stable JSON results and errors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import approve_task, db_status, docs_check, instruction_check, list_claims, prepare_change, project_status, record_claim, record_tool_execution, show_claim, start_task
from .indexing import duplicate_report, index_build, index_query


def emit(value: Any) -> None:
    """Print a JSON-serializable value.

    Args:
        value: Result object.

    Returns:
        None.
    """
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _json_arg(value: str, name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON argument: {name}") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentos")
    p.add_argument("--root", default=".")
    s = p.add_subparsers(dest="cmd", required=True)
    a = s.add_parser("start-task"); a.add_argument("--task-id", required=True); a.add_argument("--request", required=True)
    a = s.add_parser("approve-task"); a.add_argument("--task-id", required=True); a.add_argument("--scope", required=True)
    a = s.add_parser("index-build"); a.add_argument("source", nargs="?", default="src")
    a = s.add_parser("index-query"); a.add_argument("query"); a.add_argument("--limit", type=int, default=10)
    s.add_parser("duplicate-scan")
    a = s.add_parser("record-tool"); a.add_argument("--task-id", required=True); a.add_argument("--tool", required=True); a.add_argument("--input", default="{}"); a.add_argument("--success", action="store_true"); a.add_argument("--output", required=True); a.add_argument("--classification", default="local")
    a = s.add_parser("prepare-change"); a.add_argument("--task-id", required=True); a.add_argument("--operation", required=True, choices=["create", "modify"]); a.add_argument("--target", required=True); a.add_argument("--intent", required=True); a.add_argument("--symbols", default="[]"); a.add_argument("--feature"); a.add_argument("--layer"); a.add_argument("--file-kind"); a.add_argument("--temporary", action="store_true")
    a = s.add_parser("record-claim"); a.add_argument("--task-id", required=True); a.add_argument("--claim", required=True); a.add_argument("--claim-type", required=True, choices=["business_logic", "security", "data_behavior", "destructive_effect", "governance", "other"]); a.add_argument("--risk", default="medium", choices=["low", "medium", "high"]); a.add_argument("--evidence-call-ids", default="[]")
    a = s.add_parser("list-claims"); a.add_argument("--task-id", required=True)
    a = s.add_parser("show-claim"); a.add_argument("--claim-id", required=True, type=int)
    s.add_parser("docs-check"); s.add_parser("instruction-check"); s.add_parser("db-status")
    a = s.add_parser("status"); a.add_argument("--task-id")
    return p


def main() -> int:
    args = parser().parse_args()
    root = Path(args.root).resolve()
    try:
        if args.cmd == "start-task": result = start_task(root, args.task_id, args.request)
        elif args.cmd == "approve-task": result = approve_task(root, args.task_id, _json_arg(args.scope, "scope"))
        elif args.cmd == "index-build": result = index_build(root, args.source)
        elif args.cmd == "index-query": result = index_query(root, args.query, args.limit)
        elif args.cmd == "duplicate-scan": result = duplicate_report(root)
        elif args.cmd == "record-tool": result = record_tool_execution(root, args.task_id, args.tool, _json_arg(args.input, "input"), args.success, args.output, args.classification)
        elif args.cmd == "prepare-change": result = prepare_change(root, args.task_id, args.operation, args.target, args.intent, _json_arg(args.symbols, "symbols"), args.feature, args.layer, args.file_kind, args.temporary)
        elif args.cmd == "record-claim": result = record_claim(root, args.task_id, args.claim, args.claim_type, args.risk, _json_arg(args.evidence_call_ids, "evidence-call-ids"))
        elif args.cmd == "list-claims": result = list_claims(root, args.task_id)
        elif args.cmd == "show-claim": result = show_claim(root, args.claim_id)
        elif args.cmd == "docs-check": result = docs_check(root)
        elif args.cmd == "instruction-check": result = instruction_check(root)
        elif args.cmd == "db-status": result = db_status(root)
        else: result = project_status(root, args.task_id)
        emit(result)
        return 0
    except Exception as exc:
        emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
