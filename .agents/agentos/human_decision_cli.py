"""File: .agents/agentos/human_decision_cli.py

Purpose:
    Expose structured Grill Me and human decision gates through unified CLI.
"""
from __future__ import annotations
import argparse,json,os
from pathlib import Path
from typing import Any
from .human_decision import decision_list,decision_show,grill_me,record_clarity_assessment,request_human_decision,resolve_human_decision

def _emit(v:Any)->int: print(json.dumps(v,ensure_ascii=False,indent=2,sort_keys=True,default=str)); return 0 if not isinstance(v,dict) or v.get("ok",True) else 2

def _items(values):
    out=[]
    for v in values or []:
        if v.strip(): out.append(v.strip())
    return out

def build_parser()->argparse.ArgumentParser:
    """Build the v0.25.2 feature command parser.

    Returns:
        Configured argparse parser.
    """
    p=argparse.ArgumentParser(prog="agentos"); p.add_argument("--root"); s=p.add_subparsers(dest="command",required=True)
    q=s.add_parser("clarity-assess"); q.add_argument("--task-id",default=os.environ.get("AGENTOS_TASK_ID")); q.add_argument("--assessed-by",required=True); q.add_argument("--objective-understood",action="store_true"); q.add_argument("--scope-understood",action="store_true"); q.add_argument("--constraints-understood",action="store_true"); q.add_argument("--acceptance-understood",action="store_true"); q.add_argument("--assumption",action="append",default=[]); q.add_argument("--ambiguity",action="append",default=[]); q.add_argument("--decision-required",action="append",default=[])
    q=s.add_parser("grill-me"); q.add_argument("--task-id",default=os.environ.get("AGENTOS_TASK_ID"))
    q=s.add_parser("decision-list"); q.add_argument("--task-id",default=os.environ.get("AGENTOS_TASK_ID"))
    q=s.add_parser("decision-show"); q.add_argument("--decision-id",required=True)
    q=s.add_parser("decision-request"); q.add_argument("--task-id",default=os.environ.get("AGENTOS_TASK_ID")); q.add_argument("--phase",required=True); q.add_argument("--type",dest="decision_type",required=True); q.add_argument("--severity",default="normal"); q.add_argument("--question",required=True); q.add_argument("--option",action="append",default=[]); q.add_argument("--recommendation"); q.add_argument("--recommendation-rationale"); q.add_argument("--requirement-id",action="append",default=[]); q.add_argument("--architecture-section",action="append",default=[]); q.add_argument("--non-blocking",action="store_true")
    q=s.add_parser("decision-resolve"); q.add_argument("--decision-id",required=True); q.add_argument("--answer",required=True); q.add_argument("--selected-option"); q.add_argument("--resolved-by",required=True); q.add_argument("--impact",required=True,choices=["none","requirement_change","scope_change","architecture_change"]); q.add_argument("--human-confirmed",action="store_true",required=True)
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
        if x.command in {"clarity-assess","grill-me","decision-list","decision-request"} and not x.task_id: raise RuntimeError("task_id_required")
        if x.command=="clarity-assess": v=record_clarity_assessment(r,x.task_id,x.assessed_by,objective_understood=x.objective_understood,scope_understood=x.scope_understood,constraints_understood=x.constraints_understood,acceptance_understood=x.acceptance_understood,assumptions=_items(x.assumption),ambiguities=_items(x.ambiguity),decisions_required=_items(x.decision_required))
        elif x.command=="grill-me": v=grill_me(r,x.task_id)
        elif x.command=="decision-list": v={"ok":True,"task_id":x.task_id,"decisions":decision_list(r,x.task_id)}
        elif x.command=="decision-show": v={"ok":True,"decision":decision_show(r,x.decision_id)}
        elif x.command=="decision-request": v=request_human_decision(r,x.task_id,x.phase,x.decision_type,x.severity,x.question,options=_items(x.option),recommendation=x.recommendation,recommendation_rationale=x.recommendation_rationale,requirement_ids=_items(x.requirement_id),architecture_section_ids=_items(x.architecture_section),raised_by_session=os.environ.get("AGENTOS_SESSION_ID"),blocking=not x.non_blocking)
        elif x.command=="decision-resolve": v=resolve_human_decision(r,x.decision_id,x.answer,x.resolved_by,x.impact,selected_option=x.selected_option,human_confirmed=x.human_confirmed)
        else: raise RuntimeError("unknown human-decision command")
        return _emit(v)
    except Exception as e: return _emit({"ok":False,"error":type(e).__name__,"message":str(e)})
