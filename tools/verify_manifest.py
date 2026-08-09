#!/usr/bin/env python3
"""
File: tools/verify_manifest.py

Purpose:
    Verify release MANIFEST.json and CHECKSUMS.sha256 through the AgentOS library.

Responsibilities:
    - Keep the standalone release tool compatible with CI and operator workflows.
    - Delegate verification logic to the single in-process AgentOS implementation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents"))
from agentos.release_manifest import EXCLUDE, EXCLUDE_PARTS, EXCLUDE_PREFIXES, _candidate_files, verify_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args()
    result = verify_manifest(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
