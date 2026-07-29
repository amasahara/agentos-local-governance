"""
File: .agents/agentos/indexing.py

Purpose:
    Build and query an incremental Python symbol index.

Responsibilities:
    - Index functions, async functions, classes, and methods.
    - Preserve qualified names and line ranges.
    - Skip unchanged files and prune deleted files.
    - Detect duplicate implementations by AST fingerprint.
"""
import ast,hashlib
from pathlib import Path
from typing import Any
from .db import connect

def index_build(root:Path,scope:str='src')->dict[str,Any]:
    """Incrementally update the Python symbol index.

    Args:
        root: Absolute project root.
        scope: Project-relative source directory.

    Returns:
        Scan and generation counts.
    """
    base=(root/scope).resolve()
    if not base.exists():return {'scanned_files':0,'updated_files':0,'skipped_files':0,'deleted_files':0,'indexed_symbols':0,'generation':0}
    files=sorted(base.rglob('*.py')); current={str(p.relative_to(root)) for p in files}; updated=skipped=symbols=0
    with connect(root) as c:
        row=c.execute('SELECT generation FROM index_metadata WHERE scope=?',(scope,)).fetchone(); generation=int(row['generation'])+1 if row else 1
        indexed={r['path'] for r in c.execute('SELECT DISTINCT path FROM symbol_index').fetchall()}; stale=indexed-current
        for rel in stale:c.execute('DELETE FROM symbol_index WHERE path=?',(rel,))
        for p in files:
            rel=str(p.relative_to(root)); s=p.stat(); old=c.execute('SELECT mtime_ns,size FROM symbol_index WHERE path=? LIMIT 1',(rel,)).fetchone()
            if old and old['mtime_ns']==s.st_mtime_ns and old['size']==s.st_size:skipped+=1;continue
            c.execute('DELETE FROM symbol_index WHERE path=?',(rel,))
            for rec in _parse(p):
                c.execute('INSERT INTO symbol_index(path,name,qualname,kind,parent_qualname,line_start,line_end,signature,fingerprint,mtime_ns,size,generation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(rel,rec['name'],rec['qualname'],rec['kind'],rec['parent'],rec['line_start'],rec['line_end'],rec['signature'],rec['fingerprint'],s.st_mtime_ns,s.st_size,generation));symbols+=1
            updated+=1
        c.execute('INSERT INTO index_metadata(scope,generation) VALUES(?,?) ON CONFLICT(scope) DO UPDATE SET generation=excluded.generation,updated_at=CURRENT_TIMESTAMP',(scope,generation))
    return {'scanned_files':len(files),'updated_files':updated,'skipped_files':skipped,'deleted_files':len(stale),'indexed_symbols':symbols,'generation':generation}
def index_query(root:Path,query:str,limit:int=20)->list[dict[str,Any]]:
    """Query symbols by name and qualified name.

    Args:
        root: Absolute project root.
        query: Search terms.
        limit: Maximum result count.

    Returns:
        Ranked symbol dictionaries.
    """
    terms=[x.lower() for x in query.replace('_',' ').split() if x]
    with connect(root) as c:rows=c.execute('SELECT path,name,qualname,kind,line_start,line_end,signature FROM symbol_index').fetchall()
    out=[]
    for r in rows:
        hay=f"{r['name']} {r['qualname']}".lower().replace('_',' '); score=sum(t in hay for t in terms)
        if score:item=dict(r);item['score']=score;out.append(item)
    return sorted(out,key=lambda x:(-x['score'],x['path'],x['line_start']))[:limit]
def duplicate_report(root:Path)->list[dict[str,Any]]:
    """Return indexed duplicate implementation groups.

    Args:
        root: Absolute project root.

    Returns:
        Fingerprint groups with symbol locations.
    """
    with connect(root) as c:
        groups=c.execute("SELECT fingerprint,COUNT(*) n FROM symbol_index WHERE kind IN ('function','async_function','method') GROUP BY fingerprint HAVING COUNT(*)>1").fetchall();out=[]
        for g in groups:out.append({'fingerprint':g['fingerprint'],'symbols':[dict(r) for r in c.execute('SELECT path,qualname,line_start FROM symbol_index WHERE fingerprint=? ORDER BY path,line_start',(g['fingerprint'],)).fetchall()]})
    return out
def index_status(root:Path,scope:str='src')->dict[str,Any]:
    """Return symbol-index status.

    Args:
        root: Absolute project root.
        scope: Project-relative source scope.

    Returns:
        Generation and indexed counts.
    """
    with connect(root) as c:
        m=c.execute('SELECT generation,updated_at FROM index_metadata WHERE scope=?',(scope,)).fetchone();symbols=c.execute('SELECT COUNT(*) n FROM symbol_index').fetchone()['n'];files=c.execute('SELECT COUNT(DISTINCT path) n FROM symbol_index').fetchone()['n']
    return {'scope':scope,'generation':m['generation'] if m else 0,'updated_at':m['updated_at'] if m else None,'symbol_count':symbols,'file_count':files}
def _parse(path):
    try:tree=ast.parse(path.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,SyntaxError):return []
    out=[]
    def visit(node,parents):
        for child in ast.iter_child_nodes(node):
            if isinstance(child,ast.ClassDef):out.append(_rec(child,parents,'class'));visit(child,[*parents,child.name])
            elif isinstance(child,ast.AsyncFunctionDef):out.append(_rec(child,parents,'method' if parents else 'async_function'));visit(child,[*parents,child.name])
            elif isinstance(child,ast.FunctionDef):out.append(_rec(child,parents,'method' if parents else 'function'));visit(child,[*parents,child.name])
            else:visit(child,parents)
    visit(tree,[]);return out
def _rec(node,parents,kind):
    name=node.name;sig=f"{name}({', '.join(a.arg for a in node.args.args)})" if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) else None
    return {'name':name,'qualname':'.'.join([*parents,name]),'kind':kind,'parent':'.'.join(parents) or None,'line_start':node.lineno,'line_end':getattr(node,'end_lineno',None),'signature':sig,'fingerprint':hashlib.sha256(ast.dump(node,annotate_fields=False,include_attributes=False).encode()).hexdigest()}
