"""
File: .agents/agentos/core.py

Purpose:
    Provide the stable AgentOS public governance interface.

Responsibilities:
    - Manage clarity, approval, write scope, placement, and status.
    - Delegate tool, cache, index, and documentation operations.
    - Preserve compatibility with earlier AgentOS commands.
"""
from __future__ import annotations
import json,os,platform,re,sys
from pathlib import Path
from typing import Any
from .db import connect,schema_status
from .models import ClarityAssessment
from .policy import load
from .tooling import guard_tool,record_tool_execution,egress_report
from .cache import cache_lookup,cache_store
from .indexing import index_build,index_query,duplicate_report,index_status
from .documentation import documentation_scan
FORBIDDEN_INSTRUCTION_FILES={'CLAUDE.md','GEMINI.md','COPILOT.md','CODEX.md','CURSOR.md'}
def project_root(start:str|Path='.') -> Path:
    """Locate the AgentOS project root.

    Args:
        start: Starting path for upward discovery.

    Returns:
        Absolute directory containing AGENTS.md and .agents/.

    Raises:
        RuntimeError: No AgentOS root is found.
    """
    p=Path(start).resolve()
    for c in [p,*p.parents]:
        if (c/'AGENTS.md').is_file() and (c/'.agents').is_dir():return c
    raise RuntimeError('AgentOS project root not found')
def load_governance(root:Path)->dict[str,Any]:
    """Load validated governance configuration.

    Args:
        root: Absolute project root.

    Returns:
        Validated policy dictionary.
    """
    return load(root)
def db_connect(root:Path):
    """Open the migrated AgentOS database.

    Args:
        root: Absolute project root.

    Returns:
        Initialized SQLite connection.
    """
    return connect(root)
def assess_clarity(payload:dict[str,Any])->ClarityAssessment:
    """Assess semantic completeness of a user request.

    Args:
        payload: Intent, target, behavior, criteria, scope, risk, and change flags.

    Returns:
        Clarity assessment with ambiguities and readiness status.
    """
    clean=lambda v:str(v).strip() if v is not None and str(v).strip() else None
    intent=clean(payload.get('intent'));target=clean(payload.get('target'));expected=clean(payload.get('expected_behavior'));current=clean(payload.get('current_behavior'));criteria=[str(x).strip() for x in payload.get('acceptance_criteria',[]) if str(x).strip()];scope=clean(payload.get('scope'));risk=str(payload.get('risk') or 'medium').lower();assumptions=[str(x).strip() for x in payload.get('assumptions',[]) if str(x).strip()];a=[]
    if not intent:a.append('Không xác định được ý định chính.')
    if not target:a.append('Chưa xác định chức năng, module, file hoặc hành vi bị ảnh hưởng.')
    if not expected:a.append('Chưa mô tả kết quả mong muốn.')
    if intent in {'fix','modify_existing_feature','debug'} and not current:a.append('Chưa mô tả hành vi hiện tại hoặc lỗi đang xảy ra.')
    if not criteria:a.append('Chưa có tiêu chí nghiệm thu có thể kiểm chứng.')
    if not scope:a.append('Chưa xác định phạm vi thay đổi.')
    if any(payload.get(k) for k in ('destructive','schema_change','permission_change','security_change')):risk='high'
    return ClarityAssessment(intent,target,expected,current,criteria,scope,risk,a,assumptions,'ready' if not a else 'needs_clarification')
def suggested_questions(x:ClarityAssessment)->list[str]:
    """Build targeted clarification questions.

    Args:
        x: Requirement clarity result.

    Returns:
        Up to five Vietnamese clarification questions.
    """
    j=' '.join(x.ambiguities);q=[]
    if 'chức năng' in j:q.append('Chức năng, màn hình, module hoặc file nào cần thay đổi?')
    if 'hành vi hiện tại' in j:q.append('Hiện tại hệ thống đang hoạt động hoặc báo lỗi như thế nào?')
    if 'kết quả mong muốn' in j:q.append('Kết quả chính xác bạn mong muốn sau khi sửa là gì?')
    if 'tiêu chí nghiệm thu' in j:q.append('Những điều kiện nào phải đúng để xem task đã hoàn thành?')
    if 'phạm vi' in j:q.append('Phạm vi thay đổi được phép gồm những phần nào?')
    return q[:5]
def save_task(root:Path,task_id:str,request:str,x:ClarityAssessment)->None:
    """Persist or update a task brief.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        request: Unmodified user request.
        x: Current clarity assessment.

    Returns:
        None.
    """
    with connect(root) as c:c.execute('INSERT INTO tasks(task_id,original_request,intent,target,expected_behavior,current_behavior,acceptance_criteria,scope,risk,ambiguities,assumptions,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET original_request=excluded.original_request,intent=excluded.intent,target=excluded.target,expected_behavior=excluded.expected_behavior,current_behavior=excluded.current_behavior,acceptance_criteria=excluded.acceptance_criteria,scope=excluded.scope,risk=excluded.risk,ambiguities=excluded.ambiguities,assumptions=excluded.assumptions,status=excluded.status,updated_at=CURRENT_TIMESTAMP',(task_id,request,x.intent,x.target,x.expected_behavior,x.current_behavior,json.dumps(x.acceptance_criteria,ensure_ascii=False),x.scope,x.risk,json.dumps(x.ambiguities,ensure_ascii=False),json.dumps(x.assumptions,ensure_ascii=False),x.status))
def approve_task(root:Path,task_id:str)->None:
    """Approve a ready task.

    Args:
        root: Absolute project root.
        task_id: Existing task identifier.

    Returns:
        None.

    Raises:
        RuntimeError: Task is unknown or not ready.
    """
    with connect(root) as c:
        r=c.execute('SELECT status FROM tasks WHERE task_id=?',(task_id,)).fetchone()
        if not r:raise RuntimeError('Task does not exist')
        if r['status']!='ready':raise RuntimeError('Task still needs clarification')
        c.execute('UPDATE tasks SET approved=1 WHERE task_id=?',(task_id,))
def check_write(root:Path,task_id:str,target:str|Path)->dict[str,Any]:
    """Validate a requested write path.

    Args:
        root: Absolute project root.
        task_id: Existing task identifier.
        target: Requested project-relative or absolute path.

    Returns:
        Write decision with resolved path and reason.
    """
    with connect(root) as c:r=c.execute('SELECT status,approved FROM tasks WHERE task_id=?',(task_id,)).fetchone()
    allowed=bool(r and r['status']=='ready' and r['approved']);reason='approved' if allowed else 'task_not_ready_or_approved';raw=Path(target);resolved=(root/raw).resolve() if not raw.is_absolute() else raw.resolve()
    if allowed:
        try:resolved.relative_to(root)
        except ValueError:allowed,reason=False,'outside_project_root'
    if allowed and '..' in raw.parts:allowed,reason=False,'path_traversal'
    if allowed and resolved.parent==root and resolved.suffix in {'.py','.js','.ts','.java','.cs','.go','.rs'}:allowed,reason=False,'source_file_at_project_root'
    with connect(root) as c:c.execute('INSERT INTO write_audit(task_id,path,allowed,reason) VALUES(?,?,?,?)',(task_id,str(resolved),int(allowed),reason))
    return {'allowed':allowed,'reason':reason,'resolved_path':str(resolved)}
def instruction_check(root:Path)->dict[str,Any]:
    """Verify AGENTS.md is the only instruction source.

    Args:
        root: Absolute project root.

    Returns:
        Instruction check result.
    """
    found=[]
    for n in FORBIDDEN_INSTRUCTION_FILES:found.extend(str(p.relative_to(root)) for p in root.rglob(n))
    return {'ok':not found,'duplicate_instruction_sources':sorted(found)}
def docs_check(root:Path)->dict[str,Any]:
    """Verify bilingual documentation and version synchronization.

    Args:
        root: Absolute project root.

    Returns:
        Documentation consistency report.
    """
    cfg=load(root);p=cfg.get('documentation_policy',{});missing=[x for x in p.get('required_docs',[]) if not (root/x).is_file()];v=(root/'VERSION').read_text().strip();text=(root/'.agents/agentos/__init__.py').read_text();m=re.search(r"__version__\s*=\s*['\"]([^'\"]+)['\"]", text);iv=m.group(1) if m else None;guide=(root/p.get('developer_entry_point','huong_dan.md')).read_text();ch=(root/'.agents/docs/RULES_WORKFLOW_CHANGELOG.md').read_text();res={'missing_documents':missing,'version':{'VERSION':v,'governance.json':cfg['version'],'__init__.py':iv,'consistent':v==cfg['version']==iv},'bilingual_markers':{'vi':any(x in guide for x in ('Tiếng Việt','HƯỚNG DẪN','Mục đích')),'en':any(x in guide for x in ('English','Purpose','PROJECT STRUCTURE'))},'changelog_has_current_version':f'v{v}' in ch};res['ok']=not missing and res['version']['consistent'] and all(res['bilingual_markers'].values()) and res['changelog_has_current_version'];return res
def detect_environment(root:Path,session_id:str)->dict[str,Any]:
    """Detect and persist the execution environment.

    Args:
        root: Absolute project root.
        session_id: Stable profile identifier.

    Returns:
        Platform and Python environment metadata.
    """
    p={'platform':platform.system().lower(),'shell':os.environ.get('SHELL') or os.environ.get('COMSPEC') or '','project_root':str(root),'python_executable':sys.executable,'path_separator':os.sep,'default_encoding':sys.getdefaultencoding(),'virtual_environment':os.environ.get('VIRTUAL_ENV')}
    with connect(root) as c:c.execute('INSERT INTO environment_profiles(session_id,profile_json) VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET profile_json=excluded.profile_json',(session_id,json.dumps(p,ensure_ascii=False)))
    return p
def resolve_placement(root:Path,filename:str,feature:str|None,layer:str|None,temporary:bool,task_id:str|None)->str:
    """Resolve a compliant persistent or temporary path.

    Args:
        root: Absolute project root.
        filename: Requested file name.
        feature: Optional feature name.
        layer: Optional architecture layer.
        temporary: Whether the file is disposable.
        task_id: Required task identifier for temporary files.

    Returns:
        Project-relative resolved path.
    """
    if temporary:
        if not task_id:raise RuntimeError('task_id is required')
        return str(Path('.agents/runtime/task-workspaces')/task_id/('tests' if filename.startswith('test_') else 'scripts')/filename)
    if filename.startswith('test_'):return str(Path('tests')/(feature or 'integration')/filename)
    p=Path('src');p=p/feature if feature else p;p=p/layer if layer else p;return str(p/filename)
def runtime_path(root:Path,task_id:str,kind:str,filename:str)->str:
    """Create and return a task-local artifact path.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        kind: Temporary artifact type.
        filename: Artifact file name.

    Returns:
        Absolute artifact path.
    """
    m={'temporary_script':'scripts','temporary_test':'tests','fixture':'fixtures','validation_artifact':'validation-artifacts','download':'downloads','export':'exports'};p=root/'.agents/runtime/task-workspaces'/task_id/m.get(kind,kind)/filename;p.parent.mkdir(parents=True,exist_ok=True);return str(p)
def project_status(root:Path,task_id:str|None=None)->dict[str,Any]:
    """Return aggregate project and task state.

    Args:
        root: Absolute project root.
        task_id: Optional task identifier.

    Returns:
        Project checks and optional task status.
    """
    out={'project':{'instruction_check':instruction_check(root),'docs_check':docs_check(root),'schema':schema_status(root),'index':index_status(root)}}
    if task_id:
        with connect(root) as c:r=c.execute('SELECT status,approved,risk FROM tasks WHERE task_id=?',(task_id,)).fetchone();used=c.execute('SELECT COUNT(*) n FROM tool_calls WHERE task_id=?',(task_id,)).fetchone()['n']
        out['task']={'task_id':task_id,'status':r['status'] if r else 'unknown','approved':bool(r['approved']) if r else False,'risk':r['risk'] if r else None,'tool_calls_used':used,'egress_events':len(egress_report(root,task_id))}
    return out
