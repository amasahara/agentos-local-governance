"""
File: .agents/agentos/cache.py

Purpose:
    Cache bounded local file-read evidence.

Responsibilities:
    - Reuse unchanged file reads.
    - Invalidate entries when file metadata changes.
    - Normalize whole-file and bounded range keys.
"""
import hashlib
from pathlib import Path
from typing import Any
from .db import connect

def cache_lookup(root:Path,task_id:str,path:str,start:int|None=None,end:int|None=None)->dict[str,Any]:
    """Look up a fresh cached file-read result.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        path: Project-relative file path.
        start: Optional first line.
        end: Optional last line.

    Returns:
        Cache hit or miss result.
    """
    p=(root/path).resolve()
    if not p.is_file():return {'status':'miss','reason':'file_missing'}
    s=p.stat(); key=_key(start,end)
    with connect(root) as c:
        r=c.execute('SELECT mtime_ns,size,content_hash,summary FROM file_read_cache WHERE task_id=? AND path=? AND range_key=?',(task_id,str(p),key)).fetchone()
        if r and r['mtime_ns']==s.st_mtime_ns and r['size']==s.st_size:return {'status':'hit','summary':r['summary'],'content_hash':r['content_hash']}
    return {'status':'miss','reason':'not_cached_or_stale'}
def cache_store(root:Path,task_id:str,path:str,summary:str,start:int|None=None,end:int|None=None)->dict[str,Any]:
    """Store a bounded file-read summary.

    Args:
        root: Absolute project root.
        task_id: Stable task identifier.
        path: Project-relative file path.
        summary: Bounded result summary.
        start: Optional first line.
        end: Optional last line.

    Returns:
        Stored range key and content hash.

    Raises:
        FileNotFoundError: The requested file does not exist.
    """
    p=(root/path).resolve(); s=p.stat(); digest=hashlib.sha256(p.read_bytes()).hexdigest(); key=_key(start,end)
    with connect(root) as c:c.execute('INSERT INTO file_read_cache(task_id,path,range_key,mtime_ns,size,content_hash,summary) VALUES(?,?,?,?,?,?,?) ON CONFLICT(task_id,path,range_key) DO UPDATE SET mtime_ns=excluded.mtime_ns,size=excluded.size,content_hash=excluded.content_hash,summary=excluded.summary,accessed_at=CURRENT_TIMESTAMP',(task_id,str(p),key,s.st_mtime_ns,s.st_size,digest,summary[:4000]))
    return {'stored':True,'range_key':key,'content_hash':digest}
def _key(start,end):return 'all' if start is None and end is None else f"{'' if start is None else start}:{'' if end is None else end}"
