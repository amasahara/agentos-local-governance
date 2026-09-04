"""
File: .agents/agentos/skills.py

Purpose:
    Promote verified procedural memory into versioned, human-approved reusable skills.

Responsibilities:
    - Create non-active candidate skill artifacts from valid procedural memory.
    - Require human approval and signed audit before graduation.
    - Version, supersede, revoke, list, and match reusable skills.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .db import connect
from .external_audit import append_signed_event
from .policy import load_policy
from .skill_contract_v2 import default_contract, initialize_skill_contract_in_connection, validate_skill_contract


def _slug(text: str) -> str:
    value=re.sub(r"[^a-z0-9]+","-",text.lower()).strip("-")
    return value[:64] or "procedural-skill"


def _human(identity: str) -> bool:
    value=identity.strip().lower()
    return bool(value) and value not in {"agent","llm","automation","system"} and not value.startswith("agent-")


def _policy(root: Path) -> dict[str, Any]:
    return load_policy(root).get("knowledge_runtime",{}).get("skill_policy",{})


def promote_skill_candidate(root: Path, memory_id: int, promoted_by: str) -> dict[str, Any]:
    """Create a candidate skill from active, provenance-backed procedural memory."""
    cfg=_policy(root); threshold=float(cfg.get("candidate_confidence_threshold",0.8))
    with connect(root) as c:
        memory=c.execute("SELECT * FROM project_memory WHERE id=?",(memory_id,)).fetchone()
        if not memory: raise RuntimeError("memory not found")
        memory=dict(memory)
        if memory["kind"]!="procedural" or memory["status"]!="active": raise RuntimeError("only active procedural memory can be promoted")
        if float(memory["confidence"]) < threshold: raise RuntimeError("memory confidence below promotion threshold")
        if not (memory.get("evidence_hash") or memory.get("first_seen_task_id") or memory.get("source_hash")):
            raise RuntimeError("procedural memory lacks provenance/evidence")
        if memory.get("source_path"):
            source=root/memory["source_path"]
            current=hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
            if current != memory.get("source_hash"): raise RuntimeError("procedural memory source is stale")
        title=memory["statement"].splitlines()[0][:120]
        key=_slug(title)
        row=c.execute("SELECT COALESCE(MAX(version),0) v FROM promoted_skills WHERE skill_key=?",(key,)).fetchone()
        version=int(row["v"])+1
        contract=default_contract(key,version)
        body=(f"---\nid: {key}\nversion: {version}\ntitle: {json.dumps(title,ensure_ascii=False)}\n"
              f"status: candidate\ncontract_version: 2\nsource_memory_ids: [{memory_id}]\nconfidence: {memory['confidence']}\n"
              f"evidence_hashes: {json.dumps([memory.get('evidence_hash')] if memory.get('evidence_hash') else [])}\n---\n\n"
              f"## Procedure\n\n{memory['statement']}\n\n"
              "## Governed Skill Contract v2\n\n```json\n"
              + json.dumps(contract,ensure_ascii=False,sort_keys=True,indent=2) + "\n```\n")
        payload=body.encode("utf-8")
        digest=hashlib.sha256(payload).hexdigest()
        rel=Path('.agents/runtime/skills/candidates')/f"{key}-v{version}.md"
        target=root/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(payload)
        try:
            cur=c.execute("INSERT INTO promoted_skills(skill_key,version,memory_id,title,description,candidate_path,status,content_hash,promoted_by) VALUES(?,?,?,?,?,?, 'candidate',?,?)",(key,version,memory_id,title,memory["statement"],rel.as_posix(),digest,promoted_by))
            sid=int(cur.lastrowid)
            contract_state=initialize_skill_contract_in_connection(c,sid,promoted_by)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return {"ok":True,"skill_id":sid,"skill_key":key,"version":version,"status":"candidate","path":rel.as_posix(),"content_hash":digest,"contract_version":2,"contract_hash":contract_state["contract_hash"],"contract_status":"draft"}


def graduate_skill(root: Path, skill_id: int, approved_by: str, note: str) -> dict[str, Any]:
    """Graduate a candidate skill after explicit human approval."""
    if not _human(approved_by): raise RuntimeError("skill graduation requires a human identity")
    if not note.strip(): raise RuntimeError("approval note is required")
    from .closed_loop_improvement import validate_closed_loop_skill_candidate
    closed_loop_validation=validate_closed_loop_skill_candidate(root,skill_id)
    if closed_loop_validation.get("applies") and closed_loop_validation.get("ok") is not True:
        raise RuntimeError("closed_loop_skill_candidate_not_current")
    contract_validation=validate_skill_contract(root,skill_id)
    if contract_validation.get("ok") is not True:
        raise RuntimeError(f"skill_contract_v2_not_ready:{contract_validation.get('status')}")
    with connect(root) as c:
        row=c.execute("SELECT * FROM promoted_skills WHERE id=?",(skill_id,)).fetchone()
        if not row: raise RuntimeError("skill not found")
        row=dict(row)
        if row["status"]!="candidate": raise RuntimeError("only candidate skills can graduate")
        source=root/row["candidate_path"]
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=row["content_hash"]: raise RuntimeError("candidate artifact missing or changed")
        duplicate=c.execute("SELECT id FROM promoted_skills WHERE skill_key=? AND status='graduated'",(row["skill_key"],)).fetchone()
        if duplicate: raise RuntimeError("an active graduated skill with the same key already exists; supersede it instead")
        text=source.read_text(encoding='utf-8').replace('status: candidate','status: graduated',1)
        # Keep graduated skill artifacts byte-deterministic across platforms.
        payload=text.encode('utf-8')
        digest=hashlib.sha256(payload).hexdigest()
        rel=Path('.agents/skills')/f"{row['skill_key']}-v{row['version']}.md"
        target=root/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(payload)
        event=append_signed_event(root,'skill.graduated',{"skill_id":skill_id,"skill_key":row["skill_key"],"version":row["version"],"content_hash":digest,"contract_version":2,"contract_hash":row.get("contract_hash"),"architecture_baseline_hash":row.get("architecture_baseline_hash"),"approved_by":approved_by,"note":note},None,None)
        c.execute("UPDATE promoted_skills SET status='graduated',graduated_path=?,content_hash=?,approved_by=?,approval_note=?,external_event_hash=?,graduated_at=CURRENT_TIMESTAMP WHERE id=?",(rel.as_posix(),digest,approved_by,note,event["event_hash"],skill_id))
    return {"ok":True,"skill_id":skill_id,"status":"graduated","path":rel.as_posix(),"external_event_hash":event["event_hash"]}


def revoke_skill(root: Path, skill_id: int, reason: str, revoked_by: str) -> dict[str, Any]:
    """Revoke a candidate or graduated skill and record signed provenance."""
    if not _human(revoked_by): raise RuntimeError("skill revocation requires a human identity")
    if not reason.strip(): raise RuntimeError("revocation reason is required")
    with connect(root) as c:
        row=c.execute("SELECT * FROM promoted_skills WHERE id=?",(skill_id,)).fetchone()
        if not row: raise RuntimeError("skill not found")
        row=dict(row)
        if row["status"] in {"revoked","archived"}: raise RuntimeError("skill is already inactive")
        event=append_signed_event(root,'skill.revoked',{"skill_id":skill_id,"reason":reason,"revoked_by":revoked_by},None,None)
        c.execute("UPDATE promoted_skills SET status='revoked',revoke_reason=?,revoked_at=CURRENT_TIMESTAMP,external_event_hash=? WHERE id=?",(reason,event["event_hash"],skill_id))
    return {"ok":True,"skill_id":skill_id,"status":"revoked","external_event_hash":event["event_hash"]}


def list_skills(root: Path, status: str | None=None) -> list[dict[str, Any]]:
    """List skills with version, lifecycle, and provenance metadata."""
    sql="SELECT * FROM promoted_skills"; params=()
    if status: sql+=" WHERE status=?"; params=(status,)
    sql+=" ORDER BY skill_key,version DESC"
    with connect(root) as c: rows=c.execute(sql,params).fetchall()
    return [dict(r) for r in rows]


def match_skills(root: Path, query: str, limit: int=10) -> list[dict[str, Any]]:
    """Match active graduated skills using deterministic local lexical scoring."""
    terms={x for x in re.findall(r"[a-z0-9_]{2,}",query.lower())}
    results=[]
    for row in list_skills(root,'graduated'):
        hay=f"{row['skill_key']} {row['title']} {row['description']}".lower()
        matched=sorted(t for t in terms if t in hay)
        if matched or not terms:
            results.append({**row,"score":len(matched),"match_reason":"lexical_overlap","matched_terms":matched})
    return sorted(results,key=lambda x:(-x['score'],-x['version'],x['skill_key']))[:limit]
