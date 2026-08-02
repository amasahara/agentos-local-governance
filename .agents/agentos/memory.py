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
import json
from datetime import datetime, timezone, timedelta
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


def remember(root: Path, kind: str, statement: str, source_path: str | None=None, task_id: str | None=None, confidence: float=1.0, evidence_hash: str | None=None, owner_scope: str="project", sensitivity: str="normal", consent_source: str | None=None, expires_at: str | None=None) -> dict[str, Any]:
    """Store a provenance-aware project memory record."""
    if kind not in MEMORY_KINDS: raise ValueError(f"invalid memory kind: {kind}")
    if not 0 <= confidence <= 1: raise ValueError("confidence must be between 0 and 1")
    source_hash=None
    if source_path:
        p=(root.resolve()/source_path).resolve(); p.relative_to(root.resolve())
        if not p.is_file(): raise FileNotFoundError(source_path)
        source_hash=hashlib.sha256(p.read_bytes()).hexdigest()
    with connect(root) as c:
        if owner_scope.startswith("user:") and not consent_source: raise ValueError("explicit consent_source required for user memory")
        cur=c.execute("INSERT INTO project_memory(kind,statement,source_path,source_hash,first_seen_task_id,last_confirmed_task_id,confidence,evidence_hash,status,owner_scope,sensitivity,consent_source,expires_at) VALUES(?,?,?,?,?,?,?,?, 'active',?,?,?,?)",(kind,statement,source_path,source_hash,task_id,task_id,confidence,evidence_hash,owner_scope,sensitivity,consent_source,expires_at))
    return {"memory_id":cur.lastrowid,"kind":kind,"status":"active","source_hash":source_hash}


def query_memory(root: Path, query: str, kind: str | None=None, limit: int=20, include_stale: bool=False, identity: str | None=None) -> list[dict[str, Any]]:
    """Query project memory and recurring findings."""
    clauses=["statement LIKE ?"]; params:[Any]=[f"%{query}%"]
    if kind: clauses.append("kind=?"); params.append(kind)
    if not include_stale: clauses.append("status='active'")
    if identity: clauses.append("owner_scope IN ('project',?)"); params.append(f"user:{identity}")
    else: clauses.append("owner_scope='project'")
    with connect(root) as c:
        rows=c.execute("SELECT id,kind,statement,source_path,source_hash,confidence,status,first_seen_task_id,last_confirmed_task_id,evidence_hash,owner_scope,sensitivity,consent_source,expires_at,created_at FROM project_memory WHERE "+" AND ".join(clauses)+" ORDER BY confidence DESC,id DESC LIMIT ?",(*params,limit)).fetchall()
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


def decay_user_memory(root: Path, ttl_days: int=180) -> dict[str,Any]:
    """Mark expired or unconfirmed user memories stale without background jobs."""
    cutoff=(datetime.now(timezone.utc)-timedelta(days=ttl_days)).isoformat(); stale=[]
    with connect(root) as c:
        rows=c.execute("SELECT id,expires_at,created_at FROM project_memory WHERE owner_scope LIKE 'user:%' AND status='active'").fetchall()
        for r in rows:
            if (r["expires_at"] and r["expires_at"]<datetime.now(timezone.utc).isoformat()) or r["created_at"]<cutoff:
                c.execute("UPDATE project_memory SET status='stale' WHERE id=?",(r["id"],)); stale.append(r["id"])
    return {"stale_memory_ids":stale,"ttl_days":ttl_days}

def forget_identity(root: Path, identity: str) -> dict[str,Any]:
    """Revoke user-scoped memories and delete derived embeddings while preserving tombstones."""
    scope=f"user:{identity}"
    with connect(root) as c:
        ids=[str(r["id"]) for r in c.execute("SELECT id FROM project_memory WHERE owner_scope=?",(scope,))]
        c.execute("UPDATE project_memory SET statement='[forgotten]',status='revoked',revoked_at=CURRENT_TIMESTAMP,source_path=NULL,source_hash=NULL,evidence_hash=NULL WHERE owner_scope=?",(scope,))
        for mid in ids: c.execute("DELETE FROM knowledge_embeddings WHERE source_kind='memory' AND source_id=?",(mid,))
    return {"identity":identity,"revoked_count":len(ids),"embeddings_deleted":len(ids)}
