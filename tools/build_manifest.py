#!/usr/bin/env python3
"""Build deterministic AgentOS release MANIFEST.json and CHECKSUMS.sha256."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from verify_manifest import EXCLUDE, EXCLUDE_PREFIXES, EXCLUDE_PARTS, _candidate_files

def digest(p:Path)->str:
    h=hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("root",nargs="?",default=".",type=Path); ap.add_argument("--kind",default="full"); args=ap.parse_args(); root=args.root.resolve()
    files=[]
    for rel in sorted(_candidate_files(root)):
        p=root/rel; files.append({"path":rel,"size":p.stat().st_size,"sha256":digest(p)})
    release=(root/"VERSION").read_text().strip()
    (root/"MANIFEST.json").write_text(json.dumps({"release":release,"kind":args.kind,"file_count":len(files),"files":files},indent=2)+"\n")
    (root/"CHECKSUMS.sha256").write_text("".join(f"{x['sha256']}  {x['path']}\n" for x in files))
if __name__=="__main__": main()
