"""Read-only v0.30.0 Context Authority CLI."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import Any
from .context_authority_surface import (
    context_authority_explain,
    context_authority_findings_get,
    context_authority_status,
    context_provenance_get,
)
from .context_transport import ContextTransportError


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _task_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", default=os.environ.get("AGENTOS_TASK_ID"))
    parser.add_argument("--revision", type=int)


def _require_task(value: str | None) -> str:
    if not value:
        raise ContextTransportError("task_id_required")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentos context-authority")
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("context-authority-status"); _task_arg(x)
    x = sub.add_parser("context-provenance-show"); _task_arg(x); x.add_argument("--trust-class"); x.add_argument("--authority-class"); x.add_argument("--limit", type=int, default=200)
    x = sub.add_parser("context-authority-explain"); _task_arg(x)
    x = sub.add_parser("context-authority-findings"); _task_arg(x)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    try:
        task_id = _require_task(args.task_id)
        if args.command == "context-authority-status":
            return _emit(context_authority_status(root, task_id, args.revision))
        if args.command == "context-provenance-show":
            return _emit(context_provenance_get(root, task_id, args.revision, trust_class=args.trust_class, authority_class=args.authority_class, limit=args.limit))
        if args.command == "context-authority-explain":
            return _emit(context_authority_explain(root, task_id, args.revision))
        if args.command == "context-authority-findings":
            return _emit(context_authority_findings_get(root, task_id, args.revision))
    except ContextTransportError as exc:
        return _emit({"ok": False, "error": str(exc)})
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
