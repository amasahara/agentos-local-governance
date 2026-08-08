#!/usr/bin/env python3
"""
File: tools/verify_manifest.py

Purpose:
    Verify release MANIFEST.json and CHECKSUMS.sha256 against filesystem bytes.

Responsibilities:
    - Recompute SHA-256 and size for every manifest entry.
    - Cross-check checksum-file entries with the manifest.
    - Detect missing and unexpected authoritative release files.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

EXCLUDE = {"MANIFEST.json", "CHECKSUMS.sha256"}
EXCLUDE_PREFIXES = (".git/", ".agents/runtime/", ".agents/state/", ".pytest_cache/")
EXCLUDE_PARTS = {"__pycache__"}

def _hash(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def _candidate_files(root: Path) -> set[str]:
    out=set()
    for p in root.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(root).as_posix()
        if rel in EXCLUDE or rel.startswith(EXCLUDE_PREFIXES): continue
        if any(part in EXCLUDE_PARTS for part in p.relative_to(root).parts): continue
        if rel.endswith(".pyc"): continue
        out.add(rel)
    return out

def verify(root: Path) -> dict:
    root=root.resolve(); manifest_path=root/"MANIFEST.json"; checksums_path=root/"CHECKSUMS.sha256"
    findings=[]
    if not manifest_path.exists() or not checksums_path.exists():
        return {"ok":False,"findings":[{"code":"missing_manifest_files","message":"MANIFEST.json and CHECKSUMS.sha256 are required"}]}
    m=json.loads(manifest_path.read_text(encoding="utf-8"))
    entries={x["path"]:x for x in m.get("files",[])}
    checksum_entries={}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        digest, rel=line.split(None,1); checksum_entries[rel.strip()]=digest
    for rel,entry in sorted(entries.items()):
        p=root/rel
        if not p.is_file(): findings.append({"code":"missing_file","path":rel}); continue
        digest=_hash(p); size=p.stat().st_size
        if digest!=entry.get("sha256"): findings.append({"code":"manifest_hash_mismatch","path":rel})
        if size!=entry.get("size"): findings.append({"code":"manifest_size_mismatch","path":rel})
        if checksum_entries.get(rel)!=digest: findings.append({"code":"checksum_mismatch","path":rel})
    if set(entries)!=set(checksum_entries): findings.append({"code":"manifest_checksum_set_mismatch","message":"manifest/checksum path sets differ"})
    unexpected=sorted(_candidate_files(root)-set(entries))
    if unexpected: findings.append({"code":"unexpected_files","paths":unexpected[:100]})
    return {"ok":not findings,"release":m.get("release"),"kind":m.get("kind"),"file_count":len(entries),"findings":findings}

def main():
    p=argparse.ArgumentParser(); p.add_argument("root", nargs="?", default=".", type=Path); args=p.parse_args()
    result=verify(args.root); print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(0 if result["ok"] else 2)
if __name__=="__main__": main()
