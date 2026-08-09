"""
File: .agents/tests/test_context_transport_v0230.py

Purpose:
    Verify v0.23.0 Requirement-Preserving Context Compression guarantees.

Responsibilities:
    - Prove protected request/scope/authority preservation and fail-closed budgets.
    - Prove deterministic evidence compression and hash-pinned expansion.
    - Prove schema 44, evaluation metrics, and read-only MCP exposure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from agentos.context_transport import (
    ContextTransportError,
    HeuristicTokenizer,
    build_requirement_ledger,
    compile_transport_pack,
    context_expand,
    context_requirement_get,
    context_token_report,
    context_transport_get,
    evaluate_transport_pack,
)
from agentos.db import connect
from agentos.mcp_context_transport import TOOLS as TRANSPORT_TOOLS
from agentos.mcp_runtime import ALL_TOOLS
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
        sources.append(
            {
                "path": path.relative_to(root).as_posix(),
                "content_hash": _sha(path),
                "excerpt": text,
                "relevance_score": 25.0,
            }
        )
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


def test_schema_44_and_foreign_keys(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    with connect(root) as c:
        assert CURRENT_SCHEMA_VERSION == 44
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 44
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert c.execute("SELECT name FROM sqlite_master WHERE name='context_transport_packs'").fetchone()


def test_requirement_ledger_is_exact_stable_and_multilingual() -> None:
    request = "Hãy giữ nguyên yêu cầu này. Tuyệt đối không dịch hoặc tóm tắt. Mục tiêu: compression 2-4x ổn định."
    a = build_requirement_ledger(request)
    b = build_requirement_ledger(request)
    assert a == b
    assert all(item["exact_text"] in request for item in a)
    assert any(item["kind"] == "prohibition" for item in a)
    assert any(item["kind"] == "acceptance_criterion" for item in a)
    assert len({item["requirement_id"] for item in a}) == len(a)


def test_heuristic_tokenizer_multilingual_fallback() -> None:
    tokenizer = HeuristicTokenizer()
    assert tokenizer.count("Tiếng Việt có dấu và English mixed content.") > 0
    assert tokenizer.count("你好世界") >= 4


def test_compile_preserves_original_request_scope_and_authority(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/service.py"
    src.write_text("def preserve_requirement(value):\n    return value\n", encoding="utf-8")
    request = "Giữ nguyên 100% yêu cầu người dùng; không paraphrase; cập nhật deliverable context transport."
    _canonical(root, "T1", request, [src])
    pack = compile_transport_pack(root, "T1")
    control = pack["control_plane"]
    assert pack["status"] == "READY"
    assert control["original_user_request"] == request
    assert control["original_user_request_hash"] == hashlib.sha256(request.encode()).hexdigest()
    assert control["approved_scope"]["raw"] == json.dumps(["src"], ensure_ascii=False)
    assert control["instruction_authority"]["verbatim"] == (root / "AGENTS.md").read_text(encoding="utf-8")
    assert pack["preservation_gate"]["requirement_preservation_rate"] == 1.0
    assert pack["preservation_gate"]["preservation_rate_100_percent"] is True
    assert pack["preservation_gate"]["transport_integrity"] is True
    assert pack["transport_hash"]


def test_control_plane_budget_overflow_fails_closed_without_truncation(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    policy_path = root / ".agents/config/governance.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["context_transport_policy"]["model_profiles"]["tiny-test"] = {"context_capacity": 512, "tokenizer": "heuristic"}
    policy["context_transport_policy"]["reserved_output_tokens"] = 1
    policy["context_transport_policy"]["system_tool_overhead_tokens"] = 1
    policy["context_transport_policy"]["safety_margin_tokens"] = 1
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    src = root / "src/a.md"; src.write_text("evidence\n", encoding="utf-8")
    request = "Không được cắt protected content."
    _canonical(root, "T2", request, [src])
    with pytest.raises(ContextTransportError, match="protected_content_exceeds_model_budget"):
        compile_transport_pack(root, "T2", "tiny-test")
    with connect(root) as c:
        row = c.execute("SELECT status,failure_reason FROM context_transport_packs WHERE task_id='T2'").fetchone()
    assert tuple(row) == ("FAILED", "protected_content_exceeds_model_budget")


def test_exact_dedup_and_omission_handles_are_expandable(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    duplicate = "same exact evidence\n" * 20
    a = root / "src/a.md"; b = root / "src/b.md"
    a.write_text(duplicate, encoding="utf-8"); b.write_text(duplicate, encoding="utf-8")
    huge = root / "src/huge.md"
    huge.write_text("\n".join(f"unique evidence line {i} requirement transport" for i in range(30000)), encoding="utf-8")
    _canonical(root, "T3", "Build context transport; preserve requirements; do not summarize protected content.", [a, b, huge])
    pack = compile_transport_pack(root, "T3", "generic-128k")
    omitted = pack["evidence_plane"]["omitted"]
    assert any(item["reason"] == "exact_duplicate" for item in omitted)
    assert any(item["reason"] == "token_budget_omission" for item in omitted)
    handle = next(item for item in pack["evidence_plane"]["expansion_index"] if item["path"] == "src/huge.md")
    expanded = context_expand(root, "T3", handle["handle_id"], max_lines=5)
    assert expanded["read_only"] is True
    assert expanded["source_hash"] == _sha(huge)
    assert len(expanded["excerpt"].splitlines()) == 5


def test_expansion_mcp_style_can_be_strictly_read_only(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    a = root / "src/a.md"; b = root / "src/b.md"
    text = "duplicate evidence\n" * 5
    a.write_text(text, encoding="utf-8"); b.write_text(text, encoding="utf-8")
    _canonical(root, "T4", "Preserve requirements and provide expansion handles.", [a, b])
    pack = compile_transport_pack(root, "T4")
    handle = pack["evidence_plane"]["expansion_index"][0]
    result = context_expand(root, "T4", handle["handle_id"], record_event=False)
    assert result["ok"]
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_expansion_events").fetchone()[0] == 0


def test_source_change_stales_transport_and_blocks_expansion(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    a = root / "src/a.md"; b = root / "src/b.md"
    text = "same evidence\n" * 5
    a.write_text(text, encoding="utf-8"); b.write_text(text, encoding="utf-8")
    _canonical(root, "T5", "Do not use stale evidence.", [a, b])
    pack = compile_transport_pack(root, "T5")
    handle = pack["evidence_plane"]["expansion_index"][0]
    a.write_text("changed\n", encoding="utf-8")
    state = context_transport_get(root, "T5")
    assert state["stale"] is True
    with pytest.raises(ContextTransportError, match="transport_pack_stale"):
        context_expand(root, "T5", handle["handle_id"])


def test_transport_integrity_tamper_detected(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.md"; src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "T6", "Preserve transport integrity hash.", [src])
    compile_transport_pack(root, "T6")
    with connect(root, immediate=True) as c:
        c.execute("UPDATE context_transport_packs SET manifest_json='{}' WHERE task_id='T6'")
    with pytest.raises(ContextTransportError, match="transport_integrity_hash_mismatch"):
        context_transport_get(root, "T6")


def test_requirement_and_token_reports(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.py"; src.write_text("def acceptance_gate():\n    return True\n", encoding="utf-8")
    _canonical(root, "T7", "Mục tiêu: giữ requirement 100%. Không được word-level deletion.", [src])
    compile_transport_pack(root, "T7")
    req = context_requirement_get(root, "T7")
    report = context_token_report(root, "T7")
    assert req["count"] >= 2
    assert report["requirement_preservation_rate"] == 1.0
    assert report["transport_tokens"] <= report["budget"]["input_budget"]
    assert report["compression_ratio"] > 0


def test_evaluation_metrics_and_expansion_count(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    a = root / "src/a.md"; b = root / "src/b.md"
    text = "same evidence\n" * 10
    a.write_text(text, encoding="utf-8"); b.write_text(text, encoding="utf-8")
    _canonical(root, "T8", "Preserve requirement and evaluate context transport.", [a, b])
    pack = compile_transport_pack(root, "T8")
    handle = pack["evidence_plane"]["expansion_index"][0]
    context_expand(root, "T8", handle["handle_id"])
    result = evaluate_transport_pack(root, "T8")
    expected = {
        "raw_tokens", "transport_tokens", "compression_ratio", "protected_requirement_count",
        "preserved_requirement_count", "requirement_preservation_rate", "context_miss_count",
        "expansion_request_count", "task_success_rate", "test_pass_rate", "rework_count", "tool_call_count",
    }
    assert expected <= set(result)
    assert result["requirement_preservation_rate"] == 1.0
    assert result["context_miss_count"] == 0
    assert result["expansion_request_count"] == 1


def test_mcp_exposes_only_five_read_only_transport_tools() -> None:
    names = {item["name"] for item in TRANSPORT_TOOLS}
    assert names == {
        "agentos.context_transport_get",
        "agentos.context_transport_explain",
        "agentos.context_expand",
        "agentos.context_requirement_get",
        "agentos.context_token_report",
    }
    all_names = {item["name"] for item in ALL_TOOLS}
    assert names <= all_names
    forbidden = {name for name in all_names if "context" in name and any(word in name for word in ("compile", "approve", "mutate", "evaluate"))}
    assert not forbidden
