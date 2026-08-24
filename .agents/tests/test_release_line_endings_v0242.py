"""
File: .agents/tests/test_release_line_endings_v0242.py

Purpose:
    Protect cross-platform release-manifest byte stability.

Responsibilities:
    - Assert release text attributes pin authoritative formats to LF.
    - Verify generated effective-policy bytes match the manifest.
    - Protect launcher and schema bootstrap line endings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_text_attributes_pin_json_to_lf() -> None:
    """Require LF attributes for authoritative cross-platform text formats."""

    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.json text eol=lf" in attrs
    assert "*.py text eol=lf" in attrs
    assert "*.md text eol=lf" in attrs
    assert "*.cmd text eol=lf" in attrs


def test_effective_policy_is_lf_canonical() -> None:
    """Require the generated effective policy to use deterministic LF bytes."""

    data = (
        ROOT / ".agents/config/generated/governance.effective.json"
    ).read_bytes()
    assert b"\r\n" not in data
    assert data.endswith(b"\n")
    assert isinstance(json.loads(data.decode("utf-8")), dict)


def test_manifest_entry_matches_effective_policy_bytes() -> None:
    """Require manifest size and hash to match generated policy bytes exactly."""

    rel = ".agents/config/generated/governance.effective.json"
    data = (ROOT / rel).read_bytes()
    manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["path"] == rel)
    assert entry["size"] == len(data)
    assert entry["sha256"] == hashlib.sha256(data).hexdigest()


def test_windows_cmd_launchers_are_lf_canonical() -> None:
    """Require distributed Windows launchers to use canonical LF bytes."""

    for rel in (
        ".agents/bin/agentos.cmd",
        ".agents/bin/agentos-mcp.cmd",
        ".agents/bin/install.cmd",
    ):
        data = (ROOT / rel).read_bytes()
        assert b"\r\n" not in data, rel
        assert data.endswith(b"\n"), rel


def test_schema_bootstrap_sql_is_lf_canonical() -> None:
    """Require schema bootstrap SQL to use canonical LF bytes."""

    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sql text eol=lf" in attrs
    data = (ROOT / ".agents/schema/bootstrap_v46.sql").read_bytes()
    assert b"\r\n" not in data
    assert data.endswith(b"\n")
