"""
File: .agents/agentos/retrieval.py

Purpose:
    Provide a stable local semantic-retrieval abstraction across AgentOS knowledge sources.

Responsibilities:
    - Define a backend-neutral retrieval contract.
    - Search memory, findings, symbols, and graduated skills locally.
    - Return explainable scores and provenance without network or model dependencies.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

from .db import connect
from .embeddings import semantic_search


class KnowledgeRetriever(Protocol):
    """Contract implemented by local or future embedding retrieval backends."""
    def search(self, query: str, *, kinds: list[str], limit: int) -> list[dict[str, Any]]: ...


def _terms(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9_]{2,}",text.lower())}


def _score(query_terms: set[str], text: str) -> tuple[float,list[str]]:
    matched=sorted(query_terms & _terms(text))
    phrase=1.0 if " ".join(sorted(query_terms)) and " ".join(sorted(query_terms)) in text.lower() else 0.0
    return float(len(matched))*10.0+phrase,matched


class LexicalStructuredRetriever:
    """Deterministic dependency-free retriever over structured SQLite knowledge."""
    def __init__(self, root: Path): self.root=root

    def search(self, query: str, *, kinds: list[str], limit: int) -> list[dict[str, Any]]:
        """Search selected knowledge kinds and return explainable ranked results."""
        allowed={"memory","finding","symbol","skill"}; selected=set(kinds or allowed)
        invalid=selected-allowed
        if invalid: raise ValueError(f"invalid retrieval kinds: {sorted(invalid)}")
        q=_terms(query); results=[]
        with connect(self.root) as c:
            if "memory" in selected:
                for r in c.execute("SELECT id,kind,statement,source_path,confidence,evidence_hash FROM project_memory WHERE status='active'").fetchall():
                    score,matched=_score(q,r["statement"]);
                    if score: results.append({"kind":"memory","id":r["id"],"title":r["kind"],"text":r["statement"],"score":score+float(r["confidence"]),"matched_terms":matched,"provenance":{"source_path":r["source_path"],"evidence_hash":r["evidence_hash"]}})
            if "finding" in selected:
                for r in c.execute("SELECT id,kind,path,symbol,message,occurrences FROM project_findings WHERE status='active'").fetchall():
                    score,matched=_score(q,f"{r['path'] or ''} {r['symbol'] or ''} {r['message']}")
                    if score: results.append({"kind":"finding","id":r["id"],"title":r["kind"],"text":r["message"],"score":score+min(int(r["occurrences"]),10),"matched_terms":matched,"provenance":{"path":r["path"],"symbol":r["symbol"],"occurrences":r["occurrences"]}})
            if "symbol" in selected:
                for r in c.execute("SELECT path,qualname,kind,line_start,line_end,signature FROM symbol_index").fetchall():
                    score,matched=_score(q,f"{r['path']} {r['qualname']} {r['signature']}")
                    if score: results.append({"kind":"symbol","id":f"{r['path']}::{r['qualname']}","title":r["qualname"],"text":r["signature"],"score":score,"matched_terms":matched,"provenance":{"path":r["path"],"line_start":r["line_start"],"line_end":r["line_end"]}})
            if "skill" in selected:
                for r in c.execute("SELECT id,skill_key,version,title,description,graduated_path,content_hash,external_event_hash FROM promoted_skills WHERE status='graduated'").fetchall():
                    score,matched=_score(q,f"{r['skill_key']} {r['title']} {r['description']}")
                    if score: results.append({"kind":"skill","id":r["id"],"title":r["title"],"text":r["description"],"score":score+5,"matched_terms":matched,"provenance":{"version":r["version"],"path":r["graduated_path"],"content_hash":r["content_hash"],"external_event_hash":r["external_event_hash"]}})
            results=sorted(results,key=lambda x:(-x["score"],x["kind"],str(x["id"])))[:limit]
            c.execute("INSERT INTO knowledge_retrieval_events(query_hash,backend,kinds_json,limit_value,result_count,result_ids_json) VALUES(?,?,?,?,?,?)",(hashlib.sha256(query.encode()).hexdigest(),"lexical_structured",json.dumps(sorted(selected)),limit,len(results),json.dumps([f"{r['kind']}:{r['id']}" for r in results])))
        return results


def search_knowledge(root: Path, query: str, kinds: list[str] | None=None, limit: int=20, backend: str="lexical_structured") -> dict[str, Any]:
    """Search project knowledge through a stable backend-neutral API."""
    if backend=="lexical_structured":
        results=LexicalStructuredRetriever(root).search(query,kinds=kinds or ["memory","finding","symbol","skill"],limit=limit)
    elif backend=="local_feature_hash_v1":
        results=semantic_search(root,query,kinds or ["memory","finding","symbol","skill"],limit)
    else:
        raise ValueError("unsupported local retrieval backend")
    return {"ok":True,"backend":backend,"query":query,"kinds":kinds or ["memory","finding","symbol","skill"],"result_count":len(results),"results":results,"network_used":False,"llm_used":False}
