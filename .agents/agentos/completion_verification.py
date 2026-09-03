"""Path: .agents/agentos/completion_verification.py
Purpose: Provide the v0.29.0 independent completion-verification core without
         changing terminal workflow/worker authority until later integration phases.

Phase 1 intentionally defines schema migration 62 but does not register it in the
global migration chain yet. This keeps the released v0.28.4 schema identity intact
while the new persistence and verification semantics are developed and tested.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .external_audit import append_signed_event

MIGRATION_VERSION = 62
VERIFICATION_VERSION = 1

_VERDICTS = {"pass", "fail", "inconclusive"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def migration_62(c) -> None:
    """Create additive persistence for independent completion verification."""
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS completion_verification_requests(
            request_id TEXT PRIMARY KEY,
            verification_version INTEGER NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            producer_task_id TEXT NOT NULL REFERENCES tasks(id),
            producer_session_id TEXT NOT NULL,
            producer_assignment_id INTEGER,
            subject_hash TEXT NOT NULL,
            required_checks_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','verified','rejected','inconclusive','superseded')),
            external_event_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_completion_verification_subject
            ON completion_verification_requests(subject_type,subject_id,created_at);

        CREATE INDEX IF NOT EXISTS idx_completion_verification_task
            ON completion_verification_requests(task_id,status,created_at);

        CREATE TABLE IF NOT EXISTS completion_verification_attempts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL REFERENCES completion_verification_requests(request_id) ON DELETE CASCADE,
            verifier_task_id TEXT NOT NULL REFERENCES tasks(id),
            verifier_session_id TEXT NOT NULL,
            verifier_assignment_id INTEGER NOT NULL,
            verifier_role TEXT NOT NULL,
            observed_subject_hash TEXT NOT NULL,
            verdict TEXT NOT NULL CHECK(verdict IN ('pass','fail','inconclusive')),
            checks_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            result_hash TEXT NOT NULL,
            external_event_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_completion_verification_attempt_request
            ON completion_verification_attempts(request_id,id);

        CREATE INDEX IF NOT EXISTS idx_completion_verification_verifier
            ON completion_verification_attempts(verifier_task_id,verifier_session_id,created_at);
        """
    )

    # Schema 62 pins both integration and terminal-report verification receipts.
    workflow_table = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_steps'"
    ).fetchone()
    if workflow_table:
        columns = {str(row[1]) for row in c.execute("PRAGMA table_info(workflow_steps)").fetchall()}
        if "completion_verification_request_id" not in columns:
            c.execute("ALTER TABLE workflow_steps ADD COLUMN completion_verification_request_id TEXT")
        if "completion_verification_result_hash" not in columns:
            c.execute("ALTER TABLE workflow_steps ADD COLUMN completion_verification_result_hash TEXT")

    proposal_table = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='multi_agent_integration_proposals'"
    ).fetchone()
    if proposal_table:
        columns = {
            str(row[1])
            for row in c.execute(
                "PRAGMA table_info(multi_agent_integration_proposals)"
            ).fetchall()
        }
        if "completion_verification_request_id" not in columns:
            c.execute(
                "ALTER TABLE multi_agent_integration_proposals ADD COLUMN completion_verification_request_id TEXT"
            )
        if "completion_verification_result_hash" not in columns:
            c.execute(
                "ALTER TABLE multi_agent_integration_proposals ADD COLUMN completion_verification_result_hash TEXT"
            )


def completion_subject_hash(
    subject_type: str,
    subject_id: str,
    task_id: str,
    payload: dict[str, Any],
) -> str:
    """Hash a completion subject together with its stable identity envelope."""
    kind = str(subject_type or "").strip()
    sid = str(subject_id or "").strip()
    task = str(task_id or "").strip()
    if not kind or not sid or not task:
        raise ValueError("completion_subject_identity_required")
    if not isinstance(payload, dict):
        raise TypeError("completion_subject_payload_must_be_object")
    return _sha(
        {
            "verification_version": VERIFICATION_VERSION,
            "subject_type": kind,
            "subject_id": sid,
            "task_id": task,
            "payload": payload,
        }
    )


def _active_session(c, task_id: str, session_id: str):
    row = c.execute(
        """
        SELECT token_id
        FROM session_tokens
        WHERE task_id=?
          AND session_id=?
          AND revoked_at IS NULL
          AND expires_at > CURRENT_TIMESTAMP
        ORDER BY issued_at DESC
        LIMIT 1
        """,
        (str(task_id), str(session_id)),
    ).fetchone()
    if not row:
        raise PermissionError("active_capability_session_required")
    return row


def _active_assignment(c, task_id: str, session_id: str, role: str | None = None):
    sql = """
        SELECT id, role
        FROM task_role_assignments
        WHERE task_id=?
          AND session_id=?
          AND status='active'
    """
    params: list[Any] = [str(task_id), str(session_id)]
    if role is not None:
        sql += " AND role=?"
        params.append(str(role))
    sql += " ORDER BY id DESC LIMIT 1"
    return c.execute(sql, tuple(params)).fetchone()


def request_completion(
    root: Path,
    *,
    subject_type: str,
    subject_id: str,
    task_id: str,
    producer_task_id: str,
    producer_session_id: str,
    subject_payload: dict[str, Any],
    required_checks: list[str],
) -> dict[str, Any]:
    """Create an immutable completion candidate owned by the producer."""
    checks = sorted({str(x).strip() for x in required_checks if str(x).strip()})
    if not checks:
        raise ValueError("completion_required_checks_required")

    subject_hash = completion_subject_hash(
        subject_type,
        subject_id,
        task_id,
        subject_payload,
    )
    request_id = "cvreq-" + uuid.uuid4().hex

    with connect(root, immediate=True) as c:
        _active_session(c, producer_task_id, producer_session_id)
        producer_assignment = _active_assignment(
            c,
            producer_task_id,
            producer_session_id,
        )
        producer_assignment_id = (
            int(producer_assignment["id"]) if producer_assignment else None
        )

        c.execute(
            """
            UPDATE completion_verification_requests
            SET status='superseded', resolved_at=CURRENT_TIMESTAMP
            WHERE subject_type=?
              AND subject_id=?
              AND status IN ('pending','inconclusive')
            """,
            (str(subject_type), str(subject_id)),
        )

        c.execute(
            """
            INSERT INTO completion_verification_requests(
                request_id, verification_version, subject_type, subject_id,
                task_id, producer_task_id, producer_session_id,
                producer_assignment_id, subject_hash, required_checks_json,
                status
            ) VALUES(?,?,?,?,?,?,?,?,?,?,'pending')
            """,
            (
                request_id,
                VERIFICATION_VERSION,
                str(subject_type),
                str(subject_id),
                str(task_id),
                str(producer_task_id),
                str(producer_session_id),
                producer_assignment_id,
                subject_hash,
                _canonical(checks),
            ),
        )

    payload = {
        "request_id": request_id,
        "verification_version": VERIFICATION_VERSION,
        "subject_type": str(subject_type),
        "subject_id": str(subject_id),
        "task_id": str(task_id),
        "producer_task_id": str(producer_task_id),
        "producer_session_id": str(producer_session_id),
        "producer_assignment_id": producer_assignment_id,
        "subject_hash": subject_hash,
        "required_checks": checks,
        "status": "pending",
    }
    event = append_signed_event(
        root,
        "completion_verification.requested",
        payload,
        str(task_id),
        None,
    )
    external_hash = str(event.get("event_hash") or "")
    if external_hash:
        with connect(root, immediate=True) as c:
            c.execute(
                """
                UPDATE completion_verification_requests
                SET external_event_hash=?
                WHERE request_id=?
                """,
                (external_hash, request_id),
            )
    return {**payload, "external_event_hash": external_hash or None}


def verify_completion(
    root: Path,
    *,
    request_id: str,
    verifier_task_id: str,
    verifier_session_id: str,
    observed_subject_payload: dict[str, Any],
    verdict: str,
    checks: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Record an independent verifier verdict bound to the requested subject hash."""
    decision = str(verdict or "").strip().lower()
    if decision not in _VERDICTS:
        raise ValueError("invalid_completion_verdict")
    if not isinstance(checks, dict):
        raise TypeError("completion_checks_must_be_object")
    if not isinstance(evidence, dict):
        raise TypeError("completion_evidence_must_be_object")

    with connect_read_only(root) as c:
        request = c.execute(
            "SELECT * FROM completion_verification_requests WHERE request_id=?",
            (str(request_id),),
        ).fetchone()
        if not request:
            raise ValueError("completion_verification_request_not_found")
        request = dict(request)

    if str(request["status"]) not in {"pending", "inconclusive"}:
        raise PermissionError("completion_verification_request_not_open")
    if str(verifier_task_id) == str(request["producer_task_id"]):
        raise PermissionError("completion_verifier_task_must_be_independent")
    if str(verifier_session_id) == str(request["producer_session_id"]):
        raise PermissionError("completion_verifier_session_must_be_independent")

    observed_hash = completion_subject_hash(
        str(request["subject_type"]),
        str(request["subject_id"]),
        str(request["task_id"]),
        observed_subject_payload,
    )
    if observed_hash != str(request["subject_hash"]):
        raise PermissionError("completion_subject_hash_mismatch")

    required_checks = [str(x) for x in _json_list(request["required_checks_json"])]
    if decision == "pass":
        missing = [name for name in required_checks if checks.get(name) is not True]
        if missing:
            raise PermissionError(
                "completion_required_checks_not_pass:" + ",".join(sorted(missing))
            )
        if not evidence:
            raise PermissionError("completion_pass_requires_evidence")

    with connect(root, immediate=True) as c:
        _active_session(c, verifier_task_id, verifier_session_id)
        verifier_assignment = _active_assignment(
            c,
            verifier_task_id,
            verifier_session_id,
            "reviewer",
        )
        if not verifier_assignment:
            raise PermissionError("active_reviewer_assignment_required")
        verifier_assignment_id = int(verifier_assignment["id"])

        producer_assignment_id = request.get("producer_assignment_id")
        if (
            producer_assignment_id is not None
            and int(producer_assignment_id) == verifier_assignment_id
        ):
            raise PermissionError("completion_verifier_assignment_must_be_independent")

        result_payload = {
            "request_id": str(request_id),
            "verifier_task_id": str(verifier_task_id),
            "verifier_session_id": str(verifier_session_id),
            "verifier_assignment_id": verifier_assignment_id,
            "verifier_role": "reviewer",
            "observed_subject_hash": observed_hash,
            "verdict": decision,
            "checks": checks,
            "evidence": evidence,
        }
        result_hash = _sha(result_payload)

        cur = c.execute(
            """
            INSERT INTO completion_verification_attempts(
                request_id, verifier_task_id, verifier_session_id,
                verifier_assignment_id, verifier_role, observed_subject_hash,
                verdict, checks_json, evidence_json, result_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(request_id),
                str(verifier_task_id),
                str(verifier_session_id),
                verifier_assignment_id,
                "reviewer",
                observed_hash,
                decision,
                _canonical(checks),
                _canonical(evidence),
                result_hash,
            ),
        )
        attempt_id = int(cur.lastrowid)

        request_status = {
            "pass": "verified",
            "fail": "rejected",
            "inconclusive": "inconclusive",
        }[decision]
        c.execute(
            """
            UPDATE completion_verification_requests
            SET status=?,
                resolved_at=CASE WHEN ?='inconclusive' THEN NULL ELSE CURRENT_TIMESTAMP END
            WHERE request_id=?
            """,
            (request_status, request_status, str(request_id)),
        )

    event_payload = {
        "attempt_id": attempt_id,
        "request_id": str(request_id),
        "subject_type": str(request["subject_type"]),
        "subject_id": str(request["subject_id"]),
        "task_id": str(request["task_id"]),
        "subject_hash": observed_hash,
        "verifier_task_id": str(verifier_task_id),
        "verifier_session_id": str(verifier_session_id),
        "verifier_assignment_id": verifier_assignment_id,
        "verdict": decision,
        "checks": checks,
        "evidence": evidence,
        "result_hash": result_hash,
        "request_status": request_status,
    }
    event = append_signed_event(
        root,
        "completion_verification.attempted",
        event_payload,
        str(request["task_id"]),
        None,
    )
    external_hash = str(event.get("event_hash") or "")
    if external_hash:
        with connect(root, immediate=True) as c:
            c.execute(
                "UPDATE completion_verification_attempts SET external_event_hash=? WHERE id=?",
                (external_hash, attempt_id),
            )

    learning_signal=None
    learning_error=None
    if request_status=="verified":
        try:
            from .learning_signals import create_learning_signal
            learning_signal=create_learning_signal(
                root,
                task_id=str(request["task_id"]),
                session_id=str(verifier_session_id),
                signal_kind="completion_verified",
                source_type="completion_verification",
                source_id=str(request_id),
                expected_source_hash=result_hash,
            )
        except Exception as exc:
            # Learning observation is degraded-safe; verification remains authoritative.
            learning_error=f"{type(exc).__name__}:{exc}"
    return {
        **event_payload,
        "external_event_hash":external_hash or None,
        "learning_signal_id":(
            learning_signal.get("signal_id")
            if isinstance(learning_signal,dict)
            else None
        ),
        "learning_degraded":learning_error is not None,
        "learning_error":learning_error,
    }


def completion_status(
    root: Path,
    *,
    subject_type: str,
    subject_id: str,
    current_subject_payload: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Return latest or exact verification state; acceptance requires current subject data."""
    with connect_read_only(root) as c:
        schema_available = bool(
            c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='completion_verification_requests'"
            ).fetchone()
            and c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='completion_verification_attempts'"
            ).fetchone()
        )
        if not schema_available:
            return {
                "subject_type": str(subject_type),
                "subject_id": str(subject_id),
                "request": None,
                "attempt": None,
                "accepted": False,
                "current": False,
                "schema_available": False,
                "reason": "completion_verification_schema_unavailable",
            }
        if request_id is None:
            request = c.execute(
                """
                SELECT *
                FROM completion_verification_requests
                WHERE subject_type=? AND subject_id=?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (
                    str(subject_type),
                    str(subject_id),
                ),
            ).fetchone()
        else:
            request = c.execute(
                """
                SELECT *
                FROM completion_verification_requests
                WHERE request_id=?
                  AND subject_type=?
                  AND subject_id=?
                LIMIT 1
                """,
                (
                    str(request_id),
                    str(subject_type),
                    str(subject_id),
                ),
            ).fetchone()
        if not request:
            return {
                "subject_type": str(subject_type),
                "subject_id": str(subject_id),
                "request": None,
                "attempt": None,
                "accepted": False,
                "current": False,
                "schema_available": True,
                "reason": "completion_verification_missing",
            }
        request = dict(request)
        attempt = c.execute(
            """
            SELECT *
            FROM completion_verification_attempts
            WHERE request_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(request["request_id"]),),
        ).fetchone()
        attempt = dict(attempt) if attempt else None

    current = False
    reason = "current_subject_required"
    current_hash = None
    if current_subject_payload is not None:
        current_hash = completion_subject_hash(
            str(request["subject_type"]),
            str(request["subject_id"]),
            str(request["task_id"]),
            current_subject_payload,
        )
        current = current_hash == str(request["subject_hash"])
        reason = (
            "completion_verification_current"
            if current
            else "completion_verification_stale"
        )

    verified_pass = (
        str(request["status"]) == "verified"
        and attempt is not None
        and str(attempt["verdict"]) == "pass"
        and str(attempt["observed_subject_hash"]) == str(request["subject_hash"])
    )
    accepted = bool(verified_pass and current)

    return {
        "subject_type": str(subject_type),
        "subject_id": str(subject_id),
        "request": {
            **request,
            "required_checks": _json_list(request.get("required_checks_json")),
        },
        "attempt": (
            {
                **attempt,
                "checks": _json_obj(attempt.get("checks_json")),
                "evidence": _json_obj(attempt.get("evidence_json")),
            }
            if attempt is not None
            else None
        ),
        "accepted": accepted,
        "current": current,
        "schema_available": True,
        "current_subject_hash": current_hash,
        "reason": (
            "completion_verification_accepted"
            if accepted
            else reason
        ),
    }


def require_current_verification(
    root: Path,
    *,
    subject_type: str,
    subject_id: str,
    current_subject_payload: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed unless latest independent pass receipt matches current subject."""
    status = completion_status(
        root,
        subject_type=subject_type,
        subject_id=subject_id,
        current_subject_payload=current_subject_payload,
    )
    if not status["accepted"]:
        raise PermissionError(str(status["reason"]))
    return status
