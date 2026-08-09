"""
File: .agents/agentos/data_subject_rights_cli.py

Purpose:
    Provide human/operator CLI for the v0.22.7 data-subject rights lifecycle.

Responsibilities:
    - Keep erasure request/review/approval/execution outside MCP mutation authority.
    - Require explicit human confirmation for privacy decisions.
    - Expose privacy-safe request, plan, status, and tombstone evidence.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any

from .data_subject_rights import (
    DataSubjectRightsError, sync_schema, create_erasure_request, create_erasure_plan,
    review_erasure_plan, approve_erasure_plan, execute_erasure_plan,
    erasure_request_get, erasure_plan_get, erasure_status_get,
)


def _emit(value: Any) -> int:
    """Print JSON and return a conventional process status."""
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 1


def build_parser() -> argparse.ArgumentParser:
    """Build v0.22.7 operator commands."""
    p=argparse.ArgumentParser(prog="agentos data-subject-rights"); p.add_argument("--root",required=True)
    sub=p.add_subparsers(dest="command",required=True)
    x=sub.add_parser("data-subject-erasure-request-create"); x.add_argument("--entity-uuid",required=True); x.add_argument("--reason-code",required=True); x.add_argument("--requested-by",required=True); x.add_argument("--human-confirmed",action="store_true")
    x=sub.add_parser("data-subject-erasure-request-show"); x.add_argument("--request-id",type=int,required=True)
    x=sub.add_parser("data-subject-erasure-plan-create"); x.add_argument("--request-id",type=int,required=True); x.add_argument("--created-by",required=True)
    x=sub.add_parser("data-subject-erasure-plan-show"); x.add_argument("--plan-id",type=int,required=True)
    x=sub.add_parser("data-subject-erasure-plan-review"); x.add_argument("--plan-id",type=int,required=True); x.add_argument("--reviewed-by",required=True); x.add_argument("--human-confirmed",action="store_true"); x.add_argument("--reject",action="store_true")
    x=sub.add_parser("data-subject-erasure-plan-approve"); x.add_argument("--plan-id",type=int,required=True); x.add_argument("--approved-by",required=True); x.add_argument("--human-confirmed",action="store_true")
    x=sub.add_parser("data-subject-erasure-execute"); x.add_argument("--plan-id",type=int,required=True); x.add_argument("--executed-by",required=True); x.add_argument("--human-confirmed",action="store_true")
    x=sub.add_parser("data-subject-erasure-status"); x.add_argument("--entity-uuid",required=True)
    sub.add_parser("data-subject-rights-db-sync")
    return p


def main(argv: list[str] | None=None) -> int:
    """Execute one privacy lifecycle command."""
    args=build_parser().parse_args(argv); root=Path(args.root).resolve()
    try:
        c=args.command
        if c=="data-subject-erasure-request-create": return _emit(create_erasure_request(root,args.entity_uuid,reason_code=args.reason_code,requested_by=args.requested_by,human_confirmed=args.human_confirmed))
        if c=="data-subject-erasure-request-show": return _emit(erasure_request_get(root,args.request_id))
        if c=="data-subject-erasure-plan-create": return _emit(create_erasure_plan(root,args.request_id,created_by=args.created_by))
        if c=="data-subject-erasure-plan-show": return _emit(erasure_plan_get(root,args.plan_id))
        if c=="data-subject-erasure-plan-review": return _emit(review_erasure_plan(root,args.plan_id,reviewed_by=args.reviewed_by,human_confirmed=args.human_confirmed,approve_review=not args.reject))
        if c=="data-subject-erasure-plan-approve": return _emit(approve_erasure_plan(root,args.plan_id,approved_by=args.approved_by,human_confirmed=args.human_confirmed))
        if c=="data-subject-erasure-execute": return _emit(execute_erasure_plan(root,args.plan_id,executed_by=args.executed_by,human_confirmed=args.human_confirmed))
        if c=="data-subject-erasure-status": return _emit(erasure_status_get(root,args.entity_uuid))
        if c=="data-subject-rights-db-sync": return _emit(sync_schema(root))
    except DataSubjectRightsError as exc:
        return _emit({"ok":False,"error":str(exc)})
    return 2

if __name__=="__main__": raise SystemExit(main())
