"""Path: .agents/tests/test_governed_skill_contract_v0270.py
Purpose: Regression tests for v0.27.0 Governed Skill Contract v2.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agentos.db import SCHEMA_VERSION, connect
from agentos.mcp_v0270 import TOOLS as V0270_TOOLS
from agentos.skill_contract_v2 import (
    default_contract,
    set_skill_contract,
    skill_contract_get,
    skill_contract_status,
    validate_skill_contract,
)
from agentos.skills import graduate_skill, promote_skill_candidate


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    config = root / ".agents" / "config"
    config.mkdir(parents=True)
    source_config = Path(__file__).resolve().parents[1] / "config"
    shutil.copy2(source_config / "governance.json", config / "governance.json")
    release_policy = source_config / "release_policy.json"
    if release_policy.is_file():
        shutil.copy2(release_policy, config / "release_policy.json")
    monkeypatch.setenv("AGENTOS_AUDIT_HOME", str(tmp_path / "audit"))
    return root


def _memory(root: Path, statement: str = "Run the deterministic release checks") -> int:
    with connect(root, immediate=True) as c:
        cur = c.execute(
            "INSERT INTO project_memory(kind,statement,confidence,evidence_hash,status) VALUES('procedural',?,0.95,?,'active')",
            (statement, "e" * 64),
        )
        return int(cur.lastrowid)


def test_schema_58_skill_contract_tables_and_columns_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    with connect(root) as c:
        version = c.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = {row[1] for row in c.execute("PRAGMA table_info(promoted_skills)")}
    assert version == SCHEMA_VERSION
    assert SCHEMA_VERSION >= 58
    assert {"skill_contracts", "skill_contract_events"} <= tables
    assert {"contract_version", "contract_hash", "contract_status", "architecture_baseline_id", "architecture_baseline_hash"} <= columns


def test_new_promotion_materializes_v2_least_authority_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    result = promote_skill_candidate(root, _memory(root), "human:author")
    assert result["contract_version"] == 2
    assert result["contract_status"] == "draft"
    state = skill_contract_get(root, result["skill_id"])
    contract = state["contract_state"]["contract"]
    assert contract == default_contract(result["skill_key"], result["version"])
    assert contract["allowed_write_scope"] == []
    assert contract["required_capabilities"] == []
    assert state["legacy_v1"] is False


def test_contract_hash_is_deterministic_and_shape_validation_is_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    contract = default_contract(promoted["skill_key"], promoted["version"])
    first = set_skill_contract(root, promoted["skill_id"], contract, "human:architect")
    second = set_skill_contract(root, promoted["skill_id"], dict(reversed(list(contract.items()))), "human:architect")
    assert first["contract_hash"] == second["contract_hash"]
    bad = dict(contract); bad["unexpected"] = True
    result = set_skill_contract(root, promoted["skill_id"], bad, "human:architect")
    assert result["ok"] is False
    assert any(item["code"] == "skill_contract_unknown_fields" for item in result["findings"])


def test_unsafe_scope_and_unknown_architecture_section_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    contract = default_contract(promoted["skill_key"], promoted["version"])
    contract["allowed_write_scope"] = ["../outside"]
    contract["required_architecture_sections"] = ["ARCH-99"]
    result = set_skill_contract(root, promoted["skill_id"], contract, "human:architect")
    codes = {item["code"] for item in result["findings"]}
    assert {"skill_contract_unsafe_scope", "skill_contract_unknown_architecture_section"} <= codes


def test_architecture_bound_contract_requires_active_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    contract = default_contract(promoted["skill_key"], promoted["version"])
    contract["required_architecture_sections"] = ["ARCH-10"]
    assert set_skill_contract(root, promoted["skill_id"], contract, "human:architect")["ok"] is True
    result = validate_skill_contract(root, promoted["skill_id"])
    assert result["ok"] is False
    assert result["status"] == "needs_architecture"
    assert any(item["code"] == "skill_contract_active_architecture_required" for item in result["findings"])


def test_architecture_neutral_contract_can_validate_without_inventing_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    result = validate_skill_contract(root, promoted["skill_id"])
    assert result["ok"] is True
    assert result["status"] == "valid"
    assert result["architecture_baseline_hash"] is None


def test_active_architecture_change_stales_pinned_candidate_instead_of_auto_repinning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    contract = default_contract(promoted["skill_key"], promoted["version"])
    contract["architecture_constraints"] = {"requires_human_architecture_binding": True}
    assert set_skill_contract(root, promoted["skill_id"], contract, "human:architect")["ok"] is True
    with connect(root, immediate=True) as c:
        c.execute(
            "INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by) VALUES('a',1,'active',?,27,'human')",
            ("a" * 64,),
        )
    first = validate_skill_contract(root, promoted["skill_id"])
    assert first["ok"] is True
    assert first["architecture_baseline_hash"] == "a" * 64
    with connect(root, immediate=True) as c:
        c.execute("UPDATE architecture_baselines SET status='superseded' WHERE baseline_uuid='a'")
        c.execute(
            "INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by) VALUES('b',2,'active',?,27,'human')",
            ("b" * 64,),
        )
    stale = validate_skill_contract(root, promoted["skill_id"])
    assert stale["ok"] is False
    assert stale["status"] == "stale_architecture"
    assert stale["architecture_baseline_hash"] == "a" * 64
    assert any(item["code"] == "skill_contract_architecture_baseline_changed" for item in stale["findings"])


def test_graduation_requires_valid_v2_contract_and_remains_human_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    with pytest.raises(RuntimeError, match="human identity"):
        graduate_skill(root, promoted["skill_id"], "agent", "approve")
    monkeypatch.setattr("agentos.skills.append_signed_event", lambda *args, **kwargs: {"event_hash": "s" * 64})
    result = graduate_skill(root, promoted["skill_id"], "human:reviewer", "reviewed exact v2 contract")
    assert result["status"] == "graduated"
    state = skill_contract_get(root, promoted["skill_id"])
    assert state["skill"]["contract_status"] == "valid"


def test_graduated_contract_is_immutable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    promoted = promote_skill_candidate(root, _memory(root), "human:author")
    monkeypatch.setattr("agentos.skills.append_signed_event", lambda *args, **kwargs: {"event_hash": "s" * 64})
    graduate_skill(root, promoted["skill_id"], "human:reviewer", "approved")
    contract = default_contract(promoted["skill_key"], promoted["version"])
    with pytest.raises(RuntimeError, match="immutable"):
        set_skill_contract(root, promoted["skill_id"], contract, "human:architect")


def test_legacy_v1_skill_is_preserved_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    memory_id = _memory(root, "Legacy procedure")
    with connect(root, immediate=True) as c:
        cur = c.execute(
            """INSERT INTO promoted_skills(skill_key,version,memory_id,title,description,candidate_path,status,content_hash,promoted_by)
               VALUES('legacy',1,?,'Legacy','Legacy procedure','.agents/skills/legacy.md','graduated',?,'human:old')""",
            (memory_id, "a" * 64),
        )
        sid = int(cur.lastrowid)
    state = skill_contract_get(root, sid)
    assert state["legacy_v1"] is True
    assert state["contract"] is None
    assert state["migration_required"] == "create_successor_candidate_not_in_place_rewrite"


def test_contract_status_preserves_authority_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root(tmp_path, monkeypatch)
    status = skill_contract_status(root)
    assert status["legacy_v1_preserved"] is True
    assert status["legacy_in_place_rewrite"] is False
    assert status["human_graduation_required"] is True
    assert status["mcp_mutation_exposed"] is False
    assert status["automatic_skill_selection"] is False
    assert status["architecture_approval_authority_exposed"] is False


def test_mcp_v0270_is_exactly_three_read_only_tools() -> None:
    names = {item["name"] for item in V0270_TOOLS}
    assert names == {
        "agentos.skill_contract_get",
        "agentos.skill_contract_status_get",
        "agentos.skill_contracts_list",
    }
    assert not any(any(word in name for word in ("approve", "graduate", "revoke", "set", "validate", "execute", "mutate")) for name in names)


def test_distribution_model_requires_latest_full_release_without_updater(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.policy import load_release_policy
    root = Path(__file__).resolve().parents[2]
    policy = load_release_policy(root)
    install = policy["installation_policy"]
    assert install["distribution_model"] == "download_latest_full_release"
    assert install["updater_script_required"] is False
    assert install["project_owned_user_skills"] is True
    assert install["project_owned_workflows"] is True
    assert install["project_owned_source"] is True
