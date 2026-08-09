"""
File: .agents/tests/test_adaptive_budget_v0231.py

Purpose:
    Verify v0.23.1 Adaptive Token Budget & Model Profiles guarantees.

Responsibilities:
    - Prove schema 45 and immutable model-profile hash pinning.
    - Prove adaptive budgets preserve Control Plane priority and fail closed.
    - Prove numeric calibration can only increase protective reservations.
    - Prove calibration stores no prompt/response content.
    - Prove MCP exposes inspection only, never observation/profile/budget mutation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from agentos.adaptive_budget import (
    AdaptiveBudgetError,
    budget_history_get,
    model_profiles_get,
    record_token_observation,
    resolve_adaptive_budget,
    resolve_model_profile,
    token_calibration_get,
)
from agentos.context_transport import (
    ContextTransportError,
    HeuristicTokenizer,
    build_requirement_ledger,
    compile_transport_pack,
)
from agentos.db import connect
from agentos.mcp_adaptive_budget import TOOLS as ADAPTIVE_TOOLS
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


def test_schema_45_and_adaptive_tables(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    with connect(root) as c:
        assert CURRENT_SCHEMA_VERSION == 45
        assert c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 45
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "context_model_profile_snapshots",
            "context_budget_decisions",
            "context_token_observations",
        } <= tables
        columns = {r[1] for r in c.execute("PRAGMA table_info(context_transport_packs)")}
        assert {"model_profile_hash", "budget_mode", "budget_decision_id"} <= columns


def test_model_profiles_are_data_only_and_hash_pinned(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    first = model_profiles_get(root, "generic-128k")
    second = model_profiles_get(root, "generic-128k")
    assert first["ok"] and second["ok"]
    profile = first["profiles"][0]
    assert profile["profile_hash"] == second["profiles"][0]["profile_hash"]
    assert len(profile["profile_hash"]) == 64
    assert first["network_discovery"] is False
    assert first["provider_api_discovery"] is False


def test_invalid_dynamic_tokenizer_profile_fails_closed(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    policy_path = root / ".agents/config/governance.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["context_transport_policy"]["model_profiles"]["bad"] = {
        "context_capacity": 32768,
        "tokenizer": "importlib:evil.module:function",
    }
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="model profile tokenizer policy is invalid"):
        resolve_model_profile(root, "bad")


def test_adaptive_budget_uses_control_first_and_stays_inside_capacity(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    profile = resolve_model_profile(root, "generic-32k")
    ledger = build_requirement_ledger(
        "Triển khai deliverable. Phải giữ nguyên constraint. Không được cắt requirement. Acceptance: test pass."
    )
    decision = resolve_adaptive_budget(
        root,
        profile,
        HeuristicTokenizer.tokenizer_id,
        6000,
        ledger,
        None,
        mode="adaptive",
    )
    assert decision.input_budget == (
        decision.context_capacity
        - decision.reserved_output
        - decision.system_tool_overhead
        - decision.safety_margin
    )
    assert decision.evidence_budget == max(0, decision.input_budget - 6000)
    assert decision.reserved_output >= profile.reserved_output_min
    assert decision.safety_margin >= profile.safety_margin_min


def test_fixed_mode_preserves_v0230_style_explicit_overrides(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    profile = resolve_model_profile(root, "generic-16k")
    decision = resolve_adaptive_budget(
        root,
        profile,
        HeuristicTokenizer.tokenizer_id,
        1000,
        [],
        None,
        mode="fixed",
        reserved_output_override=1234,
        system_tool_overhead_override=2345,
        safety_margin_override=345,
    )
    assert decision.mode == "fixed"
    assert decision.reserved_output == 1234
    assert decision.system_tool_overhead == 2345
    assert decision.safety_margin == 345
    assert decision.calibration_headroom == 0


def test_compile_pins_profile_and_persists_budget_decision(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.py"
    src.write_text("def adaptive_budget():\n    return True\n", encoding="utf-8")
    _canonical(root, "A1", "Triển khai adaptive token budget. Không được mất requirement.", [src])
    pack = compile_transport_pack(root, "A1", "generic-128k")
    assert pack["status"] == "READY"
    assert len(pack["model_profile_hash"]) == 64
    assert pack["budget"]["mode"] == "adaptive"
    assert pack["budget"]["algorithm_version"] == "adaptive_budget_v1"
    assert pack["budget"]["budget_decision_id"] > 0
    with connect(root) as c:
        row = c.execute(
            "SELECT model_profile_hash,budget_mode,budget_decision_id FROM context_transport_packs WHERE task_id='A1'"
        ).fetchone()
        assert row["model_profile_hash"] == pack["model_profile_hash"]
        assert row["budget_mode"] == "adaptive"
        assert row["budget_decision_id"] == pack["budget"]["budget_decision_id"]
        assert c.execute("SELECT COUNT(*) FROM context_model_profile_snapshots").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM context_budget_decisions").fetchone()[0] == 1


def test_protected_control_overflow_still_fails_closed(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    policy_path = root / ".agents/config/governance.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["context_transport_policy"]["model_profiles"]["tiny-adaptive"] = {
        "context_capacity": 512,
        "tokenizer": "heuristic",
        "reserved_output_min": 16,
        "reserved_output_default": 32,
        "reserved_output_max": 64,
        "system_tool_overhead": 16,
        "safety_margin_min": 16,
        "safety_margin_ratio_ppm": 10000,
        "minimum_evidence_tokens": 8,
    }
    policy_path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    src = root / "src/a.md"
    src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "A2", "Không được cắt Control Plane protected content.", [src])
    with pytest.raises(ContextTransportError, match="protected_content_exceeds_model_budget"):
        compile_transport_pack(root, "A2", "tiny-adaptive")


def test_numeric_calibration_only_increases_future_headroom(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.py"
    src.write_text("def calibrate():\n    return 1\n", encoding="utf-8")
    _canonical(root, "A3", "Build adaptive budget and preserve requirements.", [src])
    first = compile_transport_pack(root, "A3", "generic-128k")
    first_margin = first["budget"]["safety_margin"]
    first_output = first["budget"]["reserved_output"]
    observed_input = first["metrics"]["transport_tokens"] + 5000
    record_token_observation(root, "A3", observed_input, first_output + 3000)
    second = compile_transport_pack(root, "A3", "generic-128k", shadow=True)
    assert second["budget"]["safety_margin"] >= first_margin
    assert second["budget"]["calibration_headroom"] >= 5000
    assert second["budget"]["reserved_output"] >= first_output
    stats = token_calibration_get(root, "generic-128k", first["tokenizer"]["id"])
    assert stats["sample_count"] == 1
    assert stats["input_underestimation_p95"] == 5000


def test_token_observation_persists_no_prompt_or_response_content(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    marker = "SENSITIVE-PROMPT-CONTENT-MUST-NOT-BE-IN-OBSERVATION"
    src = root / "src/a.md"
    src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "A4", marker, [src])
    pack = compile_transport_pack(root, "A4")
    result = record_token_observation(root, "A4", pack["metrics"]["transport_tokens"] + 10, 50)
    assert result["content_persisted"] is False
    # The task table legitimately contains the original request. The dedicated
    # calibration row must be numeric/hash-only and have no prompt/response columns.
    with connect(root) as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(context_token_observations)")}
        assert not ({"prompt", "response", "request", "content", "raw_text"} & cols)
        row = dict(c.execute("SELECT * FROM context_token_observations").fetchone())
        assert marker not in json.dumps(row, ensure_ascii=False)


def test_budget_history_is_task_scoped(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.md"
    src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "A5", "Preserve requirements with adaptive budget.", [src])
    compile_transport_pack(root, "A5")
    result = budget_history_get(root, "A5")
    assert result["ok"]
    assert result["count"] == 1
    assert result["decisions"][0]["task_id"] == "A5"


def test_adaptive_mcp_is_exactly_three_read_only_tools() -> None:
    names = {item["name"] for item in ADAPTIVE_TOOLS}
    assert names == {
        "agentos.context_model_profiles_get",
        "agentos.context_budget_history_get",
        "agentos.context_token_calibration_get",
    }
    all_names = {item["name"] for item in ALL_TOOLS}
    assert names <= all_names
    forbidden = {
        name
        for name in all_names
        if "context" in name
        and any(fragment in name for fragment in ("observation_record", "profile_set", "budget_set", "model_switch", "compile"))
    }
    assert not forbidden


def test_token_observation_source_is_allowlisted_and_cannot_carry_content(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.md"
    src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "A6", "Preserve protected requirements.", [src])
    pack = compile_transport_pack(root, "A6")
    with pytest.raises(AdaptiveBudgetError, match="invalid_token_observation_source"):
        record_token_observation(
            root,
            "A6",
            pack["metrics"]["transport_tokens"] + 1,
            20,
            source="secret=DO_NOT_PERSIST",
        )
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_token_observations").fetchone()[0] == 0


def test_token_observation_is_one_per_transport_and_source(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    src = root / "src/a.md"
    src.write_text("evidence\n", encoding="utf-8")
    _canonical(root, "A7", "Preserve protected requirements.", [src])
    pack = compile_transport_pack(root, "A7")
    observed = pack["metrics"]["transport_tokens"] + 7
    first = record_token_observation(root, "A7", observed, 30, source="runtime_report")
    second = record_token_observation(root, "A7", observed, 30, source="runtime_report")
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    with pytest.raises(AdaptiveBudgetError, match="token_observation_source_already_recorded"):
        record_token_observation(root, "A7", observed + 1, 30, source="runtime_report")
    with connect(root) as c:
        assert c.execute("SELECT COUNT(*) FROM context_token_observations").fetchone()[0] == 1


def test_adaptive_overrides_cannot_reduce_protective_reservations(tmp_path: Path, project_root: Path) -> None:
    root = _root(tmp_path, project_root)
    profile = resolve_model_profile(root, "generic-128k")
    baseline = resolve_adaptive_budget(
        root,
        profile,
        HeuristicTokenizer.tokenizer_id,
        4000,
        [{"kind": "deliverable"}] * 8 + [{"kind": "acceptance_criterion"}] * 6,
        json.dumps({"steps": list(range(10))}),
        mode="adaptive",
    )
    overridden = resolve_adaptive_budget(
        root,
        profile,
        HeuristicTokenizer.tokenizer_id,
        4000,
        [{"kind": "deliverable"}] * 8 + [{"kind": "acceptance_criterion"}] * 6,
        json.dumps({"steps": list(range(10))}),
        mode="adaptive",
        reserved_output_override=1,
        system_tool_overhead_override=1,
        safety_margin_override=1,
    )
    assert overridden.reserved_output >= baseline.reserved_output
    assert overridden.system_tool_overhead >= baseline.system_tool_overhead
    assert overridden.safety_margin >= baseline.safety_margin


def test_adaptive_policy_poisoning_fails_closed(tmp_path: Path, project_root: Path) -> None:
    from agentos.policy import load_policy

    root = _root(tmp_path, project_root)
    path = root / ".agents/config/governance.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["adaptive_token_budget_policy"]["network_model_discovery_allowed"] = True
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="adaptive token budget fail-closed invariant"):
        load_policy(root)
