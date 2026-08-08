from __future__ import annotations

from datetime import datetime
import json
import os
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
from agentos.read_only_extraction import (
    ReadOnlyExtractionError,
    build_select_spec,
    create_extraction_batch,
    get_extraction_summary,
    get_validation_findings,
    run_extraction_validation,
    sync_read_only_extraction_schema,
    verify_staging_artifact,
)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents/state").mkdir(parents=True)
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def source_manifest(extra: bool = False) -> dict:
    columns = [
        {"name": "MA_BN", "native_type": "nvarchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
        {"name": "NGAY_SINH", "native_type": "datetime", "canonical_type": "datetime", "nullable": True, "ordinal": 2},
        {"name": "UNUSED_SECRET_FIELD", "native_type": "nvarchar(50)", "canonical_type": "string", "nullable": True, "ordinal": 3},
    ]
    if extra:
        columns.append({"name": "EXTRA", "native_type": "int", "canonical_type": "integer", "nullable": True, "ordinal": 4})
    return {"manifest_version": 1, "tables": [{"schema": "dbo", "name": "BENH_NHAN", "columns": columns, "primary_key": ["MA_BN"], "unique_keys": []}]}


def target_manifest(extra: bool = False) -> dict:
    columns = [
        {"name": "patient_code", "native_type": "varchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
        {"name": "birth_date", "native_type": "date", "canonical_type": "date", "nullable": True, "ordinal": 2},
    ]
    if extra:
        columns.append({"name": "new_col", "native_type": "text", "canonical_type": "text", "nullable": True, "ordinal": 3})
    return {"manifest_version": 1, "tables": [{"schema": "public", "name": "patient", "columns": columns, "primary_key": [], "unique_keys": [["patient_code"]]}]}


def target_contract() -> dict:
    return {
        "contract_schema_version": 1,
        "tables": [{
            "schema": "public",
            "name": "patient",
            "columns": [
                {"name": "patient_code", "canonical_type": "string", "nullable": False, "required": True, "sensitive": True},
                {"name": "birth_date", "canonical_type": "date", "nullable": True, "required": False, "sensitive": True},
            ],
            "primary_key": [],
            "business_keys": [["patient_code"]],
        }],
    }


def setup_plan(root: Path, *, engine: str = "mssql", credential_ref: str = "env://TEST_SOURCE_DB") -> dict:
    source = register_connection(
        root, connection_alias="source1", role="SOURCE", engine=engine, host="source.internal", database_name="HIS",
        domain_id="healthcare", credential_ref=credential_ref, created_by="operator",
    )["connection"]
    verify_source_readonly(root, source["id"], verified_by="dba", method="grant_review", evidence="Ticket DB-1: SELECT/catalog only", human_confirmed=True)
    target = register_connection(
        root, connection_alias="target1", role="TARGET", engine="postgresql", host="target.internal", database_name="UnifiedHIS",
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
        confidence=1.0, match_method="manual", evidence={"reason": "business patient code"}, created_by="architect",
        validation_rule={"not_null": True, "allow_blank": False, "max_length": 50},
    )["field_mapping"]
    confirm_field_mapping(root, m1["id"], confirmed_by="owner", human_confirmed=True)
    m2 = add_field_mapping(
        root, consolidation_id=consolidation["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"],
        source_schema="dbo", source_table="BENH_NHAN", source_column="NGAY_SINH",
        target_schema="public", target_table="patient", target_column="birth_date",
        confidence=1.0, match_method="manual", evidence={"reason": "date of birth"}, created_by="architect",
        transform_rule="datetime_to_date", transform_output_type="date", validation_rule={"date_min": "1900-01-01", "date_max": "2100-01-01"},
    )["field_mapping"]
    confirm_field_mapping(root, m2["id"], confirmed_by="owner", human_confirmed=True)
    return {"source": source, "target": target, "consolidation": consolidation, "source_snapshot": ss, "target_snapshot": ts, "contract": contract, "mappings": [m1, m2]}


def create_batch(root: Path, state: dict, **kwargs) -> dict:
    return create_extraction_batch(
        root,
        consolidation_id=state["consolidation"]["id"],
        source_snapshot_id=state["source_snapshot"]["id"],
        target_contract_id=state["contract"]["id"],
        source_schema="dbo", source_table="BENH_NHAN", target_schema="public", target_table="patient",
        created_by="operator", max_rows=kwargs.get("max_rows", 100), chunk_size=kwargs.get("chunk_size", 10),
    )["batch"]


def test_schema_37_created(tmp_path):
    assert sync_read_only_extraction_schema(make_root(tmp_path))["schema"] == 37


def test_batch_requires_confirmed_mapping(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("UPDATE db_field_mappings SET status='proposed' WHERE id=?", (state["mappings"][0]["id"],))
    with pytest.raises(ReadOnlyExtractionError):
        create_batch(root, state)


def test_batch_rejects_unknown_transform(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("UPDATE db_field_mappings SET transform_rule='python_eval_custom' WHERE id=?", (state["mappings"][1]["id"],))
    with pytest.raises(ReadOnlyExtractionError):
        create_batch(root, state)


def test_batch_requires_all_required_target_fields(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
        conn.execute("UPDATE db_field_mappings SET status='rejected' WHERE target_column='patient_code'")
    with pytest.raises(ReadOnlyExtractionError):
        create_batch(root, state)


def test_select_spec_only_mapped_columns_no_star(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    spec = build_select_spec(root, batch["id"])
    assert spec["generated"] is True and spec["arbitrary_sql"] is False and spec["write_statement"] is False
    assert "SELECT" in spec["sql"].upper() and "*" not in spec["sql"]
    assert "UNUSED_SECRET_FIELD" not in spec["sql"]
    assert set(spec["selected_columns"]) == {"MA_BN", "NGAY_SINH"}


@pytest.mark.parametrize("engine, expected", [
    ("mysql", "LIMIT 100"), ("postgresql", "LIMIT 100"), ("mssql", "TOP 100"), ("oracle", "FETCH FIRST 100 ROWS ONLY"),
])
def test_select_generation_supported_engines(tmp_path, engine, expected):
    root = make_root(tmp_path); state = setup_plan(root, engine=engine); batch = create_batch(root, state)
    assert expected in build_select_spec(root, batch["id"])["sql"]


def test_source_write_operations_remain_denied(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    for op in ["insert", "update", "delete", "merge", "ddl", "execute_sql"]:
        assert authorize_operation(root, state["source"]["id"], op)["allowed"] is False


def test_target_insert_still_denied_v0212(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    decision = authorize_operation(root, state["target"]["id"], "insert")
    assert decision["allowed"] is False and "v0.22.0" in decision["reason"]


def test_valid_rows_staged_and_transformed(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    result = run_extraction_validation(root, batch["id"], row_provider=[
        {"MA_BN": "BN001", "NGAY_SINH": datetime(2000, 1, 2, 10, 30), "UNUSED_SECRET_FIELD": "must-not-be-selected"},
        {"MA_BN": "BN002", "NGAY_SINH": None},
    ])
    assert result["status"] == "validated" and result["valid_rows"] == 2 and result["rejected_rows"] == 0
    staged = (root / result["staging_path"]).read_text(encoding="utf-8").splitlines()
    first = json.loads(staged[0])
    assert first["values"] == {"patient_code": "BN001", "birth_date": "2000-01-02"}
    assert "UNUSED_SECRET_FIELD" not in staged[0]
    assert first["provenance"]["source_locator_hash"]


def test_invalid_rows_quarantined_without_raw_values(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    secret_value = "PATIENT-RAW-SHOULD-NOT-BE-IN-SQLITE"
    result = run_extraction_validation(root, batch["id"], row_provider=[
        {"MA_BN": "", "NGAY_SINH": "not-a-date", "UNUSED_SECRET_FIELD": secret_value},
    ])
    assert result["status"] == "completed_with_rejections" and result["rejected_rows"] == 1
    qtext = (root / result["quarantine_path"]).read_text(encoding="utf-8")
    assert "raw_values_stored\":false" in qtext and secret_value not in qtext and "not-a-date" not in qtext
    db = (root / ".agents/state/agentos.db").read_bytes()
    assert secret_value.encode() not in db and b"not-a-date" not in db


def test_findings_return_hash_not_value(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    run_extraction_validation(root, batch["id"], row_provider=[{"MA_BN": "", "NGAY_SINH": None}])
    findings = get_validation_findings(root, batch["id"])["findings"]
    assert findings and all(int(x["raw_value_stored"]) == 0 for x in findings)
    assert all("value_hash" in x for x in findings)


def test_artifacts_owner_only_and_hash_verified(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    summary = run_extraction_validation(root, batch["id"], row_provider=[{"MA_BN": "BN1", "NGAY_SINH": None}])
    for key in ["staging_path", "quarantine_path", "manifest_path"]:
        mode = os.stat(root / summary[key]).st_mode & 0o777
        assert mode & 0o077 == 0
    assert verify_staging_artifact(root, batch["id"])["ok"] is True


def test_artifact_tamper_detected(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    summary = run_extraction_validation(root, batch["id"], row_provider=[{"MA_BN": "BN1", "NGAY_SINH": None}])
    with (root / summary["staging_path"]).open("a", encoding="utf-8") as f:
        f.write("tamper\n")
    assert verify_staging_artifact(root, batch["id"])["ok"] is False


def test_batch_stales_on_source_schema_drift(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    register_schema_snapshot(root, connection_id=state["source"]["id"], manifest=source_manifest(extra=True), captured_by="dba")
    with pytest.raises(ReadOnlyExtractionError):
        build_select_spec(root, batch["id"])


def test_batch_stales_on_target_contract_supersede(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    register_schema_snapshot(root, connection_id=state["target"]["id"], manifest=target_manifest(extra=True), captured_by="dba")
    with pytest.raises(ReadOnlyExtractionError):
        build_select_spec(root, batch["id"])


def test_max_rows_enforced_with_injected_provider(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state, max_rows=2)
    result = run_extraction_validation(root, batch["id"], row_provider=[
        {"MA_BN": "1", "NGAY_SINH": None}, {"MA_BN": "2", "NGAY_SINH": None}, {"MA_BN": "3", "NGAY_SINH": None},
    ])
    assert result["selected_rows"] == 2 and result["valid_rows"] == 2


def test_summary_never_returns_record_content(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root); batch = create_batch(root, state)
    summary = run_extraction_validation(root, batch["id"], row_provider=[{"MA_BN": "SECRET-PATIENT-CODE", "NGAY_SINH": None}])
    assert "SECRET-PATIENT-CODE" not in json.dumps(summary)
    assert summary["raw_values_returned"] is False and summary["target_data_write_enabled"] is False


def test_mcp_exposes_read_only_summary_tools_only():
    from agentos.mcp_read_only_extraction_gateway import TOOLS
    names = {item["name"] for item in TOOLS}
    assert names == {
        "agentos.db_extraction_batch_get",
        "agentos.db_extraction_summary_get",
        "agentos.db_validation_findings_get",
        "agentos.db_staging_integrity_get",
    }
    assert all(all(token not in name for token in ("run", "execute", "insert", "create", "write", "content")) for name in names)


def test_no_raw_sql_tool_exposed_v0212():
    from agentos.mcp_read_only_extraction_gateway import TOOLS
    assert all("sql" not in item["name"] for item in TOOLS)


def test_ready_for_v0220_only_when_no_rejections(tmp_path):
    root = make_root(tmp_path); state = setup_plan(root)
    ok_batch = create_batch(root, state)
    ok = run_extraction_validation(root, ok_batch["id"], row_provider=[{"MA_BN": "BN1", "NGAY_SINH": None}])
    assert ok["ready_for_v0.22.0"] is True
    bad_batch = create_batch(root, state)
    bad = run_extraction_validation(root, bad_batch["id"], row_provider=[{"MA_BN": "", "NGAY_SINH": None}])
    assert bad["ready_for_v0.22.0"] is False


def test_top_level_mcp_catalog_aggregates_prior_read_only_tools():
    from agentos.mcp_read_only_extraction_gateway import ALL_TOOLS
    names = {item["name"] for item in ALL_TOOLS}
    assert "agentos.project_identity_get" in names
    assert "agentos.db_boundary_check" in names
    assert "agentos.db_mapping_readiness_get" in names
    assert "agentos.db_extraction_summary_get" in names
    assert len(names) >= 22


def test_top_level_mcp_catalog_has_no_database_mutation_tools():
    from agentos.mcp_read_only_extraction_gateway import ALL_TOOLS
    names = {item["name"] for item in ALL_TOOLS}
    forbidden = ("db_insert", "execute_sql", "db_extraction_run", "db_connection_register", "db_target_contract_approve")
    assert all(not any(token in name for token in forbidden) for name in names)
