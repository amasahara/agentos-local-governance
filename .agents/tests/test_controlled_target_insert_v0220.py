from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3

import pytest

from agentos.database_boundary import (
    add_source,
    authorize_operation,
    create_consolidation,
    register_connection,
    verify_source_readonly,
)
from agentos.schema_mapping import (
    add_field_mapping,
    approve_target_contract,
    confirm_field_mapping,
    create_target_contract,
    register_schema_snapshot,
    review_target_contract,
)
from agentos.read_only_extraction import create_extraction_batch, run_extraction_validation
from agentos.controlled_target_insert import (
    ControlledTargetInsertError,
    approve_target_insert_plan,
    build_insert_spec,
    create_target_insert_plan,
    execute_target_insert,
    get_target_insert_readiness,
    get_target_insert_receipt,
    review_target_insert_plan,
    sync_controlled_target_insert_schema,
)
from agentos.mcp_controlled_target_insert_gateway import ALL_TOOLS
from agentos.identity_resolution import (
    approve_identity_policy,
    create_identity_policy,
    create_identity_resolution_run,
    review_identity_policy,
    run_identity_resolution,
)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents/state").mkdir(parents=True)
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def source_manifest() -> dict:
    return {
        "manifest_version": 1,
        "tables": [{
            "schema": "dbo", "name": "BENH_NHAN",
            "columns": [
                {"name": "MA_BN", "native_type": "nvarchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
                {"name": "NGAY_SINH", "native_type": "datetime", "canonical_type": "datetime", "nullable": True, "ordinal": 2},
            ],
            "primary_key": ["MA_BN"], "unique_keys": [],
        }],
    }


def target_manifest() -> dict:
    return {
        "manifest_version": 1,
        "tables": [{
            "schema": "public", "name": "patient",
            "columns": [
                {"name": "patient_code", "native_type": "varchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
                {"name": "birth_date", "native_type": "date", "canonical_type": "date", "nullable": True, "ordinal": 2},
            ],
            "primary_key": [], "unique_keys": [["patient_code"]],
        }],
    }


def target_contract() -> dict:
    return {
        "contract_schema_version": 1,
        "tables": [{
            "schema": "public", "name": "patient",
            "columns": [
                {"name": "patient_code", "canonical_type": "string", "nullable": False, "required": True, "sensitive": True},
                {"name": "birth_date", "canonical_type": "date", "nullable": True, "required": False, "sensitive": True},
            ],
            "primary_key": [], "business_keys": [["patient_code"]],
        }],
    }


def setup_validated_batch(tmp_path: Path, *, target_engine: str = "postgresql", rejected: bool = False) -> tuple[Path, dict]:
    root = make_root(tmp_path)
    source = register_connection(
        root, connection_alias="source1", role="SOURCE", engine="mssql", host="source.internal", database_name="HIS",
        domain_id="healthcare", credential_ref="env://TEST_SOURCE_DB", created_by="operator",
    )["connection"]
    verify_source_readonly(root, source["id"], verified_by="dba", method="grant_review", evidence="SELECT only", human_confirmed=True)
    target = register_connection(
        root, connection_alias="target1", role="TARGET", engine=target_engine, host="target.internal", database_name="UnifiedHIS",
        domain_id="healthcare", credential_ref="env://TEST_TARGET_DB", created_by="operator",
    )["connection"]
    consolidation = create_consolidation(root, target_connection_id=target["id"], created_by="operator")["consolidation"]
    add_source(root, consolidation["id"], source["id"], registered_by="operator")
    ss = register_schema_snapshot(root, connection_id=source["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    ts = register_schema_snapshot(root, connection_id=target["id"], manifest=target_manifest(), captured_by="dba")["snapshot"]
    contract = create_target_contract(root, consolidation_id=consolidation["id"], target_snapshot_id=ts["id"], contract=target_contract(), created_by="architect")["target_contract"]
    review_target_contract(root, contract["id"], reviewed_by="reviewer", human_confirmed=True)
    contract = approve_target_contract(root, contract["id"], approved_by="owner", human_confirmed=True)["target_contract"]
    m1 = add_field_mapping(
        root, consolidation_id=consolidation["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"],
        source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN",
        target_schema="public", target_table="patient", target_column="patient_code",
        confidence=1.0, match_method="manual", evidence={"reason": "patient code"}, created_by="architect",
        validation_rule={"not_null": True, "allow_blank": False, "max_length": 50},
    )["field_mapping"]
    confirm_field_mapping(root, m1["id"], confirmed_by="owner", human_confirmed=True)
    m2 = add_field_mapping(
        root, consolidation_id=consolidation["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"],
        source_schema="dbo", source_table="BENH_NHAN", source_column="NGAY_SINH",
        target_schema="public", target_table="patient", target_column="birth_date",
        confidence=1.0, match_method="manual", evidence={"reason": "birth date"}, created_by="architect",
        transform_rule="datetime_to_date", transform_output_type="date",
    )["field_mapping"]
    confirm_field_mapping(root, m2["id"], confirmed_by="owner", human_confirmed=True)
    batch = create_extraction_batch(
        root, consolidation_id=consolidation["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"],
        source_schema="dbo", source_table="BENH_NHAN", target_schema="public", target_table="patient",
        created_by="operator", max_rows=100, chunk_size=10,
    )["batch"]
    rows = [
        {"MA_BN": "BN001", "NGAY_SINH": datetime(2000, 1, 2, 10, 30)},
        {"MA_BN": "BN002", "NGAY_SINH": None},
    ]
    if rejected:
        rows.append({"MA_BN": "", "NGAY_SINH": None})
    summary = run_extraction_validation(root, batch["id"], row_provider=rows)
    if summary["status"] == "validated":
        identity_policy = create_identity_policy(
            root, consolidation_id=consolidation["id"], target_contract_id=contract["id"],
            target_schema="public", target_table="patient", exact_key_fields=["patient_code"],
            strong_match_fields=["birth_date"], created_by="architect",
        )["identity_policy"]
        review_identity_policy(root, identity_policy["id"], reviewed_by="reviewer", human_confirmed=True)
        approve_identity_policy(root, identity_policy["id"], approved_by="owner", human_confirmed=True)
        resolution = create_identity_resolution_run(root, extraction_batch_id=batch["id"], policy_id=identity_policy["id"], created_by="operator")["identity_resolution"]
        resolution = run_identity_resolution(root, resolution["id"])["identity_resolution"]
        assert resolution["status"] == "resolved"
    return root, {
        "source": source, "target": target, "consolidation": consolidation,
        "source_snapshot": ss, "target_snapshot": ts, "contract": contract,
        "batch": batch, "summary": summary,
    }


class FakeCursor:
    def __init__(self, owner: "FakeTargetConnection") -> None:
        self.owner = owner
        self.closed = False

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        if self.owner.fail_execute:
            raise RuntimeError("simulated insert failure")
        self.owner.sql.append(sql)
        self.owner.rows.extend(rows)

    def close(self) -> None:
        self.closed = True


class FakeTargetConnection:
    def __init__(self, *, fail_execute: bool = False, fail_commit: bool = False) -> None:
        self.fail_execute = fail_execute
        self.fail_commit = fail_commit
        self.sql: list[str] = []
        self.rows: list[tuple] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("simulated commit uncertainty")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def approved_run(root: Path, state: dict) -> dict:
    run = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    review_target_insert_plan(root, run["id"], reviewed_by="reviewer", human_confirmed=True)
    return approve_target_insert_plan(root, run["id"], approved_by="owner", human_confirmed=True)["insert_run"]


def test_schema_38_created(tmp_path):
    assert sync_controlled_target_insert_schema(make_root(tmp_path))["schema"] == 38


def test_only_fully_validated_batch_is_insertable(tmp_path):
    root, state = setup_validated_batch(tmp_path, rejected=True)
    assert state["summary"]["status"] == "completed_with_rejections"
    with pytest.raises(ControlledTargetInsertError):
        create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")


def test_plan_requires_integrity_intact_staging(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    staging = root / state["summary"]["staging_path"]
    staging.write_text(staging.read_text() + "{}\n", encoding="utf-8")
    with pytest.raises(ControlledTargetInsertError):
        create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")


def test_one_insert_plan_per_extraction_batch(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")
    with pytest.raises(ControlledTargetInsertError):
        create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")


def test_review_and_approval_are_human_gates(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    with pytest.raises(ControlledTargetInsertError):
        review_target_insert_plan(root, run["id"], reviewed_by="reviewer", human_confirmed=False)
    review_target_insert_plan(root, run["id"], reviewed_by="reviewer", human_confirmed=True)
    with pytest.raises(ControlledTargetInsertError):
        approve_target_insert_plan(root, run["id"], approved_by="owner", human_confirmed=False)
    approved = approve_target_insert_plan(root, run["id"], approved_by="owner", human_confirmed=True)["insert_run"]
    assert approved["status"] == "approved"


@pytest.mark.parametrize("engine, marker", [
    ("postgresql", "%s"), ("mysql", "%s"), ("mssql", "?"), ("oracle", ":1"),
])
def test_insert_spec_is_parameterized_insert_only(tmp_path, engine, marker):
    root, state = setup_validated_batch(tmp_path, target_engine=engine)
    run = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    spec = build_insert_spec(root, run["id"])
    assert spec["statement_class"] == "INSERT_ONLY"
    assert spec["row_values_included"] is False and spec["raw_sql"] is False
    assert spec["sql"].startswith("INSERT INTO ") and marker in spec["sql"]
    assert "UPDATE" not in spec["sql"].upper() and "DELETE" not in spec["sql"].upper() and "MERGE" not in spec["sql"].upper()


def test_generic_target_insert_remains_denied(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    decision = authorize_operation(root, state["target"]["id"], "insert")
    assert decision["allowed"] is False


def test_execute_requires_approved_status(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    with pytest.raises(ControlledTargetInsertError):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: FakeTargetConnection())


def test_controlled_insert_commits_valid_staging_rows(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    fake = FakeTargetConnection()
    result = execute_target_insert(
        root, run["id"],
        secret_resolver=lambda _: {"user": "u", "password": "p"},
        target_connection_factory=lambda *_: fake,
    )
    assert result["status"] == "committed" and result["committed_rows"] == 2
    assert fake.committed is True and fake.rolled_back is False and fake.closed is True
    assert len(fake.rows) == 2
    assert fake.rows[0][0] is not None  # birth_date sorts before patient_code; values exist only in fake DB adapter.
    assert all(sql.upper().startswith("INSERT INTO") for sql in fake.sql)
    receipt_text = json.dumps(result, ensure_ascii=False)
    assert "BN001" not in receipt_text and "2000-01-02" not in receipt_text


def test_precommit_failure_rolls_back_whole_transaction(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    fake = FakeTargetConnection(fail_execute=True)
    with pytest.raises(ControlledTargetInsertError):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: fake)
    receipt = get_target_insert_receipt(root, run["id"])
    assert receipt["status"] == "failed" and receipt["failure_stage"] == "precommit"
    assert fake.rolled_back is True and fake.committed is False


def test_commit_failure_is_in_doubt_and_never_auto_retried(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    fake = FakeTargetConnection(fail_commit=True)
    with pytest.raises(ControlledTargetInsertError, match="uncertain"):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: fake)
    receipt = get_target_insert_receipt(root, run["id"])
    assert receipt["status"] == "in_doubt" and receipt["automatic_retry_allowed"] is False
    with pytest.raises(ControlledTargetInsertError, match="automatic retry"):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: FakeTargetConnection())


def test_source_write_invariant_rechecked_before_target_write(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("UPDATE db_connections SET data_write_enabled=1 WHERE id=?", (state["source"]["id"],))
    with pytest.raises(ControlledTargetInsertError, match="SOURCE read-only"):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: FakeTargetConnection())


def test_contract_drift_blocks_approval(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = create_target_insert_plan(root, extraction_batch_id=state["batch"]["id"], created_by="operator")["insert_run"]
    review_target_insert_plan(root, run["id"], reviewed_by="reviewer", human_confirmed=True)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("UPDATE target_schema_contracts SET status='superseded' WHERE id=?", (state["contract"]["id"],))
    with pytest.raises(ControlledTargetInsertError, match="stale"):
        approve_target_insert_plan(root, run["id"], approved_by="owner", human_confirmed=True)


def test_readiness_never_claims_raw_insert_or_source_write(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    readiness = get_target_insert_readiness(root, run["id"])
    assert readiness["eligible_to_execute"] is True
    assert readiness["raw_insert_allowed"] is False
    assert readiness["source_write_allowed"] is False
    assert readiness["automatic_retry_after_committing_or_in_doubt"] is False


def test_receipt_and_events_do_not_persist_values_or_credentials(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    fake = FakeTargetConnection()
    execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "secret-user", "password": "secret-password"}, target_connection_factory=lambda *_: fake)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        event_text = "\n".join(row[0] for row in conn.execute("SELECT event_json FROM db_target_insert_events"))
    assert "BN001" not in event_text and "secret-password" not in event_text and "secret-user" not in event_text


def test_mcp_catalog_is_read_only_for_v0220():
    names = {item["name"] for item in ALL_TOOLS}
    assert len(names) == 26
    assert {
        "agentos.db_target_insert_plan_get", "agentos.db_target_insert_readiness_get",
        "agentos.db_target_insert_spec_get", "agentos.db_target_insert_receipt_get",
    } <= names
    assert not any("execute" in name or "approve" in name or "review" in name or "credential" in name for name in names)


def test_precommit_failure_allows_manual_but_not_automatic_retry(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    failing = FakeTargetConnection(fail_execute=True)
    with pytest.raises(ControlledTargetInsertError):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: failing)
    readiness = get_target_insert_readiness(root, run["id"])
    assert readiness["manual_retry_allowed"] is True and readiness["eligible_to_execute"] is True
    success = FakeTargetConnection()
    receipt = execute_target_insert(root, run["id"], secret_resolver=lambda _: {"user": "u", "password": "p"}, target_connection_factory=lambda *_: success)
    assert receipt["status"] == "committed" and receipt["automatic_retry_allowed"] is False


def test_bad_secret_resolver_fails_preconnect_without_write(tmp_path):
    root, state = setup_validated_batch(tmp_path)
    run = approved_run(root, state)
    with pytest.raises(ControlledTargetInsertError):
        execute_target_insert(root, run["id"], secret_resolver=lambda _: "not-an-object", target_connection_factory=lambda *_: FakeTargetConnection())
    receipt = get_target_insert_receipt(root, run["id"])
    assert receipt["status"] == "failed" and receipt["failure_stage"] == "preconnect" and receipt["manual_retry_allowed"] is True
