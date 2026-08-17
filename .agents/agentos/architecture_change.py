"""
File: .agents/agentos/architecture_change.py

Purpose:
    Implement v0.25.5 Architecture Change Proposal and ADR lifecycle without
    granting AI authority to approve or activate architecture.

Responsibilities:
    - Materialize schema 53 proposal/ADR/event records additively.
    - Bind proposals to the exact ACTIVE source Architecture Baseline and optional
      Architecture Compliance run/findings that motivated the change.
    - Allow AI/system actors to draft and submit proposals only.
    - Require explicit human confirmation plus exact proposal hash for review,
      approval, rejection, and target-baseline binding.
    - Accept the linked ADR only when the human approves the exact proposal.
    - Never modify .agents/architecture working-copy artifacts or activate a baseline.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Iterable

from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .governance_enforcement import governed_mutation

MIGRATION_VERSION = 53
CHANGE_LIFECYCLE_VERSION = 1
PROPOSAL_STATUSES = {"draft", "submitted", "reviewed", "approved", "rejected", "withdrawn"}
ADR_STATUSES = {"proposed", "accepted", "rejected", "superseded"}


def migration_53(connection: Any) -> None:
    """Create additive Architecture Change Proposal and ADR schema objects."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_change_proposals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_uuid TEXT NOT NULL UNIQUE,
            lifecycle_version INTEGER NOT NULL,
            source_baseline_id INTEGER NOT NULL,
            source_baseline_hash TEXT NOT NULL,
            source_compliance_run_id INTEGER,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            rationale TEXT NOT NULL,
            affected_sections_json TEXT NOT NULL,
            proposed_changes_json TEXT NOT NULL,
            impact_analysis_json TEXT NOT NULL,
            validation_plan_json TEXT NOT NULL,
            rollback_plan_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','submitted','reviewed','approved','rejected','withdrawn')),
            proposal_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_by TEXT,
            submitted_at TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            approved_by TEXT,
            approved_at TEXT,
            rejected_by TEXT,
            rejected_at TEXT,
            rejection_reason TEXT,
            target_baseline_id INTEGER,
            target_baseline_hash TEXT,
            bound_by TEXT,
            bound_at TEXT,
            FOREIGN KEY(source_baseline_id) REFERENCES architecture_baselines(id),
            FOREIGN KEY(source_compliance_run_id) REFERENCES architecture_compliance_runs(id),
            FOREIGN KEY(target_baseline_id) REFERENCES architecture_baselines(id)
        );
        CREATE INDEX IF NOT EXISTS idx_arch_change_proposal_status
            ON architecture_change_proposals(status,id);
        CREATE INDEX IF NOT EXISTS idx_arch_change_proposal_source
            ON architecture_change_proposals(source_baseline_id,source_compliance_run_id,id);

        CREATE TABLE IF NOT EXISTS architecture_change_proposal_findings(
            proposal_id INTEGER NOT NULL,
            finding_id INTEGER NOT NULL,
            finding_hash TEXT NOT NULL,
            PRIMARY KEY(proposal_id,finding_id),
            FOREIGN KEY(proposal_id) REFERENCES architecture_change_proposals(id) ON DELETE CASCADE,
            FOREIGN KEY(finding_id) REFERENCES architecture_compliance_findings(id)
        );

        CREATE TABLE IF NOT EXISTS architecture_adrs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adr_uuid TEXT NOT NULL UNIQUE,
            proposal_id INTEGER NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK(status IN ('proposed','accepted','rejected','superseded')),
            title TEXT NOT NULL,
            context_text TEXT NOT NULL,
            decision_text TEXT NOT NULL,
            consequences_text TEXT NOT NULL,
            alternatives_json TEXT NOT NULL,
            adr_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            accepted_by TEXT,
            accepted_at TEXT,
            rejected_by TEXT,
            rejected_at TEXT,
            FOREIGN KEY(proposal_id) REFERENCES architecture_change_proposals(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arch_adr_status ON architecture_adrs(status,id);

        CREATE TABLE IF NOT EXISTS architecture_change_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER,
            adr_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            external_event_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(proposal_id) REFERENCES architecture_change_proposals(id),
            FOREIGN KEY(adr_id) REFERENCES architecture_adrs(id)
        );
        CREATE INDEX IF NOT EXISTS idx_arch_change_events_proposal
            ON architecture_change_events(proposal_id,id);
        """
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    text = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _as_object(value: Any, field: str) -> Any:
    if value is None:
        return {}
    if not isinstance(value, (dict, list)):
        raise RuntimeError(f"{field}_must_be_object_or_list")
    return value


def _section_ids(values: Iterable[str]) -> list[str]:
    result = sorted({str(value).strip().upper() for value in values if str(value).strip()})
    for section_id in result:
        if not section_id.startswith("ARCH-") or len(section_id) != 7:
            raise RuntimeError(f"unknown_architecture_section:{section_id}")
        try:
            number = int(section_id[-2:])
        except ValueError as exc:
            raise RuntimeError(f"unknown_architecture_section:{section_id}") from exc
        if number < 1 or number > 27:
            raise RuntimeError(f"unknown_architecture_section:{section_id}")
    if not result:
        raise RuntimeError("affected_architecture_sections_required")
    return result


def _active_baseline(connection: Any) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id,baseline_hash,baseline_version,status FROM architecture_baselines WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _proposal(connection: Any, proposal_id: int) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM architecture_change_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        raise RuntimeError("architecture_change_proposal_not_found")
    return dict(row)


def _human_guard(row: dict[str, Any], expected_hash: str, human_confirmed: bool, statuses: set[str]) -> None:
    if not human_confirmed:
        raise RuntimeError("explicit_human_confirmation_required")
    if str(row["proposal_hash"]) != str(expected_hash):
        raise RuntimeError("architecture_change_proposal_hash_mismatch")
    if str(row["status"]) not in statuses:
        raise RuntimeError(f"architecture_change_invalid_transition_from:{row['status']}")


def _assert_source_baseline_current(connection: Any, row: dict[str, Any]) -> None:
    active = _active_baseline(connection)
    if not active:
        raise RuntimeError("architecture_change_source_baseline_not_active")
    if int(active["id"]) != int(row["source_baseline_id"]) or str(active["baseline_hash"]) != str(row["source_baseline_hash"]):
        raise RuntimeError("architecture_change_proposal_stale_baseline")


def _event(
    root: Path,
    proposal_id: int | None,
    adr_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    *,
    task_id: str | None = None,
    session_id: str | None = None,
) -> str:
    clean = dict(payload)
    digest = _sha(clean)
    signed = append_signed_event(root, event_type, {**clean, "event_hash": digest}, task_id, session_id)
    with connect(root, immediate=True) as connection:
        connection.execute(
            "INSERT INTO architecture_change_events(proposal_id,adr_id,event_type,event_json,event_hash,external_event_hash) VALUES(?,?,?,?,?,?)",
            (proposal_id, adr_id, event_type, _canonical(clean), digest, signed["event_hash"]),
        )
    return str(signed["event_hash"])


def _compliance_binding(
    connection: Any,
    active: dict[str, Any],
    compliance_run_id: int | None,
    finding_ids: list[int] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if compliance_run_id is None:
        if finding_ids:
            raise RuntimeError("finding_ids_require_compliance_run")
        return None, []
    run = connection.execute(
        "SELECT * FROM architecture_compliance_runs WHERE id=?", (compliance_run_id,)
    ).fetchone()
    if not run:
        raise RuntimeError("architecture_compliance_run_not_found")
    run_dict = dict(run)
    if str(run_dict["status"]) not in {"block", "warn"}:
        raise RuntimeError("architecture_change_requires_noncompliant_or_warning_run")
    if int(run_dict["baseline_id"] or 0) != int(active["id"]) or str(run_dict["baseline_hash"] or "") != str(active["baseline_hash"]):
        raise RuntimeError("architecture_change_compliance_baseline_mismatch")
    rows = connection.execute(
        "SELECT id,run_id,section_id,finding_code,severity,subject,finding_hash FROM architecture_compliance_findings WHERE run_id=? ORDER BY id",
        (compliance_run_id,),
    ).fetchall()
    available = [dict(row) for row in rows]
    if finding_ids:
        selected_ids = {int(value) for value in finding_ids}
        selected = [item for item in available if int(item["id"]) in selected_ids]
        if {int(item["id"]) for item in selected} != selected_ids:
            raise RuntimeError("architecture_change_finding_not_in_run")
    else:
        blocking = [item for item in available if item["severity"] == "block"]
        selected = blocking or available
    if not selected:
        raise RuntimeError("architecture_change_compliance_run_has_no_findings")
    return run_dict, selected


def create_change_proposal(
    root: Path | str,
    *,
    title: str,
    summary: str,
    rationale: str,
    affected_sections: list[str],
    proposed_changes: Any,
    impact_analysis: Any,
    validation_plan: Any,
    rollback_plan: Any,
    created_by: str,
    compliance_run_id: int | None = None,
    finding_ids: list[int] | None = None,
    adr_alternatives: Any | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Create a proposal-only architecture change record and linked ADR draft."""
    root_path = Path(root).resolve()
    if not all(str(value).strip() for value in (title, summary, rationale, created_by)):
        raise RuntimeError("architecture_change_required_text_missing")
    sections = _section_ids(affected_sections)
    changes = _as_object(proposed_changes, "proposed_changes")
    impact = _as_object(impact_analysis, "impact_analysis")
    validation = _as_object(validation_plan, "validation_plan")
    rollback = _as_object(rollback_plan, "rollback_plan")
    alternatives = _as_object(adr_alternatives, "adr_alternatives") if adr_alternatives is not None else []
    existing_id: int | None = None
    proposal_id: int | None = None
    adr_id: int | None = None
    adr_hash: str | None = None
    with connect(root_path, immediate=True) as connection:
        active = _active_baseline(connection)
        if not active:
            raise RuntimeError("architecture_change_requires_active_baseline")
        compliance_run, findings = _compliance_binding(connection, active, compliance_run_id, finding_ids)
        identity = {
            "lifecycle_version": CHANGE_LIFECYCLE_VERSION,
            "source_baseline_id": int(active["id"]),
            "source_baseline_hash": str(active["baseline_hash"]),
            "source_compliance_run_id": compliance_run_id,
            "source_compliance_run_hash": str(compliance_run["run_hash"]) if compliance_run else None,
            "finding_hashes": [str(item["finding_hash"]) for item in findings],
            "title": title.strip(),
            "summary": summary.strip(),
            "rationale": rationale.strip(),
            "affected_sections": sections,
            "proposed_changes": changes,
            "impact_analysis": impact,
            "validation_plan": validation,
            "rollback_plan": rollback,
        }
        proposal_hash = _sha(identity)
        existing = connection.execute(
            "SELECT id FROM architecture_change_proposals WHERE proposal_hash=?", (proposal_hash,)
        ).fetchone()
        if existing:
            existing_id = int(existing[0])
        else:
            cur = connection.execute(
                """INSERT INTO architecture_change_proposals(
                    proposal_uuid,lifecycle_version,source_baseline_id,source_baseline_hash,source_compliance_run_id,
                    title,summary,rationale,affected_sections_json,proposed_changes_json,impact_analysis_json,
                    validation_plan_json,rollback_plan_json,status,proposal_hash,created_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?,?)""",
                (
                    str(uuid.uuid4()), CHANGE_LIFECYCLE_VERSION, int(active["id"]), str(active["baseline_hash"]), compliance_run_id,
                    title.strip(), summary.strip(), rationale.strip(), _canonical(sections), _canonical(changes), _canonical(impact),
                    _canonical(validation), _canonical(rollback), proposal_hash, created_by.strip(),
                ),
            )
            proposal_id = int(cur.lastrowid)
            for finding in findings:
                connection.execute(
                    "INSERT INTO architecture_change_proposal_findings(proposal_id,finding_id,finding_hash) VALUES(?,?,?)",
                    (proposal_id, int(finding["id"]), str(finding["finding_hash"])),
                )
            context = {
                "source_baseline_id": int(active["id"]),
                "source_baseline_hash": str(active["baseline_hash"]),
                "compliance_run_id": compliance_run_id,
                "findings": [
                    {"id": int(item["id"]), "section_id": item["section_id"], "finding_code": item["finding_code"], "severity": item["severity"], "subject": item["subject"]}
                    for item in findings
                ],
            }
            adr_identity = {
                "proposal_hash": proposal_hash,
                "title": title.strip(),
                "context": context,
                "decision": changes,
                "consequences": impact,
                "alternatives": alternatives,
            }
            adr_hash = _sha(adr_identity)
            adr_cur = connection.execute(
                """INSERT INTO architecture_adrs(adr_uuid,proposal_id,status,title,context_text,decision_text,consequences_text,alternatives_json,adr_hash,created_by)
                   VALUES(?,?,'proposed',?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), proposal_id, title.strip(), _canonical(context), _canonical(changes), _canonical(impact),
                    _canonical(alternatives), adr_hash, created_by.strip(),
                ),
            )
            adr_id = int(adr_cur.lastrowid)
    if existing_id is not None:
        return architecture_change_proposal_get(root_path, proposal_id=existing_id, read_only=False)
    assert proposal_id is not None and adr_id is not None and adr_hash is not None
    external = _event(
        root_path, proposal_id, adr_id, "architecture.change.proposal_created",
        {"proposal_id": proposal_id, "proposal_hash": proposal_hash, "adr_id": adr_id, "adr_hash": adr_hash, "created_by": created_by.strip()},
        task_id=task_id, session_id=session_id,
    )
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result
def submit_change_proposal(
    root: Path | str,
    proposal_id: int,
    expected_proposal_hash: str,
    submitted_by: str,
    *,
    task_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Submit an exact draft proposal for human review; submission conveys no authority."""
    root_path = Path(root).resolve()
    already_submitted = False
    adr_id: int | None = None
    with connect(root_path, immediate=True) as connection:
        row = _proposal(connection, proposal_id)
        if row["proposal_hash"] != expected_proposal_hash:
            raise RuntimeError("architecture_change_proposal_hash_mismatch")
        if row["status"] == "submitted":
            already_submitted = True
        elif row["status"] != "draft":
            raise RuntimeError(f"architecture_change_invalid_transition_from:{row['status']}")
        if not already_submitted:
            _assert_source_baseline_current(connection, row)
            connection.execute(
                "UPDATE architecture_change_proposals SET status='submitted',submitted_by=?,submitted_at=CURRENT_TIMESTAMP WHERE id=? AND status='draft'",
                (submitted_by, proposal_id),
            )
        adr = connection.execute("SELECT id FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        adr_id = int(adr[0]) if adr else None
    if already_submitted:
        return architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    external = _event(root_path, proposal_id, adr_id, "architecture.change.proposal_submitted", {"proposal_id": proposal_id, "proposal_hash": expected_proposal_hash, "submitted_by": submitted_by}, task_id=task_id, session_id=session_id)
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result


@governed_mutation("architecture.change.proposal.review")
def review_change_proposal(
    root: Path | str,
    proposal_id: int,
    expected_proposal_hash: str,
    reviewed_by: str,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Record explicit human review of one exact submitted proposal."""
    root_path = Path(root).resolve()
    with connect(root_path, immediate=True) as connection:
        row = _proposal(connection, proposal_id)
        _human_guard(row, expected_proposal_hash, human_confirmed, {"submitted"})
        _assert_source_baseline_current(connection, row)
        connection.execute(
            "UPDATE architecture_change_proposals SET status='reviewed',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='submitted'",
            (reviewed_by, proposal_id),
        )
        adr = connection.execute("SELECT id FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        adr_id = int(adr[0]) if adr else None
    external = _event(root_path, proposal_id, adr_id, "architecture.change.proposal_reviewed", {"proposal_id": proposal_id, "proposal_hash": expected_proposal_hash, "reviewed_by": reviewed_by})
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result


@governed_mutation("architecture.change.proposal.approve")
def approve_change_proposal(
    root: Path | str,
    proposal_id: int,
    expected_proposal_hash: str,
    approved_by: str,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Human-approve one exact proposal and accept its linked ADR; do not mutate the Architecture Contract."""
    root_path = Path(root).resolve()
    with connect(root_path, immediate=True) as connection:
        row = _proposal(connection, proposal_id)
        _human_guard(row, expected_proposal_hash, human_confirmed, {"reviewed"})
        _assert_source_baseline_current(connection, row)
        connection.execute(
            "UPDATE architecture_change_proposals SET status='approved',approved_by=?,approved_at=CURRENT_TIMESTAMP WHERE id=? AND status='reviewed'",
            (approved_by, proposal_id),
        )
        connection.execute(
            "UPDATE architecture_adrs SET status='accepted',accepted_by=?,accepted_at=CURRENT_TIMESTAMP WHERE proposal_id=? AND status='proposed'",
            (approved_by, proposal_id),
        )
        adr = connection.execute("SELECT id,adr_hash FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        adr_id = int(adr[0]) if adr else None
        adr_hash = str(adr[1]) if adr else None
    external = _event(root_path, proposal_id, adr_id, "architecture.change.proposal_approved", {"proposal_id": proposal_id, "proposal_hash": expected_proposal_hash, "adr_id": adr_id, "adr_hash": adr_hash, "approved_by": approved_by})
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result


@governed_mutation("architecture.change.proposal.reject")
def reject_change_proposal(
    root: Path | str,
    proposal_id: int,
    expected_proposal_hash: str,
    rejected_by: str,
    reason: str,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Human-reject one exact non-approved proposal and its ADR draft."""
    root_path = Path(root).resolve()
    if not reason.strip():
        raise RuntimeError("architecture_change_rejection_reason_required")
    with connect(root_path, immediate=True) as connection:
        row = _proposal(connection, proposal_id)
        _human_guard(row, expected_proposal_hash, human_confirmed, {"draft", "submitted", "reviewed"})
        connection.execute(
            "UPDATE architecture_change_proposals SET status='rejected',rejected_by=?,rejected_at=CURRENT_TIMESTAMP,rejection_reason=? WHERE id=?",
            (rejected_by, reason.strip(), proposal_id),
        )
        connection.execute(
            "UPDATE architecture_adrs SET status='rejected',rejected_by=?,rejected_at=CURRENT_TIMESTAMP WHERE proposal_id=? AND status='proposed'",
            (rejected_by, proposal_id),
        )
        adr = connection.execute("SELECT id FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        adr_id = int(adr[0]) if adr else None
    external = _event(root_path, proposal_id, adr_id, "architecture.change.proposal_rejected", {"proposal_id": proposal_id, "proposal_hash": expected_proposal_hash, "rejected_by": rejected_by, "reason_hash": _sha(reason.strip())})
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result


@governed_mutation("architecture.change.proposal.bind_baseline")
def bind_change_proposal_baseline(
    root: Path | str,
    proposal_id: int,
    expected_proposal_hash: str,
    target_baseline_id: int,
    expected_target_baseline_hash: str,
    bound_by: str,
    human_confirmed: bool = False,
) -> dict[str, Any]:
    """Human-bind an approved proposal to a separately-created Architecture Baseline without activating it."""
    root_path = Path(root).resolve()
    with connect(root_path, immediate=True) as connection:
        row = _proposal(connection, proposal_id)
        _human_guard(row, expected_proposal_hash, human_confirmed, {"approved"})
        target = connection.execute("SELECT id,baseline_hash,status,section_count FROM architecture_baselines WHERE id=?", (target_baseline_id,)).fetchone()
        if not target:
            raise RuntimeError("architecture_change_target_baseline_not_found")
        target_dict = dict(target)
        if str(target_dict["baseline_hash"]) != expected_target_baseline_hash:
            raise RuntimeError("architecture_change_target_baseline_hash_mismatch")
        if int(target_dict["id"]) == int(row["source_baseline_id"]):
            raise RuntimeError("architecture_change_target_must_differ_from_source")
        if str(target_dict["status"]) not in {"draft", "reviewed", "approved"}:
            raise RuntimeError("architecture_change_target_baseline_not_candidate")
        if int(target_dict["section_count"]) != 27:
            raise RuntimeError("architecture_change_target_baseline_incomplete")
        already_bound = False
        if row.get("target_baseline_id") is not None:
            if int(row["target_baseline_id"]) == target_baseline_id and str(row.get("target_baseline_hash") or "") == expected_target_baseline_hash:
                already_bound = True
            else:
                raise RuntimeError("architecture_change_proposal_already_bound")
        if not already_bound:
            connection.execute(
                "UPDATE architecture_change_proposals SET target_baseline_id=?,target_baseline_hash=?,bound_by=?,bound_at=CURRENT_TIMESTAMP WHERE id=?",
                (target_baseline_id, expected_target_baseline_hash, bound_by, proposal_id),
            )
        adr = connection.execute("SELECT id FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        adr_id = int(adr[0]) if adr else None
    if already_bound:
        return architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    external = _event(root_path, proposal_id, adr_id, "architecture.change.proposal_baseline_bound", {"proposal_id": proposal_id, "proposal_hash": expected_proposal_hash, "target_baseline_id": target_baseline_id, "target_baseline_hash": expected_target_baseline_hash, "bound_by": bound_by})
    result = architecture_change_proposal_get(root_path, proposal_id=proposal_id, read_only=False)
    result["external_event_hash"] = external
    return result


def architecture_change_proposal_get(
    root: Path | str,
    *,
    proposal_id: int | None = None,
    read_only: bool = True,
) -> dict[str, Any]:
    """Read one latest/selected change proposal, linked compliance findings, and ADR."""
    connector = connect_read_only if read_only else connect
    with connector(Path(root).resolve()) as connection:
        if proposal_id is None:
            row = connection.execute("SELECT * FROM architecture_change_proposals ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = connection.execute("SELECT * FROM architecture_change_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            return {"ok": True, "proposal": None, "findings": [], "adr": None}
        proposal = dict(row)
        for key in ("affected_sections_json", "proposed_changes_json", "impact_analysis_json", "validation_plan_json", "rollback_plan_json"):
            proposal[key.removesuffix("_json")] = json.loads(proposal.pop(key))
        findings = [dict(item) for item in connection.execute(
            """SELECT f.id,f.section_id,f.finding_code,f.severity,f.subject,pf.finding_hash
               FROM architecture_change_proposal_findings pf
               JOIN architecture_compliance_findings f ON f.id=pf.finding_id
               WHERE pf.proposal_id=? ORDER BY f.id""", (proposal["id"],)
        ).fetchall()]
        adr_row = connection.execute("SELECT * FROM architecture_adrs WHERE proposal_id=?", (proposal["id"],)).fetchone()
        adr = dict(adr_row) if adr_row else None
        if adr:
            for key in ("context_text", "decision_text", "consequences_text", "alternatives_json"):
                value = adr.pop(key)
                out_key = {"context_text":"context", "decision_text":"decision", "consequences_text":"consequences", "alternatives_json":"alternatives"}[key]
                try:
                    adr[out_key] = json.loads(value)
                except json.JSONDecodeError:
                    adr[out_key] = value
    return {
        "ok": True,
        "proposal": proposal,
        "findings": findings,
        "adr": adr,
        "architecture_authority_changed": False,
        "working_copy_modified": False,
    }


def architecture_change_proposals_list(
    root: Path | str,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List proposal summaries without architecture mutation authority."""
    if status is not None and status not in PROPOSAL_STATUSES:
        raise RuntimeError("invalid_architecture_change_status")
    query = "SELECT id,proposal_uuid,source_baseline_id,source_baseline_hash,source_compliance_run_id,title,status,proposal_hash,created_by,created_at,target_baseline_id,target_baseline_hash FROM architecture_change_proposals"
    args: list[Any] = []
    if status is not None:
        query += " WHERE status=?"; args.append(status)
    query += " ORDER BY id DESC LIMIT ?"; args.append(max(1, min(int(limit), 500)))
    with connect_read_only(Path(root).resolve()) as connection:
        return [dict(row) for row in connection.execute(query, tuple(args)).fetchall()]


def architecture_adr_get(root: Path | str, *, adr_id: int | None = None, proposal_id: int | None = None) -> dict[str, Any]:
    """Read one ADR snapshot and render a stable Markdown representation."""
    with connect_read_only(Path(root).resolve()) as connection:
        if adr_id is not None:
            row = connection.execute("SELECT * FROM architecture_adrs WHERE id=?", (adr_id,)).fetchone()
        elif proposal_id is not None:
            row = connection.execute("SELECT * FROM architecture_adrs WHERE proposal_id=?", (proposal_id,)).fetchone()
        else:
            row = connection.execute("SELECT * FROM architecture_adrs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {"ok": True, "adr": None}
        adr = dict(row)
    context = json.loads(adr["context_text"])
    decision = json.loads(adr["decision_text"])
    consequences = json.loads(adr["consequences_text"])
    alternatives = json.loads(adr["alternatives_json"])
    markdown = (
        f"# ADR — {adr['title']}\n\n"
        f"Status: {adr['status']}\n\n"
        f"Proposal ID: {adr['proposal_id']}\n\n"
        "## Context\n\n```json\n" + json.dumps(context, ensure_ascii=False, indent=2) + "\n```\n\n"
        "## Decision\n\n```json\n" + json.dumps(decision, ensure_ascii=False, indent=2) + "\n```\n\n"
        "## Consequences\n\n```json\n" + json.dumps(consequences, ensure_ascii=False, indent=2) + "\n```\n\n"
        "## Alternatives\n\n```json\n" + json.dumps(alternatives, ensure_ascii=False, indent=2) + "\n```\n"
    )
    adr["context"] = context; adr["decision"] = decision; adr["consequences"] = consequences; adr["alternatives"] = alternatives
    for key in ("context_text", "decision_text", "consequences_text", "alternatives_json"):
        adr.pop(key, None)
    return {"ok": True, "adr": adr, "markdown": markdown, "architecture_authority_changed": False}


def architecture_change_status(root: Path | str) -> dict[str, Any]:
    """Return proposal/ADR lifecycle readiness and explicit authority boundaries."""
    with connect_read_only(Path(root).resolve()) as connection:
        active = _active_baseline(connection)
        counts = {str(row[0]): int(row[1]) for row in connection.execute("SELECT status,COUNT(*) FROM architecture_change_proposals GROUP BY status").fetchall()}
        latest = connection.execute("SELECT id,title,status,proposal_hash,source_baseline_id,target_baseline_id FROM architecture_change_proposals ORDER BY id DESC LIMIT 1").fetchone()
        adr_counts = {str(row[0]): int(row[1]) for row in connection.execute("SELECT status,COUNT(*) FROM architecture_adrs GROUP BY status").fetchall()}
    return {
        "ok": True,
        "lifecycle_version": CHANGE_LIFECYCLE_VERSION,
        "active_baseline": active,
        "proposal_status_counts": counts,
        "adr_status_counts": adr_counts,
        "latest_proposal": dict(latest) if latest else None,
        "proposal_creation_authority": "ai_or_human_proposal_only",
        "human_review_required": True,
        "human_approval_required": True,
        "approval_authority_exposed_via_mcp": False,
        "baseline_activation_authority_exposed_via_mcp": False,
        "automatic_working_copy_mutation": False,
        "approved_proposal_requires_separate_baseline_lifecycle": True,
    }
