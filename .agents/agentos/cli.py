"""
File: .agents/agentos/cli.py

Purpose:
    Provide the command-line interface for AgentOS governance operations.

Responsibilities:
    - Parse commands and structured arguments.
    - Resolve current-task context and emit reminders.
    - Enforce workflow, drift, test, and synchronization gates.
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
from .tooling import egress_report, guard_tool, record_guard_result
from .workflow import current_task_id, mark_step, next_step, resolve_task_id, seed_workflow, set_current_task, workflow_status


def emit(value: Any) -> None:
    """Print a JSON-serializable value."""
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _json_arg(value: str, name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON argument: {name}") from exc


def _task_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id")


def parser() -> argparse.ArgumentParser:
    """Build the AgentOS command-line parser."""
    p = argparse.ArgumentParser(prog="agentos")
    p.add_argument("--root", default=".")
    s = p.add_subparsers(dest="cmd", required=True)
    a=s.add_parser("start-task"); a.add_argument("--task-id",required=True); a.add_argument("--request",required=True)
    a=s.add_parser("use-task"); a.add_argument("--task-id",required=True)
    s.add_parser("whoami"); s.add_parser("next-step")
    a=s.add_parser("approve-task"); _task_arg(a); a.add_argument("--scope",required=True)
    a=s.add_parser("mark-step"); _task_arg(a); a.add_argument("--step",required=True); a.add_argument("--status",required=True,choices=["done","skipped"]); a.add_argument("--note")
    a=s.add_parser("workflow-status"); _task_arg(a)
    a=s.add_parser("index-build"); a.add_argument("source",nargs="?",default="src"); _task_arg(a)
    a=s.add_parser("index-query"); a.add_argument("query"); a.add_argument("--limit",type=int,default=10)
    s.add_parser("duplicate-scan")
    a=s.add_parser("record-tool"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--input",default="{}"); a.add_argument("--success",action="store_true"); a.add_argument("--output",required=True); a.add_argument("--classification",default="local")
    a=s.add_parser("prepare-change"); _task_arg(a); a.add_argument("--operation",required=True,choices=["create","modify"]); a.add_argument("--target",required=True); a.add_argument("--intent",required=True); a.add_argument("--symbols",default="[]"); a.add_argument("--feature"); a.add_argument("--layer"); a.add_argument("--file-kind"); a.add_argument("--temporary",action="store_true")
    a=s.add_parser("record-claim"); _task_arg(a); a.add_argument("--claim",required=True); a.add_argument("--claim-type",required=True,choices=["business_logic","security","data_behavior","destructive_effect","governance","other"]); a.add_argument("--risk",default="medium",choices=["low","medium","high"]); a.add_argument("--evidence-call-ids",default="[]")
    a=s.add_parser("list-claims"); _task_arg(a)
    a=s.add_parser("show-claim"); a.add_argument("--claim-id",required=True,type=int)
    a=s.add_parser("tool-guard"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--args",default="{}"); a.add_argument("--reason-code"); a.add_argument("--justification"); a.add_argument("--target")
    a=s.add_parser("record-tool-result"); _task_arg(a); a.add_argument("--tool",required=True); a.add_argument("--args",default="{}"); a.add_argument("--success",action="store_true")
    a=s.add_parser("egress-report"); _task_arg(a)
    a=s.add_parser("cache-store"); _task_arg(a); a.add_argument("--path",required=True); a.add_argument("--range-key",required=True); a.add_argument("--summary",required=True)
    a=s.add_parser("cache-lookup"); _task_arg(a); a.add_argument("--path",required=True); a.add_argument("--range-key",required=True)
    a=s.add_parser("docs-scan"); a.add_argument("--scope",default="src"); _task_arg(a)
    a=s.add_parser("run-tests"); _task_arg(a); a.add_argument("--path",default=".agents/tests")
    a=s.add_parser("sync-check"); _task_arg(a)
    a=s.add_parser("report"); _task_arg(a)
    a=s.add_parser("ack-baseline"); a.add_argument("--acknowledged-by",default="human")
    s.add_parser("drift-check")
    a=s.add_parser("drift-diff"); a.add_argument("--file",required=True)
    s.add_parser("docs-check"); s.add_parser("instruction-check"); s.add_parser("db-status")
    a=s.add_parser("status"); _task_arg(a)
    return p


def _reminder(root: Path, task_id: str | None = None) -> dict[str, Any]:
    active = task_id or current_task_id(root)
    drift = drift_check(root, task_id=active)
    if not active:
        return {"task_id": None, "workflow_progress": None, "next_required_step": None, "unacknowledged_governance_changes": len(drift["changes"])}
    status = workflow_status(root, active)
    with __import__('sqlite3').connect(root / '.agents/state/agentos.db') as c:
        c.row_factory = __import__('sqlite3').Row
        task = c.execute('SELECT request,approved,approved_scope FROM tasks WHERE id=?',(active,)).fetchone()
    done = len(status['steps']) - len(status['required_pending'])
    return {"task_id":active,"original_request":task['request'] if task else None,"approved":bool(task['approved']) if task else False,"approved_scope":json.loads(task['approved_scope']) if task else [],"workflow_progress":f"{done}/{len(status['steps'])} required steps done","next_required_step":status['required_pending'][0] if status['required_pending'] else None,"unacknowledged_governance_changes":len(drift['changes'])}


def _run_tests(root: Path, path: str) -> dict[str, Any]:
    env={**os.environ,"PYTHONPATH":str(root/'.agents')}
    proc=subprocess.run(["python3","-m","pytest",path,"-q"],cwd=root,text=True,capture_output=True,env=env)
    return {"ok":proc.returncode==0,"exit_code":proc.returncode,"stdout":proc.stdout,"stderr":proc.stderr}


def main() -> int:
    """Execute one AgentOS CLI command."""
    args=parser().parse_args(); root=Path(args.root).resolve()
    try:
        tid=getattr(args,'task_id',None)
        if args.cmd not in {"start-task","use-task","ack-baseline","drift-check","drift-diff","docs-check","instruction-check","db-status","show-claim","index-query","duplicate-scan","docs-scan","run-tests","sync-check","status"} and hasattr(args,'task_id'):
            tid=resolve_task_id(root,tid)
        if args.cmd=="start-task":
            result=start_task(root,args.task_id,args.request); seed_workflow(root,args.task_id); set_current_task(root,args.task_id,"agentos start-task")
        elif args.cmd=="use-task": result=set_current_task(root,args.task_id,"agentos use-task")
        elif args.cmd=="whoami": result=_reminder(root)
        elif args.cmd=="next-step": result=next_step(root,resolve_task_id(root,None))
        elif args.cmd=="approve-task": result=approve_task(root,tid,_json_arg(args.scope,"scope")); mark_step(root,tid,"approve_task","done","Task approved.")
        elif args.cmd=="mark-step": result=mark_step(root,tid,args.step,args.status,args.note)
        elif args.cmd=="workflow-status": result=workflow_status(root,tid)
        elif args.cmd=="index-build": result=index_build(root,args.source); mark_step(root,tid,"build_or_update_local_index","done",f"Indexed {args.source}.")
        elif args.cmd=="index-query": result=index_query(root,args.query,args.limit)
        elif args.cmd=="duplicate-scan": result=duplicate_report(root)
        elif args.cmd=="record-tool": result=record_tool_execution(root,tid,args.tool,_json_arg(args.input,"input"),args.success,args.output,args.classification); mark_step(root,tid,"execute_guarded","done","Successful guarded tool execution." if args.success else "Tool execution recorded.") if args.success else None
        elif args.cmd=="prepare-change": result=prepare_change(root,tid,args.operation,args.target,args.intent,_json_arg(args.symbols,"symbols"),args.feature,args.layer,args.file_kind,args.temporary); mark_step(root,tid,"prepare_change","done","Composite change preparation passed.") if result.get('ready') else None
        elif args.cmd=="record-claim": result=record_claim(root,tid,args.claim,args.claim_type,args.risk,_json_arg(args.evidence_call_ids,"evidence-call-ids")); mark_step(root,tid,"evidence_review","done","Evidence-grounded claim recorded.")
        elif args.cmd=="list-claims": result=list_claims(root,tid)
        elif args.cmd=="show-claim": result=show_claim(root,args.claim_id)
        elif args.cmd=="tool-guard": result=guard_tool(root,tid,args.tool,_json_arg(args.args,"args"),args.reason_code,args.justification,args.target)
        elif args.cmd=="record-tool-result": result=record_guard_result(root,tid,args.tool,_json_arg(args.args,"args"),args.success)
        elif args.cmd=="egress-report": result=egress_report(root,tid)
        elif args.cmd=="cache-store": result=cache_store(root,tid,args.path,args.range_key,args.summary)
        elif args.cmd=="cache-lookup": result=cache_lookup(root,tid,args.path,args.range_key)
        elif args.cmd=="docs-scan": result=documentation_scan(root,args.scope); mark_step(root,tid,"documentation_check","done","Source documentation scan passed.") if tid and result.get('ok') else None
        elif args.cmd=="run-tests": result=_run_tests(root,args.path); mark_step(root,tid,"tests","done","Test suite passed.") if tid and result['ok'] else None
        elif args.cmd=="sync-check":
            dc,ic=docs_check(root),instruction_check(root); result={"ok":dc['ok'] and ic['ok'],"docs":dc,"instruction":ic}; mark_step(root,tid,"synchronize","done","Documentation and instruction synchronization passed.") if tid and result['ok'] else None
        elif args.cmd=="report":
            status=workflow_status(root,tid); pending=[x for x in status['required_pending'] if x!='report']
            if pending: result={"ok":False,"blocked":True,"pending_steps":pending}
            else: mark_step(root,tid,"report","done","Final report gate passed."); result={"ok":True,"workflow":workflow_status(root,tid)}
        elif args.cmd=="ack-baseline": result=ack_baseline(root,args.acknowledged_by)
        elif args.cmd=="drift-check": result=drift_check(root,task_id=current_task_id(root))
        elif args.cmd=="drift-diff": result=drift_diff(root,args.file)
        elif args.cmd=="docs-check": result=docs_check(root)
        elif args.cmd=="instruction-check": result=instruction_check(root)
        elif args.cmd=="db-status": result=db_status(root)
        else: result=project_status(root,tid)
        reminder=_reminder(root,tid) if args.cmd not in {"whoami","ack-baseline"} else None
        payload=result if args.cmd=="whoami" else ({"context_reminder":reminder,"result":result} if reminder is not None else result)
        emit(payload)
        governed_failure=(isinstance(result,dict) and (result.get('ok') is False or result.get('blocked') is True))
        return 2 if governed_failure else 0
    except Exception as exc:
        emit({"ok":False,"error":type(exc).__name__,"message":str(exc)}); return 2


if __name__=="__main__":
    raise SystemExit(main())
