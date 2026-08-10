"""
File: .agents/agentos/project_consolidation.py

Purpose:
    Implement AgentOS v0.20.2 Primary-Project Consolidation with one human-selected
    primary project as the only writable target and all secondary projects as
    immutable read-only sources.

Responsibilities:
    - Create consolidation state from a frozen v0.20.1 primary selection.
    - Register explicit component mappings with source and target hashes.
    - Enforce REUSE/MOVE/ADAPT/REIMPLEMENT/IGNORE/CONFLICT semantics.
    - Require human review and approval bound to an immutable plan hash.
    - Materialize only approved mappings into the active primary project.
    - Re-verify source identity, source manifest, and source file hash before use.
    - Use expected-hash/expected-absence checks and atomic target writes.
    - Preserve per-component provenance and rollback backups in the primary.
    - Never write, delete, rename, chmod, or create files in secondary projects.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any
import uuid

from .project_identity import get_project_uuid
from .project_selection import get_candidate_set, scan_candidate_readonly

SCHEMA_VERSION = 34
ACTIONS = {"REUSE", "MOVE", "ADAPT", "REIMPLEMENT", "IGNORE", "CONFLICT"}
WRITING_ACTIONS = {"MOVE", "ADAPT", "REIMPLEMENT"}
TERMINAL_MAPPING_STATES = {"applied", "skipped"}
FORBIDDEN_ROOT_FILES = {"AGENTS.md", "VERSION"}
FORBIDDEN_PREFIXES = {".agents", ".git"}
MAX_COMPONENT_BYTES = 64 * 1024 * 1024


class ProjectConsolidationError(RuntimeError):
    """Raised when a consolidation operation violates governance invariants."""


def utc_now() -> str:
    """Return current UTC time as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for evidence hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    """Return SHA-256 for bytes."""
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    """Return SHA-256 for canonical JSON."""
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_file(path: Path) -> str:
    """Return SHA-256 for a regular file without modifying it."""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _db_path(root: Path | str) -> Path:
    """Return the active primary project's AgentOS SQLite database path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


def _connect(root: Path | str) -> sqlite3.Connection:
    """Open only the active primary project's local AgentOS database."""
    path = _db_path(root)
    if not path.exists():
        raise ProjectConsolidationError(f"AgentOS database is missing: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migration_34(conn: sqlite3.Connection) -> None:
    """Apply additive schema 34 for governed primary-project consolidation."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_consolidations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            coordinator_project_uuid TEXT NOT NULL,
            primary_project_uuid TEXT NOT NULL,
            primary_root_path TEXT NOT NULL,
            selection_hash TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            plan_revision INTEGER NOT NULL DEFAULT 1,
            plan_hash TEXT,
            approved_plan_hash TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_consolidation_sources(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_root_path TEXT NOT NULL,
            source_manifest_hash TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            readonly_verified INTEGER NOT NULL DEFAULT 1,
            registered_at TEXT NOT NULL,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id),
            UNIQUE(consolidation_id, source_project_uuid)
        );
        CREATE TABLE IF NOT EXISTS project_component_mappings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            source_size INTEGER NOT NULL,
            target_path TEXT,
            target_expected_hash TEXT,
            target_expected_absent INTEGER NOT NULL DEFAULT 0,
            action TEXT NOT NULL,
            rationale TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_result_json TEXT,
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id),
            UNIQUE(consolidation_id, source_project_uuid, source_path)
        );
        CREATE TABLE IF NOT EXISTS project_consolidation_reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            reviewed_by TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            review_reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reviewed',
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id)
        );
        CREATE TABLE IF NOT EXISTS project_consolidation_approvals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            plan_hash TEXT NOT NULL,
            approved_by TEXT NOT NULL,
            approved_at TEXT NOT NULL,
            approval_reason TEXT NOT NULL,
            human_confirmed INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            FOREIGN KEY(consolidation_id) REFERENCES project_consolidations(id)
        );
        CREATE TABLE IF NOT EXISTS project_component_provenance(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER NOT NULL,
            mapping_id INTEGER NOT NULL,
            primary_project_uuid TEXT NOT NULL,
            source_project_uuid TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            target_path TEXT,
            target_before_hash TEXT,
            target_after_hash TEXT,
            backup_path TEXT,
            action TEXT NOT NULL,
            execution_id TEXT NOT NULL,
            executed_by TEXT NOT NULL,
            executed_at TEXT NOT NULL,
            rollback_status TEXT NOT NULL DEFAULT 'not_rolled_back',
            rolled_back_by TEXT,
            rolled_back_at TEXT,
            rollback_reason TEXT,
            UNIQUE(execution_id)
        );
        CREATE TABLE IF NOT EXISTS project_consolidation_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consolidation_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_consolidations_candidate
            ON project_consolidations(candidate_set_id, status);
        CREATE INDEX IF NOT EXISTS idx_project_consolidation_sources
            ON project_consolidation_sources(consolidation_id, source_project_uuid);
        CREATE INDEX IF NOT EXISTS idx_project_component_mappings
            ON project_component_mappings(consolidation_id, status, action);
        CREATE INDEX IF NOT EXISTS idx_project_component_provenance_target
            ON project_component_provenance(primary_project_uuid, target_path, executed_at);
        """
    )


def sync_consolidation_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema-34 consolidation tables to the active project database."""
    required = {
        "project_consolidations",
        "project_consolidation_sources",
        "project_component_mappings",
        "project_consolidation_reviews",
        "project_consolidation_approvals",
        "project_component_provenance",
        "project_consolidation_events",
    }
    with _connect(root) as conn:
        migration_34(conn)
        tables = {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {"ok": required <= tables, "schema": SCHEMA_VERSION, "tables": sorted(required)}


def _event(conn: sqlite3.Connection, consolidation_id: int | None, event_type: str, payload: Any) -> None:
    """Append local consolidation evidence inside the primary project only."""
    conn.execute(
        "INSERT INTO project_consolidation_events(consolidation_id,event_type,event_json,created_at) VALUES(?,?,?,?)",
        (consolidation_id, event_type, _canonical_json(payload), utc_now()),
    )


def _normalize_rel_path(value: str, *, label: str) -> str:
    """Normalize a project-relative path and reject absolute/traversal paths."""
    text = str(value).replace("\\", "/").strip()
    if not text:
        raise ProjectConsolidationError(f"{label} is required")
    p = Path(text)
    if p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        raise ProjectConsolidationError(f"{label} must be a clean project-relative path: {value!r}")
    return "/".join(p.parts)


def _is_governance_path(rel: str) -> bool:
    """Return whether a path is reserved from cross-project consolidation."""
    p = Path(rel)
    if len(p.parts) == 1 and p.name in FORBIDDEN_ROOT_FILES:
        return True
    return bool(p.parts and p.parts[0] in FORBIDDEN_PREFIXES)


def _ensure_no_symlink_chain(root: Path, rel: str, *, allow_missing_leaf: bool) -> Path:
    """Resolve a path under root while rejecting symlinks in all existing components."""
    current = root.resolve()
    parts = Path(rel).parts
    for index, part in enumerate(parts):
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise ProjectConsolidationError(f"symlink paths are not allowed for consolidation: {current}")
        elif index != len(parts) - 1 or not allow_missing_leaf:
            if not allow_missing_leaf:
                raise ProjectConsolidationError(f"path does not exist: {current}")
    try:
        current.resolve(strict=False).relative_to(root.resolve())
    except ValueError as exc:
        raise ProjectConsolidationError(f"path escapes project root: {current}") from exc
    return current


def _source_file(source_root: Path, source_path: str) -> Path:
    """Validate and return one immutable source component file."""
    rel = _normalize_rel_path(source_path, label="source_path")
    if _is_governance_path(rel):
        raise ProjectConsolidationError("governance/instruction files cannot be consolidated from a source project")
    path = _ensure_no_symlink_chain(source_root, rel, allow_missing_leaf=False)
    if not path.is_file():
        raise ProjectConsolidationError(f"source component must be a regular file: {rel}")
    size = path.stat().st_size
    if size > MAX_COMPONENT_BYTES:
        raise ProjectConsolidationError(f"source component exceeds {MAX_COMPONENT_BYTES} bytes: {rel}")
    return path


def _target_file(primary_root: Path, target_path: str) -> tuple[str, Path]:
    """Validate a writable primary-project target path without creating it."""
    rel = _normalize_rel_path(target_path, label="target_path")
    if _is_governance_path(rel):
        raise ProjectConsolidationError("primary governance/instruction paths are not writable by consolidation")
    path = _ensure_no_symlink_chain(primary_root, rel, allow_missing_leaf=True)
    return rel, path


def _load_header(conn: sqlite3.Connection, consolidation_id: int) -> sqlite3.Row:
    """Load one consolidation header or fail."""
    row = conn.execute("SELECT * FROM project_consolidations WHERE id=?", (consolidation_id,)).fetchone()
    if row is None:
        raise ProjectConsolidationError(f"consolidation not found: {consolidation_id}")
    return row


def _assert_primary_authority(root: Path, header: sqlite3.Row) -> None:
    """Require the active root to be exactly the human-selected primary project."""
    active_uuid = get_project_uuid(root)
    if str(header["primary_project_uuid"]) != active_uuid:
        raise ProjectConsolidationError("active root is not the selected primary project")
    if str(header["coordinator_project_uuid"]) != active_uuid:
        raise ProjectConsolidationError("consolidation coordinator identity mismatch")
    if Path(str(header["primary_root_path"])).resolve() != root.resolve():
        raise ProjectConsolidationError("consolidation was created for a different primary root path")


def _source_rows(conn: sqlite3.Connection, consolidation_id: int) -> list[sqlite3.Row]:
    """Return registered source projects."""
    return conn.execute(
        "SELECT * FROM project_consolidation_sources WHERE consolidation_id=? ORDER BY source_project_uuid",
        (consolidation_id,),
    ).fetchall()


def _mapping_rows(conn: sqlite3.Connection, consolidation_id: int) -> list[sqlite3.Row]:
    """Return planned component mappings."""
    return conn.execute(
        "SELECT * FROM project_component_mappings WHERE consolidation_id=? ORDER BY id",
        (consolidation_id,),
    ).fetchall()


def _plan_payload(conn: sqlite3.Connection, consolidation_id: int) -> dict[str, Any]:
    """Return immutable plan payload used for review/approval hashing."""
    header = _load_header(conn, consolidation_id)
    sources = [
        {
            "source_project_uuid": r["source_project_uuid"],
            "source_manifest_hash": r["source_manifest_hash"],
            "domain_id": r["domain_id"],
            "purpose_id": r["purpose_id"],
            "readonly_verified": int(r["readonly_verified"]),
        }
        for r in _source_rows(conn, consolidation_id)
    ]
    mappings = [
        {
            "mapping_id": int(r["id"]),
            "source_project_uuid": r["source_project_uuid"],
            "source_path": r["source_path"],
            "source_hash": r["source_hash"],
            "source_size": int(r["source_size"]),
            "target_path": r["target_path"],
            "target_expected_hash": r["target_expected_hash"],
            "target_expected_absent": int(r["target_expected_absent"]),
            "action": r["action"],
            "rationale": r["rationale"],
        }
        for r in _mapping_rows(conn, consolidation_id)
    ]
    return {
        "consolidation_id": consolidation_id,
        "candidate_set_id": int(header["candidate_set_id"]),
        "primary_project_uuid": header["primary_project_uuid"],
        "selection_hash": header["selection_hash"],
        "domain_id": header["domain_id"],
        "purpose_id": header["purpose_id"],
        "plan_revision": int(header["plan_revision"]),
        "sources": sources,
        "mappings": mappings,
    }


def _current_plan_hash(conn: sqlite3.Connection, consolidation_id: int) -> str:
    """Compute current plan hash."""
    return _sha256_json(_plan_payload(conn, consolidation_id))


def _invalidate_plan(conn: sqlite3.Connection, consolidation_id: int, *, reason: str) -> None:
    """Invalidate prior review/approval after a draft plan mutation."""
    header = _load_header(conn, consolidation_id)
    if str(header["status"]) not in {"draft", "reviewed"}:
        raise ProjectConsolidationError("approved/executing/completed consolidation plans are immutable")
    revision = int(header["plan_revision"]) + 1
    conn.execute(
        "UPDATE project_consolidations SET status='draft',plan_revision=?,plan_hash=NULL,approved_plan_hash=NULL,updated_at=? WHERE id=?",
        (revision, utc_now(), consolidation_id),
    )
    conn.execute(
        "UPDATE project_consolidation_approvals SET status='revoked' WHERE consolidation_id=? AND status='active'",
        (consolidation_id,),
    )
    _event(conn, consolidation_id, "plan_invalidated", {"reason": reason, "new_revision": revision})


def create_consolidation(root: Path | str, candidate_set_id: int, *, created_by: str) -> dict[str, Any]:
    """Create a consolidation from a committed v0.20.1 primary selection.

    The active root must already be the selected primary. Every other candidate
    becomes an immutable registered source; no external source is opened for write.
    """
    if not created_by.strip():
        raise ProjectConsolidationError("created_by is required")
    primary_root = Path(root).resolve()
    state = get_candidate_set(primary_root, candidate_set_id)
    selection = state.get("selection")
    if not selection:
        raise ProjectConsolidationError("primary project must be human-selected before consolidation")
    primary_uuid = get_project_uuid(primary_root)
    if str(selection["primary_project_uuid"]) != primary_uuid:
        raise ProjectConsolidationError("selected primary must be the active project root")

    primary_candidate = next((c for c in state["candidates"] if c["project_uuid"] == primary_uuid), None)
    if primary_candidate is None:
        raise ProjectConsolidationError("primary project is missing from candidate set")
    sources = [c for c in state["candidates"] if c["project_uuid"] != primary_uuid]
    if not sources:
        raise ProjectConsolidationError("consolidation requires at least one secondary source project")

    # Re-scan every source read-only and require the exact candidate manifest hash.
    verified_sources: list[dict[str, Any]] = []
    for candidate in sources:
        manifest = scan_candidate_readonly(Path(str(candidate["root_path"])))
        if manifest.project_uuid != str(candidate["project_uuid"]):
            raise ProjectConsolidationError("source project identity changed after primary selection")
        if manifest.manifest_hash != str(candidate["manifest_hash"]):
            raise ProjectConsolidationError(
                f"source project manifest changed after selection: {manifest.project_uuid}"
            )
        verified_sources.append({"candidate": candidate, "manifest": manifest})

    now = utc_now()
    with _connect(primary_root) as conn:
        migration_34(conn)
        cur = conn.execute(
            """
            INSERT INTO project_consolidations(
                candidate_set_id,coordinator_project_uuid,primary_project_uuid,primary_root_path,
                selection_hash,domain_id,purpose_id,status,plan_revision,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,'draft',1,?,?,?)
            """,
            (
                candidate_set_id,
                primary_uuid,
                primary_uuid,
                str(primary_root),
                str(selection["selection_hash"]),
                str(primary_candidate["domain_id"]),
                str(primary_candidate["purpose_id"]),
                created_by.strip(),
                now,
                now,
            ),
        )
        consolidation_id = int(cur.lastrowid)
        for item in verified_sources:
            candidate = item["candidate"]
            manifest = item["manifest"]
            conn.execute(
                """
                INSERT INTO project_consolidation_sources(
                    consolidation_id,source_project_uuid,source_root_path,source_manifest_hash,
                    domain_id,purpose_id,readonly_verified,registered_at
                ) VALUES(?,?,?,?,?,?,1,?)
                """,
                (
                    consolidation_id,
                    manifest.project_uuid,
                    manifest.root_path,
                    manifest.manifest_hash,
                    str(candidate["domain_id"]),
                    str(candidate["purpose_id"]),
                    now,
                ),
            )
        _event(
            conn,
            consolidation_id,
            "consolidation_created",
            {
                "candidate_set_id": candidate_set_id,
                "primary_project_uuid": primary_uuid,
                "source_project_uuids": sorted(c["manifest"].project_uuid for c in verified_sources),
                "created_by": created_by.strip(),
            },
        )
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def get_consolidation(root: Path | str, consolidation_id: int) -> dict[str, Any]:
    """Return consolidation plan, sources, mappings, approval, and provenance."""
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        sources = [dict(r) for r in _source_rows(conn, consolidation_id)]
        mappings = [dict(r) for r in _mapping_rows(conn, consolidation_id)]
        approval = conn.execute(
            "SELECT * FROM project_consolidation_approvals WHERE consolidation_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (consolidation_id,),
        ).fetchone()
        review = conn.execute(
            "SELECT * FROM project_consolidation_reviews WHERE consolidation_id=? ORDER BY id DESC LIMIT 1",
            (consolidation_id,),
        ).fetchone()
        provenance = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM project_component_provenance WHERE consolidation_id=? ORDER BY id",
                (consolidation_id,),
            ).fetchall()
        ]
        current_hash = _current_plan_hash(conn, consolidation_id)
    return {
        "ok": True,
        "consolidation": dict(header),
        "sources": sources,
        "mappings": mappings,
        "review": dict(review) if review else None,
        "approval": dict(approval) if approval else None,
        "provenance": provenance,
        "current_plan_hash": current_hash,
    }


def _find_source(conn: sqlite3.Connection, consolidation_id: int, source_project_uuid: str) -> sqlite3.Row:
    """Load a registered secondary source by project UUID."""
    row = conn.execute(
        "SELECT * FROM project_consolidation_sources WHERE consolidation_id=? AND source_project_uuid=?",
        (consolidation_id, source_project_uuid),
    ).fetchone()
    if row is None:
        raise ProjectConsolidationError("source project is not registered in this consolidation")
    return row


def add_component_mapping(
    root: Path | str,
    consolidation_id: int,
    *,
    source_project_uuid: str,
    source_path: str,
    target_path: str | None,
    action: str,
    rationale: str,
    created_by: str,
) -> dict[str, Any]:
    """Add one explicit source-to-primary component mapping to a draft plan."""
    action = action.upper().strip()
    if action not in ACTIONS:
        raise ProjectConsolidationError(f"unsupported action: {action}")
    if len(rationale.strip()) < 8 or not created_by.strip():
        raise ProjectConsolidationError("created_by and a meaningful rationale are required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) not in {"draft", "reviewed"}:
            raise ProjectConsolidationError("component mappings can only be changed before approval")
        source = _find_source(conn, consolidation_id, source_project_uuid)
        source_root = Path(str(source["source_root_path"])).resolve()
        if source_root == primary_root:
            raise ProjectConsolidationError("primary project cannot be registered as a consolidation source")
        current_manifest = scan_candidate_readonly(source_root)
        if current_manifest.project_uuid != source_project_uuid or current_manifest.manifest_hash != str(source["source_manifest_hash"]):
            raise ProjectConsolidationError("source project manifest changed since consolidation creation")
        source_rel = _normalize_rel_path(source_path, label="source_path")
        source_file = _source_file(source_root, source_rel)
        source_hash = _sha256_file(source_file)
        source_size = source_file.stat().st_size

        normalized_target: str | None = None
        target_hash: str | None = None
        target_absent = 0
        if action in {"IGNORE", "CONFLICT"}:
            if target_path:
                normalized_target, _ = _target_file(primary_root, target_path)
        else:
            if not target_path:
                raise ProjectConsolidationError(f"target_path is required for action {action}")
            normalized_target, target_file = _target_file(primary_root, target_path)
            if action == "REUSE" and not target_file.exists():
                raise ProjectConsolidationError("REUSE requires an existing primary target")
            if target_file.exists():
                if not target_file.is_file():
                    raise ProjectConsolidationError("target must be a regular file")
                target_hash = _sha256_file(target_file)
            else:
                target_absent = 1

        # A target may only have one writing mapping in one consolidation plan.
        if normalized_target and action in WRITING_ACTIONS:
            conflict = conn.execute(
                """
                SELECT id FROM project_component_mappings
                WHERE consolidation_id=? AND target_path=? AND action IN ('MOVE','ADAPT','REIMPLEMENT')
                """,
                (consolidation_id, normalized_target),
            ).fetchone()
            if conflict is not None:
                raise ProjectConsolidationError("multiple writing mappings cannot target the same primary path")

        _invalidate_plan(conn, consolidation_id, reason="component_mapping_added")
        now = utc_now()
        cur = conn.execute(
            """
            INSERT INTO project_component_mappings(
                consolidation_id,source_project_uuid,source_path,source_hash,source_size,target_path,
                target_expected_hash,target_expected_absent,action,rationale,status,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,'planned',?,?,?)
            """,
            (
                consolidation_id,
                source_project_uuid,
                source_rel,
                source_hash,
                source_size,
                normalized_target,
                target_hash,
                target_absent,
                action,
                rationale.strip(),
                created_by.strip(),
                now,
                now,
            ),
        )
        mapping_id = int(cur.lastrowid)
        _event(
            conn,
            consolidation_id,
            "component_mapping_added",
            {
                "mapping_id": mapping_id,
                "source_project_uuid": source_project_uuid,
                "source_path": source_rel,
                "source_hash": source_hash,
                "target_path": normalized_target,
                "target_expected_hash": target_hash,
                "target_expected_absent": bool(target_absent),
                "action": action,
                "created_by": created_by.strip(),
            },
        )
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)



def remove_component_mapping(
    root: Path | str,
    consolidation_id: int,
    mapping_id: int,
    *,
    removed_by: str,
    reason: str,
) -> dict[str, Any]:
    """Remove one unexecuted draft/reviewed mapping so conflicts can be replanned."""
    if not removed_by.strip() or len(reason.strip()) < 8:
        raise ProjectConsolidationError("removed_by and meaningful removal reason are required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) not in {"draft", "reviewed"}:
            raise ProjectConsolidationError("only draft/reviewed mappings can be removed")
        row = conn.execute(
            "SELECT * FROM project_component_mappings WHERE id=? AND consolidation_id=?",
            (mapping_id, consolidation_id),
        ).fetchone()
        if row is None:
            raise ProjectConsolidationError("component mapping not found")
        if str(row["status"]) != "planned":
            raise ProjectConsolidationError("executed mappings cannot be removed")
        payload = {
            "mapping_id": mapping_id,
            "source_project_uuid": row["source_project_uuid"],
            "source_path": row["source_path"],
            "target_path": row["target_path"],
            "action": row["action"],
            "removed_by": removed_by.strip(),
            "reason": reason.strip(),
        }
        _invalidate_plan(conn, consolidation_id, reason="component_mapping_removed")
        conn.execute("DELETE FROM project_component_mappings WHERE id=?", (mapping_id,))
        _event(conn, consolidation_id, "component_mapping_removed", payload)
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)

def review_consolidation(
    root: Path | str,
    consolidation_id: int,
    *,
    reviewed_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Human-review the current immutable draft plan and bind review to its hash."""
    if human_confirmed is not True:
        raise ProjectConsolidationError("plan review requires explicit human confirmation")
    if not reviewed_by.strip() or len(reason.strip()) < 8:
        raise ProjectConsolidationError("reviewed_by and meaningful review reason are required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) != "draft":
            raise ProjectConsolidationError("only a draft consolidation can be reviewed")
        mappings = _mapping_rows(conn, consolidation_id)
        if not mappings:
            raise ProjectConsolidationError("consolidation plan contains no component mappings")
        if any(str(r["action"]) == "CONFLICT" for r in mappings):
            raise ProjectConsolidationError("unresolved CONFLICT mappings block review")
        plan_hash = _current_plan_hash(conn, consolidation_id)
        now = utc_now()
        conn.execute(
            "INSERT INTO project_consolidation_reviews(consolidation_id,plan_hash,reviewed_by,reviewed_at,review_reason,status) VALUES(?,?,?,?,?,'reviewed')",
            (consolidation_id, plan_hash, reviewed_by.strip(), now, reason.strip()),
        )
        conn.execute(
            "UPDATE project_consolidations SET status='reviewed',plan_hash=?,updated_at=? WHERE id=?",
            (plan_hash, now, consolidation_id),
        )
        _event(conn, consolidation_id, "plan_reviewed", {"plan_hash": plan_hash, "reviewed_by": reviewed_by.strip(), "reason": reason.strip()})
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def _verify_registered_sources(conn: sqlite3.Connection, consolidation_id: int) -> None:
    """Re-verify every source identity and manifest with read-only scans."""
    for source in _source_rows(conn, consolidation_id):
        root = Path(str(source["source_root_path"])).resolve()
        manifest = scan_candidate_readonly(root)
        if manifest.project_uuid != str(source["source_project_uuid"]):
            raise ProjectConsolidationError("source project identity changed")
        if manifest.manifest_hash != str(source["source_manifest_hash"]):
            raise ProjectConsolidationError(
                f"source project manifest changed: {source['source_project_uuid']}"
            )


def approve_consolidation(
    root: Path | str,
    consolidation_id: int,
    *,
    approved_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Human-approve the reviewed plan; approval is valid only for its exact hash."""
    if human_confirmed is not True:
        raise ProjectConsolidationError("plan approval requires explicit human confirmation")
    if not approved_by.strip() or len(reason.strip()) < 8:
        raise ProjectConsolidationError("approved_by and meaningful approval reason are required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) != "reviewed":
            raise ProjectConsolidationError("consolidation must be human-reviewed before approval")
        _verify_registered_sources(conn, consolidation_id)
        plan_hash = _current_plan_hash(conn, consolidation_id)
        if plan_hash != str(header["plan_hash"]):
            raise ProjectConsolidationError("plan changed after review; review again")
        mappings = _mapping_rows(conn, consolidation_id)
        if any(str(r["action"]) == "CONFLICT" for r in mappings):
            raise ProjectConsolidationError("unresolved CONFLICT mappings block approval")
        now = utc_now()
        conn.execute(
            "UPDATE project_consolidation_approvals SET status='revoked' WHERE consolidation_id=? AND status='active'",
            (consolidation_id,),
        )
        conn.execute(
            """
            INSERT INTO project_consolidation_approvals(
                consolidation_id,plan_hash,approved_by,approved_at,approval_reason,human_confirmed,status
            ) VALUES(?,?,?,?,?,1,'active')
            """,
            (consolidation_id, plan_hash, approved_by.strip(), now, reason.strip()),
        )
        conn.execute(
            "UPDATE project_consolidations SET status='approved',approved_plan_hash=?,updated_at=? WHERE id=?",
            (plan_hash, now, consolidation_id),
        )
        _event(conn, consolidation_id, "plan_approved", {"plan_hash": plan_hash, "approved_by": approved_by.strip(), "reason": reason.strip()})
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def _verify_target_precondition(primary_root: Path, mapping: sqlite3.Row) -> tuple[Path | None, str | None]:
    """Verify expected target hash/absence and return target file and current hash."""
    target_rel = mapping["target_path"]
    if target_rel is None:
        return None, None
    _, target = _target_file(primary_root, str(target_rel))
    if int(mapping["target_expected_absent"] or 0) == 1:
        if target.exists():
            raise ProjectConsolidationError(f"target appeared after planning: {target_rel}")
        return target, None
    expected = mapping["target_expected_hash"]
    if expected is None:
        raise ProjectConsolidationError("target precondition is incomplete")
    if not target.exists() or not target.is_file():
        raise ProjectConsolidationError(f"target disappeared after planning: {target_rel}")
    current = _sha256_file(target)
    if current != str(expected):
        raise ProjectConsolidationError(f"target hash changed after planning: {target_rel}")
    return target, current


def _verify_source_component(conn: sqlite3.Connection, mapping: sqlite3.Row) -> tuple[Path, bytes]:
    """Read and hash one source component after re-verifying its project manifest."""
    source = _find_source(conn, int(mapping["consolidation_id"]), str(mapping["source_project_uuid"]))
    source_root = Path(str(source["source_root_path"])).resolve()
    manifest = scan_candidate_readonly(source_root)
    if manifest.project_uuid != str(source["source_project_uuid"]) or manifest.manifest_hash != str(source["source_manifest_hash"]):
        raise ProjectConsolidationError("source project changed since consolidation plan creation")
    source_file = _source_file(source_root, str(mapping["source_path"]))
    data = source_file.read_bytes()
    if _sha256_bytes(data) != str(mapping["source_hash"]):
        raise ProjectConsolidationError("source component hash changed after plan approval")
    return source_file, data


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically write bytes to an approved primary-project target path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".aos-{uuid.uuid4().hex[:12]}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _backup_existing_target(primary_root: Path, consolidation_id: int, mapping_id: int, target: Path | None) -> str | None:
    """Back up an existing target inside primary runtime before replacement."""
    if target is None or not target.exists():
        return None
    data = target.read_bytes()
    digest = _sha256_bytes(data)
    rel = Path(".agents/runtime/consolidation-backups") / str(consolidation_id) / str(mapping_id) / f"{digest}.bak"
    backup = primary_root / rel
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        _atomic_write_bytes(backup, data)
    return rel.as_posix()


def _read_prepared_content(primary_root: Path, content_file: Path | str) -> bytes:
    """Read ADAPT/REIMPLEMENT content from a regular non-symlink file inside Primary."""
    raw = Path(content_file)
    if not raw.is_absolute():
        raw = primary_root / raw
    try:
        rel = raw.absolute().relative_to(primary_root.resolve()).as_posix()
    except ValueError as exc:
        raise ProjectConsolidationError("prepared content must be inside the primary project") from exc
    path = _ensure_no_symlink_chain(primary_root, rel, allow_missing_leaf=False)
    if not path.is_file():
        raise ProjectConsolidationError("prepared content must be a regular non-symlink file")
    if path.stat().st_size > MAX_COMPONENT_BYTES:
        raise ProjectConsolidationError("prepared content exceeds component size limit")
    # Reading .agents/runtime is allowed as staging input; it is never a target path.
    if rel in FORBIDDEN_ROOT_FILES:
        raise ProjectConsolidationError("prepared content cannot be a primary authority file")
    return path.read_bytes()


def execute_mapping(
    root: Path | str,
    consolidation_id: int,
    mapping_id: int,
    *,
    executed_by: str,
    prepared_content_file: Path | str | None = None,
) -> dict[str, Any]:
    """Execute exactly one approved mapping, writing only to the primary project."""
    if not executed_by.strip():
        raise ProjectConsolidationError("executed_by is required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) not in {"approved", "executing"}:
            raise ProjectConsolidationError("consolidation plan is not approved for execution")
        plan_hash = _current_plan_hash(conn, consolidation_id)
        if plan_hash != str(header["approved_plan_hash"]):
            raise ProjectConsolidationError("approved plan hash no longer matches current plan")
        approval = conn.execute(
            "SELECT * FROM project_consolidation_approvals WHERE consolidation_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (consolidation_id,),
        ).fetchone()
        if approval is None or str(approval["plan_hash"]) != plan_hash or int(approval["human_confirmed"]) != 1:
            raise ProjectConsolidationError("active human approval for the current plan is missing")
        mapping = conn.execute(
            "SELECT * FROM project_component_mappings WHERE id=? AND consolidation_id=?",
            (mapping_id, consolidation_id),
        ).fetchone()
        if mapping is None:
            raise ProjectConsolidationError("component mapping not found")
        if str(mapping["status"]) in TERMINAL_MAPPING_STATES:
            raise ProjectConsolidationError("component mapping has already been executed")
        action = str(mapping["action"])
        if action == "CONFLICT":
            raise ProjectConsolidationError("CONFLICT mapping cannot be executed")

        source_file, source_data = _verify_source_component(conn, mapping)
        if action == "IGNORE":
            target, before_hash = None, None
        else:
            target, before_hash = _verify_target_precondition(primary_root, mapping)
        execution_id = str(uuid.uuid4())
        backup_rel: str | None = None
        after_hash: str | None = before_hash
        result_status = "applied"

        if action == "IGNORE":
            if prepared_content_file is not None:
                raise ProjectConsolidationError("IGNORE does not accept prepared content")
            result_status = "skipped"
        elif action == "REUSE":
            if prepared_content_file is not None:
                raise ProjectConsolidationError("REUSE does not accept prepared content")
            if target is None or before_hash is None:
                raise ProjectConsolidationError("REUSE target is missing")
            after_hash = before_hash
        elif action == "MOVE":
            if prepared_content_file is not None:
                raise ProjectConsolidationError("MOVE copies exact source bytes and does not accept prepared content")
            assert target is not None
            backup_rel = _backup_existing_target(primary_root, consolidation_id, mapping_id, target)
            _atomic_write_bytes(target, source_data)
            after_hash = _sha256_file(target)
            if after_hash != str(mapping["source_hash"]):
                raise ProjectConsolidationError("target verification failed after MOVE")
        elif action in {"ADAPT", "REIMPLEMENT"}:
            if prepared_content_file is None:
                raise ProjectConsolidationError(f"{action} requires a prepared content file inside the primary project")
            assert target is not None
            prepared = _read_prepared_content(primary_root, prepared_content_file)
            backup_rel = _backup_existing_target(primary_root, consolidation_id, mapping_id, target)
            _atomic_write_bytes(target, prepared)
            after_hash = _sha256_file(target)
        else:
            raise ProjectConsolidationError(f"unsupported action at execution: {action}")

        now = utc_now()
        result = {
            "execution_id": execution_id,
            "action": action,
            "source_file": str(source_file),
            "source_hash": mapping["source_hash"],
            "target_path": mapping["target_path"],
            "target_before_hash": before_hash,
            "target_after_hash": after_hash,
            "backup_path": backup_rel,
            "status": result_status,
        }
        conn.execute(
            "UPDATE project_component_mappings SET status=?,last_result_json=?,updated_at=? WHERE id=?",
            (result_status, _canonical_json(result), now, mapping_id),
        )
        conn.execute(
            """
            INSERT INTO project_component_provenance(
                consolidation_id,mapping_id,primary_project_uuid,source_project_uuid,source_path,source_hash,
                target_path,target_before_hash,target_after_hash,backup_path,action,execution_id,executed_by,executed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                consolidation_id,
                mapping_id,
                header["primary_project_uuid"],
                mapping["source_project_uuid"],
                mapping["source_path"],
                mapping["source_hash"],
                mapping["target_path"],
                before_hash,
                after_hash,
                backup_rel,
                action,
                execution_id,
                executed_by.strip(),
                now,
            ),
        )
        conn.execute(
            "UPDATE project_consolidations SET status='executing',updated_at=? WHERE id=?",
            (now, consolidation_id),
        )
        _event(conn, consolidation_id, "component_executed", {**result, "mapping_id": mapping_id, "executed_by": executed_by.strip()})
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def complete_consolidation(root: Path | str, consolidation_id: int, *, completed_by: str) -> dict[str, Any]:
    """Mark a consolidation complete only when every mapping is terminal and conflict-free."""
    if not completed_by.strip():
        raise ProjectConsolidationError("completed_by is required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        if str(header["status"]) not in {"approved", "executing"}:
            raise ProjectConsolidationError("consolidation is not in an executable state")
        mappings = _mapping_rows(conn, consolidation_id)
        blockers = [int(r["id"]) for r in mappings if str(r["status"]) not in TERMINAL_MAPPING_STATES]
        if blockers:
            raise ProjectConsolidationError(f"non-terminal mappings block completion: {blockers}")
        now = utc_now()
        conn.execute("UPDATE project_consolidations SET status='completed',updated_at=? WHERE id=?", (now, consolidation_id))
        _event(conn, consolidation_id, "consolidation_completed", {"completed_by": completed_by.strip(), "mapping_count": len(mappings)})
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def rollback_mapping(
    root: Path | str,
    consolidation_id: int,
    mapping_id: int,
    *,
    confirmed_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Rollback one materialized target while preserving immutable source projects."""
    if human_confirmed is not True:
        raise ProjectConsolidationError("rollback requires explicit human confirmation")
    if not confirmed_by.strip() or len(reason.strip()) < 8:
        raise ProjectConsolidationError("confirmed_by and meaningful rollback reason are required")
    primary_root = Path(root).resolve()
    with _connect(primary_root) as conn:
        migration_34(conn)
        header = _load_header(conn, consolidation_id)
        _assert_primary_authority(primary_root, header)
        prov = conn.execute(
            """
            SELECT * FROM project_component_provenance
            WHERE consolidation_id=? AND mapping_id=? AND rollback_status='not_rolled_back'
            ORDER BY id DESC LIMIT 1
            """,
            (consolidation_id, mapping_id),
        ).fetchone()
        if prov is None:
            raise ProjectConsolidationError("no rollback-eligible provenance entry found")
        action = str(prov["action"])
        if action not in WRITING_ACTIONS:
            raise ProjectConsolidationError("REUSE/IGNORE mappings do not modify the primary and need no rollback")
        target_rel = str(prov["target_path"])
        _, target = _target_file(primary_root, target_rel)
        if not target.exists() or not target.is_file():
            raise ProjectConsolidationError("current target is missing; rollback cannot safely proceed")
        current_hash = _sha256_file(target)
        if current_hash != str(prov["target_after_hash"]):
            raise ProjectConsolidationError("target changed after consolidation; rollback is fail-closed")
        backup_rel = prov["backup_path"]
        before_hash = prov["target_before_hash"]
        if backup_rel:
            backup = (primary_root / str(backup_rel)).resolve()
            try:
                backup.relative_to(primary_root.resolve())
            except ValueError as exc:
                raise ProjectConsolidationError("backup path escapes primary root") from exc
            if not backup.is_file() or _sha256_file(backup) != str(before_hash):
                raise ProjectConsolidationError("rollback backup is missing or corrupted")
            _atomic_write_bytes(target, backup.read_bytes())
            restored_hash = _sha256_file(target)
            if restored_hash != str(before_hash):
                raise ProjectConsolidationError("rollback verification failed")
        else:
            if before_hash is not None:
                raise ProjectConsolidationError("rollback metadata is inconsistent")
            target.unlink()
            restored_hash = None
        now = utc_now()
        conn.execute(
            """
            UPDATE project_component_provenance
            SET rollback_status='rolled_back',rolled_back_by=?,rolled_back_at=?,rollback_reason=?
            WHERE id=?
            """,
            (confirmed_by.strip(), now, reason.strip(), prov["id"]),
        )
        conn.execute(
            "UPDATE project_component_mappings SET status='rolled_back',updated_at=? WHERE id=?",
            (now, mapping_id),
        )
        conn.execute(
            "UPDATE project_consolidations SET status='rollback_required',updated_at=? WHERE id=?",
            (now, consolidation_id),
        )
        _event(
            conn,
            consolidation_id,
            "component_rolled_back",
            {"mapping_id": mapping_id, "target_path": target_rel, "restored_hash": restored_hash, "confirmed_by": confirmed_by.strip(), "reason": reason.strip()},
        )
        conn.commit()
    return get_consolidation(primary_root, consolidation_id)


def docs_check_v0202(root: Path | str) -> dict[str, Any]:
    """Validate v0.20.2 version markers and bilingual GitHub documentation links."""
    project_root = Path(root).resolve()
    required = [
        "README.md",
        "README.vi.md",
        "README.en.md",
        "huong_dan.md",
        "huong_dan.vi.md",
        "huong_dan.en.md",
        ".agents/docs/PRIMARY_PROJECT_CONSOLIDATION.md",
        ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
        "VERSION",
    ]
    missing = [rel for rel in required if not (project_root / rel).exists()]
    version = (project_root / "VERSION").read_text(encoding="utf-8").strip() if (project_root / "VERSION").exists() else None
    readme = (project_root / "README.md").read_text(encoding="utf-8") if (project_root / "README.md").exists() else ""
    links_ok = "README.vi.md" in readme and "README.en.md" in readme
    return {"ok": not missing and version == "0.20.2" and links_ok, "version": version, "missing": missing, "language_links_ok": links_ok}
