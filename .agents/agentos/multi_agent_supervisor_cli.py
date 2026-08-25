"""Path: .agents/agentos/multi_agent_supervisor_cli.py
Purpose: Local/operator CLI for v0.27.2 Multi-Agent Worker Supervisor.
"""
from __future__ import annotations

from .cli_identity import cli_program

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .multi_agent_supervisor import (
    activate_supervisor,
    add_dependency,
    add_worker,
    cancel_supervisor,
    create_supervisor,
    pause_supervisor,
    supervisor_readiness,
    supervisor_status,
    supervisor_workers,
    worker_start,
    worker_update,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def _caller() -> tuple[str, str]:
    task_id = str(os.environ.get("AGENTOS_TASK_ID", "")).strip()
    session_id = str(os.environ.get("AGENTOS_SESSION_ID", "")).strip()
    if not task_id or not session_id:
        raise PermissionError("AGENTOS_TASK_ID_and_AGENTOS_SESSION_ID_required")
    return task_id, session_id


def build_parser() -> argparse.ArgumentParser:
    """Build the unified-runtime-compatible v0.27.2 feature parser."""
    parser = argparse.ArgumentParser(prog=cli_program())
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("multi-agent-supervisor-create")
    p.add_argument("--parent-task-id", required=True)
    p.add_argument("--created-by", required=True)
    p.add_argument("--worker-limit", type=int)

    p = sub.add_parser("multi-agent-supervisor-worker-add")
    p.add_argument("--supervisor-id", type=int, required=True)
    p.add_argument("--worker-key", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--role", choices=["executor", "reviewer", "planner", "observer"], required=True)
    p.add_argument("--selection-run-id", type=int)
    p.add_argument("--skill-id", type=int)

    p = sub.add_parser("multi-agent-supervisor-dependency-add")
    p.add_argument("--supervisor-id", type=int, required=True)
    p.add_argument("--worker-key", required=True)
    p.add_argument("--depends-on", required=True)

    for command in ("multi-agent-supervisor-activate", "multi-agent-supervisor-pause", "multi-agent-supervisor-cancel"):
        p = sub.add_parser(command)
        p.add_argument("--supervisor-id", type=int, required=True)
        p.add_argument("--approved-by", required=True)

    p = sub.add_parser("multi-agent-worker-start")
    p.add_argument("--supervisor-id", type=int, required=True)
    p.add_argument("--worker-key", required=True)

    p = sub.add_parser("multi-agent-worker-update")
    p.add_argument("--supervisor-id", type=int, required=True)
    p.add_argument("--worker-key", required=True)
    p.add_argument("--status", choices=["completed", "failed", "blocked"], required=True)

    p = sub.add_parser("multi-agent-supervisor-status")
    p.add_argument("--supervisor-id", type=int, required=True)

    p = sub.add_parser("multi-agent-supervisor-workers")
    p.add_argument("--supervisor-id", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one v0.27.2 supervisor command through the feature CLI contract."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "multi-agent-supervisor-create":
            value = create_supervisor(root, args.parent_task_id, args.created_by, args.worker_limit)
        elif args.command == "multi-agent-supervisor-worker-add":
            value = add_worker(
                root,
                args.supervisor_id,
                args.worker_key,
                args.task_id,
                args.session_id,
                args.role,
                selection_run_id=args.selection_run_id,
                skill_id=args.skill_id,
            )
        elif args.command == "multi-agent-supervisor-dependency-add":
            value = add_dependency(root, args.supervisor_id, args.worker_key, args.depends_on)
        elif args.command == "multi-agent-supervisor-activate":
            value = activate_supervisor(root, args.supervisor_id, args.approved_by)
        elif args.command == "multi-agent-supervisor-pause":
            value = pause_supervisor(root, args.supervisor_id, args.approved_by)
        elif args.command == "multi-agent-supervisor-cancel":
            value = cancel_supervisor(root, args.supervisor_id, args.approved_by)
        elif args.command == "multi-agent-worker-start":
            task_id, session_id = _caller()
            value = worker_start(root, args.supervisor_id, args.worker_key, task_id, session_id)
        elif args.command == "multi-agent-worker-update":
            task_id, session_id = _caller()
            value = worker_update(root, args.supervisor_id, args.worker_key, task_id, session_id, args.status)
        elif args.command == "multi-agent-supervisor-status":
            value = supervisor_status(root, args.supervisor_id)
        elif args.command == "multi-agent-supervisor-workers":
            value = {**supervisor_workers(root, args.supervisor_id), "readiness": supervisor_readiness(root, args.supervisor_id)}
        else:
            raise RuntimeError("unknown multi-agent supervisor command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
