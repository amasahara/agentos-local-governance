"""
File: .agents/agentos/embeddings.py

Purpose:
    Provide optional dependency-free local embeddings and retrieval-augmented context.

Responsibilities:
    - Build deterministic feature-hashed vectors without network or model calls.
    - Persist vectors for AgentOS knowledge sources.
    - Produce explainable local RAG results with provenance.
"""
from __future__ import annotations
import hashlib, json, math, re, struct
from pathlib import Path
from typing import Any
from .db import connect

BACKEND="local_feature_hash_v1"
DIMENSIONS=256

def _tokens(text:str)->list[str]:
    return re.findall(r"[a-z0-9_]{2,}",text.lower())

def embed_text(text:str,dimensions:int=DIMENSIONS)->list[float]:
    """Create a deterministic normalized feature-hashed vector for text."""
    v=[0.0]*dimensions
    toks=_tokens(text)
    for token in toks:
        digest=hashlib.sha256(token.encode()).digest()
        idx=int.from_bytes(digest[:4],"big")%dimensions
        sign=1.0 if digest[4]&1 else -1.0
        v[idx]+=sign*(1.0+math.log1p(len(token)))
    norm=math.sqrt(sum(x*x for x in v)) or 1.0
    return [x/norm for x in v]

def _cosine(a:list[float],b:list[float])->float:
    return sum(x*y for x,y in zip(a,b))

def _sources(root:Path,kinds:set[str]):
    with connect(root) as c:
        if "memory" in kinds:
            for r in c.execute("SELECT id,kind,statement,source_path,evidence_hash FROM project_memory WHERE status='active'"):
                yield "memory",str(r["id"]),r["statement"],{"memory_kind":r["kind"],"source_path":r["source_path"],"evidence_hash":r["evidence_hash"]}
        if "finding" in kinds:
            for r in c.execute("SELECT id,kind,path,symbol,message,occurrences FROM project_findings WHERE status='active'"):
                yield "finding",str(r["id"]),f"{r['kind']} {r['path'] or ''} {r['symbol'] or ''} {r['message']}",{"path":r["path"],"symbol":r["symbol"],"occurrences":r["occurrences"]}
        if "symbol" in kinds:
            for r in c.execute("SELECT path,qualname,kind,signature,line_start,line_end FROM symbol_index"):
                sid=f"{r['path']}::{r['qualname']}"; yield "symbol",sid,f"{r['path']} {r['qualname']} {r['kind']} {r['signature']}",{"path":r["path"],"line_start":r["line_start"],"line_end":r["line_end"]}
        if "skill" in kinds:
            for r in c.execute("SELECT id,skill_key,version,title,description,graduated_path,content_hash,external_event_hash FROM promoted_skills WHERE status='graduated'"):
                yield "skill",str(r["id"]),f"{r['skill_key']} {r['title']} {r['description']}",{"version":r["version"],"path":r["graduated_path"],"content_hash":r["content_hash"],"external_event_hash":r["external_event_hash"]}

def build_embedding_index(root:Path,kinds:list[str]|None=None)->dict[str,Any]:
    """Build or refresh local embeddings for selected knowledge kinds."""
    selected=set(kinds or ["memory","finding","symbol","skill"]); count=0
    with connect(root,immediate=True) as c:
        for kind,sid,text,meta in _sources(root,selected):
            h=hashlib.sha256(text.encode()).hexdigest(); vec=embed_text(text)
            blob=struct.pack(f"<{len(vec)}f",*vec)
            c.execute("INSERT INTO knowledge_embeddings(source_kind,source_id,content_hash,backend,dimensions,vector_json,text_snapshot,metadata_json,vector_blob,vector_dtype,vector_version) VALUES(?,?,?,?,?,?,?,?,?,'float32',1) ON CONFLICT(source_kind,source_id,backend) DO UPDATE SET content_hash=excluded.content_hash,dimensions=excluded.dimensions,vector_json=excluded.vector_json,text_snapshot=excluded.text_snapshot,metadata_json=excluded.metadata_json,vector_blob=excluded.vector_blob,vector_dtype='float32',vector_version=1,updated_at=CURRENT_TIMESTAMP",(kind,sid,h,BACKEND,DIMENSIONS,'[]',text,json.dumps(meta,ensure_ascii=False),blob))
            count+=1
    return {"ok":True,"backend":BACKEND,"indexed":count,"dimensions":DIMENSIONS,"network_used":False,"llm_used":False}

def semantic_search(root:Path,query:str,kinds:list[str]|None=None,limit:int=20)->list[dict[str,Any]]:
    """Search persisted local embeddings by cosine similarity."""
    selected=set(kinds or ["memory","finding","symbol","skill"]); q=embed_text(query); rows=[]
    with connect(root) as c:
        placeholders=','.join('?' for _ in selected)
        for r in c.execute(f"SELECT * FROM knowledge_embeddings WHERE backend=? AND source_kind IN ({placeholders})",(BACKEND,*sorted(selected))):
            vec=list(struct.unpack(f"<{r['dimensions']}f",r["vector_blob"])) if r["vector_blob"] else json.loads(r["vector_json"]); score=_cosine(q,vec)
            if score>0: rows.append({"kind":r["source_kind"],"id":r["source_id"],"text":r["text_snapshot"],"score":round(score,6),"matched_terms":[],"provenance":json.loads(r["metadata_json"]),"backend":BACKEND})
    return sorted(rows,key=lambda x:(-x["score"],x["kind"],x["id"]))[:limit]

def rag_query(root:Path,query:str,kinds:list[str]|None=None,top_k:int=8,max_chars:int=12000,auto_index:bool=True)->dict[str,Any]:
    """Create a bounded retrieval-augmented context bundle from local embeddings."""
    if auto_index: build_embedding_index(root,kinds)
    results=semantic_search(root,query,kinds,top_k); chunks=[]; used=0
    for i,r in enumerate(results,1):
        chunk=f"[{i}] {r['kind']}:{r['id']} score={r['score']}\n{r['text']}\nprovenance={json.dumps(r['provenance'],ensure_ascii=False)}"
        if used+len(chunk)>max_chars: break
        chunks.append(chunk); used+=len(chunk)
    context="\n\n".join(chunks); ch=hashlib.sha256(context.encode()).hexdigest()
    with connect(root) as c:
        c.execute("INSERT INTO rag_retrieval_events(query_hash,backend,kinds_json,top_k,result_count,context_hash) VALUES(?,?,?,?,?,?)",(hashlib.sha256(query.encode()).hexdigest(),BACKEND,json.dumps(kinds or ["memory","finding","symbol","skill"]),top_k,len(chunks),ch))
    return {"ok":True,"backend":BACKEND,"query":query,"result_count":len(chunks),"results":results[:len(chunks)],"context":context,"context_hash":ch,"network_used":False,"llm_used":False,"optional":True}
