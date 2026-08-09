"""
File: .agents/tests/test_context_expansion_evaluation_v0232.py

Purpose:
    Verify v0.23.2 Context Expansion & Compression Evaluation guarantees.

Responsibilities:
    - Prove schema 46 expansion/evaluation persistence contracts.
    - Prove expansion is hash-pinned, bounded, requirement-aware, and content-ephemeral.
    - Prove deterministic compression hard gates and shadow comparisons.
    - Prove MCP exposes read-only expansion/evaluation operations only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from agentos.context_evaluation import (
    ContextEvaluationError,
    compare_compression,
    compression_evaluation_get,
    evaluate_compression,
    expansion_history_get,
)
from agentos.context_transport import (
    ContextTransportError,
    _nowless_transport_hash,
    compile_transport_pack,
    context_expand,
    context_expand_batch,
    context_expansion_explain,
    context_requirement_get,
)
from agentos.db import connect
from agentos.mcp_context_evaluation import TOOLS as EVALUATION_TOOLS, _local_call as mcp_call
from agentos.mcp_context_transport import TOOLS as TRANSPORT_TOOLS
from agentos.mcp_adaptive_budget import TOOLS as ADAPTIVE_TOOLS
from agentos.schema_version import CURRENT_SCHEMA_VERSION


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root(tmp_path: Path, project_root: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents/config").mkdir(parents=True)
    (root / ".agents/state").mkdir(parents=True)
    shutil.copy2(project_root / "AGENTS.md", root / "AGENTS.md")
    shutil.copy2(project_root / ".agents/config/governance.json", root / ".agents/config/governance.json")
    (root / "huong_dan.md").write_text("Hướng dẫn test\n", encoding="utf-8")
    (root / "src").mkdir()
    return root


def _canonical(root: Path, task_id: str, request: str, files: list[Path]) -> None:
    sources = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        sources.append({
            "path": path.relative_to(root).as_posix(),
            "content_hash": _sha(path),
            "excerpt": text,
            "relevance_score": 25.0,
        })
    manifest = {
        "task_id": task_id,
        "request": request,
        "approved_scope": ["src"],
        "sources": sources,
        "knowledge_sources": [],
        "omitted_files": [],
        "omitted_symbols": {},
    }
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with connect(root, immediate=True) as c:
        c.execute(
            "INSERT INTO tasks(id,request,approved,approved_scope,task_state) VALUES(?,?,1,?,'ready')",
            (task_id, request, json.dumps(["src"], ensure_ascii=False)),
        )
        c.execute(
            "INSERT INTO context_packs(task_id,revision,content_hash,manifest_json,status) VALUES(?,1,?,?,'active')",
            (task_id, digest, json.dumps(manifest, ensure_ascii=False, sort_keys=True)),
        )


def _duplicate_pack(root: Path, task_id: str = "T1", copies: int = 2) -> tuple[dict, str]:
    marker = "SENSITIVE-EXPANSION-CONTENT"
    text = "\n".join(f"{marker} line {i} preserve requirement" for i in range(1, 81)) + "\n"
    files = []
    for index in range(copies):
        path = root / f"src/evidence_{index}.md"
        path.write_text(text, encoding="utf-8")
        files.append(path)
    _canonical(root, task_id, "Mục tiêu: preserve requirement 100%. Không được mất authority hay scope.", files)
    return compile_transport_pack(root, task_id), marker


def test_schema_46_tables_columns_and_foreign_keys(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    with connect(root) as c:
        assert CURRENT_SCHEMA_VERSION == 46
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 46
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"context_expansion_sessions", "context_compression_evaluation_runs", "context_compression_comparisons"} <= tables
        columns = {r[1] for r in c.execute("PRAGMA table_info(context_expansion_events)")}
        assert {"session_id", "request_hash", "line_start", "line_end", "returned_tokens", "reason_code", "requirement_ids_json", "transport_hash"} <= columns


def test_single_expansion_is_range_and_token_bounded_without_content_persistence(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, marker = _duplicate_pack(root)
    handle = pack["evidence_plane"]["expansion_index"][0]
    req_id = context_requirement_get(root, "T1")["requirements"][0]["requirement_id"]
    result = context_expand(root, "T1", handle["handle_id"], line_start=5, max_lines=20, max_tokens=30, requirement_ids=[req_id], reason_code="requirement_gap")
    assert result["read_only"] is True
    assert result["content_persisted"] is False
    assert result["source"]["line_start"] == 5
    assert result["returned_tokens"] <= 30
    assert marker in result["excerpt"]
    with connect(root) as c:
        row = dict(c.execute("SELECT request_hash,line_start,line_end,returned_tokens,reason_code,requirement_ids_json FROM context_expansion_events ORDER BY id DESC LIMIT 1").fetchone())
    assert marker not in json.dumps(row, ensure_ascii=False)
    assert row["reason_code"] == "requirement_gap"
    assert req_id in row["requirement_ids_json"]


def test_expansion_rejects_unknown_requirement_and_reason(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, _ = _duplicate_pack(root)
    handle_id = pack["evidence_plane"]["expansion_index"][0]["handle_id"]
    with pytest.raises(ContextTransportError, match="unknown_requirement_ids"):
        context_expand(root, "T1", handle_id, requirement_ids=["REQ-NOT-REAL"])
    with pytest.raises(ContextTransportError, match="unsupported_expansion_reason"):
        context_expand(root, "T1", handle_id, reason_code="arbitrary_llm_reason")


def test_batch_expansion_is_bounded_and_metadata_only(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, marker = _duplicate_pack(root, copies=3)
    handles = pack["evidence_plane"]["expansion_index"]
    result = context_expand_batch(
        root, "T1", [{"handle_id": h["handle_id"], "max_lines": 10, "max_tokens": 18} for h in handles[:2]],
        max_total_tokens=30, reason_code="operator_review",
    )
    assert result["returned_tokens"] <= 30
    assert result["session_id"] is not None
    assert result["content_persisted"] is False
    history = expansion_history_get(root, "T1")
    serialized = json.dumps(history, ensure_ascii=False)
    assert marker not in serialized
    assert history["sessions"][0]["returned_tokens"] <= 30


def test_mcp_batch_expansion_does_not_persist_telemetry(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, _ = _duplicate_pack(root)
    handle_id = pack["evidence_plane"]["expansion_index"][0]["handle_id"]
    result = mcp_call("agentos.context_expand_batch", {"task_id": "T1", "requests": [{"handle_id": handle_id, "max_tokens": 20}]}, root)
    assert result["read_only"] is True
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_expansion_sessions").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM context_expansion_events").fetchone()[0] == 0


def test_expansion_explain_accounts_for_every_candidate(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, _ = _duplicate_pack(root, copies=3)
    explained = context_expansion_explain(root, "T1")
    assert explained["candidate_count"] == 3
    assert explained["included_count"] + explained["expandable_count"] == 3
    assert explained["expandable_count"] == len(pack["evidence_plane"]["expansion_index"])


def test_compression_evaluation_preserves_v0230_metrics_and_hard_gates(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    _duplicate_pack(root)
    result = evaluate_compression(root, "T1")
    required = {
        "raw_tokens", "transport_tokens", "compression_ratio", "protected_requirement_count",
        "preserved_requirement_count", "requirement_preservation_rate", "context_miss_count",
        "expansion_request_count", "task_success_rate", "test_pass_rate", "rework_count", "tool_call_count",
    }
    assert required <= set(result)
    assert result["requirement_preservation_rate"] == 1.0
    assert result["context_miss_count"] == 0
    assert result["handle_integrity_rate"] == 1.0
    assert result["hard_failures"] == []
    assert result["gate_status"] in {"PASS", "WARN"}


def test_evaluation_is_idempotently_persisted_for_same_state(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    _duplicate_pack(root)
    first = evaluate_compression(root, "T1")
    second = evaluate_compression(root, "T1")
    assert first["evaluation_hash"] == second["evaluation_hash"]
    assert first["evaluation_id"] == second["evaluation_id"]
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_compression_evaluation_runs").fetchone()[0] == 1


def test_missing_expansion_handle_is_a_hard_context_miss(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    _duplicate_pack(root)
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT id,manifest_json FROM context_transport_packs WHERE task_id='T1' ORDER BY id DESC LIMIT 1").fetchone()
        manifest = json.loads(row["manifest_json"])
        manifest["evidence_plane"]["expansion_index"] = []
        new_hash = _nowless_transport_hash(manifest)
        manifest["transport_hash"] = new_hash
        c.execute("UPDATE context_transport_packs SET transport_hash=?,manifest_json=? WHERE id=?", (new_hash, json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")), row["id"]))
    result = evaluate_compression(root, "T1", persist=False)
    assert result["gate_status"] == "FAIL"
    assert result["context_miss_count"] == 1
    assert "canonical_candidates_unaccounted" in result["hard_failures"]


def test_shadow_comparison_detects_no_regression_for_equivalent_revision(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    _duplicate_pack(root)
    compile_transport_pack(root, "T1")
    result = compare_compression(root, "T1", 1, 2, persist=True)
    assert result["status"] == "NO_REGRESSION"
    assert result["regression_flags"] == []
    assert result["comparison_id"] is not None


def test_evaluation_get_is_read_only_when_no_persisted_evaluation(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    _duplicate_pack(root)
    result = compression_evaluation_get(root, "T1")
    assert result["persisted"] is False
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_compression_evaluation_runs").fetchone()[0] == 0



def test_evaluation_fails_closed_when_source_becomes_stale(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    pack, _ = _duplicate_pack(root)
    source = root / "src/evidence_0.md"
    source.write_text("changed after transport compile\n", encoding="utf-8")
    result = evaluate_compression(root, "T1", pack["transport_revision"], persist=False)
    assert result["gate_status"] == "FAIL"
    assert "transport_pack_stale" in result["hard_failures"]


def test_v0232_mcp_catalog_is_read_only_and_collision_free() -> None:
    names = {item["name"] for item in EVALUATION_TOOLS}
    assert names == {
        "agentos.context_expansion_explain",
        "agentos.context_expand_batch",
        "agentos.context_expansion_history_get",
        "agentos.context_compression_evaluation_get",
        "agentos.context_compression_compare",
    }
    all_names = [str(item["name"]) for item in [*TRANSPORT_TOOLS, *ADAPTIVE_TOOLS, *EVALUATION_TOOLS]]
    assert names <= set(all_names)
    assert len(all_names) == len(set(all_names))
    forbidden = [name for name in all_names if name.startswith("agentos.context_") and any(token in name for token in ("persist", "record", "compile", "mutate", "approve"))]
    assert forbidden == []
