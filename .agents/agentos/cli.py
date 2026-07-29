"""
File: .agents/agentos/cli.py

Purpose:
    Expose AgentOS governance through a JSON command-line interface.

Responsibilities:
    - Parse developer and agent commands.
    - Delegate to governance modules.
    - Emit stable machine-readable responses.
"""
import argparse,json
from .core import *
from .db import schema_status
from .tooling import guard_tool,record_tool_execution,egress_report
from .cache import cache_lookup,cache_store
from .indexing import index_build,index_query,duplicate_report,index_status
from .documentation import documentation_scan
def emit(value)->None:
    """Print a JSON-serializable result.

    Args:
        value: Result object.

    Returns:
        None.
    """
    print(json.dumps(value,ensure_ascii=False,indent=2))
def main()->None:
    """Parse and execute one AgentOS command.

    Args:
        None.

    Returns:
        None.
    """
    p=argparse.ArgumentParser(prog='agentos');s=p.add_subparsers(dest='cmd',required=True)
    a=s.add_parser('clarity-check');a.add_argument('--task-id',required=True);a.add_argument('--request',required=True);a.add_argument('--payload',required=True)
    a=s.add_parser('approve-task');a.add_argument('task_id')
    for n in ('instruction-check','docs-check','db-status','db-migrate','duplicate-scan'):s.add_parser(n)
    a=s.add_parser('detect-environment');a.add_argument('--session-id',required=True)
    a=s.add_parser('tool-guard');a.add_argument('--task-id',required=True);a.add_argument('--tool',required=True);a.add_argument('--args',required=True);a.add_argument('--justification');a.add_argument('--target')
    a=s.add_parser('record-tool');a.add_argument('--task-id',required=True);a.add_argument('--tool',required=True);a.add_argument('--args',required=True);a.add_argument('--success',action='store_true');a.add_argument('--error');a.add_argument('--summary',default='')
    for n in ('cache-lookup','cache-store'):
        a=s.add_parser(n);a.add_argument('--task-id',required=True);a.add_argument('--path',required=True);a.add_argument('--start',type=int);a.add_argument('--end',type=int)
        if n=='cache-store':a.add_argument('--summary',required=True)
    a=s.add_parser('index-build');a.add_argument('scope',nargs='?',default='src')
    a=s.add_parser('index-query');a.add_argument('query');a.add_argument('--limit',type=int,default=20)
    a=s.add_parser('index-status');a.add_argument('scope',nargs='?',default='src')
    for n in ('docs-code-check','docs-code-scan'):
        a=s.add_parser(n);a.add_argument('scope',nargs='?',default='src')
    a=s.add_parser('egress-report');a.add_argument('--task-id',required=True)
    a=s.add_parser('status');a.add_argument('--task-id')
    a=s.add_parser('resolve-placement');a.add_argument('filename');a.add_argument('--feature');a.add_argument('--layer');a.add_argument('--temporary',action='store_true');a.add_argument('--task-id')
    a=s.add_parser('check-write');a.add_argument('path');a.add_argument('--task-id',required=True)
    a=s.add_parser('runtime-path');a.add_argument('task_id');a.add_argument('kind');a.add_argument('filename')
    x=p.parse_args();root=project_root()
    if x.cmd=='clarity-check':r=assess_clarity(json.loads(x.payload));save_task(root,x.task_id,x.request,r);o=r.__dict__.copy();o['clarification_questions']=suggested_questions(r) if r.status!='ready' else [];emit(o)
    elif x.cmd=='approve-task':approve_task(root,x.task_id);emit({'approved':True})
    elif x.cmd=='instruction-check':emit(instruction_check(root))
    elif x.cmd=='docs-check':emit(docs_check(root))
    elif x.cmd in ('db-status','db-migrate'):emit(schema_status(root))
    elif x.cmd=='detect-environment':emit(detect_environment(root,x.session_id))
    elif x.cmd=='tool-guard':emit(guard_tool(root,x.task_id,x.tool,json.loads(x.args),json.loads(x.justification) if x.justification else None,x.target))
    elif x.cmd=='record-tool':emit(record_tool_execution(root,x.task_id,x.tool,json.loads(x.args),x.success,x.summary,x.error))
    elif x.cmd=='cache-lookup':emit(cache_lookup(root,x.task_id,x.path,x.start,x.end))
    elif x.cmd=='cache-store':emit(cache_store(root,x.task_id,x.path,x.summary,x.start,x.end))
    elif x.cmd=='index-build':emit(index_build(root,x.scope))
    elif x.cmd=='index-query':emit(index_query(root,x.query,x.limit))
    elif x.cmd=='index-status':emit(index_status(root,x.scope))
    elif x.cmd=='duplicate-scan':emit(duplicate_report(root))
    elif x.cmd in ('docs-code-check','docs-code-scan'):emit(documentation_scan(root,x.scope))
    elif x.cmd=='egress-report':emit(egress_report(root,x.task_id))
    elif x.cmd=='status':emit(project_status(root,x.task_id))
    elif x.cmd=='resolve-placement':emit({'path':resolve_placement(root,x.filename,x.feature,x.layer,x.temporary,x.task_id)})
    elif x.cmd=='check-write':emit(check_write(root,x.task_id,x.path))
    elif x.cmd=='runtime-path':emit({'path':runtime_path(root,x.task_id,x.kind,x.filename)})
if __name__=='__main__':main()
