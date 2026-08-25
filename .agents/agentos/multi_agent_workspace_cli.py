"""
File: .agents/agentos/multi_agent_workspace_cli.py

Purpose:
    Expose operator/worker CLI commands for v0.27.3 isolated workspaces and controlled integration.

Responsibilities:
    - Register workspace provisioning, collection, sealing, release, and inspection commands.
    - Register human review/approval/rejection and controlled integration commands.
    - Require task/session context for worker-owned and integration-apply operations.
"""
from __future__ import annotations

from .cli_identity import cli_program
import argparse, json, os
from pathlib import Path
from typing import Any
from .multi_agent_workspace import (
    apply_integration, approve_integration, collect_workspace_diff,
    create_integration_proposal, integration_status, provision_workspace,
    reject_integration, release_workspace, review_integration, seal_workspace,
    workspace_status,
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
    """Build the v0.27.3 CLI parser.

    Returns:
        Argument parser containing exactly the isolated-workspace/integration node commands.
    """
    parser = argparse.ArgumentParser(prog=cli_program())
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p=sub.add_parser("multi-agent-workspace-provision"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True); p.add_argument("--created-by",required=True)
    p=sub.add_parser("multi-agent-workspace-collect"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True)
    p=sub.add_parser("multi-agent-workspace-seal"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True)
    p=sub.add_parser("multi-agent-workspace-release"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True); p.add_argument("--released-by",required=True)
    p=sub.add_parser("multi-agent-workspace-status"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True)
    p=sub.add_parser("multi-agent-integration-proposal-create"); p.add_argument("--supervisor-id",type=int,required=True); p.add_argument("--worker-key",required=True); p.add_argument("--created-by",required=True)
    p=sub.add_parser("multi-agent-integration-proposal-review"); p.add_argument("--proposal-id",type=int,required=True); p.add_argument("--reviewed-by",required=True)
    p=sub.add_parser("multi-agent-integration-proposal-approve"); p.add_argument("--proposal-id",type=int,required=True); p.add_argument("--approved-by",required=True)
    p=sub.add_parser("multi-agent-integration-proposal-reject"); p.add_argument("--proposal-id",type=int,required=True); p.add_argument("--rejected-by",required=True)
    p=sub.add_parser("multi-agent-integration-apply"); p.add_argument("--proposal-id",type=int,required=True); p.add_argument("--applied-by",required=True)
    p=sub.add_parser("multi-agent-integration-status"); p.add_argument("--proposal-id",type=int,required=True)
    return parser

def main(argv: list[str] | None=None) -> int:
    """Dispatch one v0.27.3 CLI operation.

    Args:
        argv: Optional CLI argument vector.
    Returns:
        Process-style exit code; mutation failures are emitted as deterministic JSON.
    """
    args=build_parser().parse_args(argv)
    root=Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT",".")).resolve()
    try:
        if args.command=="multi-agent-workspace-provision": value=provision_workspace(root,args.supervisor_id,args.worker_key,args.created_by)
        elif args.command=="multi-agent-workspace-collect":
            t,s=_caller(); value=collect_workspace_diff(root,args.supervisor_id,args.worker_key,t,s)
        elif args.command=="multi-agent-workspace-seal":
            t,s=_caller(); value=seal_workspace(root,args.supervisor_id,args.worker_key,t,s)
        elif args.command=="multi-agent-workspace-release": value=release_workspace(root,args.supervisor_id,args.worker_key,args.released_by)
        elif args.command=="multi-agent-workspace-status": value=workspace_status(root,args.supervisor_id,args.worker_key)
        elif args.command=="multi-agent-integration-proposal-create": value=create_integration_proposal(root,args.supervisor_id,args.worker_key,args.created_by)
        elif args.command=="multi-agent-integration-proposal-review": value=review_integration(root,args.proposal_id,args.reviewed_by)
        elif args.command=="multi-agent-integration-proposal-approve": value=approve_integration(root,args.proposal_id,args.approved_by)
        elif args.command=="multi-agent-integration-proposal-reject": value=reject_integration(root,args.proposal_id,args.rejected_by)
        elif args.command=="multi-agent-integration-apply":
            t,s=_caller(); value=apply_integration(root,args.proposal_id,args.applied_by,t,s)
        elif args.command=="multi-agent-integration-status": value=integration_status(root,args.proposal_id)
        else: raise RuntimeError("unknown v0.27.3 command")
        return _emit(value)
    except Exception as exc:
        return _emit({"ok":False,"error":type(exc).__name__,"message":str(exc)})

if __name__=="__main__": raise SystemExit(main())
