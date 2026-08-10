"""v0.22.6 focused regression for trusted secret resolution and lineage-key lifecycle."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pytest
from agentos.db import connect
from agentos.secret_lineage import (
    SecretLineageError, active_key, approve_provider, create_rotation_plan, review_rotation_plan,
    approve_rotation_plan, execute_rotation_plan, keyring_status, load_key, lookup_keys,
    provider_catalog, resolve_secret, resolve_runtime_secret, revoke_key,
)


def test_schema_42_and_foreign_keys(tmp_path: Path):
    with connect(tmp_path) as c:
        assert c.execute("select max(version) from schema_migrations").fetchone()[0] >= 42
        assert c.execute("pragma foreign_keys").fetchone()[0] == 1
        cols={r[1] for r in c.execute("pragma table_info(target_record_lineage)")}
        assert {"key_id","source_key_id","target_key_id"} <= cols


def test_registry_is_static_and_has_required_schemes():
    rows=provider_catalog(); schemes={x["scheme"] for x in rows}
    assert {"env","keychain","vault","file-secret"} <= schemes
    assert all(len(x["provider_hash"])==64 for x in rows)
    assert "importlib" not in json.dumps(rows).lower()


def test_unknown_capability_and_provider_fail_closed(tmp_path: Path):
    with pytest.raises(SecretLineageError):
        approve_provider(tmp_path,"env",capabilities=["arbitrary.shell"],approved_by="operator",human_confirmed=True)
    with pytest.raises(SecretLineageError):
        resolve_secret(tmp_path,"unknown://x",capability="db.source.select")


def test_env_secret_requires_exact_approval_and_does_not_persist_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENTOS_V0226_TEST_SECRET", json.dumps({"username":"alice","password":"DO_NOT_PERSIST_9226"}))
    with pytest.raises(SecretLineageError):
        resolve_secret(tmp_path,"env://AGENTOS_V0226_TEST_SECRET",capability="db.source.select")
    approve_provider(tmp_path,"env",capabilities=["db.source.select"],approved_by="operator",human_confirmed=True)
    secret=resolve_secret(tmp_path,"env://AGENTOS_V0226_TEST_SECRET",capability="db.source.select")
    assert secret["password"] == "DO_NOT_PERSIST_9226"
    with pytest.raises(SecretLineageError):
        resolve_secret(tmp_path,"env://AGENTOS_V0226_TEST_SECRET",capability="db.target.controlled_insert")
    db_bytes=(tmp_path/".agents/state/agentos.db").read_bytes()
    assert b"DO_NOT_PERSIST_9226" not in db_bytes
    assert b"alice" not in db_bytes


def test_secret_alias_and_dynamic_reference_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg=tmp_path/".agents/config/governance.json"; cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"secret_resolver_policy":{"aliases":{"source":"env://ALIAS_SECRET","bad":"importlib://evil.module:function"}}}))
    monkeypatch.setenv("ALIAS_SECRET", json.dumps({"user":"u","password":"p"}))
    approve_provider(tmp_path,"env",capabilities=["db.source.select"],approved_by="operator",human_confirmed=True)
    assert resolve_secret(tmp_path,"secret://source",capability="db.source.select")["user"] == "u"
    with pytest.raises(SecretLineageError):
        resolve_secret(tmp_path,"secret://bad",capability="db.source.select")


def test_file_secret_owner_only(tmp_path: Path):
    secret_dir=tmp_path/".agents/state/secrets"; secret_dir.mkdir(parents=True)
    path=secret_dir/"db.json"; path.write_text(json.dumps({"user":"u","password":"p"})); path.chmod(0o600)
    approve_provider(tmp_path,"file-secret",capabilities=["db.source.select"],approved_by="operator",human_confirmed=True)
    assert resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")["user"] == "u"
    if os.name == "nt":
        pytest.skip("POSIX chmod mode-bit enforcement is not a Windows security primitive")
    path.chmod(0o644)
    with pytest.raises(SecretLineageError):
        resolve_secret(tmp_path,"file-secret://db.json",capability="db.source.select")


def test_callback_injection_is_compat_only_and_denied_on_governed_root(tmp_path: Path):
    callback=lambda ref: {"password":"compat"}
    assert resolve_runtime_secret(tmp_path,"env://x",capability="db.source.select",compatibility_resolver=callback)["password"] == "compat"
    (tmp_path/"AGENTS.md").write_text("# authority\n")
    (tmp_path/"VERSION").write_text("0.22.6\n")
    cfg=tmp_path/".agents/config/governance.json"; cfg.parent.mkdir(parents=True,exist_ok=True); cfg.write_text("{}\n")
    with pytest.raises(SecretLineageError):
        resolve_runtime_secret(tmp_path,"env://x",capability="db.source.select",compatibility_resolver=callback)


def test_keyring_status_is_read_only_before_initialization(tmp_path: Path):
    status=keyring_status(tmp_path)
    assert status["initialized"] is False
    assert status["keys"] == []
    assert not (tmp_path/".agents/state/lineage-keys").exists()


def test_legacy_key_import_backfills_without_rehmac_and_removes_single_key(tmp_path: Path):
    legacy=tmp_path/".agents/state/identity_lineage.key"; legacy.parent.mkdir(parents=True); material=b"L"*32; legacy.write_bytes(material)
    with connect(tmp_path) as c:
        c.execute("INSERT INTO canonical_entities(entity_uuid,consolidation_id,target_schema,target_table,exact_key_fingerprint,created_at) VALUES('e',1,'s','t','historic-hmac','now')")
    kid,key=active_key(tmp_path)
    assert key == material
    assert not legacy.exists()
    with connect(tmp_path) as c:
        row=c.execute("select exact_key_fingerprint,key_id from canonical_entities where entity_uuid='e'").fetchone()
        assert row[0] == "historic-hmac"
        assert row[1] == kid


def test_rotation_retains_retired_for_lookup_and_new_active(tmp_path: Path):
    old_id,old_material=active_key(tmp_path)
    p=create_rotation_plan(tmp_path,reason="scheduled",created_by="operator")["plan"]["id"]
    review_rotation_plan(tmp_path,p,reviewed_by="reviewer",human_confirmed=True)
    approve_rotation_plan(tmp_path,p,approved_by="approver",human_confirmed=True)
    execute_rotation_plan(tmp_path,p,executed_by="operator")
    status={x["key_id"]:x["status"] for x in keyring_status(tmp_path)["keys"]}
    assert status[old_id]=="retired"
    new_id,new_material=active_key(tmp_path)
    assert new_id != old_id and new_material != old_material
    assert load_key(tmp_path,old_id) == old_material
    assert {kid for kid,_ in lookup_keys(tmp_path)} == {old_id,new_id}


def test_revoked_retired_key_is_not_lookup_capable(tmp_path: Path):
    old_id,_=active_key(tmp_path)
    p=create_rotation_plan(tmp_path,reason="rotate",created_by="operator")["plan"]["id"]
    review_rotation_plan(tmp_path,p,reviewed_by="reviewer",human_confirmed=True); approve_rotation_plan(tmp_path,p,approved_by="approver",human_confirmed=True); execute_rotation_plan(tmp_path,p,executed_by="operator")
    revoke_key(tmp_path,old_id,revoked_by="operator",human_confirmed=True)
    assert old_id not in {kid for kid,_ in lookup_keys(tmp_path)}
    with pytest.raises(SecretLineageError): load_key(tmp_path,old_id)


def test_unified_catalog_exposes_read_only_metadata_only():
    from agentos.cli_runtime import command_registry, PRIVILEGED_COMMANDS
    from agentos.mcp_runtime import ALL_TOOLS
    cli=command_registry(); assert len(cli)==len(set(cli))
    assert "lineage-keyring-initialize" in PRIVILEGED_COMMANDS
    names=[x["name"] for x in ALL_TOOLS]; assert len(names)==len(set(names))
    assert "agentos.secret_provider_catalog_get" in names and "agentos.lineage_keyring_get" in names
    forbidden=("approve","revoke","execute","rotate","credential","secret_resolve","initialize")
    assert not any(any(word in n.lower() for word in forbidden) for n in names if n.startswith("agentos.secret_") or n.startswith("agentos.lineage_"))


def test_keyring_recovers_single_crash_left_material_without_rehmac(tmp_path: Path):
    """A legacy move interrupted before metadata commit can resume deterministically."""
    material=b"R"*32
    import hashlib
    kid="lk_"+hashlib.sha256(material).hexdigest()[:24]
    key_path=tmp_path/".agents/state/lineage-keys"/f"{kid}.key"
    key_path.parent.mkdir(parents=True); key_path.write_bytes(material); key_path.chmod(0o600)
    with connect(tmp_path) as c:
        c.execute("INSERT INTO canonical_entities(entity_uuid,consolidation_id,target_schema,target_table,exact_key_fingerprint,created_at) VALUES('e',1,'s','t','historic-hmac','now')")
    active_id,active_material=active_key(tmp_path)
    assert (active_id,active_material)==(kid,material)
    with connect(tmp_path) as c:
        row=c.execute("select exact_key_fingerprint,key_id from canonical_entities where entity_uuid='e'").fetchone()
        assert tuple(row)==("historic-hmac",kid)


def test_key_material_path_tamper_fails_closed(tmp_path: Path):
    """Database path tampering cannot turn key loading into an arbitrary file read."""
    kid,_=active_key(tmp_path)
    outside=tmp_path/"not-a-lineage-key"; outside.write_bytes(b"X"*32)
    with connect(tmp_path) as c:
        c.execute("update lineage_keys set material_path=? where key_id=?", ("not-a-lineage-key",kid))
    with pytest.raises(SecretLineageError):
        load_key(tmp_path,kid)


def test_keychain_provider_contract_with_trusted_optional_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The keychain URI contract is executable without persisting returned values."""
    import sys, types
    fake=types.ModuleType("keyring")
    fake.get_password=lambda service, account: json.dumps({"service":service,"account":account,"password":"KEYCHAIN_ONLY"})
    monkeypatch.setitem(sys.modules,"keyring",fake)
    approve_provider(tmp_path,"keychain",capabilities=["db.source.select"],approved_by="operator",human_confirmed=True)
    value=resolve_secret(tmp_path,"keychain://db-service/db-account",capability="db.source.select")
    assert value["password"]=="KEYCHAIN_ONLY"
    assert b"KEYCHAIN_ONLY" not in (tmp_path/".agents/state/agentos.db").read_bytes()


def test_vault_provider_contract_with_trusted_optional_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The Vault KV-v2 URI contract resolves an approved object in memory only."""
    import sys, types
    class KV2:
        def read_secret_version(self, *, path, mount_point):
            assert (mount_point,path)==("secret","prod/database")
            return {"data":{"data":{"credential":{"username":"u","password":"VAULT_ONLY"}}}}
    class Client:
        def __init__(self, **kwargs): self.secrets=types.SimpleNamespace(kv=types.SimpleNamespace(v2=KV2()))
        def is_authenticated(self): return True
    fake=types.ModuleType("hvac"); fake.Client=Client
    monkeypatch.setitem(sys.modules,"hvac",fake)
    approve_provider(tmp_path,"vault",capabilities=["db.target.controlled_insert"],approved_by="operator",human_confirmed=True)
    value=resolve_secret(tmp_path,"vault://secret/prod/database#credential",capability="db.target.controlled_insert")
    assert value["password"]=="VAULT_ONLY"
    assert b"VAULT_ONLY" not in (tmp_path/".agents/state/agentos.db").read_bytes()


def test_privileged_secret_approval_fails_closed_without_task_session_on_governed_root(tmp_path: Path):
    """Production roots cannot bypass the v0.22.4 governed mutation boundary."""
    from agentos.governance_enforcement import GovernanceEnforcementError
    (tmp_path/"AGENTS.md").write_text("# authority\n")
    (tmp_path/"VERSION").write_text("0.22.6\n")
    cfg=tmp_path/".agents/config/governance.json"; cfg.parent.mkdir(parents=True); cfg.write_text('{"version":"0.22.6"}\n')
    with pytest.raises(GovernanceEnforcementError, match="task_id_and_session_id_required"):
        approve_provider(tmp_path,"env",capabilities=["db.source.select"],approved_by="operator",human_confirmed=True)
