"""Focused v0.32.0 Execution Identity & Model Provenance tests."""
from __future__ import annotations
import inspect,json,sqlite3
from pathlib import Path
import pytest
import agentos.execution_provenance as ep
from agentos import cli_runtime,mcp_runtime
from agentos.schema_version import CURRENT_SCHEMA_VERSION
ROOT=Path(__file__).resolve().parents[2]

def test_schema65_registered():
    assert CURRENT_SCHEMA_VERSION==65
    s=(ROOT/".agents/agentos/db.py").read_text(encoding="utf-8")
    assert "from .execution_provenance import migration_65" in s
    assert "migration_64, migration_65]" in s

def test_migration65_keeps_task_outcome_shape():
    c=sqlite3.connect(":memory:"); c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY)")
    c.execute("CREATE TABLE task_outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT NOT NULL,outcome TEXT NOT NULL)")
    before=[r[1] for r in c.execute("PRAGMA table_info(task_outcomes)")]
    ep.migration_65(c)
    after=[r[1] for r in c.execute("PRAGMA table_info(task_outcomes)")]
    assert before==after
    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"execution_provenance","task_outcome_provenance_links"} <= tables

def test_policy_privacy_authority():
    p=json.loads((ROOT/".agents/config/policy/execution_identity.json").read_text(encoding="utf-8"))["execution_identity_policy"]
    assert p["database_schema"]==65
    for k in ("provider_required","model_required","agent_id_required","recorded_by_required","context_hash_binding_required","provider_request_id_hash_only","separate_outcome_link_required"):
        assert p[k] is True
    for k in ("remote_provider_cryptographic_attestation_claimed","endpoint_url_persistence_allowed","credential_or_secret_persistence_allowed","raw_prompt_persistence_allowed","raw_response_persistence_allowed","context_authority_affected","instruction_authority","automatic_model_provider_selection","agent_plane_registration_allowed","mcp_mutation_allowed"):
        assert p[k] is False

def test_safe_labels_reject_secret_and_url():
    with pytest.raises(ep.ExecutionProvenanceError): ep._safe_label("Bearer x",field="provider_id",required=True)
    with pytest.raises(ep.ExecutionProvenanceError): ep._safe_label("https://example.test",field="deployment_id",required=True)

def test_external_declared_async_runtime_bound():
    class Bad:
        def execute(self,*a,**k): raise AssertionError
    x=ep._resolve_reference(Bad(),task_id="T1",session_id="S1",execution_ref_type="external_agent_run",execution_ref_id="r1")
    assert x["verification_class"]=="declared"
    class R:
        def fetchone(self): return {"task_id":"T1","session_id":"S1","spec_hash":"a"*64}
    class C:
        def execute(self,*a,**k): return R()
    x=ep._resolve_reference(C(),task_id="T1",session_id="S1",execution_ref_type="async_job",execution_ref_id="J1")
    assert x["verification_class"]=="runtime_bound" and x["execution_ref_hash"]=="a"*64

def test_outcome_conflict_blocked():
    class R:
        def fetchone(self): return {"provenance_id":"EP-1","task_id":"T1","session_id":"S1","agent_id":"a","model_id":"m","policy_revision":"0.32.0","context_revision":1,"secrets_included":0}
    class C:
        def execute(self,*a,**k): return R()
    with pytest.raises(ep.ExecutionProvenanceError,match="outcome_model_id_conflicts"):
        ep.resolve_provenance_for_outcome(C(),task_id="T1",provenance_id="EP-1",caller_model_id="other")

def test_evaluation_and_effectiveness_integration():
    e=(ROOT/".agents/agentos/evaluation.py").read_text(encoding="utf-8")
    assert all(x in e for x in ("execution_provenance_id","resolve_provenance_for_outcome","link_outcome_provenance"))
    l=(ROOT/".agents/agentos/learning_effectiveness.py").read_text(encoding="utf-8")
    assert all(x in l for x in ("task_outcome_provenance_links","execution_provenance ep","provenance_model_id","legacy_outcome_without_execution_provenance_excluded"))
    p=json.loads((ROOT/".agents/config/policy/learning.json").read_text(encoding="utf-8"))["governed_learning_policy"]["effectiveness"]
    assert p["provider_model_matching_required"] is True
    assert "ALTER TABLE task_outcomes" not in inspect.getsource(ep.migration_65)

def test_command_planes_exact():
    reg=cli_runtime.command_registry(); agent=cli_runtime.agent_command_registry(); priv=cli_runtime.privileged_command_registry()
    assert "execution-provenance-register" in reg and "execution-provenance-register" not in agent and "execution-provenance-register" in priv
    for cmd in ("execution-provenance-get","execution-provenance-status"):
        assert cmd in agent and cmd not in priv
    assert len(reg)==367
    assert len(agent)==269
    assert len(priv)==100

def test_mcp_and_multi_agent_nonclaims():
    assert len(mcp_runtime.ALL_TOOLS)==132
    assert "V0320" not in (ROOT/".agents/agentos/mcp_runtime.py").read_text(encoding="utf-8")
    assert '"auto_model_provider_select": False' in (ROOT/".agents/agentos/multi_agent_supervisor.py").read_text(encoding="utf-8")

def test_release_notes_preserve_nonclaims():
    n=(ROOT/"RELEASE_NOTES.md").read_text(encoding="utf-8")
    for x in ("v0.29.5 — Native Physical Isolation Extensions","v0.29.4 Restricted Token","restricted_token_attested = true","low_integrity_attested = true","host_filesystem_isolation_attested = false"):
        assert x in n
    assert "cryptographic" in n.lower() and "prompt injection" in n.lower()
