"""Path: .agents/agentos/architecture_planning_cli.py
Purpose: Read-only and analysis CLI surface for v0.26.0 Architecture-Aware Task Planning.
"""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from typing import Any
from .architecture_planning import architecture_plan_get, architecture_plan_impact, architecture_plan_status

def _emit(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not isinstance(value, dict) or value.get("ok", True) else 2

def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="agentos"); parser.add_argument("--root"); sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("architecture-plan-impact"); p.add_argument("--task-id",required=True); p.add_argument("--plan",required=True)
    p=sub.add_parser("architecture-plan-show"); p.add_argument("--plan-id",type=int); p.add_argument("--task-id")
    p=sub.add_parser("architecture-plan-status"); p.add_argument("--task-id",required=True)
    return parser

def main(argv: list[str] | None=None) -> int:
    args=build_parser().parse_args(argv); root=Path(args.root or os.environ.get("AGENTOS_PROJECT_ROOT", ".")).resolve()
    try:
        if args.command=="architecture-plan-impact": value=architecture_plan_impact(root,args.task_id,json.loads(args.plan))
        elif args.command=="architecture-plan-show": value=architecture_plan_get(root,plan_id=args.plan_id,task_id=args.task_id)
        elif args.command=="architecture-plan-status": value=architecture_plan_status(root,args.task_id)
        else: raise RuntimeError("unknown architecture planning command")
        return _emit(value)
    except Exception as exc: return _emit({"ok":False,"error":type(exc).__name__,"message":str(exc)})

if __name__=="__main__": raise SystemExit(main())
