"""
File: .agents/agentos/learning_signals.py

Purpose:
    Provide the schema-64 governed learning evidence and linkage layer.

Responsibilities:
    - Persist hash-only learning signals linked to existing AgentOS evidence.
    - Assign per-task signal sequence numbers transactionally and idempotently.
    - Revalidate source hashes before promotion-oriented linkage is finalized.
    - Record actual skill, memory, and finding inclusion without raw-content copies.
    - Keep raw learning signals outside context retrieval and instruction authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only

MIGRATION_VERSION = 64
LEARNING_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KNOWLEDGE_KINDS = {"skill", "memory", "finding"}
_SOURCE_TYPES = {"task_outcome", "project_finding", "completion_verification"}
_PROMOTION_RELATIONS = {
    "memory_candidate", "skill_candidate", "evolution_proposal",
    "architecture_proposal", "effectiveness_finding",
}

class LearningSignalError(RuntimeError):
    """Raised when a deterministic learning-linkage invariant is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    raw = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256.fullmatch(str(value or "").strip().lower()))


def migration_64(c: Any) -> None:
    """Create additive schema-64 learning linkage tables."""
    c.executescript("""
    CREATE TABLE IF NOT EXISTS learning_signals(
        signal_id TEXT PRIMARY KEY,
        learning_version INTEGER NOT NULL,
        signal_kind TEXT NOT NULL,
        task_id TEXT NOT NULL REFERENCES tasks(id),
        session_id TEXT,
        signal_sequence_number INTEGER NOT NULL,
        source_type TEXT NOT NULL,
        source_id TEXT NOT NULL,
        source_hash TEXT NOT NULL,
        signature_hash TEXT NOT NULL,
        idempotency_hash TEXT NOT NULL UNIQUE,
        architecture_baseline_hash TEXT,
        plan_hash TEXT,
        context_authority_hash TEXT,
        provenance_manifest_hash TEXT,
        cross_task_eligible INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id, signal_sequence_number)
    );
    CREATE INDEX IF NOT EXISTS idx_learning_signals_task
        ON learning_signals(task_id, signal_sequence_number);
    CREATE INDEX IF NOT EXISTS idx_learning_signals_signature
        ON learning_signals(signature_hash, created_at);

    CREATE TABLE IF NOT EXISTS learning_signal_links(
        link_id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id TEXT NOT NULL REFERENCES learning_signals(signal_id) ON DELETE CASCADE,
        relation_type TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        target_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(signal_id, relation_type, target_type, target_id, target_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_learning_signal_links_signal
        ON learning_signal_links(signal_id, relation_type);

    CREATE TABLE IF NOT EXISTS knowledge_usage(
        usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL REFERENCES tasks(id),
        session_id TEXT,
        context_revision INTEGER NOT NULL,
        knowledge_kind TEXT NOT NULL,
        knowledge_id TEXT NOT NULL,
        knowledge_hash TEXT NOT NULL,
        source_signal_id TEXT REFERENCES learning_signals(signal_id),
        context_pack_hash TEXT NOT NULL,
        provenance_manifest_hash TEXT,
        inclusion_reason TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(task_id, context_revision, knowledge_kind, knowledge_id, knowledge_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_knowledge_usage_task
        ON knowledge_usage(task_id, context_revision);
    CREATE INDEX IF NOT EXISTS idx_knowledge_usage_knowledge
        ON knowledge_usage(knowledge_kind, knowledge_id, created_at);
    """)


def _table_exists(c: Any, name: str) -> bool:
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _active_architecture_hash(c: Any) -> str | None:
    if not _table_exists(c, "architecture_baselines"):
        return None
    columns = {str(row[1]) for row in c.execute("PRAGMA table_info(architecture_baselines)")}
    order = "activated_at DESC, rowid DESC" if "activated_at" in columns else "rowid DESC"
    row = c.execute(f"SELECT baseline_hash FROM architecture_baselines WHERE status='active' ORDER BY {order} LIMIT 1").fetchone()
    value = str(row["baseline_hash"] or "") if row else ""
    return value if _valid_sha(value) else None


def _active_plan_hash(c: Any, task_id: str) -> str | None:
    if not _table_exists(c, "task_plans"):
        return None
    columns = {str(row[1]) for row in c.execute("PRAGMA table_info(task_plans)")}
    if "plan_hash" not in columns:
        return None
    order = "revision DESC, rowid DESC" if "revision" in columns else "rowid DESC"
    status = "AND status='active'" if "status" in columns else ""
    row = c.execute(f"SELECT plan_hash FROM task_plans WHERE task_id=? {status} ORDER BY {order} LIMIT 1", (task_id,)).fetchone()
    value = str(row["plan_hash"] or "") if row else ""
    return value if _valid_sha(value) else None


def _latest_context_pins(c: Any, task_id: str) -> tuple[str | None, str | None]:
    if not _table_exists(c, "context_authority_evaluations"):
        return None, None
    row = c.execute("""
        SELECT provenance_manifest_hash,context_authority_hash
        FROM context_authority_evaluations
        WHERE task_id=? ORDER BY context_revision DESC,id DESC LIMIT 1
    """, (task_id,)).fetchone()
    if not row:
        return None, None
    p = str(row["provenance_manifest_hash"] or "")
    a = str(row["context_authority_hash"] or "")
    return (p if _valid_sha(p) else None, a if _valid_sha(a) else None)


def _verified_completion_exists(c: Any, task_id: str) -> bool:
    if not (_table_exists(c, "completion_verification_requests") and _table_exists(c, "completion_verification_attempts")):
        return False
    return bool(c.execute("""
        SELECT 1
        FROM completion_verification_requests r
        JOIN completion_verification_attempts a ON a.request_id=r.request_id
        WHERE (r.task_id=? OR r.producer_task_id=?)
          AND r.status='verified' AND a.verdict='pass'
          AND a.observed_subject_hash=r.subject_hash
        ORDER BY a.id DESC LIMIT 1
    """, (task_id, task_id)).fetchone())


def _source_current_hash(c: Any, task_id: str, source_type: str, source_id: str) -> str:
    if source_type not in _SOURCE_TYPES:
        raise LearningSignalError("unsupported_learning_source_type")
    if source_type == "task_outcome":
        row = c.execute("SELECT * FROM task_outcomes WHERE id=? AND task_id=?", (source_id, task_id)).fetchone()
        if not row:
            raise LearningSignalError("learning_source_task_outcome_missing")
        return _sha(dict(row))
    if source_type == "project_finding":
        row = c.execute("SELECT * FROM project_findings WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise LearningSignalError("learning_source_project_finding_missing")
        # project_findings is a recurring/mutable aggregate. Pin stable finding
        # identity fields so later occurrence counters/timestamps do not stale
        # the signal that represented an earlier task observation.
        return _sha({
            "finding_key": row["finding_key"],
            "kind": row["kind"],
            "path": row["path"],
            "symbol": row["symbol"],
            "message": row["message"],
        })
    request = c.execute("""
        SELECT * FROM completion_verification_requests
        WHERE request_id=? AND (task_id=? OR producer_task_id=?) AND status='verified'
    """, (source_id, task_id, task_id)).fetchone()
    if not request:
        raise LearningSignalError("learning_source_verified_completion_missing")
    attempt = c.execute("""
        SELECT result_hash,verdict,observed_subject_hash
        FROM completion_verification_attempts
        WHERE request_id=? ORDER BY id DESC LIMIT 1
    """, (source_id,)).fetchone()
    if not attempt or str(attempt["verdict"]) != "pass" or str(attempt["observed_subject_hash"]) != str(request["subject_hash"]):
        raise LearningSignalError("learning_source_verified_completion_invalid")
    value = str(attempt["result_hash"] or "").lower()
    if not _valid_sha(value):
        raise LearningSignalError("learning_source_result_hash_invalid")
    return value


def _cross_task_eligible(c: Any, task_id: str, source_type: str) -> bool:
    return source_type == "completion_verification" or _verified_completion_exists(c, task_id)


def revalidate_learning_signal(
    root: Path,
    signal_id: str,
    *,
    persist_eligibility: bool = False,
) -> dict[str, Any]:
    """Revalidate one source-bound signal without copying raw source content."""
    with connect(root, immediate=bool(persist_eligibility)) as c:
        row = c.execute(
            "SELECT * FROM learning_signals WHERE signal_id=?",
            (str(signal_id),),
        ).fetchone()
        if not row:
            raise LearningSignalError("learning_signal_missing")
        signal = dict(row)
        current_hash = _source_current_hash(
            c,
            str(signal["task_id"]),
            str(signal["source_type"]),
            str(signal["source_id"]),
        )
        source_current = current_hash == str(signal["source_hash"])
        eligible = _cross_task_eligible(
            c,
            str(signal["task_id"]),
            str(signal["source_type"]),
        )
        if persist_eligibility and eligible and not int(signal["cross_task_eligible"]):
            c.execute(
                "UPDATE learning_signals SET cross_task_eligible=1 WHERE signal_id=?",
                (str(signal_id),),
            )
    return {
        "ok": True,
        "signal_id": str(signal["signal_id"]),
        "task_id": str(signal["task_id"]),
        "source_type": str(signal["source_type"]),
        "source_id": str(signal["source_id"]),
        "source_hash": str(signal["source_hash"]),
        "current_source_hash": current_hash,
        "source_current": bool(source_current),
        "cross_task_eligible": bool(eligible),
        "architecture_baseline_hash": signal.get("architecture_baseline_hash"),
        "context_authority_hash": signal.get("context_authority_hash"),
        "provenance_manifest_hash": signal.get("provenance_manifest_hash"),
        "instruction_authority": False,
    }


def create_learning_signal(root: Path, *, task_id: str, session_id: str | None,
                           signal_kind: str, source_type: str, source_id: str,
                           expected_source_hash: str | None = None) -> dict[str, Any]:
    """Create/replay one source-bound telemetry signal; never a context source."""
    task_id = str(task_id or "").strip()
    signal_kind = str(signal_kind or "").strip().lower()
    source_type = str(source_type or "").strip()
    source_id = str(source_id or "").strip()
    if not task_id or not signal_kind or not source_id:
        raise LearningSignalError("learning_signal_identity_required")
    with connect(root, immediate=True) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise LearningSignalError("learning_signal_task_missing")
        source_hash = _source_current_hash(c, task_id, source_type, source_id)
        if expected_source_hash is not None:
            expected = str(expected_source_hash).lower().strip()
            if not _valid_sha(expected) or expected != source_hash:
                raise LearningSignalError("learning_source_hash_mismatch")
        signature_hash = _sha({"v": LEARNING_VERSION, "kind": signal_kind, "source_type": source_type, "source_hash": source_hash})
        idem = _sha({"task_id": task_id, "kind": signal_kind, "source_type": source_type, "source_id": source_id, "source_hash": source_hash})
        old = c.execute("SELECT * FROM learning_signals WHERE idempotency_hash=?", (idem,)).fetchone()
        if old:
            return {**dict(old), "created": False, "idempotent": True}
        seq = int(c.execute("SELECT COALESCE(MAX(signal_sequence_number),0)+1 AS n FROM learning_signals WHERE task_id=?", (task_id,)).fetchone()["n"])
        provenance_hash, authority_hash = _latest_context_pins(c, task_id)
        signal_id = "LS-" + idem[:24].upper()
        c.execute("""
            INSERT INTO learning_signals(
                signal_id,learning_version,signal_kind,task_id,session_id,
                signal_sequence_number,source_type,source_id,source_hash,
                signature_hash,idempotency_hash,architecture_baseline_hash,
                plan_hash,context_authority_hash,provenance_manifest_hash,cross_task_eligible
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            signal_id, LEARNING_VERSION, signal_kind, task_id,
            str(session_id) if session_id else None, seq, source_type, source_id,
            source_hash, signature_hash, idem, _active_architecture_hash(c),
            _active_plan_hash(c, task_id), authority_hash, provenance_hash,
            int(_cross_task_eligible(c, task_id, source_type)),
        ))
        row = c.execute("SELECT * FROM learning_signals WHERE signal_id=?", (signal_id,)).fetchone()
    return {**dict(row), "created": True, "idempotent": False}


def link_learning_signal(root: Path, *, signal_id: str, relation_type: str,
                         target_type: str, target_id: str, target_hash: str) -> dict[str, Any]:
    """Link to an existing object; promotion-oriented links revalidate eligibility."""
    digest = str(target_hash or "").strip().lower()
    if not _valid_sha(digest):
        raise LearningSignalError("learning_signal_target_hash_must_be_sha256")
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM learning_signals WHERE signal_id=?", (signal_id,)).fetchone()
        if not row:
            raise LearningSignalError("learning_signal_missing")
        signal = dict(row)
        current = _source_current_hash(c, str(signal["task_id"]), str(signal["source_type"]), str(signal["source_id"]))
        if current != str(signal["source_hash"]):
            raise LearningSignalError("learning_source_hash_stale")
        if relation_type in _PROMOTION_RELATIONS:
            eligible = _cross_task_eligible(c, str(signal["task_id"]), str(signal["source_type"]))
            if not eligible:
                raise LearningSignalError("learning_signal_not_cross_task_eligible")
            c.execute("UPDATE learning_signals SET cross_task_eligible=1 WHERE signal_id=?", (signal_id,))
        c.execute("""
            INSERT OR IGNORE INTO learning_signal_links(signal_id,relation_type,target_type,target_id,target_hash)
            VALUES(?,?,?,?,?)
        """, (signal_id, relation_type, target_type, target_id, digest))
        result = c.execute("""
            SELECT * FROM learning_signal_links
            WHERE signal_id=? AND relation_type=? AND target_type=? AND target_id=? AND target_hash=?
        """, (signal_id, relation_type, target_type, target_id, digest)).fetchone()
    return dict(result)


def _knowledge_hash(item: dict[str, Any]) -> str:
    # Raw text is used only transiently as hash input; it is never stored here.
    return _sha({"kind": item.get("kind"), "id": item.get("id"), "title": item.get("title"),
                 "text": item.get("text"), "provenance": item.get("provenance") or {}})


def record_knowledge_usage_rows(c: Any, *, task_id: str, context_revision: int,
                                context_pack_hash: str, knowledge: list[dict[str, Any]]) -> int:
    """Record actual inclusion in the same context-pack transaction."""
    if not _valid_sha(context_pack_hash):
        raise LearningSignalError("context_pack_hash_must_be_sha256")
    task = c.execute("SELECT owner_session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
    session_id = str(task["owner_session_id"]) if task and task["owner_session_id"] else None
    count = 0
    for item in knowledge:
        kind = str(item.get("kind") or "")
        kid = str(item.get("id") or "")
        if kind not in _KNOWLEDGE_KINDS or not kid:
            continue
        reasons = item.get("selection_reasons") or ["knowledge_relevance"]
        reason = ",".join(sorted({str(x) for x in reasons if str(x)})) or "knowledge_relevance"
        cur = c.execute("""
            INSERT OR IGNORE INTO knowledge_usage(
                task_id,session_id,context_revision,knowledge_kind,knowledge_id,
                knowledge_hash,source_signal_id,context_pack_hash,provenance_manifest_hash,inclusion_reason
            ) VALUES(?,?,?,?,?,?,NULL,?,NULL,?)
        """, (task_id, session_id, int(context_revision), kind, kid, _knowledge_hash(item), context_pack_hash, reason))
        count += int(cur.rowcount > 0)
    return count


def learning_signals_get(root: Path, *, task_id: str | None = None,
                         signature_hash: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Return privacy-safe hash-only learning signals."""
    limit = max(1, min(int(limit), 1000))
    clauses, params = ["1=1"], []
    if task_id:
        clauses.append("task_id=?"); params.append(str(task_id))
    if signature_hash:
        signature_hash = str(signature_hash).lower().strip()
        if not _valid_sha(signature_hash):
            raise LearningSignalError("signature_hash_must_be_sha256")
        clauses.append("signature_hash=?"); params.append(signature_hash)
    params.append(limit)
    with connect_read_only(root) as c:
        rows = c.execute("SELECT * FROM learning_signals WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC,signal_sequence_number DESC LIMIT ?", tuple(params)).fetchall()
    return {"ok": True, "signals": [dict(r) for r in rows], "count": len(rows)}


def learning_signal_links_get(root: Path, *, signal_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Return links from learning signals to existing governed objects."""
    limit = max(1, min(int(limit), 1000))
    sql, params = "SELECT * FROM learning_signal_links", []
    if signal_id:
        sql += " WHERE signal_id=?"; params.append(str(signal_id))
    sql += " ORDER BY link_id DESC LIMIT ?"; params.append(limit)
    with connect_read_only(root) as c:
        rows = c.execute(sql, tuple(params)).fetchall()
    return {"ok": True, "links": [dict(r) for r in rows], "count": len(rows)}


def knowledge_usage_get(root: Path, *, task_id: str | None = None,
                        knowledge_kind: str | None = None, limit: int = 100) -> dict[str, Any]:
    """Return hash-only records of actual context knowledge inclusion."""
    limit = max(1, min(int(limit), 1000))
    clauses, params = ["1=1"], []
    if task_id:
        clauses.append("task_id=?"); params.append(str(task_id))
    if knowledge_kind:
        if knowledge_kind not in _KNOWLEDGE_KINDS:
            raise LearningSignalError("invalid_knowledge_kind")
        clauses.append("knowledge_kind=?"); params.append(knowledge_kind)
    params.append(limit)
    with connect_read_only(root) as c:
        rows = c.execute("SELECT * FROM knowledge_usage WHERE " + " AND ".join(clauses) + " ORDER BY usage_id DESC LIMIT ?", tuple(params)).fetchall()
    return {"ok": True, "usage": [dict(r) for r in rows], "count": len(rows)}


def learning_status(root: Path) -> dict[str, Any]:
    """Return governed-learning status and explicit authority non-claims."""
    with connect_read_only(root) as c:
        counts = {name: int(c.execute(f"SELECT COUNT(*) AS n FROM {name}").fetchone()["n"])
                  for name in ("learning_signals", "learning_signal_links", "knowledge_usage")}
    return {
        "ok": True, "learning_version": LEARNING_VERSION, "schema": MIGRATION_VERSION,
        "tables": counts, "learning_signals_directly_injected": False,
        "raw_content_persisted": False, "instruction_authority": False,
        "mcp_mutation_allowed": False, "automatic_skill_graduation": False,
        "automatic_policy_activation": False, "automatic_architecture_mutation": False,
        "automatic_deactivation": False, "failure_mode": "degraded_safe_for_learning_only",
    }
