"""
File: .agents/agentos/context_runtime.py

Purpose:
    Build deterministic, provenance-aware task context packages.

Responsibilities:
    - Select task-relevant policy, documentation, symbols, tests, and memory.
    - Enforce bounded context budgets without external LLM calls.
    - Detect stale packages when source content changes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .db import connect


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_bounded(path: Path, max_lines: int) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"path": path.as_posix(), "line_count": len(lines), "excerpt": "\n".join(lines[:max_lines])}


def _task(root: Path, task_id: str) -> dict[str, Any]:
    with connect(root) as c:
        row = c.execute("SELECT id,request,approved_scope,task_state FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise RuntimeError(f"task not found: {task_id}")
    out = dict(row); out["approved_scope"] = json.loads(out["approved_scope"] or "[]")
    return out


def build_context_pack(root: Path, task_id: str, max_lines: int = 500) -> dict[str, Any]:
    """Build and persist a deterministic context package for one task.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        max_lines: Maximum total excerpt lines.

    Returns:
        Context manifest with provenance hashes and selected content.
    """
    root = root.resolve(); task = _task(root, task_id)
    candidates = [root / "AGENTS.md", root / ".agents/config/governance.json", root / "huong_dan.md"]
    for scope in task["approved_scope"]:
        p = (root / scope).resolve()
        try: p.relative_to(root)
        except ValueError: continue
        if p.is_file(): candidates.append(p)
        elif p.is_dir(): candidates.extend(sorted(p.rglob("*.py"))[:40])
    seen: set[str] = set(); sources=[]; remaining=max_lines
    for path in candidates:
        if not path.is_file(): continue
        rel=path.relative_to(root).as_posix()
        if rel in seen: continue
        seen.add(rel); take=max(1, min(remaining, 120)); data=_read_bounded(path,take); data["path"]=rel; data["content_hash"]=_hash(path); sources.append(data); remaining-=len(data["excerpt"].splitlines())
        if remaining <= 0: break
    with connect(root) as c:
        symbols=[dict(r) for r in c.execute("SELECT path,qualname,kind,line_start,line_end FROM symbol_index WHERE " + " OR ".join(["path LIKE ?"]*len(task["approved_scope"])) + " ORDER BY path,qualname LIMIT 100", tuple(f"{s.rstrip('/')}%" for s in task["approved_scope"])).fetchall()] if task["approved_scope"] else []
        findings=[dict(r) for r in c.execute("SELECT kind,path,symbol,message,occurrences,last_seen_at FROM project_findings WHERE status='active' ORDER BY occurrences DESC,last_seen_at DESC LIMIT 50").fetchall()]
    manifest={"task_id":task_id,"request":task["request"],"approved_scope":task["approved_scope"],"max_lines":max_lines,"sources":sources,"symbols":symbols,"project_findings":findings}
    digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest(); manifest["content_hash"]=digest
    with connect(root) as c:
        rev=c.execute("SELECT COALESCE(MAX(revision),0)+1 AS n FROM context_packs WHERE task_id=?",(task_id,)).fetchone()["n"]
        c.execute("UPDATE context_packs SET status='superseded' WHERE task_id=? AND status='active'",(task_id,))
        c.execute("INSERT INTO context_packs(task_id,revision,content_hash,manifest_json,status) VALUES(?,?,?,?, 'active')",(task_id,rev,digest,json.dumps(manifest,sort_keys=True)))
    return {**manifest,"revision":rev,"status":"active"}


def context_status(root: Path, task_id: str) -> dict[str, Any]:
    """Return active context package and stale-source diagnostics."""
    with connect(root) as c:
        row=c.execute("SELECT revision,content_hash,manifest_json,status,created_at FROM context_packs WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1",(task_id,)).fetchone()
    if not row: return {"exists":False,"stale":True,"reason":"not_built"}
    manifest=json.loads(row["manifest_json"]); stale=[]
    for src in manifest.get("sources",[]):
        path=root.resolve()/src["path"]
        if not path.is_file() or _hash(path)!=src["content_hash"]: stale.append(src["path"])
    return {"exists":True,"revision":row["revision"],"content_hash":row["content_hash"],"status":row["status"],"stale":bool(stale),"stale_sources":stale,"manifest":manifest}


def context_explain(root: Path, task_id: str) -> dict[str, Any]:
    """Explain why each context source was selected."""
    status=context_status(root,task_id)
    if not status.get("exists"): return status
    scope=status["manifest"].get("approved_scope",[]); explanations=[]
    for src in status["manifest"].get("sources",[]):
        p=src["path"]
        reason="mandatory_governance" if p in {"AGENTS.md",".agents/config/governance.json","huong_dan.md"} else "approved_scope" if any(p==s or p.startswith(s.rstrip('/')+'/') for s in scope) else "related_source"
        explanations.append({"path":p,"reason":reason,"content_hash":src["content_hash"]})
    return {"task_id":task_id,"revision":status["revision"],"stale":status["stale"],"sources":explanations}
