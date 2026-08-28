"""Path: .agents/tests/test_completion_verification_v0290.py
Purpose: Verify the Phase-1 v0.29.0 independent completion-verification core.
"""

from __future__ import annotations

import contextlib
import hashlib
import sqlite3
from pathlib import Path

import pytest

from agentos import completion_verification as cv


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "agentos.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(
        """
        CREATE TABLE tasks(id TEXT PRIMARY KEY);

        CREATE TABLE session_tokens(
            token_hash TEXT PRIMARY KEY,
            token_id TEXT NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            capability_set_json TEXT NOT NULL DEFAULT '[]',
            issued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        );

        CREATE TABLE task_role_assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            token_id TEXT,
            role TEXT NOT NULL,
            permissions_json TEXT NOT NULL DEFAULT '[]',
            assigned_by TEXT NOT NULL DEFAULT 'test',
            status TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cv.migration_62(con)
    con.executemany(
        "INSERT INTO tasks(id) VALUES(?)",
        [("producer-task",), ("reviewer-task",), ("other-task",)],
    )
    con.execute(
        """
        INSERT INTO session_tokens(
            token_hash,token_id,session_id,task_id,capability_set_json,expires_at
        ) VALUES('p','tok-p','producer-session','producer-task','[]','2999-01-01 00:00:00')
        """
    )
    con.execute(
        """
        INSERT INTO session_tokens(
            token_hash,token_id,session_id,task_id,capability_set_json,expires_at
        ) VALUES('r','tok-r','reviewer-session','reviewer-task','[]','2999-01-01 00:00:00')
        """
    )
    con.execute(
        """
        INSERT INTO task_role_assignments(
            task_id,session_id,token_id,role,permissions_json,assigned_by,status
        ) VALUES('producer-task','producer-session','tok-p','executor','[]','test','active')
        """
    )
    con.execute(
        """
        INSERT INTO task_role_assignments(
            task_id,session_id,token_id,role,permissions_json,assigned_by,status
        ) VALUES('reviewer-task','reviewer-session','tok-r','reviewer','[]','test','active')
        """
    )
    con.commit()
    con.close()

    @contextlib.contextmanager
    def rw(_root, immediate=False):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        if immediate:
            c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    @contextlib.contextmanager
    def ro(_root):
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
        finally:
            c.close()

    events = []

    def signed(_root, event_type, payload, task_id, session_id):
        digest = hashlib.sha256(
            repr((event_type, payload, task_id, session_id, len(events))).encode()
        ).hexdigest()
        events.append((event_type, payload, task_id, session_id, digest))
        return {"event_hash": digest}

    monkeypatch.setattr(cv, "connect", rw)
    monkeypatch.setattr(cv, "connect_read_only", ro)
    monkeypatch.setattr(cv, "append_signed_event", signed)

    return {"root": tmp_path, "rw": rw, "ro": ro, "events": events}


def _subject(value: str = "hash-a"):
    return {
        "plan_hash": "plan-1",
        "result_hash": value,
        "tests_receipt": "tests-1",
    }


def _request(runtime, payload=None):
    return cv.request_completion(
        runtime["root"],
        subject_type="workflow",
        subject_id="producer-task:default",
        task_id="producer-task",
        producer_task_id="producer-task",
        producer_session_id="producer-session",
        subject_payload=payload or _subject(),
        required_checks=["evidence", "tests"],
    )


def _pass(runtime, request_id, payload=None):
    return cv.verify_completion(
        runtime["root"],
        request_id=request_id,
        verifier_task_id="reviewer-task",
        verifier_session_id="reviewer-session",
        observed_subject_payload=payload or _subject(),
        verdict="pass",
        checks={"evidence": True, "tests": True},
        evidence={"claim_ids": [1], "test_receipt": "tests-1"},
    )


def test_migration_62_is_additive(runtime):
    with runtime["ro"](runtime["root"]) as c:
        names = {
            r["name"]
            for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {
        "completion_verification_requests",
        "completion_verification_attempts",
    } <= names


def test_subject_hash_is_deterministic_and_identity_bound():
    a = cv.completion_subject_hash("workflow", "x", "T1", {"b": 2, "a": 1})
    b = cv.completion_subject_hash("workflow", "x", "T1", {"a": 1, "b": 2})
    c = cv.completion_subject_hash("workflow", "y", "T1", {"a": 1, "b": 2})
    assert a == b
    assert a != c


def test_request_requires_active_producer_session(runtime):
    with runtime["rw"](runtime["root"]) as c:
        c.execute("UPDATE session_tokens SET revoked_at=CURRENT_TIMESTAMP WHERE token_id='tok-p'")
    with pytest.raises(PermissionError, match="active_capability_session_required"):
        _request(runtime)


def test_request_is_persisted_and_signed(runtime):
    result = _request(runtime)
    assert result["status"] == "pending"
    assert result["request_id"].startswith("cvreq-")
    assert result["external_event_hash"]
    assert runtime["events"][0][0] == "completion_verification.requested"


def test_verifier_requires_active_reviewer_assignment(runtime):
    request = _request(runtime)
    with runtime["rw"](runtime["root"]) as c:
        c.execute(
            "UPDATE task_role_assignments SET status='superseded' WHERE task_id='reviewer-task'"
        )
    with pytest.raises(PermissionError, match="active_reviewer_assignment_required"):
        _pass(runtime, request["request_id"])


def test_producer_cannot_verify_its_own_request(runtime):
    request = _request(runtime)
    with pytest.raises(
        PermissionError,
        match="completion_verifier_task_must_be_independent",
    ):
        cv.verify_completion(
            runtime["root"],
            request_id=request["request_id"],
            verifier_task_id="producer-task",
            verifier_session_id="producer-session",
            observed_subject_payload=_subject(),
            verdict="pass",
            checks={"evidence": True, "tests": True},
            evidence={"x": 1},
        )


def test_different_task_with_same_session_is_not_independent(runtime):
    request = _request(runtime)

    with runtime["rw"](runtime["root"]) as c:
        c.execute(
            """
            INSERT INTO session_tokens(
                token_hash,
                token_id,
                session_id,
                task_id,
                capability_set_json,
                expires_at
            ) VALUES(
                'r2',
                'tok-r2',
                'producer-session',
                'reviewer-task',
                '[]',
                '2999-01-01 00:00:00'
            )
            """
        )

        c.execute(
            """
            INSERT INTO task_role_assignments(
                task_id,
                session_id,
                token_id,
                role,
                permissions_json,
                assigned_by,
                status
            ) VALUES(
                'reviewer-task',
                'producer-session',
                'tok-r2',
                'reviewer',
                '[]',
                'test',
                'active'
            )
            """
        )

    with pytest.raises(
        PermissionError,
        match="completion_verifier_session_must_be_independent",
    ):
        cv.verify_completion(
            runtime["root"],
            request_id=request["request_id"],
            verifier_task_id="reviewer-task",
            verifier_session_id="producer-session",
            observed_subject_payload=_subject(),
            verdict="pass",
            checks={
                "evidence": True,
                "tests": True,
            },
            evidence={"x": 1},
        )


def test_same_task_with_different_session_is_not_independent(runtime):
    request = _request(runtime)
    with runtime["rw"](runtime["root"]) as c:
        c.execute("INSERT INTO session_tokens(token_hash,token_id,session_id,task_id,capability_set_json,expires_at) VALUES('p2','tok-p2','producer-review-session','producer-task','[]','2999-01-01 00:00:00')")
        c.execute("INSERT INTO task_role_assignments(task_id,session_id,token_id,role,permissions_json,assigned_by,status) VALUES('producer-task','producer-review-session','tok-p2','reviewer','[]','test','active')")
    with pytest.raises(PermissionError, match="completion_verifier_task_must_be_independent"):
        cv.verify_completion(
            runtime["root"],
            request_id=request["request_id"],
            verifier_task_id="producer-task",
            verifier_session_id="producer-review-session",
            observed_subject_payload=_subject(),
            verdict="pass",
            checks={"evidence": True, "tests": True},
            evidence={"x": 1},
        )


def test_subject_hash_mismatch_is_rejected(runtime):
    request = _request(runtime)
    with pytest.raises(PermissionError, match="completion_subject_hash_mismatch"):
        _pass(runtime, request["request_id"], _subject("changed"))


def test_pass_requires_all_declared_checks(runtime):
    request = _request(runtime)
    with pytest.raises(PermissionError, match="completion_required_checks_not_pass"):
        cv.verify_completion(
            runtime["root"],
            request_id=request["request_id"],
            verifier_task_id="reviewer-task",
            verifier_session_id="reviewer-session",
            observed_subject_payload=_subject(),
            verdict="pass",
            checks={"evidence": True, "tests": False},
            evidence={"x": 1},
        )


def test_pass_requires_evidence(runtime):
    request = _request(runtime)
    with pytest.raises(PermissionError, match="completion_pass_requires_evidence"):
        cv.verify_completion(
            runtime["root"],
            request_id=request["request_id"],
            verifier_task_id="reviewer-task",
            verifier_session_id="reviewer-session",
            observed_subject_payload=_subject(),
            verdict="pass",
            checks={"evidence": True, "tests": True},
            evidence={},
        )


def test_current_independent_pass_is_accepted(runtime):
    request = _request(runtime)
    attempt = _pass(runtime, request["request_id"])
    assert attempt["verdict"] == "pass"
    assert attempt["request_status"] == "verified"
    status = cv.completion_status(
        runtime["root"],
        subject_type="workflow",
        subject_id="producer-task:default",
        current_subject_payload=_subject(),
    )
    assert status["accepted"] is True
    assert status["current"] is True
    required = cv.require_current_verification(
        runtime["root"],
        subject_type="workflow",
        subject_id="producer-task:default",
        current_subject_payload=_subject(),
    )
    assert required["accepted"] is True


def test_subject_mutation_makes_verified_receipt_stale(runtime):
    request = _request(runtime)
    _pass(runtime, request["request_id"])
    status = cv.completion_status(
        runtime["root"],
        subject_type="workflow",
        subject_id="producer-task:default",
        current_subject_payload=_subject("changed"),
    )
    assert status["accepted"] is False
    assert status["current"] is False
    assert status["reason"] == "completion_verification_stale"
    with pytest.raises(PermissionError, match="completion_verification_stale"):
        cv.require_current_verification(
            runtime["root"],
            subject_type="workflow",
            subject_id="producer-task:default",
            current_subject_payload=_subject("changed"),
        )


def test_fail_verdict_is_terminal_and_not_accepted(runtime):
    request = _request(runtime)
    result = cv.verify_completion(
        runtime["root"],
        request_id=request["request_id"],
        verifier_task_id="reviewer-task",
        verifier_session_id="reviewer-session",
        observed_subject_payload=_subject(),
        verdict="fail",
        checks={"evidence": False, "tests": True},
        evidence={"reason": "claim evidence incomplete"},
    )
    assert result["request_status"] == "rejected"
    status = cv.completion_status(
        runtime["root"],
        subject_type="workflow",
        subject_id="producer-task:default",
        current_subject_payload=_subject(),
    )
    assert status["accepted"] is False
    with pytest.raises(PermissionError, match="completion_verification_request_not_open"):
        _pass(runtime, request["request_id"])


def test_new_request_supersedes_open_request(runtime):
    first = _request(runtime)
    second = _request(runtime, _subject("new"))
    assert first["request_id"] != second["request_id"]
    with runtime["ro"](runtime["root"]) as c:
        old = c.execute(
            "SELECT status FROM completion_verification_requests WHERE request_id=?",
            (first["request_id"],),
        ).fetchone()
        new = c.execute(
            "SELECT status FROM completion_verification_requests WHERE request_id=?",
            (second["request_id"],),
        ).fetchone()
    assert old["status"] == "superseded"
    assert new["status"] == "pending"


def test_phase1_core_imports_no_process_execution_primitive():
    source = Path(cv.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "subprocess.run(" not in source
    assert "subprocess.Popen(" not in source
