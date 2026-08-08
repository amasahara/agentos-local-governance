from pathlib import Path
import json
import sqlite3

import pytest

from agentos.database_boundary import (
    DatabaseBoundaryError,
    add_source,
    authorize_operation,
    create_consolidation,
    get_connection,
    get_consolidation,
    migration_35,
    register_connection,
    sync_database_boundary_schema,
    verify_source_readonly,
)


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / ".agents/state").mkdir(parents=True)
    sqlite3.connect(root / ".agents/state/agentos.db").close()
    return root


def source(root: Path, alias="source1", domain="healthcare"):
    return register_connection(
        root,
        connection_alias=alias,
        role="SOURCE",
        engine="mssql",
        host="source.internal",
        database_name="HIS",
        domain_id=domain,
        credential_ref=f"secret://db/{alias}",
        created_by="operator",
    )["connection"]


def target(root: Path, alias="target1", domain="healthcare"):
    return register_connection(
        root,
        connection_alias=alias,
        role="TARGET",
        engine="postgresql",
        host="target.internal",
        database_name="UnifiedHIS",
        domain_id=domain,
        credential_ref=f"secret://db/{alias}",
        created_by="operator",
    )["connection"]


def verify(root: Path, cid: int):
    return verify_source_readonly(root, cid, verified_by="dba", method="grant_review", evidence="Ticket DB-1: SELECT/catalog grants only", human_confirmed=True)


def test_schema_35_created(tmp_path):
    root = make_root(tmp_path)
    assert sync_database_boundary_schema(root)["schema"] == 35


def test_supported_source_registration(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    assert c["role"] == "SOURCE"
    assert c["data_write_enabled"] is False


def test_target_registration_write_disabled(tmp_path):
    root = make_root(tmp_path)
    c = target(root)
    assert c["role"] == "TARGET"
    assert c["data_write_enabled"] is False


def test_raw_credential_rejected(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(DatabaseBoundaryError):
        register_connection(root, connection_alias="bad1", role="SOURCE", engine="mysql", host="h", database_name="d", domain_id="healthcare", credential_ref="mysql://user:pass@host/db", created_by="op")


def test_tls_false_rejected(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(DatabaseBoundaryError):
        register_connection(root, connection_alias="bad2", role="SOURCE", engine="mysql", host="h", database_name="d", domain_id="healthcare", credential_ref="secret://db/bad2", created_by="op", tls_required=False)


def test_unsupported_engine_rejected(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(DatabaseBoundaryError):
        register_connection(root, connection_alias="bad3", role="SOURCE", engine="sqlite", host="h", database_name="d", domain_id="healthcare", credential_ref="secret://db/bad3", created_by="op")


def test_credentials_redacted_from_get(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    got = get_connection(root, c["id"])["connection"]
    assert got["credential_ref"] == "<redacted-ref>"


def test_source_requires_human_readonly_verification(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    with pytest.raises(DatabaseBoundaryError):
        verify_source_readonly(root, c["id"], verified_by="dba", method="grant_review", evidence="ticket", human_confirmed=False)


def test_target_cannot_be_readonly_verified_as_source(tmp_path):
    root = make_root(tmp_path)
    c = target(root)
    with pytest.raises(DatabaseBoundaryError):
        verify(root, c["id"])


def test_secret_in_evidence_rejected(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    with pytest.raises(DatabaseBoundaryError):
        verify_source_readonly(root, c["id"], verified_by="dba", method="grant_review", evidence="password=secret", human_confirmed=True)


def test_source_select_allowed_after_verification(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    verify(root, c["id"])
    assert authorize_operation(root, c["id"], "select_read")["allowed"] is True


def test_source_insert_denied(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    verify(root, c["id"])
    result = authorize_operation(root, c["id"], "insert")
    assert result["allowed"] is False and result["reason"] == "source_write_forbidden"


def test_source_update_denied(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    verify(root, c["id"])
    assert authorize_operation(root, c["id"], "update")["allowed"] is False


def test_unverified_source_read_denied(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    assert authorize_operation(root, c["id"], "select_read")["reason"] == "source_not_readonly_verified"


def test_target_select_allowed(tmp_path):
    root = make_root(tmp_path)
    c = target(root)
    assert authorize_operation(root, c["id"], "select_read")["allowed"] is True


def test_target_insert_denied_until_v0220(tmp_path):
    root = make_root(tmp_path)
    c = target(root)
    result = authorize_operation(root, c["id"], "insert")
    assert result["allowed"] is False
    assert result["reason"] == "target_data_write_not_enabled_until_v0.22.0"


def test_consolidation_requires_target_role(tmp_path):
    root = make_root(tmp_path)
    c = source(root)
    with pytest.raises(DatabaseBoundaryError):
        create_consolidation(root, target_connection_id=c["id"], created_by="op")


def test_source_must_be_verified_before_add(tmp_path):
    root = make_root(tmp_path)
    s = source(root)
    t = target(root)
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="op")["consolidation"]
    with pytest.raises(DatabaseBoundaryError):
        add_source(root, plan["id"], s["id"], registered_by="op")


def test_source_target_domain_must_match(tmp_path):
    root = make_root(tmp_path)
    s = source(root, domain="retail")
    verify(root, s["id"])
    t = target(root, domain="healthcare")
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="op")["consolidation"]
    with pytest.raises(DatabaseBoundaryError):
        add_source(root, plan["id"], s["id"], registered_by="op")


def test_multiple_verified_sources_supported(tmp_path):
    root = make_root(tmp_path)
    t = target(root)
    s1 = source(root, alias="src1")
    s2 = source(root, alias="src2")
    verify(root, s1["id"]); verify(root, s2["id"])
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="op")["consolidation"]
    add_source(root, plan["id"], s1["id"], registered_by="op")
    state = add_source(root, plan["id"], s2["id"], registered_by="op")
    assert len(state["sources"]) == 2


def test_duplicate_source_rejected(tmp_path):
    root = make_root(tmp_path)
    t = target(root); s = source(root); verify(root, s["id"])
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="op")["consolidation"]
    add_source(root, plan["id"], s["id"], registered_by="op")
    with pytest.raises(DatabaseBoundaryError):
        add_source(root, plan["id"], s["id"], registered_by="op")


def test_consolidation_reports_boundary_invariants(tmp_path):
    root = make_root(tmp_path)
    t = target(root); s = source(root); verify(root, s["id"])
    plan = create_consolidation(root, target_connection_id=t["id"], created_by="op")["consolidation"]
    add_source(root, plan["id"], s["id"], registered_by="op")
    state = get_consolidation(root, plan["id"])
    assert state["invariants"]["exactly_one_target"] is True
    assert state["invariants"]["target_data_write_enabled"] is False
    assert state["invariants"]["arbitrary_sql_exposed"] is False


def test_mcp_exposes_only_read_boundary_tools():
    from agentos.mcp_database_boundary_gateway import TOOLS
    names = {item["name"] for item in TOOLS}
    assert names == {"agentos.db_connection_get", "agentos.db_consolidation_get", "agentos.db_boundary_check"}
    assert all("register" not in name and "verify" not in name and "execute" not in name for name in names)


def test_no_arbitrary_sql_operation_is_allowed(tmp_path):
    root = make_root(tmp_path)
    t = target(root)
    result = authorize_operation(root, t["id"], "execute_sql")
    assert result["allowed"] is False
