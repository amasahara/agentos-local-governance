"""
File: .agents/agentos/cli.py

Purpose:
    Provide the hardened AgentOS command-line interface.

Responsibilities:
    - Resolve session-scoped task context.
    - Enforce canonical tool, workflow, drift, and policy gates.
    - Emit structured JSON and fail-loud exit codes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .cache import cache_lookup, cache_store
from .core import approve_task, db_status, docs_check, instruction_check, list_claims, prepare_change, project_status, record_claim, record_tool_execution, show_claim, start_task
from .documentation import documentation_scan
from .drift import ack_baseline, drift_check, drift_diff
from .indexing import duplicate_report, index_build, index_query
from .policy import approve_local_override, local_override_status
from .proxy import proxy_execute
from .external_audit import verify_external_log
from .tooling import complete_tool, egress_report, guard_tool
from .workflow import complete_automated_step, current_task_id, mark_step, next_step, normalize_session_id, resolve_task_id, seed_workflow, set_current_task, workflow_status


def emit(value: Any) -> None:
    """Print a JSON-serializable value.

    Args:
        value: Structured value to emit.

    Returns:
        None.
    """
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _json_arg(value: str, name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON argument: {name}") from exc


def _task_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--task-id")


def parser() -> argparse.ArgumentParser:
    """Build and return the AgentOS argument parser.

    Returns:
        Configured argument parser.
    """
    p=argparse.ArgumentParser(prog="agentos"); p.add_argument("--root",default="."); p.add_argument("--session-id")
    s=p.add_subparsers(dest="cmd",required=True)
    a=s.add_parser("start-task"); a.add_argument("--task-id",required=True); a.add_argument("--request",required=True)
    a=s.add_parser("use-task"); a.add_argument("--task-id",required=True)
    s.add_parser("whoami"); s.add_parser("next-step")
    a=s.add_parser("approve-task"); _task_arg(a); a.add_argument("--scope",required=True)
    a=s.add_parser("mark-step"); _task_arg(a); a.add_argument("--step",required=True); a.add_argument("--status",required=True,choices=["done","skipped"]); a.add_argument("--note",required=True)
    a=s.add_parser("workflow-status"); _task_arg(a)
    a=s.add_parser("index-build"); a.add_argument("source",nargs="?",default="src"); _task_arg(a)
    a=s.add_parser("index-query"); a.add_argument("query"); a.add_argument("--limit",type=int,default=10)
    s.add_parser("duplicate-scan")
    a=s.add_parser("guard-tool"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--args",default="{}"); a.add_argument("--reason-code"); a.add_argument("--justification"); a.add_argument("--target")
    a=s.add_parser("complete-tool"); a.add_argument("--execution-token",required=True); a.add_argument("--input",default="{}"); a.add_argument("--success",action="store_true"); a.add_argument("--output",required=True)
    a=s.add_parser("record-tool"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--input",default="{}"); a.add_argument("--success",action="store_true"); a.add_argument("--output",required=True); a.add_argument("--classification")
    a=s.add_parser("prepare-change"); _task_arg(a); a.add_argument("--operation",required=True,choices=["create","modify"]); a.add_argument("--target",required=True); a.add_argument("--intent",required=True); a.add_argument("--symbols",default="[]"); a.add_argument("--feature"); a.add_argument("--layer"); a.add_argument("--file-kind"); a.add_argument("--temporary",action="store_true")
    a=s.add_parser("record-claim"); _task_arg(a); a.add_argument("--claim",required=True); a.add_argument("--claim-type",required=True,choices=["business_logic","security","data_behavior","destructive_effect","governance","other"]); a.add_argument("--risk",default="medium",choices=["low","medium","high"]); a.add_argument("--evidence-call-ids",default="[]")
    a=s.add_parser("list-claims"); _task_arg(a)
    a=s.add_parser("show-claim"); a.add_argument("--claim-id",required=True,type=int)
    a=s.add_parser("egress-report"); _task_arg(a)
    a=s.add_parser("cache-store"); _task_arg(a); a.add_argument("--path",required=True); a.add_argument("--range-key",required=True); a.add_argument("--summary",required=True)
    a=s.add_parser("cache-lookup"); _task_arg(a); a.add_argument("--path",required=True); a.add_argument("--range-key",required=True)
    a=s.add_parser("docs-scan"); a.add_argument("--scope",default="src"); _task_arg(a)
    a=s.add_parser("run-tests"); _task_arg(a); a.add_argument("--path",default=".agents/tests")
    a=s.add_parser("sync-check"); _task_arg(a)
    a=s.add_parser("report"); _task_arg(a)
    a=s.add_parser("ack-baseline"); a.add_argument("--identity"); a.add_argument("--force-noninteractive",action="store_true")
    s.add_parser("drift-check")
    a=s.add_parser("drift-diff"); a.add_argument("--file",required=True)
    a=s.add_parser("approve-local-override"); a.add_argument("--reviewed-by",required=True); a.add_argument("--note",required=True)
    s.add_parser("local-override-status")
    s.add_parser("docs-check"); s.add_parser("instruction-check"); s.add_parser("db-status")
    a=s.add_parser("proxy-execute"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--args",default="{}"); a.add_argument("--reason-code"); a.add_argument("--justification"); a.add_argument("--target")
    s.add_parser("audit-verify")
    a=s.add_parser("mcp-serve"); _task_arg(a)
    a=s.add_parser("status"); _task_arg(a)
    return p


def _run_tests(root: Path, path: str) -> dict[str, Any]:
    env={**os.environ,"PYTHONPATH":str(root/".agents")}
    proc=subprocess.run(["python3","-m","pytest",path,"-q"],cwd=root,text=True,capture_output=True,env=env)
    return {"ok":proc.returncode==0,"exit_code":proc.returncode,"stdout":proc.stdout,"stderr":proc.stderr}


def _reminder(root: Path, session: str, task_id: str | None = None) -> dict[str, Any]:
    active=task_id or current_task_id(root,session); drift=drift_check(root,task_id=active); override=local_override_status(root)
    if not active:
        return {"session_id":session,"task_id":None,"baseline_state":drift["baseline_state"],"unacknowledged_governance_changes":len(drift["changes"]),"sensitive_override_status":override["status"]}
    status=workflow_status(root,active)
    with __import__("sqlite3").connect(root/".agents/state/agentos.db") as c:
        c.row_factory=__import__("sqlite3").Row; task=c.execute("SELECT request,approved,approved_scope FROM tasks WHERE id=?",(active,)).fetchone()
    done=len(status["steps"])-len(status["required_pending"])
    return {"session_id":session,"task_id":active,"original_request":task["request"] if task else None,"approved":bool(task["approved"]) if task else False,"approved_scope":json.loads(task["approved_scope"]) if task else [],"workflow_progress":f"{done}/{len(status['steps'])} steps done","next_required_step":status["required_pending"][0] if status["required_pending"] else None,"invalid_workflow_provenance":status["invalid_provenance"],"baseline_state":drift["baseline_state"],"unacknowledged_governance_changes":len(drift["changes"]),"sensitive_override_status":override["status"]}


def main() -> int:
    """Execute one AgentOS command.

    Returns:
        Process exit code.
    """
    args=parser().parse_args(); root=Path(args.root).resolve(); session=normalize_session_id(args.session_id)
    try:
        tid=getattr(args,"task_id",None)
        task_commands={"approve-task","mark-step","workflow-status","index-build","guard-tool","prepare-change","record-claim","list-claims","egress-report","cache-store","cache-lookup","report","proxy-execute","mcp-serve"}
        if args.cmd in task_commands:
            tid=resolve_task_id(root,tid,session)
        if args.cmd=="start-task":
            result=start_task(root,args.task_id,args.request); seed_workflow(root,args.task_id); set_current_task(root,args.task_id,"agentos start-task",session)
        elif args.cmd=="use-task": result=set_current_task(root,args.task_id,"agentos use-task",session)
        elif args.cmd=="whoami": result=_reminder(root,session)
        elif args.cmd=="next-step": result=next_step(root,resolve_task_id(root,None,session))
        elif args.cmd=="approve-task": result=approve_task(root,tid,_json_arg(args.scope,"scope")); complete_automated_step(root,tid,"approve_task","approve-task",result,evidence_id=tid)
        elif args.cmd=="mark-step": result=mark_step(root,tid,args.step,args.status,args.note)
        elif args.cmd=="workflow-status": result=workflow_status(root,tid)
        elif args.cmd=="index-build": result=index_build(root,args.source); complete_automated_step(root,tid,"build_or_update_local_index","index-build",result)
        elif args.cmd=="index-query": result=index_query(root,args.query,args.limit)
        elif args.cmd=="duplicate-scan": result=duplicate_report(root)
        elif args.cmd=="guard-tool": result=guard_tool(root,tid,session,args.tool,_json_arg(args.args,"args"),args.reason_code,args.justification,args.target)
        elif args.cmd=="complete-tool":
            result=complete_tool(root,args.execution_token,_json_arg(args.input,"input"),args.success,args.output,session)
            if result["success"]: complete_automated_step(root,result["task_id"],"execute_guarded","complete-tool",result,evidence_type="tool_call",evidence_id=str(result["tool_call_id"]))
        elif args.cmd=="record-tool": result=record_tool_execution(root,tid,args.tool,_json_arg(args.input,"input"),args.success,args.output,args.classification)
        elif args.cmd=="proxy-execute":
            result=proxy_execute(root,tid,session,args.tool,_json_arg(args.args,"args"),args.reason_code,args.justification,args.target)
            if result.get("success"): complete_automated_step(root,tid,"execute_guarded","proxy-execute",result,evidence_type="tool_call",evidence_id=str(result["tool_call_id"]))
        elif args.cmd=="audit-verify": result=verify_external_log(root)
        elif args.cmd=="mcp-serve":
            from .mcp_server import serve
            serve(root,tid,session); return 0
        elif args.cmd=="prepare-change":
            result=prepare_change(root,tid,args.operation,args.target,args.intent,_json_arg(args.symbols,"symbols"),args.feature,args.layer,args.file_kind,args.temporary)
            if result.get("ready"): complete_automated_step(root,tid,"prepare_change","prepare-change",result)
        elif args.cmd=="record-claim":
            result=record_claim(root,tid,args.claim,args.claim_type,args.risk,_json_arg(args.evidence_call_ids,"evidence-call-ids")); complete_automated_step(root,tid,"evidence_review","record-claim",result,evidence_type="claim",evidence_id=str(result["claim_id"]))
        elif args.cmd=="list-claims": result=list_claims(root,tid)
        elif args.cmd=="show-claim": result=show_claim(root,args.claim_id)
        elif args.cmd=="egress-report": result=egress_report(root,tid)
        elif args.cmd=="cache-store": result=cache_store(root,tid,args.path,args.range_key,args.summary)
        elif args.cmd=="cache-lookup": result=cache_lookup(root,tid,args.path,args.range_key)
        elif args.cmd=="docs-scan":
            result=documentation_scan(root,args.scope)
            if tid and result.get("ok"): complete_automated_step(root,tid,"documentation_check","docs-scan",result)
        elif args.cmd=="run-tests":
            result=_run_tests(root,args.path)
            if tid and result["ok"]: complete_automated_step(root,tid,"tests","run-tests",result,exit_code=result["exit_code"])
        elif args.cmd=="sync-check":
            dc,ic=docs_check(root),instruction_check(root); result={"ok":dc["ok"] and ic["ok"],"docs":dc,"instruction":ic}
            if tid and result["ok"]: complete_automated_step(root,tid,"synchronize","sync-check",result)
        elif args.cmd=="report":
            status=workflow_status(root,tid); pending=[x for x in status["required_pending"] if x!="report"]; drift=drift_check(root,task_id=tid); override=local_override_status(root); audit=verify_external_log(root)
            blockers={"pending_steps":pending,"invalid_provenance":status["invalid_provenance"],"baseline_state":drift["baseline_state"],"drift_changes":drift["changes"],"sensitive_override_status":override["status"],"external_audit":audit}
            blocked=bool(pending or status["invalid_provenance"] or drift["baseline_state"]!="initialized" or drift["drift_detected"] or (override["sensitive"] and override["status"]!="approved") or not audit["ok"])
            if blocked: result={"ok":False,"blocked":True,**blockers}
            else: mark_step(root,tid,"report","done","Final report produced after all automated gates and governance review passed."); result={"ok":True,"workflow":workflow_status(root,tid),"drift":drift,"override":override,"external_audit":audit}
        elif args.cmd=="ack-baseline": result=ack_baseline(root,args.identity,force_noninteractive=args.force_noninteractive,session_id=session)
        elif args.cmd=="drift-check": result=drift_check(root,task_id=current_task_id(root,session))
        elif args.cmd=="drift-diff": result=drift_diff(root,args.file)
        elif args.cmd=="approve-local-override": result=approve_local_override(root,args.reviewed_by,args.note)
        elif args.cmd=="local-override-status": result=local_override_status(root)
        elif args.cmd=="docs-check": result=docs_check(root)
        elif args.cmd=="instruction-check": result=instruction_check(root)
        elif args.cmd=="db-status": result=db_status(root)
        else: result=project_status(root,tid)
        reminder=None if args.cmd in {"whoami","ack-baseline"} else _reminder(root,session,tid)
        emit(result if args.cmd=="whoami" else ({"context_reminder":reminder,"result":result} if reminder is not None else result))
        failure=isinstance(result,dict) and (result.get("ok") is False or result.get("blocked") is True or result.get("allowed") is False)
        return 2 if failure else 0
    except Exception as exc:
        emit({"ok":False,"error":type(exc).__name__,"message":str(exc)}); return 2


if __name__=="__main__":
    raise SystemExit(main())
