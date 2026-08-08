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
    SchemaMappingError,
    add_field_mapping,
    approve_target_contract,
    confirm_field_mapping,
    create_target_contract,
    get_field_mapping,
    get_target_contract,
    list_field_mappings,
    mapping_readiness,
    register_schema_snapshot,
    review_target_contract,
    suggest_field_mappings,
    sync_schema_mapping_schema,
    type_compatibility,
)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents/state").mkdir(parents=True)
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def source_conn(root: Path, alias="source1") -> dict:
    c = register_connection(
        root,
        connection_alias=alias,
        role="SOURCE",
        engine="mssql",
        host="source.internal",
        database_name="HIS",
        domain_id="healthcare",
        credential_ref=f"secret://db/{alias}",
        created_by="operator",
    )["connection"]
    verify_source_readonly(
        root,
        c["id"],
        verified_by="dba",
        method="grant_review",
        evidence="Ticket DB-1: SELECT/catalog grants only",
        human_confirmed=True,
    )
    return c


def target_conn(root: Path) -> dict:
    return register_connection(
        root,
        connection_alias="target1",
        role="TARGET",
        engine="postgresql",
        host="target.internal",
        database_name="UnifiedHIS",
        domain_id="healthcare",
        credential_ref="secret://db/target1",
        created_by="operator",
    )["connection"]


def source_manifest(extra=False) -> dict:
    cols = [
        {"name": "MA_BN", "native_type": "nvarchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
        {"name": "NGAY_SINH", "native_type": "datetime", "canonical_type": "datetime", "nullable": True, "ordinal": 2},
        {"name": "GIOI_TINH", "native_type": "int", "canonical_type": "integer", "nullable": True, "ordinal": 3},
    ]
    if extra:
        cols.append({"name": "EXTRA", "native_type": "nvarchar(20)", "canonical_type": "string", "nullable": True, "ordinal": 4})
    return {
        "manifest_version": 1,
        "tables": [{
            "schema": "dbo",
            "name": "BENH_NHAN",
            "columns": cols,
            "primary_key": ["MA_BN"],
            "unique_keys": [],
        }],
    }


def target_manifest(extra=False) -> dict:
    cols = [
        {"name": "patient_code", "native_type": "varchar(50)", "canonical_type": "string", "nullable": False, "ordinal": 1},
        {"name": "birth_date", "native_type": "date", "canonical_type": "date", "nullable": True, "ordinal": 2},
        {"name": "gender_code", "native_type": "varchar(20)", "canonical_type": "code", "nullable": True, "ordinal": 3},
    ]
    if extra:
        cols.append({"name": "new_col", "native_type": "text", "canonical_type": "text", "nullable": True, "ordinal": 4})
    return {
        "manifest_version": 1,
        "tables": [{
            "schema": "public",
            "name": "patient",
            "columns": cols,
            "primary_key": [],
            "unique_keys": [["patient_code"]],
        }],
    }


def target_contract(required_birth=False) -> dict:
    return {
        "contract_schema_version": 1,
        "tables": [{
            "schema": "public",
            "name": "patient",
            "columns": [
                {"name": "patient_code", "canonical_type": "string", "nullable": False, "required": True, "sensitive": False},
                {"name": "birth_date", "canonical_type": "date", "nullable": True, "required": required_birth, "sensitive": True},
                {"name": "gender_code", "canonical_type": "code", "nullable": True, "required": False, "sensitive": False},
            ],
            "primary_key": [],
            "business_keys": [["patient_code"]],
        }],
    }


def plan_with_source(root: Path):
    s = source_conn(root)
    t = target_conn(root)
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="operator")["consolidation"]
    add_source(root, plan["id"], s["id"], registered_by="operator")
    return s, t, plan


def approved_contract(root: Path, plan: dict, target_id: int, *, required_birth=False):
    ts = register_schema_snapshot(root, connection_id=target_id, manifest=target_manifest(), captured_by="dba")["snapshot"]
    c = create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ts["id"], contract=target_contract(required_birth=required_birth), created_by="architect")["target_contract"]
    review_target_contract(root, c["id"], reviewed_by="reviewer", human_confirmed=True)
    return approve_target_contract(root, c["id"], approved_by="owner", human_confirmed=True)["target_contract"]


def test_schema_36_created(tmp_path):
    assert sync_schema_mapping_schema(make_root(tmp_path))["schema"] == 36


def test_source_snapshot_requires_readonly_verification(tmp_path):
    root = make_root(tmp_path)
    c = register_connection(root, connection_alias="src", role="SOURCE", engine="mssql", host="h", database_name="d", domain_id="healthcare", credential_ref="secret://db/src", created_by="op")["connection"]
    with pytest.raises(SchemaMappingError):
        register_schema_snapshot(root, connection_id=c["id"], manifest=source_manifest(), captured_by="dba")


def test_schema_manifest_rejects_secret_payload(tmp_path):
    root = make_root(tmp_path)
    s = source_conn(root)
    m = source_manifest()
    m["note"] = "password=secret"
    with pytest.raises(SchemaMappingError):
        register_schema_snapshot(root, connection_id=s["id"], manifest=m, captured_by="dba")


def test_target_contract_requires_target_snapshot(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    with pytest.raises(SchemaMappingError):
        create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ss["id"], contract=target_contract(), created_by="architect")


def test_target_contract_rejects_missing_table(tmp_path):
    root = make_root(tmp_path)
    _, t, plan = plan_with_source(root)
    ts = register_schema_snapshot(root, connection_id=t["id"], manifest=target_manifest(), captured_by="dba")["snapshot"]
    c = target_contract(); c["tables"][0]["name"] = "does_not_exist"
    with pytest.raises(SchemaMappingError):
        create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ts["id"], contract=c, created_by="architect")


def test_target_contract_rejects_type_mismatch(tmp_path):
    root = make_root(tmp_path)
    _, t, plan = plan_with_source(root)
    ts = register_schema_snapshot(root, connection_id=t["id"], manifest=target_manifest(), captured_by="dba")["snapshot"]
    c = target_contract(); c["tables"][0]["columns"][0]["canonical_type"] = "integer"
    with pytest.raises(SchemaMappingError):
        create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ts["id"], contract=c, created_by="architect")


def test_contract_review_and_approval_are_human_gated(tmp_path):
    root = make_root(tmp_path)
    _, t, plan = plan_with_source(root)
    ts = register_schema_snapshot(root, connection_id=t["id"], manifest=target_manifest(), captured_by="dba")["snapshot"]
    c = create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ts["id"], contract=target_contract(), created_by="architect")["target_contract"]
    with pytest.raises(SchemaMappingError):
        review_target_contract(root, c["id"], reviewed_by="reviewer", human_confirmed=False)
    review_target_contract(root, c["id"], reviewed_by="reviewer", human_confirmed=True)
    with pytest.raises(SchemaMappingError):
        approve_target_contract(root, c["id"], approved_by="owner", human_confirmed=False)
    approved = approve_target_contract(root, c["id"], approved_by="owner", human_confirmed=True)
    assert approved["target_contract"]["status"] == "approved"


def test_field_mapping_requires_source_registered_in_plan(tmp_path):
    root = make_root(tmp_path)
    s1, t, plan = plan_with_source(root)
    s2 = source_conn(root, alias="source2")
    ss2 = register_schema_snapshot(root, connection_id=s2["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss2["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"same patient code"}, created_by="architect")


def test_mapping_requires_approved_contract(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    ts = register_schema_snapshot(root, connection_id=t["id"], manifest=target_manifest(), captured_by="dba")["snapshot"]
    c = create_target_contract(root, consolidation_id=plan["id"], target_snapshot_id=ts["id"], contract=target_contract(), created_by="architect")["target_contract"]
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=c["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"same patient code"}, created_by="architect")


def test_exact_mapping_can_be_proposed_and_confirmed(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"business key mapping"}, created_by="architect")["field_mapping"]
    assert m["status"] == "proposed" and m["type_compatibility"] == "exact"
    with pytest.raises(SchemaMappingError):
        confirm_field_mapping(root, m["id"], confirmed_by="owner", human_confirmed=False)
    confirmed = confirm_field_mapping(root, m["id"], confirmed_by="owner", human_confirmed=True)["field_mapping"]
    assert confirmed["status"] == "confirmed"


def test_coercible_type_requires_transform(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="NGAY_SINH", target_schema="public", target_table="patient", target_column="birth_date", confidence=.9, match_method="manual", evidence={"reason":"date normalization"}, created_by="architect")
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="NGAY_SINH", target_schema="public", target_table="patient", target_column="birth_date", confidence=.9, match_method="manual", evidence={"reason":"date normalization"}, created_by="architect", transform_rule="datetime_to_date", transform_output_type="date")["field_mapping"]
    assert m["type_compatibility"] == "coercible"


def test_incompatible_type_requires_explicit_output_type(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    assert type_compatibility("integer", "code") == "incompatible"
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="GIOI_TINH", target_schema="public", target_table="patient", target_column="gender_code", confidence=.8, match_method="dictionary", evidence={"dictionary":"gender code"}, created_by="architect", transform_rule="map_gender")
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="GIOI_TINH", target_schema="public", target_table="patient", target_column="gender_code", confidence=.8, match_method="dictionary", evidence={"dictionary":"gender code"}, created_by="architect", transform_rule="map_gender", transform_output_type="code")["field_mapping"]
    assert m["type_compatibility"] == "incompatible"


def test_mapping_evidence_rejects_secret(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"note":"password=secret"}, created_by="architect")


def test_mapping_to_unknown_target_column_rejected(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    with pytest.raises(SchemaMappingError):
        add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="missing", confidence=1, match_method="manual", evidence={"reason":"x"}, created_by="architect")


def test_duplicate_mapping_rejected(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    kwargs = dict(root=root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"key"}, created_by="architect")
    add_field_mapping(**kwargs)
    with pytest.raises(SchemaMappingError):
        add_field_mapping(**kwargs)


def test_new_source_snapshot_stales_mapping(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"key"}, created_by="architect")["field_mapping"]
    confirm_field_mapping(root, m["id"], confirmed_by="owner", human_confirmed=True)
    register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(extra=True), captured_by="dba")
    assert get_field_mapping(root, m["id"])["field_mapping"]["status"] == "stale"


def test_new_target_snapshot_supersedes_contract_and_stales_mapping(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"key"}, created_by="architect")["field_mapping"]
    confirm_field_mapping(root, m["id"], confirmed_by="owner", human_confirmed=True)
    register_schema_snapshot(root, connection_id=t["id"], manifest=target_manifest(extra=True), captured_by="dba")
    assert get_target_contract(root, contract["id"])["target_contract"]["status"] == "superseded"
    assert get_field_mapping(root, m["id"])["field_mapping"]["status"] == "stale"


def test_suggestions_are_advisory_and_not_persisted(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    result = suggest_field_mappings(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"])
    assert result["advisory_only"] is True and result["record_data_read"] is False
    assert list_field_mappings(root, plan["id"])["mappings"] == []


def test_readiness_requires_required_fields_and_all_sources(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"], required_birth=True)
    m1 = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"key"}, created_by="architect")["field_mapping"]
    confirm_field_mapping(root, m1["id"], confirmed_by="owner", human_confirmed=True)
    state = mapping_readiness(root, plan["id"], contract["id"])
    assert state["ready_for_v0.21.2"] is False
    assert "public.patient.birth_date" in state["unmapped_required_target_fields"]
    m2 = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="NGAY_SINH", target_schema="public", target_table="patient", target_column="birth_date", confidence=.9, match_method="manual", evidence={"reason":"DOB"}, created_by="architect", transform_rule="datetime_to_date", transform_output_type="date")["field_mapping"]
    confirm_field_mapping(root, m2["id"], confirmed_by="owner", human_confirmed=True)
    assert mapping_readiness(root, plan["id"], contract["id"])["ready_for_v0.21.2"] is True


def test_target_insert_still_denied_v0211(tmp_path):
    root = make_root(tmp_path)
    t = target_conn(root)
    result = authorize_operation(root, t["id"], "insert")
    assert result["allowed"] is False and result["reason"] == "target_data_write_not_enabled_until_v0.22.0"


def test_mcp_exposes_only_read_schema_mapping_tools():
    from agentos.mcp_schema_mapping_gateway import TOOLS
    names = {item["name"] for item in TOOLS}
    assert names == {
        "agentos.db_schema_snapshot_get",
        "agentos.db_target_contract_get",
        "agentos.db_field_mappings_get",
        "agentos.db_field_mapping_suggest",
        "agentos.db_mapping_readiness_get",
    }
    assert all(all(token not in name for token in ("approve", "confirm", "register", "execute", "insert", "extract")) for name in names)


def test_no_record_extraction_or_arbitrary_sql_module_tools():
    from agentos.mcp_schema_mapping_gateway import TOOLS
    text = " ".join(item["name"] + " " + item["description"] for item in TOOLS).lower()
    assert "execute_sql" not in text
    assert "target_insert" not in text

def test_identical_source_snapshot_is_idempotent_and_does_not_stale_mapping(tmp_path):
    root = make_root(tmp_path)
    s, t, plan = plan_with_source(root)
    ss = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")["snapshot"]
    contract = approved_contract(root, plan, t["id"])
    m = add_field_mapping(root, consolidation_id=plan["id"], source_snapshot_id=ss["id"], target_contract_id=contract["id"], source_schema="dbo", source_table="BENH_NHAN", source_column="MA_BN", target_schema="public", target_table="patient", target_column="patient_code", confidence=1, match_method="manual", evidence={"reason":"key"}, created_by="architect")["field_mapping"]
    confirm_field_mapping(root, m["id"], confirmed_by="owner", human_confirmed=True)
    same = register_schema_snapshot(root, connection_id=s["id"], manifest=source_manifest(), captured_by="dba")
    assert same.get("unchanged") is True
    assert same["snapshot"]["id"] == ss["id"]
    assert get_field_mapping(root, m["id"])["field_mapping"]["status"] == "confirmed"
