"""
File: .agents/agentos/skill_contract_v2.py

Purpose:
    Define and validate the v0.27.0 Governed Skill Contract v2 without granting
    skill-selection, architecture-approval, or execution authority.

Responsibilities:
    - Persist a deterministic v2 contract beside the existing human-gated skill lifecycle.
    - Bind architecture-sensitive skills to the exact ACTIVE Architecture Baseline when present.
    - Keep legacy v1 skills readable and unchanged rather than rewriting approved artifacts.
    - Validate capability/tool/scope/dependency/external-service declarations deterministically.
    - Expose read-only contract/status queries for CLI/MCP inspection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .architecture_contract import SECTION_BY_ID, architecture_section_get, architecture_status
from .db import connect, connect_read_only

MIGRATION_VERSION = 58
CONTRACT_VERSION = 2
RISK_TIERS = {"low", "medium", "high"}
CONTRACT_KEYS = {
    "contract_version", "skill_key", "skill_version", "inputs", "outputs",
    "required_architecture_sections", "required_capabilities", "required_tools",
    "allowed_read_scope", "allowed_write_scope", "allowed_dependencies",
    "allowed_external_services", "preconditions", "postconditions", "risk_tier",
    "test_contract", "architecture_constraints",
}


def migration_58(c) -> None:
    """Add Skill Contract v2 state while preserving all historical v1 skill rows."""
    columns = {row[1] for row in c.execute("PRAGMA table_info(promoted_skills)")}
    additions = (
        ("contract_version", "INTEGER NOT NULL DEFAULT 1"),
        ("contract_hash", "TEXT"),
        ("contract_status", "TEXT NOT NULL DEFAULT 'legacy_v1'"),
        ("architecture_baseline_id", "INTEGER"),
        ("architecture_baseline_hash", "TEXT"),
    )
    for name, spec in additions:
        if name not in columns:
            c.execute(f"ALTER TABLE promoted_skills ADD COLUMN {name} {spec}")
    c.executescript("""
    CREATE TABLE IF NOT EXISTS skill_contracts(
        skill_id INTEGER PRIMARY KEY,
        contract_version INTEGER NOT NULL CHECK(contract_version=2),
        contract_json TEXT NOT NULL,
        contract_hash TEXT NOT NULL,
        validation_status TEXT NOT NULL CHECK(validation_status IN ('draft','valid','invalid','needs_architecture','stale_architecture')),
        validation_findings_json TEXT NOT NULL DEFAULT '[]',
        architecture_baseline_id INTEGER,
        architecture_baseline_hash TEXT,
        drafted_by TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        validated_at TEXT,
        FOREIGN KEY(skill_id) REFERENCES promoted_skills(id),
        FOREIGN KEY(architecture_baseline_id) REFERENCES architecture_baselines(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skill_contract_status ON skill_contracts(validation_status,skill_id);
    CREATE TABLE IF NOT EXISTS skill_contract_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        event_json TEXT NOT NULL,
        event_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(skill_id) REFERENCES promoted_skills(id)
    );
    CREATE INDEX IF NOT EXISTS idx_skill_contract_events_skill ON skill_contract_events(skill_id,id);
    """)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _event(c, skill_id: int, event_type: str, payload: dict[str, Any]) -> None:
    text = _canonical(payload)
    c.execute(
        "INSERT INTO skill_contract_events(skill_id,event_type,event_json,event_hash) VALUES(?,?,?,?)",
        (skill_id, event_type, text, _sha_text(text)),
    )


def default_contract(skill_key: str, skill_version: int) -> dict[str, Any]:
    """Return the deterministic least-authority v2 contract for a new candidate."""
    return {
        "contract_version": CONTRACT_VERSION,
        "skill_key": skill_key,
        "skill_version": int(skill_version),
        "inputs": [],
        "outputs": [],
        "required_architecture_sections": [],
        "required_capabilities": [],
        "required_tools": [],
        "allowed_read_scope": [],
        "allowed_write_scope": [],
        "allowed_dependencies": [],
        "allowed_external_services": [],
        "preconditions": [],
        "postconditions": [],
        "risk_tier": "medium",
        "test_contract": {"required": True, "suites": []},
        "architecture_constraints": {},
    }


def _safe_scope(value: str) -> bool:
    text = str(value).strip().replace("\\", "/")
    if not text or text.startswith("/") or ":/" in text or text.startswith("~"):
        return False
    path = PurePosixPath(text)
    return ".." not in path.parts and ".agents/state" not in text and ".agents/runtime" not in text


def _string_list(value: Any, field: str, findings: list[dict[str, Any]]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        findings.append({"code": "skill_contract_invalid_list", "field": field})
        return []
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        findings.append({"code": "skill_contract_duplicate_values", "field": field})
    return normalized


def validate_contract_shape(contract: dict[str, Any], *, skill_key: str, skill_version: int) -> list[dict[str, Any]]:
    """Validate the closed v2 contract schema without consulting project architecture."""
    findings: list[dict[str, Any]] = []
    if not isinstance(contract, dict):
        return [{"code": "skill_contract_not_object"}]
    missing = sorted(CONTRACT_KEYS - set(contract))
    extra = sorted(set(contract) - CONTRACT_KEYS)
    if missing:
        findings.append({"code": "skill_contract_missing_fields", "fields": missing})
    if extra:
        findings.append({"code": "skill_contract_unknown_fields", "fields": extra})
    if contract.get("contract_version") != CONTRACT_VERSION:
        findings.append({"code": "skill_contract_version_invalid"})
    if contract.get("skill_key") != skill_key or contract.get("skill_version") != int(skill_version):
        findings.append({"code": "skill_contract_identity_mismatch"})
    list_fields = (
        "inputs", "outputs", "required_architecture_sections", "required_capabilities", "required_tools",
        "allowed_read_scope", "allowed_write_scope", "allowed_dependencies", "allowed_external_services",
        "preconditions", "postconditions",
    )
    values: dict[str, list[str]] = {field: _string_list(contract.get(field), field, findings) for field in list_fields}
    unknown_sections = sorted(set(values["required_architecture_sections"]) - set(SECTION_BY_ID))
    if unknown_sections:
        findings.append({"code": "skill_contract_unknown_architecture_section", "sections": unknown_sections})
    for field in ("allowed_read_scope", "allowed_write_scope"):
        bad = sorted(item for item in values[field] if not _safe_scope(item))
        if bad:
            findings.append({"code": "skill_contract_unsafe_scope", "field": field, "values": bad})
    if contract.get("risk_tier") not in RISK_TIERS:
        findings.append({"code": "skill_contract_risk_tier_invalid"})
    test_contract = contract.get("test_contract")
    if not isinstance(test_contract, dict) or set(test_contract) != {"required", "suites"}:
        findings.append({"code": "skill_contract_test_contract_invalid"})
    else:
        if not isinstance(test_contract.get("required"), bool):
            findings.append({"code": "skill_contract_test_required_invalid"})
        _string_list(test_contract.get("suites"), "test_contract.suites", findings)
    if not isinstance(contract.get("architecture_constraints"), dict):
        findings.append({"code": "skill_contract_architecture_constraints_invalid"})
    return findings


def _active_architecture(root: Path) -> dict[str, Any] | None:
    status = architecture_status(root)
    return status.get("active_baseline")


def _architecture_findings(root: Path, contract: dict[str, Any], active: dict[str, Any] | None) -> list[dict[str, Any]]:
    required = list(contract.get("required_architecture_sections") or [])
    architecture_bound = bool(
        required
        or contract.get("allowed_dependencies")
        or contract.get("allowed_external_services")
        or contract.get("architecture_constraints")
    )
    if architecture_bound and not active:
        return [{"code": "skill_contract_active_architecture_required"}]
    if not active:
        return []
    findings: list[dict[str, Any]] = []
    baseline_id = int(active["id"])
    for section_id in required:
        section = architecture_section_get(root, section_id, baseline_id=baseline_id)
        payload = section.get("section") or section.get("revision") or section
        applicability = payload.get("applicability") if isinstance(payload, dict) else None
        if applicability == "not_applicable":
            findings.append({"code": "skill_contract_required_section_not_applicable", "section_id": section_id})
    # Only explicit allowlists become authority. Missing allowlists are not invented.
    if contract.get("allowed_dependencies"):
        section = architecture_section_get(root, "ARCH-02", baseline_id=baseline_id)
        raw = (section.get("section") or {}).get("contract") or section.get("contract") or section.get("contract_json") or {}
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except json.JSONDecodeError: raw = {}
        payload = raw.get("payload", {}) if isinstance(raw, dict) else {}
        allowed = payload.get("allowed_dependencies")
        if isinstance(allowed, list):
            excess = sorted(set(contract["allowed_dependencies"]) - {str(x) for x in allowed})
            if excess:
                findings.append({"code": "skill_contract_dependency_exceeds_architecture", "dependencies": excess})
    if contract.get("allowed_external_services"):
        section = architecture_section_get(root, "ARCH-13", baseline_id=baseline_id)
        raw = (section.get("section") or {}).get("contract") or section.get("contract") or section.get("contract_json") or {}
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except json.JSONDecodeError: raw = {}
        payload = raw.get("payload", {}) if isinstance(raw, dict) else {}
        allowed = payload.get("allowed_hosts") or payload.get("allowed_external_services")
        if isinstance(allowed, list):
            excess = sorted(set(contract["allowed_external_services"]) - {str(x) for x in allowed})
            if excess:
                findings.append({"code": "skill_contract_external_service_exceeds_architecture", "services": excess})
    return findings


def initialize_skill_contract_in_connection(c, skill_id: int, drafted_by: str) -> dict[str, Any]:
    """Create one v2 draft inside an existing AgentOS transaction."""
    row = c.execute("SELECT id,skill_key,version,status FROM promoted_skills WHERE id=?", (skill_id,)).fetchone()
    if not row:
        raise RuntimeError("skill not found")
    if row["status"] != "candidate":
        raise RuntimeError("skill contract initialization requires candidate status")
    contract = default_contract(row["skill_key"], int(row["version"]))
    text = _canonical(contract); digest = _sha_text(text)
    c.execute(
        """INSERT INTO skill_contracts(skill_id,contract_version,contract_json,contract_hash,validation_status,drafted_by)
           VALUES(?,2,?,?,'draft',?)""",
        (skill_id, text, digest, drafted_by),
    )
    c.execute(
        "UPDATE promoted_skills SET contract_version=2,contract_hash=?,contract_status='draft' WHERE id=?",
        (digest, skill_id),
    )
    _event(c, skill_id, "skill.contract.created", {"contract_hash": digest, "contract_version": 2, "drafted_by": drafted_by})
    return {"ok": True, "skill_id": skill_id, "contract": contract, "contract_hash": digest, "status": "draft"}


def initialize_skill_contract(root: Path, skill_id: int, drafted_by: str) -> dict[str, Any]:
    """Create the v2 least-authority draft for one new candidate skill."""
    with connect(root, immediate=True) as c:
        return initialize_skill_contract_in_connection(c, skill_id, drafted_by)


def set_skill_contract(root: Path, skill_id: int, contract: dict[str, Any], drafted_by: str) -> dict[str, Any]:
    """Replace only a candidate's non-authoritative v2 draft and invalidate prior validation."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM promoted_skills WHERE id=?", (skill_id,)).fetchone()
        if not row:
            raise RuntimeError("skill not found")
        if row["status"] != "candidate":
            raise RuntimeError("graduated_or_inactive_skill_contract_is_immutable")
        findings = validate_contract_shape(contract, skill_key=row["skill_key"], skill_version=int(row["version"]))
        text = _canonical(contract); digest = _sha_text(text)
        status = "invalid" if findings else "draft"
        candidate = root / str(row["candidate_path"])
        if not candidate.is_file():
            raise RuntimeError("candidate artifact missing")
        artifact = candidate.read_text(encoding="utf-8")
        marker = "## Governed Skill Contract v2\n\n```json\n"
        if marker not in artifact:
            raise RuntimeError("candidate artifact lacks governed contract section")
        prefix, rest = artifact.split(marker, 1)
        if "\n```" not in rest:
            raise RuntimeError("candidate governed contract block is malformed")
        _, suffix = rest.split("\n```", 1)
        artifact = prefix + marker + json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n```" + suffix
        # Persist canonical UTF-8/LF bytes so content_hash is identical on Windows,
        # POSIX, and macOS.  Path.write_text() may translate newlines on Windows.
        artifact_bytes = artifact.encode("utf-8")
        candidate.write_bytes(artifact_bytes)
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        c.execute(
            """INSERT INTO skill_contracts(skill_id,contract_version,contract_json,contract_hash,validation_status,validation_findings_json,drafted_by,updated_at,validated_at)
               VALUES(?,2,?,?,?,?,?,CURRENT_TIMESTAMP,NULL)
               ON CONFLICT(skill_id) DO UPDATE SET contract_version=2,contract_json=excluded.contract_json,
                 contract_hash=excluded.contract_hash,validation_status=excluded.validation_status,
                 validation_findings_json=excluded.validation_findings_json,drafted_by=excluded.drafted_by,
                 updated_at=CURRENT_TIMESTAMP,validated_at=NULL,architecture_baseline_id=NULL,architecture_baseline_hash=NULL""",
            (skill_id, text, digest, status, _canonical(findings), drafted_by),
        )
        c.execute(
            "UPDATE promoted_skills SET contract_version=2,contract_hash=?,contract_status=?,content_hash=?,architecture_baseline_id=NULL,architecture_baseline_hash=NULL WHERE id=?",
            (digest, status, artifact_hash, skill_id),
        )
        _event(c, skill_id, "skill.contract.drafted", {"contract_hash": digest, "drafted_by": drafted_by, "shape_findings": findings})
    return {"ok": not findings, "skill_id": skill_id, "contract_hash": digest, "status": status, "findings": findings}


def validate_skill_contract(root: Path, skill_id: int) -> dict[str, Any]:
    """Validate exact v2 draft plus explicit ACTIVE architecture constraints."""
    with connect(root, immediate=True) as c:
        row = c.execute("SELECT * FROM promoted_skills WHERE id=?", (skill_id,)).fetchone()
        stored = c.execute("SELECT * FROM skill_contracts WHERE skill_id=?", (skill_id,)).fetchone()
        if not row:
            raise RuntimeError("skill not found")
        if int(row["contract_version"] or 1) != 2 or not stored:
            return {"ok": False, "skill_id": skill_id, "status": "legacy_v1", "findings": [{"code": "skill_contract_v2_required"}]}
        contract = json.loads(stored["contract_json"])
        findings = validate_contract_shape(contract, skill_key=row["skill_key"], skill_version=int(row["version"]))
        candidate = root / str(row["candidate_path"])
        if row["status"] == "candidate":
            if not candidate.is_file():
                findings.append({"code": "skill_contract_candidate_artifact_missing"})
            else:
                current_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
                if current_hash != row["content_hash"]:
                    findings.append({"code": "skill_contract_candidate_artifact_changed"})
        active = _active_architecture(root)
        architecture_bound = bool(
            contract.get("required_architecture_sections")
            or contract.get("allowed_dependencies")
            or contract.get("allowed_external_services")
            or contract.get("architecture_constraints")
        )
        previous_baseline_hash = stored["architecture_baseline_hash"]
        active_hash = str(active["baseline_hash"]) if active else None
        baseline_changed = bool(
            architecture_bound
            and previous_baseline_hash
            and active_hash
            and str(previous_baseline_hash) != active_hash
        )
        if baseline_changed:
            findings.append({
                "code": "skill_contract_architecture_baseline_changed",
                "previous_architecture_baseline_hash": str(previous_baseline_hash),
                "active_architecture_baseline_hash": active_hash,
                "required_action": "redraft_or_reconfirm_candidate_contract",
            })
        else:
            findings.extend(_architecture_findings(root, contract, active))
        needs_arch = any(item.get("code") == "skill_contract_active_architecture_required" for item in findings)
        if baseline_changed:
            status = "stale_architecture"
        else:
            status = "needs_architecture" if needs_arch else ("invalid" if findings else "valid")
        baseline_id = int(active["id"]) if active and status == "valid" else (stored["architecture_baseline_id"] if baseline_changed else None)
        baseline_hash = active_hash if active and status == "valid" else (str(previous_baseline_hash) if baseline_changed else None)
        c.execute(
            """UPDATE skill_contracts SET validation_status=?,validation_findings_json=?,architecture_baseline_id=?,architecture_baseline_hash=?,validated_at=CURRENT_TIMESTAMP WHERE skill_id=?""",
            (status, _canonical(findings), baseline_id, baseline_hash, skill_id),
        )
        c.execute(
            "UPDATE promoted_skills SET contract_status=?,architecture_baseline_id=?,architecture_baseline_hash=? WHERE id=?",
            (status, baseline_id, baseline_hash, skill_id),
        )
        _event(c, skill_id, "skill.contract.validated", {"contract_hash": stored["contract_hash"], "status": status, "architecture_baseline_hash": baseline_hash, "findings": findings})
    return {"ok": status == "valid", "skill_id": skill_id, "status": status, "contract_hash": stored["contract_hash"], "architecture_baseline_id": baseline_id, "architecture_baseline_hash": baseline_hash, "findings": findings}


def skill_contract_get(root: Path, skill_id: int, *, read_only: bool = False) -> dict[str, Any]:
    """Return one v2 contract or a legacy-v1 marker without mutating state."""
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        row = c.execute("SELECT id,skill_key,version,status,contract_version,contract_hash,contract_status,architecture_baseline_id,architecture_baseline_hash FROM promoted_skills WHERE id=?", (skill_id,)).fetchone()
        if not row:
            raise RuntimeError("skill not found")
        stored = c.execute("SELECT * FROM skill_contracts WHERE skill_id=?", (skill_id,)).fetchone()
    result = dict(row)
    if not stored:
        return {"ok": True, "skill": result, "contract": None, "legacy_v1": True, "migration_required": "create_successor_candidate_not_in_place_rewrite"}
    item = dict(stored)
    item["contract"] = json.loads(item.pop("contract_json"))
    item["validation_findings"] = json.loads(item.pop("validation_findings_json"))
    return {"ok": True, "skill": result, "contract_state": item, "legacy_v1": False}


def skill_contract_status(root: Path, skill_id: int | None = None, *, read_only: bool = False) -> dict[str, Any]:
    """Return privacy-safe governed-contract coverage and authority boundaries."""
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        if skill_id is not None:
            row = c.execute("SELECT contract_version,contract_status,status FROM promoted_skills WHERE id=?", (skill_id,)).fetchone()
            if not row:
                raise RuntimeError("skill not found")
            counts = {str(row["contract_status"]): 1}
            total = 1
        else:
            rows = c.execute("SELECT contract_status,COUNT(*) n FROM promoted_skills GROUP BY contract_status").fetchall()
            counts = {str(row["contract_status"]): int(row["n"]) for row in rows}
            total = sum(counts.values())
    return {
        "ok": True,
        "contract_version": 2,
        "skill_id": skill_id,
        "total_skills": total,
        "by_contract_status": counts,
        "legacy_v1_preserved": True,
        "legacy_in_place_rewrite": False,
        "human_graduation_required": True,
        "human_revocation_required": True,
        "mcp_mutation_exposed": False,
        "automatic_skill_selection": False,
        "architecture_approval_authority_exposed": False,
    }


def list_skill_contracts(root: Path, *, read_only: bool = False) -> list[dict[str, Any]]:
    """List contract metadata without exposing mutable approval operations."""
    cm = connect_read_only(root) if read_only else connect(root)
    with cm as c:
        rows = c.execute(
            """SELECT id,skill_key,version,status,contract_version,contract_hash,contract_status,
                      architecture_baseline_id,architecture_baseline_hash
               FROM promoted_skills ORDER BY skill_key,version DESC"""
        ).fetchall()
    return [dict(row) for row in rows]
