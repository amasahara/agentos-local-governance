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
from .context_runtime import build_context_pack, context_compare, context_explain, context_status
from .memory import decay_user_memory, forget_identity, query_memory, record_finding, remember, validate_memory
from .skills import graduate_skill, list_skills, match_skills, promote_skill_candidate, revoke_skill
from .skill_contract_v2 import set_skill_contract, skill_contract_get, skill_contract_status, validate_skill_contract
from .retrieval import search_knowledge
from .embeddings import build_embedding_index, rag_query
from .knowledge_graph import build_graph, graph_neighbors, graph_path
from .jobs import cancel_job, discover_tools, job_status, recover_jobs, submit_job
from .planning import active_plan, approve_plan, precommit_check, submit_plan
from .evaluation import aggregate_metrics, compare_outcomes, export_metrics, record_outcome
from .evolution import create_proposal, proposal_status, simulate_proposal, transition_proposal
from .collaboration import assign_role, collaboration_readiness, list_messages, send_message
from .concurrency import acquire_resource, claim_task, handoff_task, heartbeat_resource, list_resources, release_resource
from .core import approve_task, db_status, docs_check, instruction_check, list_claims, prepare_change, project_status, record_claim, record_tool_execution, show_claim, start_task
from .documentation import documentation_scan
from .drift import ack_baseline, drift_check, drift_diff
from .indexing import duplicate_report, index_build, index_query, index_status
from .incremental_index_benchmark import DEFAULT_BENCHMARK_FILE, check_incremental_index_benchmark, run_incremental_index_benchmark
from .policy import approve_local_override, local_override_status, load_policy
from .proxy import proxy_execute
from .external_audit import rotate_signing_key, verify_external_log
from .tooling import complete_tool, egress_report, guard_tool
from .storage import archive_audit_segment, backup_create, backup_verify, prune_observability
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
    a=s.add_parser("acquire-resource"); _task_arg(a); a.add_argument("--type",required=True,choices=["file","directory","symbol","governance"]); a.add_argument("--resource",required=True); a.add_argument("--mode",default="exclusive_write",choices=["shared_read","intent_write","exclusive_write"]); a.add_argument("--ttl",type=int); a.add_argument("--base-hash")
    a=s.add_parser("heartbeat-resource"); _task_arg(a); a.add_argument("--lease-id",required=True,type=int); a.add_argument("--ttl",type=int)
    a=s.add_parser("release-resource"); _task_arg(a); a.add_argument("--lease-id",required=True,type=int)
    a=s.add_parser("list-resources"); _task_arg(a); a.add_argument("--all",action="store_true")
    a=s.add_parser("claim-task"); _task_arg(a)
    a=s.add_parser("handoff-task"); _task_arg(a); a.add_argument("--to-session",required=True); a.add_argument("--note",required=True)
    a=s.add_parser("mark-step"); _task_arg(a); a.add_argument("--step",required=True); a.add_argument("--status",required=True,choices=["done","skipped"]); a.add_argument("--note",required=True)
    a=s.add_parser("workflow-status"); _task_arg(a)
    a=s.add_parser("index-build"); a.add_argument("source",nargs="?",default="src"); a.add_argument("--full",action="store_true"); _task_arg(a)
    s.add_parser("index-status")
    a=s.add_parser("index-benchmark-run"); a.add_argument("--repeats",type=int,default=3); a.add_argument("--output",default=DEFAULT_BENCHMARK_FILE)
    a=s.add_parser("index-benchmark-check"); a.add_argument("--path",default=DEFAULT_BENCHMARK_FILE)
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
    a=s.add_parser("context-build"); _task_arg(a); a.add_argument("--max-lines",type=int,default=500)
    a=s.add_parser("context-status"); _task_arg(a)
    a=s.add_parser("context-explain"); _task_arg(a)
    a=s.add_parser("context-compare"); _task_arg(a); a.add_argument("--max-lines",type=int,default=500)
    a=s.add_parser("memory-record"); a.add_argument("--kind",required=True,choices=["semantic","episodic","procedural","evidence"]); a.add_argument("--statement",required=True); a.add_argument("--source-path"); _task_arg(a); a.add_argument("--confidence",type=float,default=1.0); a.add_argument("--evidence-hash")
    a=s.add_parser("memory-query"); a.add_argument("query"); a.add_argument("--kind",choices=["semantic","episodic","procedural","evidence"]); a.add_argument("--limit",type=int,default=20); a.add_argument("--include-stale",action="store_true")
    a=s.add_parser("skill-promote"); a.add_argument("--memory-id",required=True,type=int); a.add_argument("--promoted-by",required=True)
    a=s.add_parser("skill-list"); a.add_argument("--status",choices=["candidate","graduated","revoked","superseded","archived"])
    a=s.add_parser("skill-graduate"); a.add_argument("--skill-id",required=True,type=int); a.add_argument("--approved-by",required=True); a.add_argument("--note",required=True)
    a=s.add_parser("skill-match"); a.add_argument("query"); a.add_argument("--limit",type=int,default=10)
    a=s.add_parser("skill-revoke"); a.add_argument("--skill-id",required=True,type=int); a.add_argument("--reason",required=True); a.add_argument("--revoked-by",required=True)
    a=s.add_parser("skill-contract-set"); a.add_argument("--skill-id",required=True,type=int); a.add_argument("--contract",required=True); a.add_argument("--drafted-by",required=True)
    a=s.add_parser("skill-contract-show"); a.add_argument("--skill-id",required=True,type=int)
    a=s.add_parser("skill-contract-validate"); a.add_argument("--skill-id",required=True,type=int)
    a=s.add_parser("skill-contract-status"); a.add_argument("--skill-id",type=int)
    a=s.add_parser("knowledge-search"); a.add_argument("query"); a.add_argument("--kinds",default='["memory","finding","symbol","skill"]'); a.add_argument("--limit",type=int,default=20); a.add_argument("--backend",default="lexical_structured")
    a=s.add_parser("embedding-index"); a.add_argument("--kinds",default='["memory","finding","symbol","skill"]')
    a=s.add_parser("rag-query"); a.add_argument("query"); a.add_argument("--kinds",default='["memory","finding","symbol","skill"]'); a.add_argument("--top-k",type=int,default=8); a.add_argument("--max-chars",type=int,default=12000); a.add_argument("--no-auto-index",action="store_true")
    s.add_parser("graph-build")
    a=s.add_parser("graph-neighbors"); a.add_argument("--node-id",required=True); a.add_argument("--relation"); a.add_argument("--limit",type=int,default=50)
    a=s.add_parser("graph-path"); a.add_argument("--from-node",required=True); a.add_argument("--to-node",required=True); a.add_argument("--max-depth",type=int,default=4)
    a=s.add_parser("memory-validate")
    a=s.add_parser("finding-record"); a.add_argument("--kind",required=True); a.add_argument("--message",required=True); a.add_argument("--path"); a.add_argument("--symbol"); _task_arg(a)
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
    a=s.add_parser("rotate-audit-key"); a.add_argument("--identity",required=True); a.add_argument("--reason",required=True)
    a=s.add_parser("doctor"); a.add_argument("--scope",default=".agents/agentos")
    a=s.add_parser("job-submit"); _task_arg(a); a.add_argument("--command",required=True); a.add_argument("--cwd",default="."); a.add_argument("--timeout",type=int,default=900); a.add_argument("--env",default="{}"); a.add_argument("--no-start",action="store_true")
    a=s.add_parser("job-status"); a.add_argument("--job-id",required=True)
    a=s.add_parser("job-cancel"); a.add_argument("--job-id",required=True); a.add_argument("--reason",required=True)
    s.add_parser("job-recover")
    a=s.add_parser("tools-discover"); _task_arg(a)
    a=s.add_parser("plan-submit"); _task_arg(a); a.add_argument("--plan",required=True)
    a=s.add_parser("plan-approve"); a.add_argument("--plan-id",required=True,type=int); a.add_argument("--approved-by",required=True); a.add_argument("--note",required=True)
    a=s.add_parser("plan-show"); _task_arg(a)
    a=s.add_parser("precommit-check"); _task_arg(a); a.add_argument("--changed-files",default=None)
    a=s.add_parser("evaluation-report"); a.add_argument("--since"); a.add_argument("--agent"); a.add_argument("--model"); a.add_argument("--output"); a.add_argument("--format",choices=["json","csv"],default="json")
    a=s.add_parser("outcome-record"); a.add_argument("--task-id",required=True); a.add_argument("--outcome",required=True,choices=["success","partial","failed"]); a.add_argument("--rated-by",required=True); a.add_argument("--test-pass-rate",type=float); a.add_argument("--rework-count",type=int,default=0); a.add_argument("--note"); a.add_argument("--task-category"); a.add_argument("--agent-id"); a.add_argument("--model-id"); a.add_argument("--retrieval-backend")
    a=s.add_parser("outcome-compare"); a.add_argument("--filter-a",required=True); a.add_argument("--filter-b",required=True)
    a=s.add_parser("memory-decay"); a.add_argument("--ttl-days",type=int,default=180)
    a=s.add_parser("memory-forget"); a.add_argument("--identity",required=True)
    a=s.add_parser("observability-prune"); a.add_argument("--older-than-days",type=int,default=30)
    a=s.add_parser("audit-segment-archive"); a.add_argument("--max-events",type=int,default=10000)
    a=s.add_parser("backup-create"); a.add_argument("--output",required=True)
    a=s.add_parser("backup-verify"); a.add_argument("--path",required=True)
    a=s.add_parser("evolution-propose"); a.add_argument("--title",required=True); a.add_argument("--findings",default="[]"); a.add_argument("--patch",required=True); a.add_argument("--benefit",required=True); a.add_argument("--risks",default="[]"); a.add_argument("--rollback",required=True); a.add_argument("--created-by",required=True)
    a=s.add_parser("evolution-simulate"); a.add_argument("--proposal-id",type=int,required=True)
    a=s.add_parser("evolution-transition"); a.add_argument("--proposal-id",type=int,required=True); a.add_argument("--status",required=True,choices=["reviewed","shadow","canary","active","rolled_back"]); a.add_argument("--actor",required=True); a.add_argument("--note",required=True)
    a=s.add_parser("evolution-status"); a.add_argument("--proposal-id",type=int,required=True)
    a=s.add_parser("role-assign"); _task_arg(a); a.add_argument("--target-session",required=True); a.add_argument("--role",required=True); a.add_argument("--assigned-by",required=True)
    a=s.add_parser("collaboration-readiness"); _task_arg(a)
    a=s.add_parser("message-send"); _task_arg(a); a.add_argument("--to-session",required=True); a.add_argument("--kind",required=True); a.add_argument("--payload",required=True); a.add_argument("--disclosure",default="metadata-only"); a.add_argument("--artifacts",default="[]"); a.add_argument("--correlation-id"); a.add_argument("--causation-id")
    a=s.add_parser("message-list"); _task_arg(a)
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



def _doctor(root: Path, scope: str) -> dict[str, Any]:
    """Run consolidated installation and enforcement health checks."""
    policy = load_policy(root)
    checks = {
        "instruction": instruction_check(root),
        "documentation": docs_check(root),
        "source_docs": documentation_scan(root, scope),
        "database": db_status(root),
        "drift": drift_check(root),
        "external_audit": verify_external_log(root),
        "policy": {"ok": True, "version": policy["version"]},
        "proxy": {
            "ok": bool(policy.get("proxy_policy", {}).get("enabled") and policy.get("tool_policy", {}).get("proxy_only_mode")),
            "proxy_only_mode": policy.get("tool_policy", {}).get("proxy_only_mode"),
            "direct_backend_access_forbidden": policy.get("proxy_policy", {}).get("direct_backend_access_forbidden"),
        },
    }
    ok = all(item.get("ok", False) for item in checks.values())
    return {"ok": ok, "checks": checks}


def main(argv: list[str] | None = None) -> int:
    """Execute one AgentOS command.

    Returns:
        Process exit code.
    """
    args=parser().parse_args(argv); root=Path(args.root).resolve(); session=normalize_session_id(args.session_id)
    try:
        tid=getattr(args,"task_id",None)
        task_commands={"role-assign","collaboration-readiness","message-send","message-list","job-submit","tools-discover","plan-submit","plan-show","precommit-check","context-build","context-status","context-explain","context-compare","memory-record","finding-record","approve-task","acquire-resource","heartbeat-resource","release-resource","list-resources","claim-task","handoff-task","mark-step","workflow-status","index-build","guard-tool","prepare-change","record-claim","list-claims","egress-report","cache-store","cache-lookup","report","proxy-execute","mcp-serve"}
        if args.cmd in task_commands:
            tid=resolve_task_id(root,tid,session)
        if args.cmd=="start-task":
            result=start_task(root,args.task_id,args.request); seed_workflow(root,args.task_id); set_current_task(root,args.task_id,"agentos start-task",session)
        elif args.cmd=="use-task": result=set_current_task(root,args.task_id,"agentos use-task",session)
        elif args.cmd=="whoami": result=_reminder(root,session)
        elif args.cmd=="next-step": result=next_step(root,resolve_task_id(root,None,session))
        elif args.cmd=="approve-task": result=approve_task(root,tid,_json_arg(args.scope,"scope")); complete_automated_step(root,tid,"approve_task","approve-task",result,evidence_id=tid)
        elif args.cmd=="acquire-resource": result=proxy_execute(root,tid,session,"agentos.acquire_resource",{"resource_type":args.type,"resource":args.resource,"lease_mode":args.mode,"ttl_seconds":args.ttl,"base_hash":args.base_hash})
        elif args.cmd=="heartbeat-resource": result=proxy_execute(root,tid,session,"agentos.heartbeat_resource",{"lease_id":args.lease_id,"ttl_seconds":args.ttl})
        elif args.cmd=="release-resource": result=proxy_execute(root,tid,session,"agentos.release_resource",{"lease_id":args.lease_id})
        elif args.cmd=="list-resources": result=proxy_execute(root,tid,session,"agentos.list_resources",{"active_only":not args.all,"task_only":True})
        elif args.cmd=="claim-task": result=proxy_execute(root,tid,session,"agentos.claim_task",{})
        elif args.cmd=="handoff-task": result=proxy_execute(root,tid,session,"agentos.handoff_task",{"to_session":args.to_session,"note":args.note})
        elif args.cmd=="mark-step": result=mark_step(root,tid,args.step,args.status,args.note)
        elif args.cmd=="workflow-status": result=workflow_status(root,tid)
        elif args.cmd=="index-build": result=index_build(root,args.source,force_full=args.full); complete_automated_step(root,tid,"build_or_update_local_index","index-build",result)
        elif args.cmd=="index-status": result=index_status(root)
        elif args.cmd=="index-benchmark-run":
            result=run_incremental_index_benchmark(root,args.repeats)
            output=(root/args.output).resolve()
            try: output.relative_to(root)
            except ValueError as exc: raise RuntimeError("index benchmark output must stay inside project root") from exc
            output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
            result={**result,"output":output.relative_to(root).as_posix()}
        elif args.cmd=="index-benchmark-check": result=check_incremental_index_benchmark(root,args.path)
        elif args.cmd=="index-query": result=index_query(root,args.query,args.limit)
        elif args.cmd=="duplicate-scan": result=duplicate_report(root)
        elif args.cmd in {"guard-tool", "complete-tool"}:
            if load_policy(root).get("tool_policy", {}).get("proxy_only_mode", True):
                raise RuntimeError("legacy guarded execution is disabled; use the MCP gateway or proxy-execute")
            if args.cmd == "guard-tool":
                result=guard_tool(root,tid,session,args.tool,_json_arg(args.args,"args"),args.reason_code,args.justification,args.target)
            else:
                result=complete_tool(root,args.execution_token,_json_arg(args.input,"input"),args.success,args.output,session)
        elif args.cmd=="record-tool": result=record_tool_execution(root,tid,args.tool,_json_arg(args.input,"input"),args.success,args.output,args.classification)
        elif args.cmd=="proxy-execute":
            result=proxy_execute(root,tid,session,args.tool,_json_arg(args.args,"args"),args.reason_code,args.justification,args.target)
            if result.get("success"): complete_automated_step(root,tid,"execute_guarded","proxy-execute",result,evidence_type="tool_call",evidence_id=str(result["tool_call_id"]))
        elif args.cmd=="audit-verify": result=verify_external_log(root)
        elif args.cmd=="rotate-audit-key":
            result=rotate_signing_key(root,args.identity,args.reason)
            with __import__("sqlite3").connect(root/".agents/state/agentos.db") as c:
                c.execute("INSERT INTO audit_key_rotations(old_key_id,new_key_id,identity,reason,event_hash) VALUES(?,?,?,?,?)",(result["old_key_id"],result["new_key_id"],args.identity,args.reason,result["event"]["event_hash"]))
        elif args.cmd=="doctor": result=_doctor(root,args.scope)
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
        elif args.cmd=="context-build": result=build_context_pack(root,tid,args.max_lines)
        elif args.cmd=="context-status": result=context_status(root,tid)
        elif args.cmd=="context-explain": result=context_explain(root,tid)
        elif args.cmd=="context-compare": result=context_compare(root,tid,args.max_lines)
        elif args.cmd=="memory-record": result=remember(root,args.kind,args.statement,args.source_path,tid,args.confidence,args.evidence_hash)
        elif args.cmd=="memory-query": result=query_memory(root,args.query,args.kind,args.limit,args.include_stale)
        elif args.cmd=="skill-promote": result=promote_skill_candidate(root,args.memory_id,args.promoted_by)
        elif args.cmd=="skill-list": result=list_skills(root,args.status)
        elif args.cmd=="skill-graduate": result=graduate_skill(root,args.skill_id,args.approved_by,args.note)
        elif args.cmd=="skill-match": result=match_skills(root,args.query,args.limit)
        elif args.cmd=="skill-revoke": result=revoke_skill(root,args.skill_id,args.reason,args.revoked_by)
        elif args.cmd=="skill-contract-set": result=set_skill_contract(root,args.skill_id,_json_arg(args.contract,"contract"),args.drafted_by)
        elif args.cmd=="skill-contract-show": result=skill_contract_get(root,args.skill_id)
        elif args.cmd=="skill-contract-validate": result=validate_skill_contract(root,args.skill_id)
        elif args.cmd=="skill-contract-status": result=skill_contract_status(root,args.skill_id)
        elif args.cmd=="knowledge-search": result=search_knowledge(root,args.query,_json_arg(args.kinds,"kinds"),args.limit,args.backend)
        elif args.cmd=="embedding-index": result=build_embedding_index(root,_json_arg(args.kinds,"kinds"))
        elif args.cmd=="rag-query": result=rag_query(root,args.query,_json_arg(args.kinds,"kinds"),args.top_k,args.max_chars,not args.no_auto_index)
        elif args.cmd=="graph-build": result=build_graph(root)
        elif args.cmd=="graph-neighbors": result=graph_neighbors(root,args.node_id,args.relation,args.limit)
        elif args.cmd=="graph-path": result=graph_path(root,args.from_node,args.to_node,args.max_depth)
        elif args.cmd=="memory-validate": result=validate_memory(root)
        elif args.cmd=="finding-record": result=record_finding(root,args.kind,args.message,args.path,args.symbol,tid)
        elif args.cmd=="job-submit": result=submit_job(root,tid,session,_json_arg(args.command,"command"),args.cwd,args.timeout,_json_arg(args.env,"env"),not args.no_start)
        elif args.cmd=="job-status": result=job_status(root,args.job_id)
        elif args.cmd=="job-cancel": result=cancel_job(root,args.job_id,session,args.reason)
        elif args.cmd=="job-recover": result=recover_jobs(root)
        elif args.cmd=="tools-discover": result=discover_tools(root,tid)
        elif args.cmd=="plan-submit": result=submit_plan(root,tid,session,_json_arg(args.plan,"plan"))
        elif args.cmd=="plan-approve": result=approve_plan(root,args.plan_id,args.approved_by,args.note)
        elif args.cmd=="plan-show": result=active_plan(root,tid) or {"ok":False,"task_id":tid,"status":"missing"}
        elif args.cmd=="precommit-check":
            files=_json_arg(args.changed_files,"changed-files") if args.changed_files else None
            result=precommit_check(root,tid,files)
            with __import__("sqlite3").connect(root/".agents/state/agentos.db") as c: c.execute("INSERT INTO precommit_checks(task_id,ok,changed_files_json,blockers_json) VALUES(?,?,?,?)",(tid,int(result["ok"]),json.dumps(result["changed_files"]),json.dumps(result["blockers"])))
        elif args.cmd=="outcome-record": result=record_outcome(root,args.task_id,args.outcome,args.rated_by,args.test_pass_rate,args.rework_count,args.note,task_category=args.task_category,agent_id=args.agent_id,model_id=args.model_id,retrieval_backend=args.retrieval_backend,policy_revision=load_policy(root)["version"],repository_revision=(root/"VERSION").read_text().strip())
        elif args.cmd=="outcome-compare": result=compare_outcomes(root,_json_arg(args.filter_a,"filter-a"),_json_arg(args.filter_b,"filter-b"))
        elif args.cmd=="memory-decay": result=decay_user_memory(root,args.ttl_days)
        elif args.cmd=="memory-forget": result=forget_identity(root,args.identity)
        elif args.cmd=="observability-prune": result=prune_observability(root,args.older_than_days)
        elif args.cmd=="audit-segment-archive": result=archive_audit_segment(root,args.max_events)
        elif args.cmd=="backup-create": result=backup_create(root,args.output)
        elif args.cmd=="backup-verify": result=backup_verify(root,args.path)
        elif args.cmd=="evaluation-report":
            result=export_metrics(root,args.output,args.format,since=args.since,agent=args.agent,model=args.model) if args.output else aggregate_metrics(root,args.since,args.agent,args.model)
        elif args.cmd=="evolution-propose": result=create_proposal(root,args.title,_json_arg(args.findings,"findings"),_json_arg(args.patch,"patch"),args.benefit,_json_arg(args.risks,"risks"),_json_arg(args.rollback,"rollback"),args.created_by)
        elif args.cmd=="evolution-simulate": result=simulate_proposal(root,args.proposal_id)
        elif args.cmd=="evolution-transition": result=transition_proposal(root,args.proposal_id,args.status,args.actor,args.note)
        elif args.cmd=="evolution-status": result=proposal_status(root,args.proposal_id)
        elif args.cmd=="role-assign": result=assign_role(root,tid,args.target_session,args.role,args.assigned_by)
        elif args.cmd=="collaboration-readiness": result=collaboration_readiness(root,tid)
        elif args.cmd=="message-send": result=send_message(root,tid,session,args.to_session,args.kind,_json_arg(args.payload,"payload"),args.disclosure,_json_arg(args.artifacts,"artifacts"),args.correlation_id,args.causation_id)
        elif args.cmd=="message-list": result=list_messages(root,tid,session)
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
            from .architecture_compliance import architecture_compliance_check
            architecture=architecture_compliance_check(root,task_id=tid,mode="final_report",refresh_scan=True,created_by="system:final-report")
            blockers={"pending_steps":pending,"invalid_provenance":status["invalid_provenance"],"baseline_state":drift["baseline_state"],"drift_changes":drift["changes"],"sensitive_override_status":override["status"],"external_audit":audit,"architecture_compliance":architecture if not architecture.get("ok",True) else None}
            blocked=bool(pending or status["invalid_provenance"] or drift["baseline_state"]!="initialized" or drift["drift_detected"] or (override["sensitive"] and override["status"]!="approved") or not audit["ok"] or not architecture.get("ok",False))
            if blocked: result={"ok":False,"blocked":True,**blockers}
            else: mark_step(root,tid,"report","done","Final report produced after all automated gates, architecture compliance, and governance review passed."); result={"ok":True,"workflow":workflow_status(root,tid),"drift":drift,"override":override,"external_audit":audit,"architecture_compliance":architecture}
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
