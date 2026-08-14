"""
File: .agents/tests/test_db_aware_context_projection_v0242.py

Purpose:
    Verify v0.24.2 reversible schema/mapping/manifest codecs, schema-49 telemetry,
    context-transport integration, and read-only MCP authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from agentos.db import connect
from agentos.db_aware_context_projection import (
    CODECS,
    decode_projection,
    encode_projection,
    migration_49,
    preview_file,
    project_db_aware_candidate,
)
from agentos.mcp_db_aware_context_projection import TOOLS


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_schema_codec_roundtrip_and_determinism() -> None:
    value = {
        "tables": [
            {"name": "patients", "columns": [{"name": "id", "type": "INTEGER", "nullable": False}, {"name": "name", "type": "TEXT", "nullable": False}]},
            {"name": "visits", "columns": [{"name": "id", "type": "INTEGER", "nullable": False}, {"name": "patient_id", "type": "INTEGER", "nullable": False}]},
        ]
    }
    first = encode_projection("schema", value)
    second = encode_projection("schema", value)
    assert first["codec"] == CODECS["schema"]
    assert first["projection_text"] == second["projection_text"]
    assert _canonical(decode_projection(first["projection"])) == _canonical(value)


def test_mapping_codec_roundtrip() -> None:
    value = {
        "field_mappings": [
            {"source_field": "patient_id", "target_field": "patient_id", "type": "INTEGER", "nullable": False},
            {"source_field": "full_name", "target_field": "name", "type": "TEXT", "nullable": False},
            {"source_field": "birth_date", "target_field": "date_of_birth", "type": "DATE", "nullable": True},
        ]
    }
    encoded = encode_projection("mapping", value)
    assert encoded["codec"] == CODECS["mapping"]
    assert _canonical(decode_projection(encoded["projection"])) == _canonical(value)


def test_manifest_codec_roundtrip() -> None:
    value = {
        "files": [
            {"path": ".agents/agentos/a.py", "sha256": "a" * 64, "size": 100},
            {"path": ".agents/agentos/b.py", "sha256": "b" * 64, "size": 120},
            {"path": ".agents/tests/test_a.py", "sha256": "c" * 64, "size": 90},
        ]
    }
    encoded = encode_projection("manifest", value)
    assert encoded["codec"] == CODECS["manifest"]
    assert _canonical(decode_projection(encoded["projection"])) == _canonical(value)


def test_detection_requires_strong_path_and_structure_signal() -> None:
    mapping = {"field_mappings": [{"source_field": "a", "target_field": "b"}] * 12}
    text = json.dumps(mapping)
    assert project_db_aware_candidate("mapping/field_mapping.json", text) is not None
    assert project_db_aware_candidate("notes.json", text) is None


def test_projection_only_selected_when_smaller() -> None:
    tiny = json.dumps({"tables": [{"name": "x"}]})
    assert project_db_aware_candidate("schema.json", tiny) is None


def test_preview_is_read_only_and_project_root_bounded(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    value = {"manifest": {"files": [{"path": f"src/{i}.py", "sha256": "a" * 64, "size": i} for i in range(20)]}}
    path = root / "release_manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    result = preview_file(root, "release_manifest.json")
    assert result["ok"] and result["read_only"] and result["persisted"] is False
    assert not (root / ".agents").exists()


def test_schema_49_adds_hash_only_projection_telemetry(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        migration_49(conn)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(context_db_projection_events)")}
    finally:
        conn.close()
    assert {"source_hash", "source_structure_hash", "projection_hash", "source_bytes", "projected_bytes"} <= columns
    assert "raw_text" not in columns
    assert "projected_text" not in columns
    assert "payload_json" not in columns


def test_mcp_surface_is_read_only() -> None:
    names = {item["name"] for item in TOOLS}
    assert names == {"agentos.context_db_projection_get"}
    assert all(name.endswith("_get") for name in names)
