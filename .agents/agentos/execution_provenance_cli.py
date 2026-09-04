"""
File: .agents/agentos/execution_provenance_cli.py

Purpose:
    Expose schema-65 execution provenance registration and inspection.

Responsibilities:
    - Register provenance only through the privileged control-plane command.
    - Read task/session identity from the unified control-plane dispatcher.
    - Expose privacy-safe get/status operations to the normal agent plane.
    - Never select a provider/model or add MCP mutation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .execution_provenance import (
    ENDPOINT_CLASSES,
    EXECUTION_REF_TYPES,
    execution_provenance_status,
    get_execution_provenance,
    register_execution_provenance,
)


def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.32.0 execution-provenance CLI parser."""
    parser = argparse.ArgumentParser(prog="agentos execution-provenance")
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)

    item = sub.add_parser("execution-provenance-register")
    item.add_argument("--execution-ref-type", choices=sorted(EXECUTION_REF_TYPES), required=True)
    item.add_argument("--execution-ref-id", required=True)
    item.add_argument("--provider-id", required=True)
    item.add_argument("--model-id", required=True)
    item.add_argument("--model-revision")
    item.add_argument("--deployment-id")
    item.add_argument("--provider-request-id")
    item.add_argument("--agent-id", required=True)
    item.add_argument("--runtime-id")
    item.add_argument("--runtime-version")
    item.add_argument("--endpoint-class", choices=sorted(ENDPOINT_CLASSES), required=True)
    item.add_argument("--recorded-by", required=True)

    item = sub.add_parser("execution-provenance-get")
    item.add_argument("--provenance-id", required=True)

    sub.add_parser("execution-provenance-status")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch one schema-65 execution-provenance operation."""
    args = build_parser().parse_args(argv)
    root = Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command == "execution-provenance-register":
            task_id = os.environ.get("AGENTOS_TASK_ID")
            session_id = os.environ.get("AGENTOS_SESSION_ID")
            if not task_id or not session_id:
                raise RuntimeError("privileged_registration_requires_task_and_session")
            value = register_execution_provenance(
                root,
                task_id=task_id,
                session_id=session_id,
                execution_ref_type=args.execution_ref_type,
                execution_ref_id=args.execution_ref_id,
                provider_id=args.provider_id,
                model_id=args.model_id,
                model_revision=args.model_revision,
                deployment_id=args.deployment_id,
                provider_request_id=args.provider_request_id,
                agent_id=args.agent_id,
                runtime_id=args.runtime_id,
                runtime_version=args.runtime_version,
                endpoint_class=args.endpoint_class,
                recorded_by=args.recorded_by,
            )
        elif args.command == "execution-provenance-get":
            value = get_execution_provenance(root, args.provenance_id)
        elif args.command == "execution-provenance-status":
            value = execution_provenance_status(root)
        else:
            raise RuntimeError("unknown_execution_provenance_command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok": False, "error": type(exc).__name__, "message": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())
