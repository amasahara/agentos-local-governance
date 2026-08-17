"""Path: .agents/tests/test_architecture_planning_v0260.py
Purpose: Regression tests for v0.26.0 Architecture-Aware Task Planning.
"""
from __future__ import annotations
from pathlib import Path
import pytest

from agentos.architecture_planning import (
    architecture_plan_status,
    mark_plans_stale_for_baseline_change,
)
from agentos.core import start_task
from agentos.db import SCHEMA_VERSION, connect
from agentos.human_decision import record_clarity_assessment
from agentos.planning import approve_plan, submit_plan
from agentos.mcp_v0260 import TOOLS as V0260_TOOLS


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root=tmp_path/'project'; (root/'.agents').mkdir(parents=True)
    monkeypatch.setenv('AGENTOS_AUDIT_HOME',str(tmp_path/'audit'))
    start_task(root,'T1','Change the service safely')
    record_clarity_assessment(root,'T1','pytest',objective_understood=True,scope_understood=True,constraints_understood=True,acceptance_understood=True)
    return root


def _active(root: Path, digest: str='a'*64, version: int=1) -> int:
    with connect(root,immediate=True) as c:
        cur=c.execute("""INSERT INTO architecture_baselines(
            baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by,activated_by,activated_at
        ) VALUES(?,?, 'active', ?,27,'human:test','human:test',CURRENT_TIMESTAMP)""",(f'b-{version}',version,digest))
        return int(cur.lastrowid)


def _plan() -> dict:
    return {
        'goal':'Change service',
        'requirements':['REQ-1 preserve behavior'],
        'files':['src/service.py'],
        'affected_architecture_sections':['ARCH-05','ARCH-12'],
        'expected_modules':['src/service.py'],
        'expected_dependency_edges':[],
        'acceptance_criteria':['existing tests remain green'],
        'tests':['tests/test_service.py'],
    }


def test_schema_54_architecture_planning_tables_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch)
    with connect(root) as c:
        version=c.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
        tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert version == SCHEMA_VERSION == 54
    assert {'task_plan_architecture_contexts','task_plan_architecture_events'} <= tables


def test_no_active_baseline_preserves_historical_plan_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch)
    submitted=submit_plan(root,'T1','S1',{'goal':'legacy','files':['src/a.py'],'tests':['tests/test_a.py']})
    assert submitted['architecture']['state']=='not_evaluable'
    approved=approve_plan(root,submitted['plan_id'],'human','reviewed')
    assert approved['status']=='active'


def test_active_baseline_requires_architecture_aware_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch); _active(root)
    with pytest.raises(RuntimeError,match='architecture_plan_blocked'):
        submit_plan(root,'T1','S1',{'goal':'legacy','files':['src/a.py']})


def test_system_pins_exact_active_baseline_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch); _active(root,'b'*64)
    submitted=submit_plan(root,'T1','S1',_plan())
    assert submitted['architecture']['architecture_baseline_hash']=='b'*64
    with connect(root) as c:
        row=c.execute('SELECT baseline_hash,impact_hash,state FROM task_plan_architecture_contexts WHERE plan_id=?',(submitted['plan_id'],)).fetchone()
    assert row['baseline_hash']=='b'*64 and row['state']=='bound' and len(row['impact_hash'])==64


def test_ai_cannot_spoof_baseline_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch); _active(root,'c'*64)
    plan=_plan(); plan['architecture_baseline_hash']='d'*64
    with pytest.raises(RuntimeError,match='supplied_baseline_hash_mismatch'):
        submit_plan(root,'T1','S1',plan)


def test_plan_approval_fails_closed_after_baseline_hash_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch); baseline_id=_active(root,'e'*64)
    submitted=submit_plan(root,'T1','S1',_plan())
    with connect(root,immediate=True) as c:
        c.execute('UPDATE architecture_baselines SET baseline_hash=? WHERE id=?',('f'*64,baseline_id))
    with pytest.raises(RuntimeError,match='architecture_plan_stale'):
        approve_plan(root,submitted['plan_id'],'human','reviewed')
    assert architecture_plan_status(root,'T1')['reason']=='architecture_baseline_changed' or architecture_plan_status(root,'T1')['plan_status']=='stale'


def test_first_architecture_activation_stales_unbound_submitted_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch)
    submitted=submit_plan(root,'T1','S1',{'goal':'legacy','files':['src/a.py']})
    baseline_id=_active(root,'1'*64)
    with connect(root,immediate=True) as c:
        report=mark_plans_stale_for_baseline_change(c,None,baseline_id)
        status=c.execute('SELECT status FROM task_plans WHERE id=?',(submitted['plan_id'],)).fetchone()['status']
    assert report['stale_plan_count']==1 and status=='stale'


def test_declared_forbidden_dependency_edge_blocks_before_plan_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=_root(tmp_path,monkeypatch); baseline_id=_active(root,'2'*64)
    with connect(root,immediate=True) as c:
        rev=c.execute("""INSERT INTO architecture_section_revisions(
            section_id,revision,title,applicability,authority_mode,markdown_hash,contract_hash,section_hash,markdown_content,contract_json,created_by
        ) VALUES('ARCH-12',1,'Dependency Graph','applicable','current',?,?,?,?,?,?)""",
        ('m'*64,'c'*64,'s'*64,'x','{"payload":{"forbidden_import_edges":[{"from":"service.*","import":"db.*"}]}}','human:test'))
        c.execute('INSERT INTO architecture_baseline_sections(baseline_id,section_id,section_revision_id,section_hash) VALUES(?,?,?,?)',(baseline_id,'ARCH-12',int(rev.lastrowid),'s'*64))
    plan=_plan(); plan['expected_dependency_edges']=[{'from':'service.api','import':'db.raw'}]
    with pytest.raises(RuntimeError,match='architecture_plan_blocked'):
        submit_plan(root,'T1','S1',plan)


def test_mcp_v0260_is_read_only_three_tool_surface() -> None:
    names={item['name'] for item in V0260_TOOLS}
    assert len(names)==3
    assert names=={'agentos.architecture_plan_get','agentos.architecture_plan_status_get','agentos.architecture_plan_impact_get'}
    assert not any(any(word in name for word in ('approve','submit','activate','mutate','waive')) for name in names)
