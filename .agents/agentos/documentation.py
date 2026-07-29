"""
File: .agents/agentos/documentation.py

Purpose:
    Enforce file-header and symbol-contract documentation for Python source.

Responsibilities:
    - Require the project-relative path once in the module header.
    - Require module purpose and responsibilities in the file header.
    - Require public class and function contracts.
    - Compare documented inputs and outputs with actual signatures.
"""
import ast,re
from pathlib import Path
from typing import Any
from .models import DocumentationFinding

def documentation_scan(root:Path,scope:str='src')->dict[str,Any]:
    """Scan a source scope for documentation violations.

    Args:
        root: Absolute project root.
        scope: Project-relative file or directory.

    Returns:
        Scan status, counts, unsupported files, and findings.
    """
    target=(root/scope).resolve();paths=[target] if target.is_file() else sorted(target.rglob('*')) if target.exists() else [];findings=[];unsupported=[];scanned=0
    for p in paths:
        if not p.is_file() or any(x in {'vendor','node_modules','.git','__pycache__','generated'} for x in p.parts):continue
        if p.suffix=='.py':findings.extend(_scan(root,p));scanned+=1
        elif p.suffix in {'.js','.jsx','.ts','.tsx','.java','.cs','.go','.rs'}:unsupported.append(str(p.relative_to(root)))
    return {'status':'failed' if any(x.severity=='error' for x in findings) else 'passed','files_scanned':scanned,'unsupported_files':unsupported,'findings':[x.__dict__ for x in findings]}
def _scan(root,p):
    rel=str(p.relative_to(root)).replace('\\','/')
    try:tree=ast.parse(p.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,SyntaxError) as e:return [DocumentationFinding(rel,None,1,'error','python_parse_failed',str(e))]
    out=[];doc=ast.get_docstring(tree,clean=False) or ''
    if not doc:out.append(DocumentationFinding(rel,None,1,'error','missing_file_header','Missing module docstring header.'))
    else:
        for f in ('File:','Purpose:','Responsibilities:'):
            if f not in doc:out.append(DocumentationFinding(rel,None,1,'error','missing_'+f[:-1].lower(),f'Missing {f} in module header.'))
        m=re.search(r'(?m)^\s*File:\s*(.+?)\s*$',doc)
        if m and m.group(1).strip().replace('\\','/')!=rel:out.append(DocumentationFinding(rel,None,1,'error','stale_file_path','Header path does not match actual path.'))
    for node,qn in _symbols(tree):
        if _required(node):out.extend(_contract(rel,node,qn))
    return out
def _symbols(tree):
    def visit(node,parents):
        for c in ast.iter_child_nodes(node):
            if isinstance(c,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                q='.'.join([*parents,c.name]);yield c,q;yield from visit(c,[*parents,c.name])
            else:yield from visit(c,parents)
    return visit(tree,[])
def _required(node):return not getattr(node,'name','').startswith('_') or len(getattr(node,'body',[]))>2
def _contract(path,node,qn):
    line=getattr(node,'lineno',1);doc=ast.get_docstring(node,clean=False) or ''
    if not doc:return [DocumentationFinding(path,qn,line,'error','missing_symbol_docstring','Missing symbol docstring.')]
    out=[];first=next((x.strip() for x in doc.splitlines() if x.strip()),'')
    if len(first.split())<3:out.append(DocumentationFinding(path,qn,line,'error','missing_symbol_purpose','Docstring must explain symbol purpose.'))
    if isinstance(node,ast.ClassDef):return out
    actual={a.arg for a in [*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs] if a.arg not in {'self','cls'}};documented=set(_args(doc))
    for a in sorted(actual-documented):out.append(DocumentationFinding(path,qn,line,'error','missing_input_documentation',f'Missing input documentation for {a}.'))
    for a in sorted(documented-actual):out.append(DocumentationFinding(path,qn,line,'warning','stale_input_documentation',f'Documented input {a} is not in signature.'))
    if _returns(node) and not re.search(r'(?m)^\s*Returns:\s*$',doc):out.append(DocumentationFinding(path,qn,line,'error','missing_output_documentation','Function returns data but has no Returns contract.'))
    return out
def _args(doc):
    m=re.search(r'(?ms)^\s*Args:\s*$\n(.*?)(?=^\s*(?:Returns|Raises|Side Effects):\s*$|\Z)',doc)
    return [] if not m else re.findall(r'(?m)^\s{4,}([A-Za-z_][A-Za-z0-9_]*)(?:\s*\([^)]*\))?:\s*',m.group(1))
def _returns(node):
    if node.returns is not None:return not (isinstance(node.returns,ast.Constant) and node.returns.value is None)
    return any(isinstance(x,ast.Return) and x.value is not None for x in ast.walk(node))
