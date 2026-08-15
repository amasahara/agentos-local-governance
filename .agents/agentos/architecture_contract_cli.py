"""File: .agents/agentos/architecture_contract_cli.py

Purpose:
    Expose v0.25.2 Architecture Contract lifecycle commands through unified CLI.
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from typing import Any
from .architecture_contract import (
    activate_baseline, approve_baseline, architecture_get, architecture_init, architecture_section_get,
    architecture_status, create_baseline, reject_baseline, review_baseline, validate_working_copy,
)

def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)); return 0 if not isinstance(value,dict) or value.get("ok",True) else 2

def build_parser()->argparse.ArgumentParser:
    """Build the v0.25.2 feature command parser.

    Returns:
        Configured argparse parser.
    """
    p=argparse.ArgumentParser(prog="agentos"); p.add_argument("--root"); s=p.add_subparsers(dest="command",required=True)
    q=s.add_parser("architecture-init"); q.add_argument("--created-by",default="human"); q.add_argument("--overwrite",action="store_true")
    s.add_parser("architecture-validate")
    q=s.add_parser("architecture-show"); q.add_argument("--baseline-id",type=int)
    q=s.add_parser("architecture-section-show"); q.add_argument("--section-id",required=True); q.add_argument("--baseline-id",type=int)
    s.add_parser("architecture-status")
    q=s.add_parser("architecture-baseline-create"); q.add_argument("--created-by",required=True)
    for name, actor in (("architecture-baseline-review","reviewed-by"),("architecture-baseline-approve","approved-by"),("architecture-baseline-activate","activated-by")):
        q=s.add_parser(name); q.add_argument("--baseline-id",required=True,type=int); q.add_argument("--expected-baseline-hash",required=True); q.add_argument(f"--{actor}",required=True); q.add_argument("--human-confirmed",action="store_true",required=True)
    q=s.add_parser("architecture-baseline-reject"); q.add_argument("--baseline-id",required=True,type=int); q.add_argument("--expected-baseline-hash",required=True); q.add_argument("--rejected-by",required=True); q.add_argument("--reason",required=True); q.add_argument("--human-confirmed",action="store_true",required=True)
    return p

def main(argv=None)->int:
    """Dispatch one v0.25.2 feature command.

    Args:
        argv: Optional command arguments for embedding/tests.

    Returns:
        Process-style exit code.
    """
    x=build_parser().parse_args(argv); r=Path(x.root or os.environ.get("AGENTOS_PROJECT_ROOT",".")).resolve()
    try:
        if x.command=="architecture-init": v=architecture_init(r,x.created_by,x.overwrite)
        elif x.command=="architecture-validate": v=validate_working_copy(r); v={k:v[k] for k in ("ok","approval_ready","section_count","expected_section_count","baseline_hash","unresolved_sections","findings")}
        elif x.command=="architecture-show": v=architecture_get(r,x.baseline_id)
        elif x.command=="architecture-section-show": v=architecture_section_get(r,x.section_id,x.baseline_id)
        elif x.command=="architecture-status": v=architecture_status(r)
        elif x.command=="architecture-baseline-create": v=create_baseline(r,x.created_by)
        elif x.command=="architecture-baseline-review": v=review_baseline(r,x.baseline_id,x.expected_baseline_hash,x.reviewed_by,x.human_confirmed)
        elif x.command=="architecture-baseline-approve": v=approve_baseline(r,x.baseline_id,x.expected_baseline_hash,x.approved_by,x.human_confirmed)
        elif x.command=="architecture-baseline-activate": v=activate_baseline(r,x.baseline_id,x.expected_baseline_hash,x.activated_by,x.human_confirmed)
        elif x.command=="architecture-baseline-reject": v=reject_baseline(r,x.baseline_id,x.expected_baseline_hash,x.rejected_by,x.reason,x.human_confirmed)
        else: raise RuntimeError("unknown architecture command")
        return _emit(v)
    except Exception as e: return _emit({"ok":False,"error":type(e).__name__,"message":str(e)})
