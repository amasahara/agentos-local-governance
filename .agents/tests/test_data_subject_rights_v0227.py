"""Focused v0.22.7 privacy lifecycle regression tests."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import pytest


def _root(tmp_path: Path) -> Path:
    root=tmp_path/'r'; (root/'.agents').mkdir(parents=True); return root


def _entity(root: Path, entity_uuid: str='entity-001', key_id: str | None='legacy') -> int:
    from agentos.db import connect
    with connect(root) as c:
        cur=c.execute("INSERT INTO canonical_entities(entity_uuid,consolidation_id,target_schema,target_table,exact_key_fingerprint,created_at,key_id) VALUES(?,1,'public','people','fp','now',?)",(entity_uuid,key_id))
        return int(cur.lastrowid)


def _request_plan(root: Path, entity_uuid='entity-001'):
    from agentos.data_subject_rights import create_erasure_request, create_erasure_plan, review_erasure_plan, approve_erasure_plan
    req=create_erasure_request(root,entity_uuid,reason_code='subject_request',requested_by='operator',human_confirmed=True)
    plan=create_erasure_plan(root,req['request_id'],created_by='operator')
    review_erasure_plan(root,plan['plan_id'],reviewed_by='reviewer',human_confirmed=True)
    approve_erasure_plan(root,plan['plan_id'],approved_by='approver',human_confirmed=True)
    return req,plan


def test_schema_43_and_foreign_keys(tmp_path):
    from agentos.db import connect
    root=_root(tmp_path)
    with connect(root) as c:
        assert c.execute('select max(version) from schema_migrations').fetchone()[0] >= 43
        assert c.execute('select 1 from schema_migrations where version=43').fetchone()[0] == 1
        assert c.execute('pragma foreign_keys').fetchone()[0] == 1
        assert c.execute('pragma secure_delete').fetchone()[0] == 1
        tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        assert {'data_subject_erasure_requests','data_subject_erasure_plans','privacy_tombstones'} <= tables


def test_erasure_lifecycle_is_idempotent_and_tombstones_without_target_mutation(tmp_path):
    from agentos.db import connect
    from agentos.data_subject_rights import execute_erasure_plan
    root=_root(tmp_path); eid=_entity(root)
    req,plan=_request_plan(root)
    first=execute_erasure_plan(root,plan['plan_id'],executed_by='operator',human_confirmed=True)
    second=execute_erasure_plan(root,plan['plan_id'],executed_by='operator',human_confirmed=True)
    assert first['execution']['local_erasure_completed'] is True
    assert first['execution']['external_target_erasure_required'] is False
    assert second['idempotent'] is True
    with connect(root) as c:
        entity=c.execute('select entity_uuid,privacy_status,key_id,exact_key_fingerprint from canonical_entities where id=?',(eid,)).fetchone()
        assert entity['privacy_status']=='tombstoned' and entity['key_id'] is None
        assert entity['entity_uuid'].startswith('tombstone:') and entity['entity_uuid'] != 'entity-001'
        assert entity['exact_key_fingerprint'].startswith('erased:')
        request_row=c.execute('select entity_locator_hash from data_subject_erasure_requests where id=?',(req['request_id'],)).fetchone()
        assert request_row[0] and request_row[0] != 'entity-001'
        assert c.execute('select count(*) from privacy_tombstones where canonical_entity_id=?',(eid,)).fetchone()[0]==1
        assert c.execute('select count(*) from data_subject_erasure_executions where plan_id=?',(plan['plan_id'],)).fetchone()[0]==1


def test_external_target_erasure_is_flag_only_and_local_lineage_removed(tmp_path):
    from agentos.db import connect
    from agentos.data_subject_rights import create_erasure_request, create_erasure_plan, review_erasure_plan, approve_erasure_plan, execute_erasure_plan
    root=_root(tmp_path); eid=_entity(root)
    # Build historical lineage using a raw fixture connection with FK checks disabled; production code never does this.
    db=root/'.agents/state/agentos.db'; raw=sqlite3.connect(db)
    raw.execute("INSERT INTO target_record_lineage(canonical_entity_id,insert_run_id,extraction_batch_id,target_connection_id,target_schema,target_table,target_record_token,source_record_token,source_connection_id,source_snapshot_hash,source_schema,source_table,source_locator_hash,mapping_set_hash,target_contract_hash,commit_receipt_hash,created_at,key_id,source_key_id,target_key_id) VALUES(?,999,998,997,'public','people','target-token','source-token',996,'snap','public','people','loc','map','contract','receipt','now','legacy','legacy','legacy')",(eid,)); raw.commit(); raw.close()
    req=create_erasure_request(root,'entity-001',reason_code='subject_request',requested_by='operator',human_confirmed=True)
    plan=create_erasure_plan(root,req['request_id'],created_by='operator')
    assert plan['external_target_erasure_required'] is True and plan['target_update_delete_permitted'] is False
    review_erasure_plan(root,plan['plan_id'],reviewed_by='r',human_confirmed=True); approve_erasure_plan(root,plan['plan_id'],approved_by='a',human_confirmed=True)
    out=execute_erasure_plan(root,plan['plan_id'],executed_by='x',human_confirmed=True)
    assert out['execution']['external_target_erasure_required'] is True
    with connect(root) as c: assert c.execute('select count(*) from target_record_lineage where canonical_entity_id=?',(eid,)).fetchone()[0]==0


def test_active_or_in_doubt_target_operation_blocks_erasure_plan(tmp_path):
    from agentos.data_subject_rights import create_erasure_request, create_erasure_plan, DataSubjectRightsError
    root=_root(tmp_path); eid=_entity(root)
    db=root/'.agents/state/agentos.db'; raw=sqlite3.connect(db)
    raw.execute("INSERT INTO db_target_insert_runs(id,insert_uuid,extraction_batch_id,consolidation_id,target_connection_id,target_contract_id,target_schema,target_table,insert_plan_version,insert_plan_json,insert_plan_hash,staging_path,staging_hash,staging_manifest_hash,extraction_plan_hash,mapping_set_hash,target_contract_hash,target_snapshot_hash,row_count,column_order_json,chunk_size,status,created_by,created_at) VALUES(999,'i',998,1,997,996,'public','people',1,'{}','ph','.agents/runtime/stage','sh','mh','eh','map','contract','snap',1,'[]',1,'in_doubt','op','now')")
    raw.execute("INSERT INTO target_record_lineage(canonical_entity_id,insert_run_id,extraction_batch_id,target_connection_id,target_schema,target_table,target_record_token,source_record_token,source_connection_id,source_snapshot_hash,source_schema,source_table,source_locator_hash,mapping_set_hash,target_contract_hash,commit_receipt_hash,created_at) VALUES(?,999,998,997,'public','people','t','s',996,'snap','public','people','loc','map','contract','receipt','now')",(eid,)); raw.commit(); raw.close()
    req=create_erasure_request(root,'entity-001',reason_code='subject_request',requested_by='op',human_confirmed=True)
    with pytest.raises(DataSubjectRightsError, match='active_or_in_doubt_target_operation'):
        create_erasure_plan(root,req['request_id'],created_by='op')


def test_unauthorized_erasure_fails_closed_on_agentos_project(tmp_path):
    from agentos.data_subject_rights import create_erasure_request
    from agentos.governance_enforcement import GovernanceEnforcementError
    root=_root(tmp_path); _entity(root)
    (root/'AGENTS.md').write_text('# AgentOS\n'); (root/'VERSION').write_text('0.22.7\n'); (root/'.agents/config').mkdir(parents=True,exist_ok=True); (root/'.agents/config/governance.json').write_text(json.dumps({'version':'0.22.7'}))
    with pytest.raises(GovernanceEnforcementError, match='task_id_and_session_id_required'):
        create_erasure_request(root,'entity-001',reason_code='subject_request',requested_by='op',human_confirmed=True)


def test_lineage_key_is_not_needed_after_tombstone(tmp_path):
    from agentos.db import connect
    from agentos.secret_lineage import ensure_keyring, active_key, keyring_status
    from agentos.data_subject_rights import execute_erasure_plan
    root=_root(tmp_path); ensure_keyring(root); kid,_=active_key(root); eid=_entity(root,key_id=kid)
    req,plan=_request_plan(root); execute_erasure_plan(root,plan['plan_id'],executed_by='op',human_confirmed=True)
    with connect(root) as c:
        assert c.execute('select key_id from canonical_entities where id=?',(eid,)).fetchone()[0] is None
    assert any(k['key_id']==kid for k in keyring_status(root)['keys'])


def test_sensitive_values_do_not_enter_privacy_events_or_mcp_catalog(tmp_path):
    from agentos.db import connect
    from agentos.data_subject_rights import execute_erasure_plan
    from agentos.mcp_runtime import ALL_TOOLS
    root=_root(tmp_path); _entity(root,'entity-sensitive'); req,plan=_request_plan(root,'entity-sensitive'); execute_erasure_plan(root,plan['plan_id'],executed_by='op',human_confirmed=True)
    with connect(root) as c:
        events='\n'.join(str(r[0]) for r in c.execute('select event_json from data_subject_erasure_events'))
        retained='\n'.join(str(x) for row in c.execute('select entity_uuid,exact_key_fingerprint from canonical_entities') for x in row)
        requests='\n'.join(str(x) for row in c.execute('select entity_locator_hash,request_hash from data_subject_erasure_requests') for x in row)
    assert 'entity-sensitive' not in events and 'source-token' not in events and 'target-token' not in events
    assert 'entity-sensitive' not in retained and 'entity-sensitive' not in requests
    names=[t['name'] for t in ALL_TOOLS]
    assert len(names)==len(set(names))
    assert not any(any(x in n for x in ('erasure_execute','erasure_approve','erasure_review','target_update','target_delete')) for n in names)


def test_request_and_plan_are_database_immutable(tmp_path):
    from agentos.db import connect
    root=_root(tmp_path); _entity(root); req,plan=_request_plan(root)
    with pytest.raises(sqlite3.IntegrityError, match='immutable_erasure_request'):
        with connect(root) as c:
            c.execute("UPDATE data_subject_erasure_requests SET reason_code='changed' WHERE id=?",(req['request_id'],))
    with pytest.raises(sqlite3.IntegrityError, match='immutable_erasure_plan'):
        with connect(root) as c:
            c.execute("DELETE FROM data_subject_erasure_plans WHERE id=?",(plan['plan_id'],))


def test_pending_identity_candidate_for_entity_blocks_erasure_plan(tmp_path):
    from agentos.data_subject_rights import create_erasure_request, create_erasure_plan, DataSubjectRightsError
    root=_root(tmp_path); _entity(root)
    db=root/'.agents/state/agentos.db'; raw=sqlite3.connect(db)
    raw.execute("INSERT INTO identity_resolution_runs(id,resolution_uuid,extraction_batch_id,policy_id,input_staging_path,input_staging_hash,status,created_by,created_at) VALUES(999,'r',998,997,'.agents/runtime/in.jsonl','h','awaiting_human','op','now')")
    raw.execute("INSERT INTO identity_candidates(resolution_run_id,source_record_token,matched_entity_uuid,candidate_hash,match_method,evidence_json,status,created_at) VALUES(999,'source-hmac','entity-001','candidate-hash','deterministic_exact_multifield_candidate','{}','pending','now')")
    raw.commit(); raw.close()
    req=create_erasure_request(root,'entity-001',reason_code='subject_request',requested_by='op',human_confirmed=True)
    with pytest.raises(DataSubjectRightsError, match='active_identity_operation'):
        create_erasure_plan(root,req['request_id'],created_by='op')


def test_old_pseudonymous_uuid_can_only_resolve_status_through_one_way_locator(tmp_path):
    from agentos.data_subject_rights import execute_erasure_plan, erasure_status_get, erasure_request_get
    root=_root(tmp_path); _entity(root,'entity-old-ref'); req,plan=_request_plan(root,'entity-old-ref')
    execute_erasure_plan(root,plan['plan_id'],executed_by='op',human_confirmed=True)
    status=erasure_status_get(root,'entity-old-ref')
    assert status['privacy_status']=='tombstoned'
    assert status['entity_reference']=='one_way_request_locator'
    request=erasure_request_get(root,req['request_id'])
    assert 'entity_uuid' not in request and 'entity_locator_hash' not in request
    assert request['entity_locator_retained']=='one_way_hash_only'


def test_in_doubt_insert_for_related_extraction_batch_blocks_without_finalized_lineage(tmp_path):
    from agentos.data_subject_rights import create_erasure_request, create_erasure_plan, DataSubjectRightsError
    root=_root(tmp_path); eid=_entity(root)
    db=root/'.agents/state/agentos.db'; raw=sqlite3.connect(db)
    raw.execute("INSERT INTO identity_resolution_runs(id,resolution_uuid,extraction_batch_id,policy_id,input_staging_path,input_staging_hash,status,created_by,created_at) VALUES(999,'r',998,997,'.agents/runtime/in.jsonl','h','resolved','op','now')")
    raw.execute("INSERT INTO identity_bindings(canonical_entity_id,resolution_run_id,source_connection_id,source_snapshot_hash,source_schema,source_table,source_locator_hash,source_record_token,exact_key_fingerprint,decision_type,created_at) VALUES(?,999,996,'snap','public','people','loc','subject-token','fp','exact','now')",(eid,))
    raw.execute("INSERT INTO db_target_insert_runs(id,insert_uuid,extraction_batch_id,consolidation_id,target_connection_id,target_contract_id,target_schema,target_table,insert_plan_version,insert_plan_json,insert_plan_hash,staging_path,staging_hash,staging_manifest_hash,extraction_plan_hash,mapping_set_hash,target_contract_hash,target_snapshot_hash,row_count,column_order_json,chunk_size,status,created_by,created_at) VALUES(999,'i',998,1,997,996,'public','people',1,'{}','ph','.agents/runtime/stage','sh','mh','eh','map','contract','snap',1,'[]',1,'in_doubt','op','now')")
    raw.commit(); raw.close()
    req=create_erasure_request(root,'entity-001',reason_code='subject_request',requested_by='op',human_confirmed=True)
    with pytest.raises(DataSubjectRightsError, match='active_or_in_doubt_target_operation'):
        create_erasure_plan(root,req['request_id'],created_by='op')

def test_erasure_reason_code_is_bounded(tmp_path):
    from agentos.db import connect
    from agentos.data_subject_rights import DataSubjectRightsError, create_erasure_request
    root=_root(tmp_path)
    _entity(root)
    with pytest.raises(DataSubjectRightsError, match='unsupported_erasure_reason_code'):
        create_erasure_request(root,'entity-001',reason_code='subject_request: Alice@example.com',requested_by='op',human_confirmed=True)


def test_erasure_never_deletes_non_staging_project_path(tmp_path):
    root=_root(tmp_path)
    protected=root/'README.keep'; protected.write_text('keep',encoding='utf-8')
    # Directly exercise the bounded path resolver: even compromised state cannot turn privacy purge into arbitrary project deletion.
    from agentos.data_subject_rights import _delete_artifacts
    removed=_delete_artifacts(root,[str(protected.relative_to(root))])
    assert removed == (0,0)
    assert protected.read_text(encoding='utf-8') == 'keep'
