"""
File: .agents/agentos/memory.py

Purpose:
    Maintain provenance-aware project memory and recurring findings.

Responsibilities:
    - Upsert recurring findings instead of duplicating observations.
    - Store semantic, episodic, procedural, and evidence memories.
    - Query only active, non-superseded knowledge by default.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .db import connect

MEMORY_KINDS={"semantic","episodic","procedural","evidence"}


def record_finding(root: Path, kind: str, message: str, path: str | None=None, symbol: str | None=None, task_id: str | None=None) -> dict[str, Any]:
    """Insert or increment a recurring project finding."""
    key=hashlib.sha256(f"{kind}\0{path or ''}\0{symbol or ''}\0{message}".encode()).hexdigest()
    with connect(root) as c:
        row=c.execute("SELECT id,occurrences FROM project_findings WHERE finding_key=?",(key,)).fetchone()
        if row:
            c.execute("UPDATE project_findings SET occurrences=occurrences+1,last_seen_at=CURRENT_TIMESTAMP,status='active' WHERE id=?",(row["id"],)); fid=row["id"]; count=row["occurrences"]+1
        else:
            cur=c.execute("INSERT INTO project_findings(finding_key,kind,path,symbol,message,first_seen_task_id) VALUES(?,?,?,?,?,?)",(key,kind,path,symbol,message,task_id)); fid=cur.lastrowid; count=1
    return {"finding_id":fid,"occurrences":count,"finding_key":key}


def remember(root: Path, kind: str, statement: str, source_path: str | None=None, task_id: str | None=None, confidence: float=1.0, evidence_hash: str | None=None) -> dict[str, Any]:
    """Store a provenance-aware project memory record."""
    if kind not in MEMORY_KINDS: raise ValueError(f"invalid memory kind: {kind}")
    if not 0 <= confidence <= 1: raise ValueError("confidence must be between 0 and 1")
    source_hash=None
    if source_path:
        p=(root.resolve()/source_path).resolve(); p.relative_to(root.resolve())
        if not p.is_file(): raise FileNotFoundError(source_path)
        source_hash=hashlib.sha256(p.read_bytes()).hexdigest()
    with connect(root) as c:
        cur=c.execute("INSERT INTO project_memory(kind,statement,source_path,source_hash,first_seen_task_id,last_confirmed_task_id,confidence,evidence_hash,status) VALUES(?,?,?,?,?,?,?,?, 'active')",(kind,statement,source_path,source_hash,task_id,task_id,confidence,evidence_hash))
    return {"memory_id":cur.lastrowid,"kind":kind,"status":"active","source_hash":source_hash}


def query_memory(root: Path, query: str, kind: str | None=None, limit: int=20, include_stale: bool=False) -> list[dict[str, Any]]:
    """Query project memory and recurring findings."""
    clauses=["statement LIKE ?"]; params:[Any]=[f"%{query}%"]
    if kind: clauses.append("kind=?"); params.append(kind)
    if not include_stale: clauses.append("status='active'")
    with connect(root) as c:
        rows=c.execute("SELECT id,kind,statement,source_path,source_hash,confidence,status,first_seen_task_id,last_confirmed_task_id,evidence_hash,created_at FROM project_memory WHERE "+" AND ".join(clauses)+" ORDER BY confidence DESC,id DESC LIMIT ?",(*params,limit)).fetchall()
    return [dict(r) for r in rows]


def validate_memory(root: Path) -> dict[str, Any]:
    """Mark source-backed memory stale when its source content changes."""
    stale=[]
    with connect(root) as c:
        rows=c.execute("SELECT id,source_path,source_hash FROM project_memory WHERE status='active' AND source_path IS NOT NULL").fetchall()
        for row in rows:
            p=root.resolve()/row["source_path"]; current=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            if current!=row["source_hash"]:
                c.execute("UPDATE project_memory SET status='stale' WHERE id=?",(row["id"],)); stale.append(row["id"])
    return {"ok":not stale,"stale_memory_ids":stale,"checked":len(rows)}
