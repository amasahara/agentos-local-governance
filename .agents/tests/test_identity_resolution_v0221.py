from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.append(str(Path(__file__).parent))
from test_controlled_target_insert_v0220 import FakeTargetConnection, setup_validated_batch  # noqa: E402

from agentos.controlled_target_insert import (
    ControlledTargetInsertError,
    approve_target_insert_plan,
    create_target_insert_plan,
    execute_target_insert,
    review_target_insert_plan,
)
from agentos.identity_resolution import (
    IdentityResolutionError,
    approve_identity_policy,
    create_identity_policy,
    create_identity_resolution_run,
    decide_identity_candidate,
    get_entity_lineage,
    get_identity_readiness,
    get_identity_resolution_run,
    list_identity_candidates,
    review_identity_policy,
    run_identity_resolution,
    sync_identity_resolution_schema,
)
from agentos.mcp_identity_resolution_gateway import ALL_TOOLS
from agentos.read_only_extraction import create_extraction_batch, run_extraction_validation


def policy_id(root: Path) -> int:
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        return int(conn.execute("SELECT id FROM identity_resolution_policies ORDER BY id LIMIT 1").fetchone()[0])


def create_second_batch(root: Path, state: dict, rows: list[dict]) -> dict:
    batch = create_extraction_batch(
        root,
        consolidation_id=state["consolidation"]["id"],
        source_snapshot_id=state["source_snapshot"]["id"],
        target_contract_id=state["contract"]["id"],
        source_schema="dbo", source_table="BENH_NHAN",
        target_schema="public", target_table="patient",
        created_by="operator", max_rows=100, chunk_size=10,
    )["batch"]
    summary = run_extraction_validation(root, batch["id"], row_provider=rows)
    assert summary["status"] == "validated"
    return batch


def test_schema_39_created(tmp_path):
    root, _ = setup_validated_batch(tmp_path)
    assert sync_identity_resolution_schema(root)["schema"] == 39


def test_policy_requires_contract_business_key_and_human_gates(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    with pytest.raises(IdentityResolutionError):
        create_identity_policy(
            root, consolidation_id=state["consolidation"]["id"], target_contract_id=state["contract"]["id"],
            target_schema="public", target_table="patient", exact_key_fields=["birth_date"], strong_match_fields=[], created_by="architect",
        )
    p = create_identity_policy(
        root, consolidation_id=state["consolidation"]["id"], target_contract_id=state["contract"]["id"],
        target_schema="public", target_table="patient", exact_key_fields=["patient_code"], strong_match_fields=["birth_date"], created_by="architect", normalizer="exact",
    )["identity_policy"]
    with pytest.raises(IdentityResolutionError):
        review_identity_policy(root, p["id"], reviewed_by="reviewer", human_confirmed=False)
    review_identity_policy(root, p["id"], reviewed_by="reviewer", human_confirmed=True)
    with pytest.raises(IdentityResolutionError):
        approve_identity_policy(root, p["id"], approved_by="owner", human_confirmed=False)


def test_insert_requires_resolved_identity_artifact(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("DELETE FROM identity_bindings")
        conn.execute("DELETE FROM identity_resolution_runs")
    with pytest.raises(ControlledTargetInsertError):
        create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")


def test_exact_business_key_deduplicates_intra_batch(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    batch = create_second_batch(root, state, [
        {"MA_BN": "SAME", "NGAY_SINH": datetime(1990, 1, 1, 8, 0)},
        {"MA_BN": " same ", "NGAY_SINH": datetime(1991, 1, 1, 8, 0)},
    ])
    run = create_identity_resolution_run(root, extraction_batch_id=batch["id"], policy_id=policy_id(root), created_by="operator")["identity_resolution"]
    result = run_identity_resolution(root, run["id"])["identity_resolution"]
    assert result["status"] == "resolved"
    assert result["input_rows"] == 2 and result["output_rows"] == 1 and result["duplicate_rows"] == 1


def test_strong_multifield_match_never_auto_merges(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    batch = create_second_batch(root, state, [{"MA_BN": "NEW-CODE", "NGAY_SINH": datetime(2000, 1, 2, 5, 0)}])
    run = create_identity_resolution_run(root, extraction_batch_id=batch["id"], policy_id=policy_id(root), created_by="operator")["identity_resolution"]
    result = run_identity_resolution(root, run["id"])["identity_resolution"]
    assert result["status"] == "awaiting_human"
    candidates = list_identity_candidates(root, run["id"])["candidates"]
    assert len(candidates) == 1 and candidates[0]["status"] == "pending"
    assert candidates[0]["raw_values_included"] is False


def test_human_confirmed_candidate_can_resume(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    batch = create_second_batch(root, state, [{"MA_BN": "NEW-CODE", "NGAY_SINH": datetime(2000, 1, 2, 5, 0)}])
    run = create_identity_resolution_run(root, extraction_batch_id=batch["id"], policy_id=policy_id(root), created_by="operator")["identity_resolution"]
    run_identity_resolution(root, run["id"])
    c = list_identity_candidates(root, run["id"])["candidates"][0]
    with pytest.raises(IdentityResolutionError):
        decide_identity_candidate(root, c["id"], decision="confirm", decided_by="owner", human_confirmed=False)
    decide_identity_candidate(root, c["id"], decision="confirm", decided_by="owner", human_confirmed=True)
    result = run_identity_resolution(root, run["id"])["identity_resolution"]
    assert result["status"] == "resolved"


def test_committed_target_gets_pseudonymous_lineage(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    insert = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    review_target_insert_plan(root, insert["id"], reviewed_by="reviewer", human_confirmed=True)
    approve_target_insert_plan(root, insert["id"], approved_by="owner", human_confirmed=True)
    result = execute_target_insert(
        root, insert["id"], secret_resolver=lambda _: {"user": "u", "password": "p"},
        target_connection_factory=lambda *_: FakeTargetConnection(),
    )
    assert result["status"] == "committed" and result["lineage_status"] == "complete"
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        entity_uuid = conn.execute("SELECT entity_uuid FROM canonical_entities ORDER BY id LIMIT 1").fetchone()[0]
    lineage = get_entity_lineage(root, entity_uuid)
    blob = json.dumps(lineage)
    assert lineage["lineage"] and "BN001" not in blob and "2000-01-02" not in blob
    assert len(lineage["lineage"][0]["source_record_token"]) == 64
    assert len(lineage["lineage"][0]["target_record_token"]) == 64


def test_cross_batch_duplicate_of_committed_entity_is_not_reinserted_and_keeps_lineage(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    insert = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    review_target_insert_plan(root, insert["id"], reviewed_by="reviewer", human_confirmed=True)
    approve_target_insert_plan(root, insert["id"], approved_by="owner", human_confirmed=True)
    execute_target_insert(root, insert["id"], secret_resolver=lambda _: {"user":"u","password":"p"}, target_connection_factory=lambda *_: FakeTargetConnection())

    batch = create_second_batch(root, state, [{"MA_BN": "BN001", "NGAY_SINH": datetime(2000, 1, 2, 9, 0)}])
    run = create_identity_resolution_run(root, extraction_batch_id=batch["id"], policy_id=policy_id(root), created_by="operator")["identity_resolution"]
    resolved = run_identity_resolution(root, run["id"])["identity_resolution"]
    assert resolved["status"] == "resolved" and resolved["output_rows"] == 0 and resolved["duplicate_rows"] == 1
    ready = get_identity_readiness(root, batch["id"])
    assert ready["resolved"] is True and ready["ready"] is False
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        entity_uuid = conn.execute("SELECT entity_uuid FROM canonical_entities ORDER BY id LIMIT 1").fetchone()[0]
    lineage = get_entity_lineage(root, entity_uuid)["lineage"]
    assert len(lineage) >= 2


def test_lineage_key_is_local_owner_only(tmp_path):
    root, _ = setup_validated_batch(tmp_path)
    from agentos.secret_lineage import active_key
    key_id, material = active_key(root)
    key = root / ".agents/state/lineage-keys" / f"{key_id}.key"
    assert key.exists() and key.read_bytes() == material and len(material) >= 32
    assert not (root / ".agents/state/identity_lineage.key").exists()
    if hasattr(key.stat(), "st_mode"):
        assert key.stat().st_mode & 0o077 == 0


def test_mcp_is_read_only_for_identity_decisions(tmp_path):
    names = {x["name"] for x in ALL_TOOLS}
    assert "agentos.db_identity_candidates_get" in names
    assert "agentos.db_entity_lineage_get" in names
    forbidden = ("approve", "decide", "execute", "credential", "raw_value")
    assert not any(any(word in name for word in forbidden) for name in names)
    assert len(names) == 31
