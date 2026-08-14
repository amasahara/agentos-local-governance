"""
File: .agents/tests/test_release_line_endings_v0242.py

Purpose:
    Protect cross-platform release-manifest byte stability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_text_attributes_pin_json_to_lf() -> None:
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.json text eol=lf" in attrs
    assert "*.py text eol=lf" in attrs
    assert "*.md text eol=lf" in attrs
    assert "*.cmd text eol=lf" in attrs


def test_historical_incremental_benchmark_is_lf_canonical() -> None:
    data = (ROOT / "INDEX_INCREMENTAL_BENCHMARK_V0234.json").read_bytes()
    assert b"\r\n" not in data
    assert data.endswith(b"\n")
    payload = json.loads(data.decode("utf-8"))
    assert payload["version"] == "0.23.4"
    assert payload["schema_version"] == 47


def test_manifest_entry_matches_canonical_benchmark_bytes() -> None:
    path = ROOT / "INDEX_INCREMENTAL_BENCHMARK_V0234.json"
    data = path.read_bytes()
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == path.name)
    assert entry["size"] == len(data)
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()

def test_windows_cmd_launchers_are_lf_canonical() -> None:
    for rel in (
        ".agents/bin/agentos.cmd",
        ".agents/bin/agentos-mcp.cmd",
        ".agents/bin/install.cmd",
    ):
        data = (ROOT / rel).read_bytes()
        assert b"\r\n" not in data, rel
        assert data.endswith(b"\n"), rel
