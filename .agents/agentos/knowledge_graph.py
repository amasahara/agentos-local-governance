"""
File: .agents/agentos/knowledge_graph.py

Purpose:
    Build a small use-case-driven relationship graph over AgentOS knowledge.

Responsibilities:
    - Materialize only relationships supported by existing project evidence.
    - Connect symbols, findings, memories, and promoted skills.
    - Support neighborhood and bounded path queries without a graph database.
"""
from __future__ import annotations
import ast, hashlib, json
from collections import deque
from pathlib import Path
from typing import Any
from .db import connect

def _nid(kind:str,key:str)->str: return f"{kind}:{key}"
def _edge(a:str,b:str,rel:str)->str: return hashlib.sha256(f"{a}|{rel}|{b}".encode()).hexdigest()
def build_graph(root:Path)->dict[str,Any]:
    """Rebuild evidence-backed graph nodes and edges from current knowledge state."""
    nodes={}; edges=[]
    with connect(root) as c:
        for r in c.execute("SELECT path,qualname,kind,signature FROM symbol_index"):
            n=_nid("symbol",f"{r['path']}::{r['qualname']}"); nodes[n]=( "symbol",r["qualname"],{"path":r["path"],"kind":r["kind"],"signature":r["signature"]})
        for r in c.execute("SELECT id,kind,path,symbol,message FROM project_findings WHERE status='active'"):
            n=_nid("finding",str(r["id"])); nodes[n]=( "finding",r["message"],{"kind":r["kind"],"path":r["path"],"symbol":r["symbol"]})
            if r["path"] and r["symbol"]:
                target=_nid("symbol",f"{r['path']}::{r['symbol']}")
                if target in nodes: edges.append((n,target,"observes",{"source":"project_findings"},1.0))
        for r in c.execute("SELECT id,kind,statement,source_path FROM project_memory WHERE status='active'"):
            n=_nid("memory",str(r["id"])); nodes[n]=( "memory",r["statement"],{"kind":r["kind"],"source_path":r["source_path"]})
        for r in c.execute("SELECT id,memory_id,skill_key,version,title FROM promoted_skills WHERE status='graduated'"):
            n=_nid("skill",str(r["id"])); nodes[n]=( "skill",r["title"],{"skill_key":r["skill_key"],"version":r["version"]})
            m=_nid("memory",str(r["memory_id"]));
            if m in nodes: edges.append((n,m,"derived_from",{"source":"promoted_skills"},1.0))
        for path in sorted(root.rglob("*.py")):
            if ".agents/runtime" in path.as_posix(): continue
            rel=path.relative_to(root).as_posix()
            try: tree=ast.parse(path.read_text(encoding="utf-8"))
            except Exception: continue
            file_symbols=[n for n,(t,_,p) in nodes.items() if t=="symbol" and p.get("path")==rel]
            for imp in [x for x in ast.walk(tree) if isinstance(x,(ast.Import,ast.ImportFrom))]:
                names=[a.name for a in imp.names] if isinstance(imp,ast.Import) else ([imp.module] if imp.module else [])
                for name in names:
                    for target,(t,_,p) in nodes.items():
                        if t=="symbol" and str(p.get("path","")).replace("/",".").endswith(f"{name}.py"):
                            for src in file_symbols: edges.append((src,target,"imports",{"module":name,"path":rel},0.9))
        c.execute("DELETE FROM knowledge_edges"); c.execute("DELETE FROM knowledge_nodes")
        for n,(t,label,props) in nodes.items(): c.execute("INSERT INTO knowledge_nodes(node_id,node_type,label,properties_json,content_hash) VALUES(?,?,?,?,?)",(n,t,label,json.dumps(props,ensure_ascii=False),hashlib.sha256((label+json.dumps(props,sort_keys=True)).encode()).hexdigest()))
        for a,b,rel,evidence,conf in edges:
            if a in nodes and b in nodes: c.execute("INSERT OR IGNORE INTO knowledge_edges(edge_id,from_node_id,to_node_id,relation,evidence_json,confidence) VALUES(?,?,?,?,?,?)",(_edge(a,b,rel),a,b,rel,json.dumps(evidence,ensure_ascii=False),conf))
    return {"ok":True,"nodes":len(nodes),"edges":len({(a,b,r) for a,b,r,_,_ in edges}),"use_cases":["impact_analysis","finding_to_symbol","skill_provenance"]}
def graph_neighbors(root:Path,node_id:str,relation:str|None=None,limit:int=50)->dict[str,Any]:
    """Return bounded incoming and outgoing graph neighbors."""
    with connect(root) as c:
        sql="SELECT e.*,nf.label from_label,nt.label to_label FROM knowledge_edges e JOIN knowledge_nodes nf ON nf.node_id=e.from_node_id JOIN knowledge_nodes nt ON nt.node_id=e.to_node_id WHERE (e.from_node_id=? OR e.to_node_id=?) AND e.status='active'"; args=[node_id,node_id]
        if relation: sql+=" AND e.relation=?"; args.append(relation)
        rows=[dict(r) for r in c.execute(sql+" ORDER BY e.relation,e.edge_id LIMIT ?",(*args,limit))]
    return {"ok":True,"node_id":node_id,"neighbors":rows}
def graph_path(root:Path,from_node:str,to_node:str,max_depth:int=4)->dict[str,Any]:
    """Find one bounded relationship path using breadth-first traversal."""
    with connect(root) as c: rows=c.execute("SELECT from_node_id,to_node_id,relation FROM knowledge_edges WHERE status='active'").fetchall()
    adj={}
    for r in rows: adj.setdefault(r["from_node_id"],[]).append((r["to_node_id"],r["relation"]))
    q=deque([(from_node,[])]); seen={from_node}
    while q:
        node,path=q.popleft()
        if node==to_node: return {"ok":True,"path":path}
        if len(path)>=max_depth: continue
        for nxt,rel in adj.get(node,[]):
            if nxt not in seen: seen.add(nxt); q.append((nxt,path+[{"from":node,"relation":rel,"to":nxt}]))
    return {"ok":False,"reason":"path_not_found","max_depth":max_depth}
