"""
File: .agents/agentos/project_selection.py

Purpose:
    Implement AgentOS v0.20.1 Primary Project Selection and Domain
    Compatibility without modifying candidate source projects.

Responsibilities:
    - Scan v0.20.0 project identity/purpose manifests in read-only mode.
    - Build local candidate sets and deterministic compatibility evidence.
    - Enforce business-domain compatibility before a primary may be selected.
    - Require explicit human confirmation for conditional purpose compatibility.
    - Require explicit human selection of exactly one primary project.
    - Refuse to commit a primary selection unless the selected project is the
      active AgentOS root, ensuring future secondary projects remain read-only.
    - Provide SQLite migration 33 and local audit/provenance state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable
import uuid

from .project_identity import (
    ProjectIdentityError,
    get_project_uuid,
    validate_project_id,
    validate_purpose,
)

SCHEMA_VERSION = 33
COMPATIBLE = "compatible"
CONDITIONAL = "conditionally_compatible"
INCOMPATIBLE = "incompatible"
ROLE_PRIMARY_WEIGHT = {
    "core_application": 100,
    "service": 70,
    "data_pipeline": 60,
    "governance_platform": 60,
    "library": 45,
    "integration_adapter": 30,
    "other": 20,
}


class ProjectSelectionError(RuntimeError):
    """Raised when project selection or compatibility violates governance."""


@dataclass(frozen=True)
class CandidateManifest:
    """Immutable read-only snapshot of one v0.20.0 project candidate.

    Attributes:
        project_uuid: Stable project identity from `.agents/config/project.id`.
        instance_uuid: Working-copy identity when available.
        root_path: Resolved root path used only as scan evidence, not identity.
        version: Project AgentOS version marker.
        governance_version: Machine-readable governance version when available.
        identity: Validated project identity document.
        purpose: Human-confirmed purpose document.
        manifest_hash: SHA-256 over the canonical snapshot payload.
    """

    project_uuid: str
    instance_uuid: str | None
    root_path: str
    version: str
    governance_version: str | None
    identity: dict[str, Any]
    purpose: dict[str, Any]
    manifest_hash: str

    def as_dict(self) -> dict[str, Any]:
        """Return the normalized JSON-compatible manifest."""
        return {
            "project_uuid": self.project_uuid,
            "instance_uuid": self.instance_uuid,
            "root_path": self.root_path,
            "version": self.version,
            "governance_version": self.governance_version,
            "identity": self.identity,
            "purpose": self.purpose,
            "manifest_hash": self.manifest_hash,
        }


def utc_now() -> str:
    """Return current UTC time in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for evidence hashing."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    """Return SHA-256 of canonical JSON data."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object without writing or normalizing the source file."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectSelectionError(f"required candidate file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectSelectionError(f"invalid candidate JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectSelectionError(f"candidate JSON must be an object: {path}")
    return value


def _inside(root: Path, path: Path) -> bool:
    """Return whether a resolved candidate file remains inside its project root."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_candidate_file(root: Path, rel: str, *, required: bool = True) -> Path | None:
    """Resolve a candidate metadata file and block symlink/path escape."""
    path = root / rel
    if not path.exists():
        if required:
            raise ProjectSelectionError(f"candidate is missing {rel}: {root}")
        return None
    if not _inside(root, path):
        raise ProjectSelectionError(f"candidate metadata escapes project root: {path}")
    return path


def _validate_instance_uuid(value: Any) -> str | None:
    """Validate optional instance UUID from local state."""
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProjectSelectionError(f"invalid candidate instance_uuid: {value!r}") from exc


def scan_candidate_readonly(root: Path | str) -> CandidateManifest:
    """Read a candidate project's v0.20.0 identity/purpose without mutation.

    Args:
        root: Candidate project root supplied by the user/operator.

    Returns:
        Immutable normalized candidate manifest with evidence hash.

    Raises:
        ProjectSelectionError: If identity/purpose is missing, invalid, not human
            confirmed, or metadata resolves outside the candidate root.

    Side Effects:
        None. This function never creates identity, purpose, registry, database,
        audit, or runtime state inside the candidate project.
    """
    candidate_root = Path(root).resolve()
    identity_path = _safe_candidate_file(candidate_root, ".agents/config/project.id")
    purpose_path = _safe_candidate_file(candidate_root, ".agents/config/project.purpose.json")
    version_path = _safe_candidate_file(candidate_root, "VERSION")
    governance_path = _safe_candidate_file(candidate_root, ".agents/config/governance.json")
    instance_path = _safe_candidate_file(
        candidate_root, ".agents/state/project.instance.json", required=False
    )
    assert identity_path is not None and purpose_path is not None
    assert version_path is not None and governance_path is not None

    identity = _read_json(identity_path)
    purpose = _read_json(purpose_path)
    try:
        validate_project_id(identity)
        validate_purpose(purpose)
    except ProjectIdentityError as exc:
        raise ProjectSelectionError(str(exc)) from exc

    version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        raise ProjectSelectionError(f"candidate VERSION is empty: {candidate_root}")
    governance = _read_json(governance_path)
    governance_version = governance.get("version") or governance.get("governance_version")
    if governance_version is not None:
        governance_version = str(governance_version)

    instance_uuid: str | None = None
    if instance_path is not None:
        instance_value = _read_json(instance_path)
        instance_uuid = _validate_instance_uuid(instance_value.get("instance_uuid"))

    payload = {
        "project_uuid": identity["project_uuid"],
        "instance_uuid": instance_uuid,
        "root_path": str(candidate_root),
        "version": version,
        "governance_version": governance_version,
        "identity": identity,
        "purpose": purpose,
    }
    return CandidateManifest(
        project_uuid=str(identity["project_uuid"]),
        instance_uuid=instance_uuid,
        root_path=str(candidate_root),
        version=version,
        governance_version=governance_version,
        identity=identity,
        purpose=purpose,
        manifest_hash=_sha256_json(payload),
    )


def assess_compatibility(left: CandidateManifest, right: CandidateManifest) -> dict[str, Any]:
    """Assess business compatibility deterministically and fail closed on domain mismatch.

    Args:
        left: First candidate snapshot.
        right: Second candidate snapshot.

    Returns:
        Compatibility evidence with one of `compatible`,
        `conditionally_compatible`, or `incompatible`.

    Notes:
        Capability overlap is explanatory evidence only. It can never convert a
        business-domain mismatch into compatibility. Different purpose IDs inside
        the same domain remain conditional until a human explicitly confirms them.
    """
    if left.project_uuid == right.project_uuid:
        raise ProjectSelectionError("cannot assess two roots with the same project_uuid")
    left_purpose = left.purpose
    right_purpose = right.purpose
    left_domain = str(left_purpose["domain"]["id"])
    right_domain = str(right_purpose["domain"]["id"])
    left_purpose_id = str(left_purpose["purpose"]["id"])
    right_purpose_id = str(right_purpose["purpose"]["id"])
    left_caps = set(str(x) for x in left_purpose.get("capabilities", []))
    right_caps = set(str(x) for x in right_purpose.get("capabilities", []))
    overlap = sorted(left_caps & right_caps)

    if left_domain != right_domain:
        status = INCOMPATIBLE
        reason = "business_domain_mismatch"
        purpose_status = "not_evaluated_due_to_domain_mismatch"
    elif left_purpose_id == right_purpose_id:
        status = COMPATIBLE
        reason = "exact_domain_and_purpose_match"
        purpose_status = "exact_match"
    else:
        status = CONDITIONAL
        reason = "same_domain_different_purpose_requires_human_confirmation"
        purpose_status = "different_requires_human_confirmation"

    evidence = {
        "left_project_uuid": left.project_uuid,
        "right_project_uuid": right.project_uuid,
        "left_domain_id": left_domain,
        "right_domain_id": right_domain,
        "domain_status": "exact_match" if left_domain == right_domain else "mismatch",
        "left_purpose_id": left_purpose_id,
        "right_purpose_id": right_purpose_id,
        "purpose_status": purpose_status,
        "capability_overlap": overlap,
        "left_role": left_purpose.get("role"),
        "right_role": right_purpose.get("role"),
        "technical_similarity_can_override_domain": False,
        "status": status,
        "reason": reason,
    }
    evidence["evidence_hash"] = _sha256_json(evidence)
    return evidence


def _pair(a: str, b: str) -> tuple[str, str]:
    """Return a stable UUID pair ordering for symmetric compatibility rows."""
    if a == b:
        raise ProjectSelectionError("compatibility pair requires two distinct projects")
    return tuple(sorted((a, b)))  # type: ignore[return-value]


def _db_path(root: Path | str) -> Path:
    """Return the local AgentOS SQLite database path."""
    return Path(root).resolve() / ".agents/state/agentos.db"


def _connect(root: Path | str) -> sqlite3.Connection:
    """Open only the active project's local AgentOS state database."""
    path = _db_path(root)
    if not path.exists():
        raise ProjectSelectionError(f"AgentOS database is missing: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def migration_33(conn: sqlite3.Connection) -> None:
    """Apply additive schema 33 for candidate, compatibility, and primary state.

    Args:
        conn: Existing AgentOS SQLite connection at schema 32.

    Returns:
        None.

    Side Effects:
        Adds v0.20.1 tables and indexes. It never opens or writes another
        project's database.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_candidate_sets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coordinator_project_uuid TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_candidates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            project_uuid TEXT NOT NULL,
            instance_uuid TEXT,
            root_path TEXT NOT NULL,
            project_role TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            purpose_id TEXT NOT NULL,
            manifest_hash TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            is_active_root INTEGER NOT NULL DEFAULT 0,
            scanned_at TEXT NOT NULL,
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id),
            UNIQUE(candidate_set_id, project_uuid)
        );
        CREATE TABLE IF NOT EXISTS project_compatibility(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL,
            project_a_uuid TEXT NOT NULL,
            project_b_uuid TEXT NOT NULL,
            compatibility_status TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            human_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmed_by TEXT,
            confirmed_at TEXT,
            confirmation_reason TEXT,
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id),
            UNIQUE(candidate_set_id, project_a_uuid, project_b_uuid)
        );
        CREATE TABLE IF NOT EXISTS primary_project_selections(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER NOT NULL UNIQUE,
            primary_project_uuid TEXT NOT NULL,
            selected_by TEXT NOT NULL,
            selected_at TEXT NOT NULL,
            selection_reason TEXT NOT NULL,
            recommendation_json TEXT NOT NULL,
            selection_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'selected',
            FOREIGN KEY(candidate_set_id) REFERENCES project_candidate_sets(id)
        );
        CREATE TABLE IF NOT EXISTS project_selection_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_set_id INTEGER,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_candidates_set
            ON project_candidates(candidate_set_id, project_uuid);
        CREATE INDEX IF NOT EXISTS idx_project_compatibility_set
            ON project_compatibility(candidate_set_id, compatibility_status);
        CREATE INDEX IF NOT EXISTS idx_primary_project_selected
            ON primary_project_selections(primary_project_uuid, selected_at);
        """
    )


def sync_selection_schema(root: Path | str) -> dict[str, Any]:
    """Apply schema-33 tables directly to the active project's local SQLite DB."""
    with _connect(root) as conn:
        migration_33(conn)
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    required = {
        "project_candidate_sets",
        "project_candidates",
        "project_compatibility",
        "primary_project_selections",
        "project_selection_events",
    }
    return {"ok": required <= tables, "schema": SCHEMA_VERSION, "tables": sorted(required)}


def _event(conn: sqlite3.Connection, candidate_set_id: int | None, event_type: str, payload: Any) -> None:
    """Append local selection evidence without touching source projects."""
    conn.execute(
        "INSERT INTO project_selection_events(candidate_set_id,event_type,event_json,created_at) VALUES(?,?,?,?)",
        (candidate_set_id, event_type, _canonical_json(payload), utc_now()),
    )


def create_candidate_set(
    root: Path | str,
    source_roots: Iterable[Path | str],
    *,
    created_by: str,
) -> dict[str, Any]:
    """Create a candidate set by read-only scanning the active root and sources.

    Args:
        root: Active AgentOS project root. This is a candidate, not automatically
            the primary project.
        source_roots: One or more additional user-provided project roots.
        created_by: Human/operator identity creating the comparison set.

    Returns:
        Candidate-set ID, normalized manifests, and compatibility matrix.

    Raises:
        ProjectSelectionError: If fewer than two distinct projects are supplied,
            identities collide, or candidate metadata cannot be validated.

    Side Effects:
        Writes only to the active root's AgentOS SQLite database. Source project
        roots are read-only.
    """
    if not created_by.strip():
        raise ProjectSelectionError("created_by is required")
    active_root = Path(root).resolve()
    roots = [active_root]
    seen_paths = {str(active_root)}
    for item in source_roots:
        resolved = Path(item).resolve()
        if str(resolved) not in seen_paths:
            roots.append(resolved)
            seen_paths.add(str(resolved))
    if len(roots) < 2:
        raise ProjectSelectionError("candidate set requires at least two distinct project roots")

    manifests = [scan_candidate_readonly(item) for item in roots]
    uuids = [item.project_uuid for item in manifests]
    if len(set(uuids)) != len(uuids):
        raise ProjectSelectionError(
            "candidate set contains duplicate project_uuid; clone/fork identity must be resolved first"
        )
    active_uuid = manifests[0].project_uuid
    if active_uuid != get_project_uuid(active_root):
        raise ProjectSelectionError("active root identity changed during candidate scan")

    pair_evidence: list[dict[str, Any]] = []
    for index, left in enumerate(manifests):
        for right in manifests[index + 1 :]:
            pair_evidence.append(assess_compatibility(left, right))

    with _connect(active_root) as conn:
        migration_33(conn)
        now = utc_now()
        cur = conn.execute(
            """
            INSERT INTO project_candidate_sets(
                coordinator_project_uuid,status,created_by,created_at,updated_at
            ) VALUES(?,?,?,?,?)
            """,
            (active_uuid, "draft", created_by.strip(), now, now),
        )
        set_id = int(cur.lastrowid)
        for manifest in manifests:
            purpose = manifest.purpose
            conn.execute(
                """
                INSERT INTO project_candidates(
                    candidate_set_id,project_uuid,instance_uuid,root_path,project_role,
                    domain_id,purpose_id,manifest_hash,manifest_json,is_active_root,scanned_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    set_id,
                    manifest.project_uuid,
                    manifest.instance_uuid,
                    manifest.root_path,
                    purpose["role"],
                    purpose["domain"]["id"],
                    purpose["purpose"]["id"],
                    manifest.manifest_hash,
                    _canonical_json(manifest.as_dict()),
                    1 if manifest.project_uuid == active_uuid else 0,
                    now,
                ),
            )
        for evidence in pair_evidence:
            a, b = _pair(evidence["left_project_uuid"], evidence["right_project_uuid"])
            conn.execute(
                """
                INSERT INTO project_compatibility(
                    candidate_set_id,project_a_uuid,project_b_uuid,compatibility_status,
                    evidence_hash,evidence_json,human_confirmed
                ) VALUES(?,?,?,?,?,?,0)
                """,
                (
                    set_id,
                    a,
                    b,
                    evidence["status"],
                    evidence["evidence_hash"],
                    _canonical_json(evidence),
                ),
            )
        _event(
            conn,
            set_id,
            "candidate_set_created",
            {
                "created_by": created_by.strip(),
                "active_project_uuid": active_uuid,
                "project_uuids": sorted(uuids),
            },
        )
        conn.commit()
    return get_candidate_set(active_root, set_id)


def _candidate_rows(conn: sqlite3.Connection, candidate_set_id: int) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM project_candidates WHERE candidate_set_id=? ORDER BY id",
        (candidate_set_id,),
    ).fetchall()
    if not rows:
        raise ProjectSelectionError(f"candidate set not found: {candidate_set_id}")
    return rows


def _compat_rows(conn: sqlite3.Connection, candidate_set_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM project_compatibility WHERE candidate_set_id=? ORDER BY project_a_uuid,project_b_uuid",
        (candidate_set_id,),
    ).fetchall()


def get_candidate_set(root: Path | str, candidate_set_id: int) -> dict[str, Any]:
    """Return candidate-set state from the active project's local database."""
    with _connect(root) as conn:
        migration_33(conn)
        header = conn.execute(
            "SELECT * FROM project_candidate_sets WHERE id=?", (candidate_set_id,)
        ).fetchone()
        if header is None:
            raise ProjectSelectionError(f"candidate set not found: {candidate_set_id}")
        candidates = [dict(row) for row in _candidate_rows(conn, candidate_set_id)]
        compatibility = []
        for row in _compat_rows(conn, candidate_set_id):
            item = dict(row)
            item["evidence"] = json.loads(item.pop("evidence_json"))
            compatibility.append(item)
        selection = conn.execute(
            "SELECT * FROM primary_project_selections WHERE candidate_set_id=?",
            (candidate_set_id,),
        ).fetchone()
    return {
        "ok": True,
        "candidate_set": dict(header),
        "candidates": candidates,
        "compatibility": compatibility,
        "selection": dict(selection) if selection is not None else None,
    }


def confirm_conditional_compatibility(
    root: Path | str,
    candidate_set_id: int,
    project_a_uuid: str,
    project_b_uuid: str,
    *,
    confirmed_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Human-confirm a same-domain/different-purpose pair.

    Domain mismatch is intentionally non-overridable in v0.20.1.
    """
    if human_confirmed is not True:
        raise ProjectSelectionError("conditional compatibility requires explicit human confirmation")
    if not confirmed_by.strip() or len(reason.strip()) < 8:
        raise ProjectSelectionError("confirmed_by and a meaningful confirmation reason are required")
    a, b = _pair(project_a_uuid, project_b_uuid)
    active_uuid = get_project_uuid(Path(root).resolve())
    with _connect(root) as conn:
        migration_33(conn)
        header = conn.execute(
            "SELECT * FROM project_candidate_sets WHERE id=?", (candidate_set_id,)
        ).fetchone()
        if header is None:
            raise ProjectSelectionError(f"candidate set not found: {candidate_set_id}")
        if str(header["coordinator_project_uuid"]) != active_uuid:
            raise ProjectSelectionError("candidate set belongs to a different active project root")
        if str(header["status"]) != "draft":
            raise ProjectSelectionError("compatibility state is frozen after primary selection")
        row = conn.execute(
            """
            SELECT * FROM project_compatibility
            WHERE candidate_set_id=? AND project_a_uuid=? AND project_b_uuid=?
            """,
            (candidate_set_id, a, b),
        ).fetchone()
        if row is None:
            raise ProjectSelectionError("compatibility pair not found")
        if row["compatibility_status"] == INCOMPATIBLE:
            raise ProjectSelectionError("business-domain mismatch cannot be human-overridden")
        if row["compatibility_status"] != CONDITIONAL:
            raise ProjectSelectionError("only conditionally compatible pairs require confirmation")
        now = utc_now()
        conn.execute(
            """
            UPDATE project_compatibility
            SET human_confirmed=1, confirmed_by=?, confirmed_at=?, confirmation_reason=?
            WHERE id=?
            """,
            (confirmed_by.strip(), now, reason.strip(), row["id"]),
        )
        _event(
            conn,
            candidate_set_id,
            "conditional_compatibility_confirmed",
            {"project_a_uuid": a, "project_b_uuid": b, "confirmed_by": confirmed_by.strip(), "reason": reason.strip()},
        )
        conn.commit()
    return get_candidate_set(root, candidate_set_id)


def _effective_pair(row: sqlite3.Row) -> bool:
    status = row["compatibility_status"]
    if status == COMPATIBLE:
        return True
    return status == CONDITIONAL and int(row["human_confirmed"] or 0) == 1


def _candidate_feasibility(
    candidate_uuid: str,
    candidates: list[sqlite3.Row],
    compat: list[sqlite3.Row],
) -> tuple[bool, list[str]]:
    """Check whether every other source is effectively compatible with a primary."""
    blockers: list[str] = []
    others = {str(row["project_uuid"]) for row in candidates if row["project_uuid"] != candidate_uuid}
    by_other: dict[str, sqlite3.Row] = {}
    for row in compat:
        a = str(row["project_a_uuid"])
        b = str(row["project_b_uuid"])
        if candidate_uuid == a:
            by_other[b] = row
        elif candidate_uuid == b:
            by_other[a] = row
    for other in sorted(others):
        row = by_other.get(other)
        if row is None:
            blockers.append(f"missing_compatibility:{other}")
        elif row["compatibility_status"] == INCOMPATIBLE:
            blockers.append(f"domain_incompatible:{other}")
        elif row["compatibility_status"] == CONDITIONAL and not _effective_pair(row):
            blockers.append(f"purpose_confirmation_required:{other}")
    return not blockers, blockers


def recommend_primary(root: Path | str, candidate_set_id: int) -> dict[str, Any]:
    """Produce an advisory primary ranking without selecting or mutating state.

    Role and business-capability breadth influence ranking only after the project
    is feasible against every intended source. The recommendation never becomes
    an approval or primary selection automatically.
    """
    with _connect(root) as conn:
        migration_33(conn)
        candidates = _candidate_rows(conn, candidate_set_id)
        compat = _compat_rows(conn, candidate_set_id)
    ranked: list[dict[str, Any]] = []
    for row in candidates:
        project_uuid = str(row["project_uuid"])
        manifest = json.loads(row["manifest_json"])
        purpose = manifest["purpose"]
        feasible, blockers = _candidate_feasibility(project_uuid, candidates, compat)
        role = str(row["project_role"])
        capabilities = list(purpose.get("capabilities", []))
        score = ROLE_PRIMARY_WEIGHT.get(role, 0) + min(len(capabilities) * 2, 20)
        exact_matches = 0
        for pair in compat:
            if project_uuid not in (pair["project_a_uuid"], pair["project_b_uuid"]):
                continue
            if pair["compatibility_status"] == COMPATIBLE:
                exact_matches += 1
        score += exact_matches * 5
        ranked.append(
            {
                "project_uuid": project_uuid,
                "name": purpose.get("name"),
                "role": role,
                "domain_id": row["domain_id"],
                "purpose_id": row["purpose_id"],
                "feasible": feasible,
                "blockers": blockers,
                "advisory_score": score if feasible else None,
                "reasons": [
                    f"role_weight={ROLE_PRIMARY_WEIGHT.get(role, 0)}",
                    f"business_capability_count={len(capabilities)}",
                    f"exact_compatibility_pairs={exact_matches}",
                ],
            }
        )
    ranked.sort(
        key=lambda item: (
            0 if item["feasible"] else 1,
            -(item["advisory_score"] or -1),
            item["project_uuid"],
        )
    )
    recommended = next((item for item in ranked if item["feasible"]), None)
    return {
        "ok": True,
        "candidate_set_id": candidate_set_id,
        "recommended_project_uuid": recommended["project_uuid"] if recommended else None,
        "recommendation_is_advisory_only": True,
        "human_selection_required": True,
        "ranking": ranked,
    }


def select_primary(
    root: Path | str,
    candidate_set_id: int,
    project_uuid: str,
    *,
    selected_by: str,
    reason: str,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Commit exactly one human-selected primary project.

    Args:
        root: Active project root where selection governance is persisted.
        candidate_set_id: Candidate set being decided.
        project_uuid: Human-selected primary project UUID.
        selected_by: Human/operator identity responsible for the selection.
        reason: Business/architecture rationale for the selection.
        human_confirmed: Must be True.

    Returns:
        Persisted selection and candidate-set state.

    Raises:
        ProjectSelectionError: If the selected project is not the active root,
            any intended source is incompatible/unconfirmed, or selection was
            already committed.

    Side Effects:
        Writes selection state only to the selected active primary project's
        AgentOS database. No source project is modified.
    """
    if human_confirmed is not True:
        raise ProjectSelectionError("primary selection requires explicit human confirmation")
    if not selected_by.strip() or len(reason.strip()) < 8:
        raise ProjectSelectionError("selected_by and a meaningful selection reason are required")
    active_uuid = get_project_uuid(Path(root).resolve())
    if project_uuid != active_uuid:
        raise ProjectSelectionError(
            "selected primary must be the active AgentOS root; re-run selection from that project so non-primary candidates remain read-only"
        )
    recommendation = recommend_primary(root, candidate_set_id)
    with _connect(root) as conn:
        migration_33(conn)
        header = conn.execute(
            "SELECT * FROM project_candidate_sets WHERE id=?", (candidate_set_id,)
        ).fetchone()
        if header is None:
            raise ProjectSelectionError(f"candidate set not found: {candidate_set_id}")
        if str(header["coordinator_project_uuid"]) != active_uuid:
            raise ProjectSelectionError("candidate set belongs to a different active project root")
        existing = conn.execute(
            "SELECT 1 FROM primary_project_selections WHERE candidate_set_id=?", (candidate_set_id,)
        ).fetchone()
        if existing is not None:
            raise ProjectSelectionError("primary project has already been selected for this candidate set")
        if str(header["status"]) != "draft":
            raise ProjectSelectionError("candidate set is no longer open for primary selection")
        candidates = _candidate_rows(conn, candidate_set_id)
        if project_uuid not in {str(row["project_uuid"]) for row in candidates}:
            raise ProjectSelectionError("selected primary is not a member of this candidate set")
        compat = _compat_rows(conn, candidate_set_id)
        feasible, blockers = _candidate_feasibility(project_uuid, candidates, compat)
        if not feasible:
            raise ProjectSelectionError("primary selection blocked: " + ", ".join(blockers))
        now = utc_now()
        payload = {
            "candidate_set_id": candidate_set_id,
            "primary_project_uuid": project_uuid,
            "selected_by": selected_by.strip(),
            "selected_at": now,
            "selection_reason": reason.strip(),
            "recommendation_snapshot": recommendation,
        }
        selection_hash = _sha256_json(payload)
        conn.execute(
            """
            INSERT INTO primary_project_selections(
                candidate_set_id,primary_project_uuid,selected_by,selected_at,
                selection_reason,recommendation_json,selection_hash,status
            ) VALUES(?,?,?,?,?,?,?,'selected')
            """,
            (
                candidate_set_id,
                project_uuid,
                selected_by.strip(),
                now,
                reason.strip(),
                _canonical_json(recommendation),
                selection_hash,
            ),
        )
        conn.execute(
            "UPDATE project_candidate_sets SET status='primary_selected',updated_at=? WHERE id=?",
            (now, candidate_set_id),
        )
        _event(
            conn,
            candidate_set_id,
            "primary_project_selected",
            {
                "primary_project_uuid": project_uuid,
                "selected_by": selected_by.strip(),
                "selection_hash": selection_hash,
            },
        )
        conn.commit()
    return get_candidate_set(root, candidate_set_id)


def get_primary_selection(root: Path | str, candidate_set_id: int) -> dict[str, Any]:
    """Read the committed primary selection, if any."""
    state = get_candidate_set(root, candidate_set_id)
    return {
        "ok": True,
        "candidate_set_id": candidate_set_id,
        "selection": state["selection"],
        "primary_selected": state["selection"] is not None,
    }
