"""
File: .agents/agentos/architecture_contract.py

Purpose:
    Implement the v0.25.2 27-section Architecture Contract authority.

Responsibilities:
    - Maintain the fixed ARCH-01..ARCH-27 registry.
    - Materialize human-readable and machine-readable working-copy templates.
    - Validate working-copy structure without inferring project architecture.
    - Snapshot immutable section revisions into deterministic baselines.
    - Enforce human-only review, approval, activation, rejection, and supersession.
    - Expose redacted/read-only architecture state for governed clients.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .governance_enforcement import governed_mutation

MIGRATION_VERSION = 50
CONTRACT_SCHEMA_VERSION = 1
APPLICABILITY = {"unresolved", "applicable", "not_applicable"}
BASELINE_STATUSES = {"draft", "reviewed", "approved", "active", "superseded", "rejected"}
FORBIDDEN_AUTHORITY_FIELDS = {
    "status", "active", "activated", "approved", "reviewed", "rejected", "superseded",
    "approved_by", "reviewed_by", "activated_by", "rejected_by", "human_confirmed",
}

_SECTION_NAMES = (
    "Project Overview", "Tech Stack", "Folder Structure", "System Architecture", "Module Breakdown",
    "Request Flow", "Authentication", "Authorization", "Database", "API Architecture", "Business Flow",
    "Dependency Graph", "External Services", "Configuration", "Logging", "Error Handling", "Security",
    "Performance", "Scalability", "Deployment", "Testing", "Coding Convention", "Design Pattern", "Strengths",
    "Technical Debt", "Improvement Proposal", "Appendix",
)
ARCHITECTURE_SECTIONS: tuple[dict[str, str], ...] = tuple(
    {"section_id": f"ARCH-{index:02d}", "title": title, "authority_mode": "proposal_only" if index == 26 else "current"}
    for index, title in enumerate(_SECTION_NAMES, 1)
)
SECTION_BY_ID = {item["section_id"]: item for item in ARCHITECTURE_SECTIONS}


def migration_50(c) -> None:
    """Create Architecture Contract and Human Clarification schema objects."""
    c.executescript("""
    CREATE TABLE IF NOT EXISTS architecture_baselines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        baseline_uuid TEXT NOT NULL UNIQUE,
        baseline_version INTEGER NOT NULL UNIQUE,
        status TEXT NOT NULL CHECK(status IN ('draft','reviewed','approved','active','superseded','rejected')),
        baseline_hash TEXT NOT NULL UNIQUE,
        section_count INTEGER NOT NULL CHECK(section_count=27),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reviewed_by TEXT,
        reviewed_at TEXT,
        approved_by TEXT,
        approved_at TEXT,
        activated_by TEXT,
        activated_at TEXT,
        superseded_by_baseline_id INTEGER,
        rejected_by TEXT,
        rejected_at TEXT,
        rejection_reason TEXT,
        FOREIGN KEY(superseded_by_baseline_id) REFERENCES architecture_baselines(id)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_architecture_one_active
        ON architecture_baselines(status) WHERE status='active';

    CREATE TABLE IF NOT EXISTS architecture_section_revisions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        title TEXT NOT NULL,
        applicability TEXT NOT NULL CHECK(applicability IN ('unresolved','applicable','not_applicable')),
        authority_mode TEXT NOT NULL CHECK(authority_mode IN ('current','proposal_only')),
        markdown_hash TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        section_hash TEXT NOT NULL,
        markdown_content TEXT NOT NULL,
        contract_json TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(section_id, revision),
        UNIQUE(section_id, section_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_arch_section_hash ON architecture_section_revisions(section_hash);

    CREATE TABLE IF NOT EXISTS architecture_contract_artifacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section_revision_id INTEGER NOT NULL,
        artifact_kind TEXT NOT NULL CHECK(artifact_kind IN ('markdown','json')),
        source_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        content_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(section_revision_id) REFERENCES architecture_section_revisions(id),
        UNIQUE(section_revision_id, artifact_kind)
    );

    CREATE TABLE IF NOT EXISTS architecture_baseline_sections(
        baseline_id INTEGER NOT NULL,
        section_id TEXT NOT NULL,
        section_revision_id INTEGER NOT NULL,
        section_hash TEXT NOT NULL,
        PRIMARY KEY(baseline_id, section_id),
        FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id),
        FOREIGN KEY(section_revision_id) REFERENCES architecture_section_revisions(id)
    );

    CREATE TABLE IF NOT EXISTS architecture_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        baseline_id INTEGER,
        section_id TEXT,
        event_type TEXT NOT NULL,
        event_json TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id)
    );
    CREATE INDEX IF NOT EXISTS idx_architecture_events_baseline ON architecture_events(baseline_id,id);

    CREATE TABLE IF NOT EXISTS task_clarity_assessments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_uuid TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('clear','needs_clarification')),
        objective_understood INTEGER NOT NULL,
        scope_understood INTEGER NOT NULL,
        constraints_understood INTEGER NOT NULL,
        acceptance_understood INTEGER NOT NULL,
        assumptions_json TEXT NOT NULL,
        ambiguities_json TEXT NOT NULL,
        decisions_required_json TEXT NOT NULL,
        blocking_question_count INTEGER NOT NULL,
        assessed_by TEXT NOT NULL,
        assessment_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX IF NOT EXISTS idx_clarity_task ON task_clarity_assessments(task_id,id);

    CREATE TABLE IF NOT EXISTS human_decision_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_uuid TEXT NOT NULL UNIQUE,
        task_id TEXT NOT NULL,
        phase TEXT NOT NULL,
        decision_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        blocking INTEGER NOT NULL DEFAULT 1,
        question TEXT NOT NULL,
        question_hash TEXT NOT NULL,
        options_json TEXT NOT NULL,
        recommendation TEXT,
        recommendation_rationale TEXT,
        requirement_ids_json TEXT NOT NULL,
        architecture_section_ids_json TEXT NOT NULL,
        task_request_hash TEXT NOT NULL,
        plan_hash TEXT,
        architecture_baseline_hash TEXT,
        raised_by_session TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved','withdrawn')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        FOREIGN KEY(task_id) REFERENCES tasks(id)
    );
    CREATE INDEX IF NOT EXISTS idx_human_decision_task_status ON human_decision_requests(task_id,status,blocking);

    CREATE TABLE IF NOT EXISTS human_decision_resolutions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER NOT NULL UNIQUE,
        selected_option TEXT,
        answer_text TEXT NOT NULL,
        answer_hash TEXT NOT NULL,
        resolved_by TEXT NOT NULL,
        human_confirmed INTEGER NOT NULL CHECK(human_confirmed=1),
        impact_classification TEXT NOT NULL CHECK(impact_classification IN ('none','requirement_change','scope_change','architecture_change')),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(decision_id) REFERENCES human_decision_requests(id)
    );

    CREATE TABLE IF NOT EXISTS human_decision_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id INTEGER,
        event_type TEXT NOT NULL,
        event_json TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        external_event_hash TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(decision_id) REFERENCES human_decision_requests(id)
    );
    """)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _slug(title: str) -> str:
    return title.lower().replace("/", "-").replace("&", "and").replace(" ", "-")


def _paths(root: Path, section: dict[str, str]) -> tuple[Path, Path]:
    base = root.resolve() / ".agents" / "architecture"
    stem = f'{section["section_id"]}-{_slug(section["title"])}'
    return base / "sections" / f"{stem}.md", base / "contracts" / f"{stem}.json"


def architecture_init(root: Path, created_by: str = "human", overwrite: bool = False) -> dict[str, Any]:
    """Create non-authoritative 27-section working-copy templates without source inference."""
    root = root.resolve()
    base = root / ".agents" / "architecture"
    (base / "sections").mkdir(parents=True, exist_ok=True)
    (base / "contracts").mkdir(parents=True, exist_ok=True)
    created, preserved = [], []
    for section in ARCHITECTURE_SECTIONS:
        md_path, json_path = _paths(root, section)
        md = (
            f'# {section["section_id"]} — {section["title"]}\n\n'
            "> Working copy only. This file is not Architecture Authority until a human-approved baseline is activated.\n\n"
            "## Intent\n\nUNRESOLVED — human architect input required.\n\n"
            "## Contract\n\nUNRESOLVED.\n\n"
            "## Notes\n\n"
        )
        contract = {
            "contract_schema_version": CONTRACT_SCHEMA_VERSION,
            "section_id": section["section_id"],
            "title": section["title"],
            "applicability": "unresolved",
            "authority_mode": section["authority_mode"],
            "payload": {},
        }
        for path, content in ((md_path, md), (json_path, json.dumps(contract, ensure_ascii=False, indent=2) + "\n")):
            if path.exists() and not overwrite:
                preserved.append(path.relative_to(root).as_posix())
            else:
                path.write_text(content, encoding="utf-8")
                created.append(path.relative_to(root).as_posix())
    index = base / "architecture.json"
    index_payload = {
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "section_count": 27,
        "authority": "human_only",
        "working_copy_is_authority": False,
        "created_by": created_by,
        "sections": [{"section_id": s["section_id"], "title": s["title"], "authority_mode": s["authority_mode"]} for s in ARCHITECTURE_SECTIONS],
    }
    if not index.exists() or overwrite:
        index.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created.append(index.relative_to(root).as_posix())
    else:
        preserved.append(index.relative_to(root).as_posix())
    return {"ok": True, "section_count": 27, "created": created, "preserved": preserved, "source_inference_performed": False}


def _find_forbidden(value: Any, prefix: str = "") -> list[str]:
    """Return forbidden top-level authority fields from a working-copy contract.

    Payload fields are project data, not AgentOS lifecycle authority, so they are not
    interpreted as review/approval state.
    """
    if not isinstance(value, dict):
        return []
    return sorted(str(key) for key in value if str(key).lower() in FORBIDDEN_AUTHORITY_FIELDS)


def validate_working_copy(root: Path) -> dict[str, Any]:
    """Validate exact section registry, contract envelopes, and deterministic hashes."""
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    expected_paths: set[str] = set()
    for section in ARCHITECTURE_SECTIONS:
        md_path, json_path = _paths(root, section)
        expected_paths |= {md_path.relative_to(root).as_posix(), json_path.relative_to(root).as_posix()}
        if not md_path.is_file():
            findings.append({"code": "missing_markdown", "section_id": section["section_id"], "path": md_path.relative_to(root).as_posix()})
            continue
        if not json_path.is_file():
            findings.append({"code": "missing_contract", "section_id": section["section_id"], "path": json_path.relative_to(root).as_posix()})
            continue
        markdown = md_path.read_text(encoding="utf-8")
        try:
            contract = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append({"code": "invalid_contract_json", "section_id": section["section_id"], "detail": str(exc)})
            continue
        if contract.get("contract_schema_version") != CONTRACT_SCHEMA_VERSION:
            findings.append({"code": "contract_schema_version_mismatch", "section_id": section["section_id"]})
        if contract.get("section_id") != section["section_id"]:
            findings.append({"code": "section_id_mismatch", "section_id": section["section_id"]})
        if contract.get("title") != section["title"]:
            findings.append({"code": "section_title_mismatch", "section_id": section["section_id"]})
        applicability = contract.get("applicability")
        if applicability not in APPLICABILITY:
            findings.append({"code": "invalid_applicability", "section_id": section["section_id"]})
        if applicability == "not_applicable" and not str(contract.get("not_applicable_reason", "")).strip():
            findings.append({"code": "not_applicable_reason_required", "section_id": section["section_id"]})
        if contract.get("authority_mode") != section["authority_mode"]:
            findings.append({"code": "authority_mode_mismatch", "section_id": section["section_id"]})
        payload = contract.get("payload")
        if not isinstance(payload, dict):
            findings.append({"code": "contract_payload_must_be_object", "section_id": section["section_id"]})
        if applicability == "applicable" and isinstance(payload, dict) and not payload:
            findings.append({"code": "applicable_contract_payload_required", "section_id": section["section_id"]})
        if applicability != "unresolved" and ("UNRESOLVED — human architect input required." in markdown or "## Contract\n\nUNRESOLVED." in markdown):
            findings.append({"code": "resolved_section_contains_default_unresolved_marker", "section_id": section["section_id"]})
        forbidden = _find_forbidden(contract)
        if forbidden:
            findings.append({"code": "authority_fields_forbidden_in_working_copy", "section_id": section["section_id"], "fields": forbidden})
        markdown_hash = _sha(markdown)
        contract_text = _canonical(contract)
        contract_hash = _sha(contract_text)
        section_hash = _sha(f'{section["section_id"]}|{markdown_hash}|{contract_hash}')
        sections.append({
            "section_id": section["section_id"], "title": section["title"], "applicability": applicability,
            "authority_mode": section["authority_mode"], "markdown_hash": markdown_hash,
            "contract_hash": contract_hash, "section_hash": section_hash,
            "markdown": markdown, "contract": contract,
            "markdown_path": md_path.relative_to(root).as_posix(), "contract_path": json_path.relative_to(root).as_posix(),
        })
    for bucket, suffix in ((root / ".agents" / "architecture" / "sections", ".md"), (root / ".agents" / "architecture" / "contracts", ".json")):
        if bucket.is_dir():
            for path in bucket.glob(f"ARCH-*{suffix}"):
                rel = path.relative_to(root).as_posix()
                if rel not in expected_paths:
                    findings.append({"code": "unknown_architecture_section_artifact", "path": rel})
    unresolved = [item["section_id"] for item in sections if item.get("applicability") == "unresolved"]
    structural_ok = not findings and len(sections) == 27
    baseline_hash = _sha("\n".join(f'{item["section_id"]}:{item["section_hash"]}' for item in sections)) if structural_ok else None
    return {
        "ok": structural_ok,
        "approval_ready": structural_ok and not unresolved,
        "section_count": len(sections),
        "expected_section_count": 27,
        "baseline_hash": baseline_hash,
        "unresolved_sections": unresolved,
        "findings": findings,
        "sections": sections,
    }


def _event(root: Path, baseline_id: int | None, section_id: str | None, event_type: str, payload: dict[str, Any], task_id: str | None = None, session_id: str | None = None) -> str:
    clean = dict(payload)
    body = _canonical(clean)
    digest = _sha(body)
    signed = append_signed_event(root, event_type, {**clean, "event_hash": digest}, task_id, session_id)
    with connect(root) as c:
        c.execute(
            "INSERT INTO architecture_events(baseline_id,section_id,event_type,event_json,event_hash,external_event_hash) VALUES(?,?,?,?,?,?)",
            (baseline_id, section_id, event_type, body, digest, signed["event_hash"]),
        )
    return signed["event_hash"]


def create_baseline(root: Path, created_by: str) -> dict[str, Any]:
    """Snapshot the current working copy into immutable DB revisions."""
    report = validate_working_copy(root)
    if not report["ok"]:
        raise RuntimeError("architecture_working_copy_invalid")
    baseline_hash = str(report["baseline_hash"])
    with connect(root, immediate=True) as c:
        existing = c.execute("SELECT * FROM architecture_baselines WHERE baseline_hash=?", (baseline_hash,)).fetchone()
        if existing:
            return {"ok": True, "existing": True, **dict(existing)}
        version = int(c.execute("SELECT COALESCE(MAX(baseline_version),0)+1 AS v FROM architecture_baselines").fetchone()["v"])
        cur = c.execute(
            "INSERT INTO architecture_baselines(baseline_uuid,baseline_version,status,baseline_hash,section_count,created_by) VALUES(?,?,?,?,27,?)",
            (str(uuid.uuid4()), version, "draft", baseline_hash, created_by),
        )
        baseline_id = int(cur.lastrowid)
        for item in report["sections"]:
            row = c.execute("SELECT id,revision FROM architecture_section_revisions WHERE section_id=? AND section_hash=?", (item["section_id"], item["section_hash"])).fetchone()
            if row:
                revision_id = int(row["id"])
            else:
                revision = int(c.execute("SELECT COALESCE(MAX(revision),0)+1 AS r FROM architecture_section_revisions WHERE section_id=?", (item["section_id"],)).fetchone()["r"])
                cur = c.execute(
                    """INSERT INTO architecture_section_revisions(section_id,revision,title,applicability,authority_mode,markdown_hash,contract_hash,section_hash,markdown_content,contract_json,created_by)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (item["section_id"], revision, item["title"], item["applicability"], item["authority_mode"], item["markdown_hash"], item["contract_hash"], item["section_hash"], item["markdown"], _canonical(item["contract"]), created_by),
                )
                revision_id = int(cur.lastrowid)
                c.execute("INSERT INTO architecture_contract_artifacts(section_revision_id,artifact_kind,source_path,content_hash,content_text) VALUES(?,?,?,?,?)", (revision_id, "markdown", item["markdown_path"], item["markdown_hash"], item["markdown"]))
                c.execute("INSERT INTO architecture_contract_artifacts(section_revision_id,artifact_kind,source_path,content_hash,content_text) VALUES(?,?,?,?,?)", (revision_id, "json", item["contract_path"], item["contract_hash"], _canonical(item["contract"])))
            c.execute("INSERT INTO architecture_baseline_sections(baseline_id,section_id,section_revision_id,section_hash) VALUES(?,?,?,?)", (baseline_id, item["section_id"], revision_id, item["section_hash"]))
    external = _event(root, baseline_id, None, "architecture.baseline_created", {"baseline_id": baseline_id, "baseline_version": version, "baseline_hash": baseline_hash, "section_count": 27})
    return {"ok": True, "existing": False, "id": baseline_id, "baseline_version": version, "status": "draft", "baseline_hash": baseline_hash, "section_count": 27, "external_event_hash": external}


def _baseline(root: Path, baseline_id: int, read_only: bool = False) -> dict[str, Any]:
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        row = c.execute("SELECT * FROM architecture_baselines WHERE id=?", (baseline_id,)).fetchone()
    if not row:
        raise RuntimeError("architecture_baseline_not_found")
    return dict(row)


def _human_guard(row: dict[str, Any], expected_hash: str, human_confirmed: bool, allowed_statuses: set[str]) -> None:
    if not human_confirmed:
        raise RuntimeError("explicit_human_confirmation_required")
    if row["baseline_hash"] != expected_hash:
        raise RuntimeError("architecture_baseline_hash_mismatch")
    if row["status"] not in allowed_statuses:
        raise RuntimeError(f'architecture_invalid_transition_from:{row["status"]}')


@governed_mutation("architecture.baseline.review")
def review_baseline(root: Path, baseline_id: int, expected_baseline_hash: str, reviewed_by: str, human_confirmed: bool = False) -> dict[str, Any]:
    """Record explicit human review of one exact draft baseline.

    Args:
        root: Project root.
        baseline_id: Draft baseline database identifier.
        expected_baseline_hash: Exact content hash reviewed by the human.
        reviewed_by: Human reviewer identity label.
        human_confirmed: Explicit confirmation flag.

    Returns:
        Updated lifecycle metadata and signed-event hash.

    Raises:
        RuntimeError: When confirmation, hash, or lifecycle state is invalid.
    """
    row = _baseline(root, baseline_id)
    _human_guard(row, expected_baseline_hash, human_confirmed, {"draft"})
    with connect(root, immediate=True) as c:
        c.execute("UPDATE architecture_baselines SET status='reviewed',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=? AND status='draft'", (reviewed_by, baseline_id))
    external = _event(root, baseline_id, None, "architecture.baseline_reviewed", {"baseline_id": baseline_id, "baseline_hash": expected_baseline_hash, "reviewed_by": reviewed_by})
    return {"ok": True, "baseline_id": baseline_id, "status": "reviewed", "external_event_hash": external}


@governed_mutation("architecture.baseline.approve")
def approve_baseline(root: Path, baseline_id: int, expected_baseline_hash: str, approved_by: str, human_confirmed: bool = False) -> dict[str, Any]:
    """Approve a reviewed, fully resolved baseline by explicit human authority.

    Args:
        root: Project root.
        baseline_id: Reviewed baseline database identifier.
        expected_baseline_hash: Exact approved content hash.
        approved_by: Human approver identity label.
        human_confirmed: Explicit confirmation flag.

    Returns:
        Approved lifecycle metadata.

    Raises:
        RuntimeError: When sections remain unresolved or authority checks fail.
    """
    row = _baseline(root, baseline_id)
    _human_guard(row, expected_baseline_hash, human_confirmed, {"reviewed"})
    with connect(root) as c:
        unresolved = c.execute("""SELECT COUNT(*) AS n FROM architecture_baseline_sections bs JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id WHERE bs.baseline_id=? AND sr.applicability='unresolved'""", (baseline_id,)).fetchone()["n"]
    if unresolved:
        raise RuntimeError(f"architecture_unresolved_sections:{unresolved}")
    with connect(root, immediate=True) as c:
        c.execute("UPDATE architecture_baselines SET status='approved',approved_by=?,approved_at=CURRENT_TIMESTAMP WHERE id=? AND status='reviewed'", (approved_by, baseline_id))
    external = _event(root, baseline_id, None, "architecture.baseline_approved", {"baseline_id": baseline_id, "baseline_hash": expected_baseline_hash, "approved_by": approved_by})
    return {"ok": True, "baseline_id": baseline_id, "status": "approved", "external_event_hash": external}


@governed_mutation("architecture.baseline.activate")
def activate_baseline(root: Path, baseline_id: int, expected_baseline_hash: str, activated_by: str, human_confirmed: bool = False) -> dict[str, Any]:
    """Activate one approved baseline and supersede any prior active baseline.

    Args:
        root: Project root.
        baseline_id: Approved baseline identifier.
        expected_baseline_hash: Exact content hash being activated.
        activated_by: Human activator identity label.
        human_confirmed: Explicit confirmation flag.

    Returns:
        Active lifecycle metadata.

    Raises:
        RuntimeError: When hash, confirmation, or state is invalid.
    """
    row = _baseline(root, baseline_id)
    _human_guard(row, expected_baseline_hash, human_confirmed, {"approved"})
    with connect(root, immediate=True) as c:
        old = c.execute("SELECT id FROM architecture_baselines WHERE status='active'").fetchone()
        if old and int(old["id"]) != baseline_id:
            c.execute("UPDATE architecture_baselines SET status='superseded',superseded_by_baseline_id=? WHERE id=? AND status='active'", (baseline_id, int(old["id"])))
        c.execute("UPDATE architecture_baselines SET status='active',activated_by=?,activated_at=CURRENT_TIMESTAMP WHERE id=? AND status='approved'", (activated_by, baseline_id))
    external = _event(root, baseline_id, None, "architecture.baseline_activated", {"baseline_id": baseline_id, "baseline_hash": expected_baseline_hash, "activated_by": activated_by})
    return {"ok": True, "baseline_id": baseline_id, "status": "active", "external_event_hash": external}


@governed_mutation("architecture.baseline.reject")
def reject_baseline(root: Path, baseline_id: int, expected_baseline_hash: str, rejected_by: str, reason: str, human_confirmed: bool = False) -> dict[str, Any]:
    """Reject a non-active baseline under explicit human authority.

    Args:
        root: Project root.
        baseline_id: Candidate baseline identifier.
        expected_baseline_hash: Exact content hash being rejected.
        rejected_by: Human reviewer identity label.
        reason: Local rejection explanation.
        human_confirmed: Explicit confirmation flag.

    Returns:
        Rejected lifecycle metadata.

    Raises:
        RuntimeError: When reason, confirmation, hash, or state is invalid.
    """
    row = _baseline(root, baseline_id)
    _human_guard(row, expected_baseline_hash, human_confirmed, {"draft", "reviewed", "approved"})
    if not reason.strip():
        raise RuntimeError("rejection_reason_required")
    with connect(root, immediate=True) as c:
        c.execute("UPDATE architecture_baselines SET status='rejected',rejected_by=?,rejected_at=CURRENT_TIMESTAMP,rejection_reason=? WHERE id=?", (rejected_by, reason, baseline_id))
    external = _event(root, baseline_id, None, "architecture.baseline_rejected", {"baseline_id": baseline_id, "baseline_hash": expected_baseline_hash, "rejected_by": rejected_by, "reason_hash": _sha(reason)})
    return {"ok": True, "baseline_id": baseline_id, "status": "rejected", "external_event_hash": external}


def architecture_status(root: Path, read_only: bool = False) -> dict[str, Any]:
    """Return active/latest baseline and working-copy integrity without mutation."""
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        active = c.execute("SELECT * FROM architecture_baselines WHERE status='active' LIMIT 1").fetchone()
        latest = c.execute("SELECT * FROM architecture_baselines ORDER BY baseline_version DESC LIMIT 1").fetchone()
    working = validate_working_copy(root)
    active_dict = dict(active) if active else None
    return {
        "ok": True,
        "active_baseline": active_dict,
        "latest_baseline": dict(latest) if latest else None,
        "working_copy": {k: working[k] for k in ("ok", "approval_ready", "baseline_hash", "unresolved_sections", "findings")},
        "workspace_matches_active": bool(active_dict and working.get("baseline_hash") == active_dict.get("baseline_hash")),
    }


def architecture_get(root: Path, baseline_id: int | None = None, read_only: bool = False) -> dict[str, Any]:
    """Read one active/latest architecture baseline without changing authority.

    Args:
        root: Project root.
        baseline_id: Optional explicit baseline identifier.
        read_only: Use strict SQLite read-only mode when true.

    Returns:
        Baseline metadata and ordered section revision summaries.
    """
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        if baseline_id is None:
            row = c.execute("SELECT * FROM architecture_baselines WHERE status='active' LIMIT 1").fetchone() or c.execute("SELECT * FROM architecture_baselines ORDER BY baseline_version DESC LIMIT 1").fetchone()
        else:
            row = c.execute("SELECT * FROM architecture_baselines WHERE id=?", (baseline_id,)).fetchone()
        if not row:
            return {"ok": True, "baseline": None, "sections": []}
        rows = c.execute("""SELECT bs.section_id,sr.revision,sr.title,sr.applicability,sr.authority_mode,bs.section_hash FROM architecture_baseline_sections bs JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id WHERE bs.baseline_id=? ORDER BY bs.section_id""", (row["id"],)).fetchall()
    return {"ok": True, "baseline": dict(row), "sections": [dict(item) for item in rows]}


def architecture_section_get(root: Path, section_id: str, baseline_id: int | None = None, read_only: bool = False) -> dict[str, Any]:
    """Read one fixed architecture section from a baseline snapshot.

    Args:
        root: Project root.
        section_id: Fixed ARCH-01..ARCH-27 identifier.
        baseline_id: Optional explicit baseline identifier.
        read_only: Use strict SQLite read-only mode when true.

    Returns:
        Section revision, Markdown snapshot, machine contract, and hash.

    Raises:
        RuntimeError: When the section identifier is unknown.
    """
    if section_id not in SECTION_BY_ID:
        raise RuntimeError("unknown_architecture_section")
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        if baseline_id is None:
            base = c.execute("SELECT id FROM architecture_baselines WHERE status='active' LIMIT 1").fetchone() or c.execute("SELECT id FROM architecture_baselines ORDER BY baseline_version DESC LIMIT 1").fetchone()
            if not base:
                return {"ok": True, "section_id": section_id, "revision": None}
            baseline_id = int(base["id"])
        row = c.execute("""SELECT sr.section_id,sr.revision,sr.title,sr.applicability,sr.authority_mode,sr.markdown_content,sr.contract_json,sr.section_hash FROM architecture_baseline_sections bs JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id WHERE bs.baseline_id=? AND bs.section_id=?""", (baseline_id, section_id)).fetchone()
    if not row:
        return {"ok": True, "section_id": section_id, "revision": None}
    result = dict(row)
    result["contract"] = json.loads(result.pop("contract_json"))
    return {"ok": True, "baseline_id": baseline_id, "section": result}
