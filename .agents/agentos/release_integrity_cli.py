"""
File: .agents/agentos/release_integrity_cli.py

Purpose:
    Expose v0.22.3 release-integrity and aggregate documentation gates.

Responsibilities:
    - Parse the project root and requested integrity mode.
    - Print deterministic JSON results.
    - Return non-zero when the selected release gate is not satisfied.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
from .release_integrity import check_release_integrity, docs_check_v0223

def main() -> None:
    """Run a v0.22.3 release gate and exit fail-closed on findings."""
    p=argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--mode", choices=("integrity","docs"), default="integrity")
    args=p.parse_args()
    result = docs_check_v0223(args.root) if args.mode == "docs" else check_release_integrity(args.root)
    print(json.dumps(result,indent=2,sort_keys=True))
    raise SystemExit(0 if result["ok"] else 2)

if __name__ == "__main__": main()
