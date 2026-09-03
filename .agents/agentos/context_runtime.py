"""
File: .agents/agentos/context_runtime.py

Purpose:
    Build deterministic, transparent, provenance-aware task context packages.

Responsibilities:
    - Rank candidate files and symbols using local structural evidence.
    - Compact source files by symbol windows without calling an LLM.
    - Report every omitted file and symbol with a reason.
    - Detect stale packages when source content changes.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .db import connect
from .policy import load_policy
from .retrieval import search_knowledge

MANDATORY = {"AGENTS.md", ".agents/config/governance.json", "huong_dan.md"}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_bounded(path: Path, max_lines: int) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    excerpt = "\n".join(lines[:max_lines])
    return {"path": path.as_posix(), "line_count": len(excerpt.splitlines()), "source_line_count": len(lines), "approx_tokens": max(1, len(excerpt) // 4), "excerpt": excerpt}


def _task(root: Path, task_id: str) -> dict[str, Any]:
    with connect(root) as c:
        row = c.execute("SELECT id,request,approved_scope,task_state FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise RuntimeError(f"task not found: {task_id}")
    out = dict(row)
    out["approved_scope"] = json.loads(out["approved_scope"] or "[]")
    return out


def _terms(text: str) -> set[str]:
    return {x.lower() for x in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")}


def _candidate_files(root: Path, scopes: list[str]) -> list[Path]:
    result = [root / x for x in sorted(MANDATORY)]
    for scope in scopes:
        p = (root / scope).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            continue
        if p.is_file():
            result.append(p)
        elif p.is_dir():
            result.extend(sorted(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in {".py", ".md", ".json", ".yaml", ".yml", ".toml"}))
    seen = set(); out=[]
    for p in result:
        if p.is_file():
            rel=p.relative_to(root).as_posix()
            if rel not in seen: seen.add(rel); out.append(p)
    return out


def _symbols_for_path(root: Path, rel: str) -> list[dict[str, Any]]:
    with connect(root) as c:
        return [dict(r) for r in c.execute("SELECT path,qualname,kind,line_start,line_end FROM symbol_index WHERE path=? ORDER BY line_start,line_end,qualname", (rel,)).fetchall()]


def _score_file(rel: str, request_terms: set[str], symbols: list[dict[str, Any]]) -> tuple[float, list[str]]:
    if rel in MANDATORY:
        return 1000.0, ["mandatory_governance"]
    reasons=[]; score=10.0
    rel_terms=_terms(rel)
    overlap=request_terms & rel_terms
    if overlap: score += 8*len(overlap); reasons.append("request_path_overlap")
    matched=[s["qualname"] for s in symbols if request_terms & _terms(s["qualname"])]
    if matched: score += 15*len(matched); reasons.append("requested_symbol_match")
    if "/test" in rel.lower() or rel.lower().startswith("tests/"): score += 3; reasons.append("related_test_candidate")
    return score, reasons or ["approved_scope"]


def _symbol_window_excerpt(path: Path, symbols: list[dict[str, Any]], request_terms: set[str], max_lines: int) -> dict[str, Any]:
    lines=path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not symbols:
        out=_read_bounded(path,max_lines); out.update({"included_symbols":[],"omitted_symbols":[],"compaction":"flat_fallback"}); return out
    ranked=[]
    for s in symbols:
        overlap=len(request_terms & _terms(s["qualname"]))
        ranked.append((overlap, -(s["line_end"]-s["line_start"]), s))
    ranked.sort(key=lambda x:(-x[0],-x[1],x[2]["line_start"],x[2]["qualname"]))
    selected=[]; used=set(); included=[]; omitted=[]
    # Preserve module-level lines not inside symbols where budget permits.
    covered=set()
    for s in symbols:
        covered.update(range(max(1,s["line_start"]), min(len(lines),s["line_end"])+1))
    module_lines=[i for i in range(1,len(lines)+1) if i not in covered]
    for i in module_lines:
        if len(selected)>=max_lines: break
        selected.append((i,lines[i-1])); used.add(i)
    for _,__,s in ranked:
        rng=list(range(max(1,s["line_start"]), min(len(lines),s["line_end"])+1))
        new=[i for i in rng if i not in used]
        if len(selected)+len(new) <= max_lines:
            for i in new: selected.append((i,lines[i-1])); used.add(i)
            included.append(s["qualname"])
        else:
            omitted.append(s["qualname"])
    selected.sort(key=lambda x:x[0])
    excerpt="\n".join(text for _,text in selected)
    return {"path":path.as_posix(),"line_count":len(selected),"source_line_count":len(lines),"approx_tokens":max(1,len(excerpt)//4),"excerpt":excerpt,"included_symbols":included,"omitted_symbols":omitted,"compaction":"symbol_window"}


def _knowledge_candidates(root: Path, request: str, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], bool, str | None]:
    """Return provenance-verified knowledge candidates using lexical-first semantic fallback."""
    try:
        lexical=search_knowledge(root,request,["skill","memory","finding"],12,"lexical_structured")
        results=lexical["results"]; fallback=False
        threshold=float(cfg.get("semantic_fallback_threshold",10.0))
        if not results or float(results[0].get("score",0)) < threshold:
            semantic=search_knowledge(root,request,["skill","memory","finding"],12,"local_feature_hash_v1")
            if semantic["results"]:
                results=semantic["results"]; fallback=True
        trusted=[]
        for item in results:
            prov=item.get("provenance") or {}
            if item["kind"]=="skill" and not prov.get("external_event_hash"):
                continue
            trusted.append(item)
        return trusted,fallback,None
    except Exception as exc:
        return [],False,f"{type(exc).__name__}: {exc}"

def build_context_pack(root: Path, task_id: str, max_lines: int = 500, mode: str | None = None) -> dict[str, Any]:
    """Build and persist a deterministic transparent context package."""
    root=root.resolve(); task=_task(root,task_id); cfg=load_policy(root).get("knowledge_runtime",{}).get("context_runtime",{})
    mode=mode or cfg.get("compaction_mode","flat_lines")
    allowed=set(cfg.get("compaction_mode_allowed",["flat_lines","symbol_window"]))
    if mode not in allowed: raise RuntimeError("invalid_context_compaction_mode")
    global_lines=min(int(max_lines),int(cfg.get("global_max_lines",max_lines)))
    token_budget=int(cfg.get("global_max_approx_tokens",12000)); per_file=int(cfg.get("per_file_max_lines",160))
    req_terms=_terms(task["request"])
    ranked=[]
    for path in _candidate_files(root,task["approved_scope"]):
        rel=path.relative_to(root).as_posix(); syms=_symbols_for_path(root,rel); score,reasons=_score_file(rel,req_terms,syms)
        ranked.append((-score,rel,path,syms,reasons))
    ranked.sort(key=lambda x:(x[0],x[1]))
    sources=[]; omitted_files=[]; omitted_symbols={}; used_lines=0; used_tokens=0
    for negscore,rel,path,syms,reasons in ranked:
        remaining_lines=global_lines-used_lines; remaining_tokens=token_budget-used_tokens
        if remaining_lines<=0 or remaining_tokens<=0:
            omitted_files.append({"path":rel,"reason":"global_budget_exceeded","relevance_score":-negscore}); continue
        mandatory_cap=max(1, global_lines // max(1, len(MANDATORY))) if rel in MANDATORY else per_file
        take=min(mandatory_cap,per_file,remaining_lines,max(1,remaining_tokens*4//40))
        data=_symbol_window_excerpt(path,syms,req_terms,take) if mode=="symbol_window" and path.suffix==".py" else _read_bounded(path,take)
        data["path"]=rel; data["content_hash"]=_hash(path); data["selection_reasons"]=reasons; data["relevance_score"]=-negscore
        if data.get("omitted_symbols"): omitted_symbols[rel]=data["omitted_symbols"]
        if data["line_count"]<=0: omitted_files.append({"path":rel,"reason":"empty_excerpt","relevance_score":-negscore}); continue
        sources.append(data); used_lines+=data["line_count"]; used_tokens+=data["approx_tokens"]
    with connect(root) as c:
        findings=[dict(r) for r in c.execute("SELECT kind,path,symbol,message,occurrences,last_seen_at FROM project_findings WHERE status='active' ORDER BY occurrences DESC,last_seen_at DESC LIMIT 50").fetchall()]
    knowledge=[]; omitted_knowledge=[]; fallback_used=False; merge_error=None
    if bool(cfg.get("include_knowledge",True)):
        candidates,fallback_used,merge_error=_knowledge_candidates(root,task["request"],cfg)
        reserve=int(cfg.get("knowledge_reserved_tokens",1000)); available=max(0,token_budget-used_tokens); knowledge_budget=min(max(reserve,available),available)
        for item in candidates:
            text=str(item.get("text") or item.get("title") or "")
            cost=max(1,len(text)//4)
            if cost<=knowledge_budget:
                knowledge.append({**item,"approx_tokens":cost,"selection_reasons":["knowledge_relevance","verified_evidence_provenance"]})
                knowledge_budget-=cost; used_tokens+=cost
            else:
                omitted_knowledge.append({"kind":item["kind"],"id":item["id"],"reason":"global_budget_exceeded","relevance_score":item.get("score")})
    manifest={"task_id":task_id,"request":task["request"],"approved_scope":task["approved_scope"],"compaction_mode":mode,"max_lines":global_lines,"max_approx_tokens":token_budget,"line_count":used_lines,"approx_tokens":used_tokens,"sources":sources,"knowledge_sources":knowledge,"omitted_knowledge":omitted_knowledge,"knowledge_candidates":len(knowledge)+len(omitted_knowledge),"included_knowledge":len(knowledge),"knowledge_fallback_used":fallback_used,"knowledge_merge_error":merge_error,"omitted_files":omitted_files,"omitted_symbols":omitted_symbols,"total_candidate_files":len(ranked),"included_files":len(sources),"project_findings":findings}
    digest=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest(); manifest["content_hash"]=digest
    with connect(root) as c:
        rev=c.execute("SELECT COALESCE(MAX(revision),0)+1 AS n FROM context_packs WHERE task_id=?",(task_id,)).fetchone()["n"]
        c.execute("UPDATE context_packs SET status='superseded' WHERE task_id=? AND status='active'",(task_id,))
        c.execute("INSERT INTO context_packs(task_id,revision,content_hash,manifest_json,status) VALUES(?,?,?,?, 'active')",(task_id,rev,digest,json.dumps(manifest,sort_keys=True)))
        c.execute("INSERT INTO context_knowledge_events(task_id,context_revision,candidate_count,included_count,omitted_count,fallback_used,manifest_hash) VALUES(?,?,?,?,?,?,?)",(task_id,rev,manifest["knowledge_candidates"],manifest["included_knowledge"],len(manifest["omitted_knowledge"]),int(fallback_used),digest))
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
    """Explain selected and omitted context with completeness statistics."""
    status=context_status(root,task_id)
    if not status.get("exists"): return status
    m=status["manifest"]
    explanations=[{"path":s["path"],"reasons":s.get("selection_reasons",[]),"relevance_score":s.get("relevance_score"),"content_hash":s["content_hash"],"included_symbols":s.get("included_symbols",[]),"omitted_symbols":s.get("omitted_symbols",[])} for s in m.get("sources",[])]
    return {"task_id":task_id,"revision":status["revision"],"stale":status["stale"],"compaction_mode":m.get("compaction_mode","flat_lines"),"total_candidate_files":m.get("total_candidate_files",len(explanations)),"included_files":m.get("included_files",len(explanations)),"omitted_files":m.get("omitted_files",[]),"omitted_symbols":m.get("omitted_symbols",{}),"line_count":m.get("line_count"),"approx_tokens":m.get("approx_tokens"),"sources":explanations}


def context_compare(root: Path, task_id: str, max_lines: int = 500) -> dict[str, Any]:
    """Compare flat and symbol-window packs without changing source files."""
    flat=build_context_pack(root,task_id,max_lines,"flat_lines")
    symbol=build_context_pack(root,task_id,max_lines,"symbol_window")
    return {"task_id":task_id,"flat_lines":{"revision":flat["revision"],"included_files":flat["included_files"],"line_count":flat["line_count"],"approx_tokens":flat["approx_tokens"],"omitted_files":len(flat["omitted_files"])},"symbol_window":{"revision":symbol["revision"],"included_files":symbol["included_files"],"line_count":symbol["line_count"],"approx_tokens":symbol["approx_tokens"],"omitted_files":len(symbol["omitted_files"]),"omitted_symbols":sum(len(v) for v in symbol["omitted_symbols"].values())}}
