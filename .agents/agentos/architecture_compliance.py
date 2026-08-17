"""
File: .agents/agentos/architecture_compliance.py

Purpose:
    Enforce the human-approved Architecture Contract against deterministic source evidence.

Responsibilities:
    - Materialize schema 52 compliance runs/findings.
    - Evaluate only explicit machine-readable hard-contract keys.
    - Fail closed for blocking violations when an ACTIVE architecture baseline exists.
    - Remain non-blocking/not-evaluable when no human-activated baseline exists.
    - Provide path-level checks for prepare/write and repository-level checks for precommit/final report.
    - Never approve, waive, mutate, or activate Architecture Authority.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .db import connect, connect_read_only

MIGRATION_VERSION = 52
COMPLIANCE_ENGINE_VERSION = 1
SEVERITIES = {"info", "warn", "block"}
RUN_STATUSES = {"pass", "warn", "block", "not_evaluable"}


def migration_52(connection: Any) -> None:
    """Create architecture compliance schema objects additively for schema 52."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_compliance_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid TEXT NOT NULL UNIQUE,
            engine_version INTEGER NOT NULL,
            mode TEXT NOT NULL,
            task_id TEXT,
            baseline_id INTEGER,
            baseline_hash TEXT,
            scan_id INTEGER,
            scan_hash TEXT,
            status TEXT NOT NULL CHECK(status IN ('pass','warn','block','not_evaluable')),
            finding_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            blocking_count INTEGER NOT NULL DEFAULT 0,
            changed_files_json TEXT NOT NULL,
            run_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id),
            FOREIGN KEY(scan_id) REFERENCES architecture_scan_runs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_arch_compliance_task
            ON architecture_compliance_runs(task_id,id);
        CREATE INDEX IF NOT EXISTS idx_arch_compliance_baseline
            ON architecture_compliance_runs(baseline_id,id);

        CREATE TABLE IF NOT EXISTS architecture_compliance_findings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            section_id TEXT NOT NULL,
            finding_code TEXT NOT NULL,
            severity TEXT NOT NULL CHECK(severity IN ('info','warn','block')),
            subject TEXT NOT NULL,
            expected_json TEXT NOT NULL,
            observed_json TEXT NOT NULL,
            evidence_paths_json TEXT NOT NULL,
            finding_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_id,finding_hash),
            FOREIGN KEY(run_id) REFERENCES architecture_compliance_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arch_compliance_findings_run
            ON architecture_compliance_findings(run_id,severity,section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_compliance_findings_code
            ON architecture_compliance_findings(finding_code,severity);
        """
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalize_path(value: str) -> str:
    text = str(value).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _as_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []


def _matches(value: str, patterns: Iterable[str]) -> bool:
    normalized = _normalize_path(value)
    return any(fnmatch.fnmatchcase(normalized, _normalize_path(pattern)) for pattern in patterns)


def _active_baseline(connection: Any) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id,baseline_hash,baseline_version FROM architecture_baselines WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "baseline_hash": str(row[1]), "baseline_version": int(row[2])}


def _baseline_sections(connection: Any, baseline_id: int) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT bs.section_id,sr.applicability,sr.section_hash,sr.contract_json
        FROM architecture_baseline_sections bs
        JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id
        WHERE bs.baseline_id=? ORDER BY bs.section_id
        """,
        (baseline_id,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            contract = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            contract = {}
        payload = contract.get("payload") if isinstance(contract, dict) else {}
        result[str(row[0])] = {
            "applicability": str(row[1]),
            "section_hash": str(row[2]),
            "contract": contract,
            "payload": payload if isinstance(payload, dict) else {},
        }
    return result


def _latest_scan(connection: Any, baseline_id: int | None = None) -> dict[str, Any] | None:
    query = "SELECT id,scan_hash,active_baseline_id,active_baseline_hash FROM architecture_scan_runs WHERE status='completed'"
    args: tuple[Any, ...] = ()
    if baseline_id is not None:
        query += " AND active_baseline_id=?"
        args = (baseline_id,)
    query += " ORDER BY id DESC LIMIT 1"
    row = connection.execute(query, args).fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "scan_hash": str(row[1] or ""), "active_baseline_id": row[2], "active_baseline_hash": row[3]}


def _observations(connection: Any, scan_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT section_id,observation_kind,subject,value_json,observation_hash FROM architecture_observations WHERE scan_id=? ORDER BY section_id,observation_kind,subject",
        (scan_id,),
    ).fetchall()
    result = []
    for row in rows:
        try:
            value = json.loads(row[3])
        except json.JSONDecodeError:
            value = None
        result.append({"section_id": str(row[0]), "kind": str(row[1]), "subject": str(row[2]), "value": value, "hash": str(row[4])})
    return result


def _evidence_map(connection: Any, scan_id: int) -> dict[str, str]:
    rows = connection.execute(
        "SELECT source_path,source_hash FROM architecture_evidence WHERE scan_id=? ORDER BY source_path",
        (scan_id,),
    ).fetchall()
    return {_normalize_path(str(row[0])): str(row[1]) for row in rows}


def _discrepancies(connection: Any, scan_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT section_id,discrepancy_type,subject,severity,details_json FROM architecture_discrepancies WHERE scan_id=? ORDER BY section_id,discrepancy_type,subject",
        (scan_id,),
    ).fetchall()
    out = []
    for row in rows:
        try:
            details = json.loads(row[4])
        except json.JSONDecodeError:
            details = {}
        out.append({"section_id": str(row[0]), "type": str(row[1]), "subject": str(row[2]), "severity": str(row[3]), "details": details})
    return out


def _finding(section_id: str, code: str, severity: str, subject: str, expected: Any, observed: Any, evidence_paths: Iterable[str] = ()) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise RuntimeError(f"invalid architecture compliance severity: {severity}")
    item = {
        "section_id": section_id,
        "finding_code": code,
        "severity": severity,
        "subject": subject,
        "expected": expected,
        "observed": observed,
        "evidence_paths": sorted({_normalize_path(path) for path in evidence_paths}),
    }
    item["finding_hash"] = _sha(item)
    return item


def _obs_values(observations: list[dict[str, Any]], section_id: str, kind: str) -> list[Any]:
    return [item["value"] for item in observations if item["section_id"] == section_id and item["kind"] == kind]


def _flatten_inventory(values: list[Any], key: str | None = None) -> set[str]:
    out: set[str] = set()
    for value in values:
        if key and isinstance(value, dict):
            value = value.get(key, [])
        if isinstance(value, dict):
            out.update(str(k) for k in value)
        elif isinstance(value, list):
            out.update(str(x) for x in value)
        elif isinstance(value, str):
            out.add(value)
    return out


def _contract_list(payload: dict[str, Any], name: str) -> list[str]:
    return [_normalize_path(x) if "path" in name or "root" in name else str(x) for x in _as_strings(payload.get(name))]


def _evidence_bindings(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if isinstance(value, dict):
        path = value.get("source_path", value.get("path"))
        digest = value.get("sha256", value.get("source_hash", value.get("content_hash")))
        if isinstance(path, str) and isinstance(digest, str) and len(digest) == 64:
            result.append({"path": _normalize_path(path), "hash": digest.lower()})
        for item in value.values():
            if isinstance(item, (dict, list)):
                result.extend(_evidence_bindings(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_evidence_bindings(item))
    dedup: dict[tuple[str, str], dict[str, str]] = {(x["path"], x["hash"]): x for x in result}
    return [dedup[key] for key in sorted(dedup)]


def _module_import_edges(observations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for item in observations:
        if item["section_id"] != "ARCH-12" or item["kind"] != "python_imports" or not isinstance(item["value"], list):
            continue
        source = _normalize_path(item["subject"])
        for entry in item["value"]:
            if isinstance(entry, dict) and isinstance(entry.get("module"), str):
                edges.append((source, str(entry["module"])))
    return edges


def _evaluate_machine_contract(
    sections: dict[str, dict[str, Any]],
    observations: list[dict[str, Any]],
    evidence: dict[str, str],
    discrepancies: list[dict[str, Any]],
    changed_files: list[str],
    root_path: Path,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    # A human-declared not-applicable section is a hard boundary once observations exist.
    by_section: dict[str, list[dict[str, Any]]] = {}
    for obs in observations:
        by_section.setdefault(obs["section_id"], []).append(obs)
    for section_id, items in sorted(by_section.items()):
        section = sections.get(section_id)
        if section and section["applicability"] == "not_applicable" and items:
            findings.append(_finding(section_id, "observed_for_not_applicable_section", "block", section_id, "no observed architecture", sorted({x["kind"] for x in items})))

    # ARCH-02 — technology/dependencies.
    p = sections.get("ARCH-02", {}).get("payload", {})
    languages = _flatten_inventory(_obs_values(observations, "ARCH-02", "language_inventory"))
    dependencies = _flatten_inventory(_obs_values(observations, "ARCH-02", "dependency_inventory"), "dependencies")
    allowed = set(_as_strings(p.get("allowed_languages")))
    forbidden = set(_as_strings(p.get("forbidden_languages")))
    if allowed:
        for value in sorted(languages - allowed):
            findings.append(_finding("ARCH-02", "unapproved_language", "block", value, sorted(allowed), value))
    for value in sorted(languages & forbidden):
        findings.append(_finding("ARCH-02", "forbidden_language", "block", value, sorted(forbidden), value))
    allowed = set(_as_strings(p.get("allowed_dependencies")))
    forbidden = set(_as_strings(p.get("forbidden_dependencies")))
    required = set(_as_strings(p.get("required_dependencies")))
    if allowed:
        for value in sorted(dependencies - allowed):
            findings.append(_finding("ARCH-02", "unapproved_dependency", "block", value, sorted(allowed), value))
    for value in sorted(dependencies & forbidden):
        findings.append(_finding("ARCH-02", "forbidden_dependency", "block", value, sorted(forbidden), value))
    for value in sorted(required - dependencies):
        findings.append(_finding("ARCH-02", "required_dependency_missing", "block", value, value, "missing"))

    # ARCH-03 / ARCH-05 — folder and module boundaries, evaluated from discovery + changed files.
    p3 = sections.get("ARCH-03", {}).get("payload", {})
    top_level = _flatten_inventory(_obs_values(observations, "ARCH-03", "folder_inventory"))
    allowed_top = set(_as_strings(p3.get("allowed_top_level")))
    forbidden_top = set(_as_strings(p3.get("forbidden_top_level")))
    if allowed_top:
        for value in sorted(top_level - allowed_top):
            findings.append(_finding("ARCH-03", "unapproved_top_level_folder", "block", value, sorted(allowed_top), value))
    for value in sorted(top_level & forbidden_top):
        findings.append(_finding("ARCH-03", "forbidden_top_level_folder", "block", value, sorted(forbidden_top), value))

    p5 = sections.get("ARCH-05", {}).get("payload", {})
    module_paths = _flatten_inventory(_obs_values(observations, "ARCH-05", "module_inventory"))
    allowed_module_roots = _contract_list(p5, "allowed_module_roots")
    forbidden_module_paths = _contract_list(p5, "forbidden_module_paths")
    for path in sorted(module_paths):
        if allowed_module_roots and not _matches(path, [root.rstrip("/") + "/**" for root in allowed_module_roots] + allowed_module_roots):
            findings.append(_finding("ARCH-05", "unknown_module", "block", path, allowed_module_roots, path, [path]))
        if forbidden_module_paths and _matches(path, forbidden_module_paths):
            findings.append(_finding("ARCH-05", "forbidden_module", "block", path, forbidden_module_paths, path, [path]))

    for path in sorted({_normalize_path(x) for x in changed_files}):
        target = architecture_target_check_from_sections(sections, path)
        if not target["allowed"]:
            findings.append(_finding(target["section_id"], target["reason"], "block", path, target.get("expected"), path, [path]))

    # ARCH-10 — public CLI/MCP surfaces.
    p10 = sections.get("ARCH-10", {}).get("payload", {})
    cli = _flatten_inventory(_obs_values(observations, "ARCH-10", "cli_surface"))
    mcp = _flatten_inventory(_obs_values(observations, "ARCH-10", "mcp_surface"))
    for surface, observed, allowed_key, forbidden_key in (
        ("cli", cli, "allowed_cli_commands", "forbidden_cli_commands"),
        ("mcp", mcp, "allowed_mcp_tools", "forbidden_mcp_tools"),
    ):
        allowed_values = set(_as_strings(p10.get(allowed_key)))
        forbidden_values = set(_as_strings(p10.get(forbidden_key)))
        if allowed_values:
            for value in sorted(observed - allowed_values):
                findings.append(_finding("ARCH-10", f"unapproved_{surface}_surface", "block", value, sorted(allowed_values), value))
        for value in sorted(observed & forbidden_values):
            findings.append(_finding("ARCH-10", f"forbidden_{surface}_surface", "block", value, sorted(forbidden_values), value))

    # ARCH-12 — imports/layer boundaries.
    p12 = sections.get("ARCH-12", {}).get("payload", {})
    forbidden_imports = _as_strings(p12.get("forbidden_imports"))
    edge_rules = p12.get("forbidden_import_edges") if isinstance(p12.get("forbidden_import_edges"), list) else []
    for source, imported in _module_import_edges(observations):
        if forbidden_imports and _matches(imported, forbidden_imports):
            findings.append(_finding("ARCH-12", "forbidden_import", "block", f"{source} -> {imported}", forbidden_imports, imported, [source]))
        for rule in edge_rules:
            if not isinstance(rule, dict):
                continue
            source_pattern = str(rule.get("from", "*"))
            import_pattern = str(rule.get("import", "*"))
            if _matches(source, [source_pattern]) and fnmatch.fnmatchcase(imported, import_pattern):
                findings.append(_finding("ARCH-12", "forbidden_import_edge", "block", f"{source} -> {imported}", rule, {"from": source, "import": imported}, [source]))

    # ARCH-13 — externally observed domains are names only; no URL/query/secret is persisted.
    p13 = sections.get("ARCH-13", {}).get("payload", {})
    domains = _flatten_inventory(_obs_values(observations, "ARCH-13", "external_service_domains"))
    allowed_domains = set(_as_strings(p13.get("allowed_domains")))
    forbidden_domains = set(_as_strings(p13.get("forbidden_domains")))
    if allowed_domains:
        for domain in sorted(domains - allowed_domains):
            findings.append(_finding("ARCH-13", "unapproved_external_service", "block", domain, sorted(allowed_domains), domain))
    for domain in sorted(domains & forbidden_domains):
        findings.append(_finding("ARCH-13", "forbidden_external_service", "block", domain, sorted(forbidden_domains), domain))

    # ARCH-14 — environment variable names and committed .env files only, never values.
    p14 = sections.get("ARCH-14", {}).get("payload", {})
    env_names = _flatten_inventory(_obs_values(observations, "ARCH-14", "environment_variables"))
    allowed_env = set(_as_strings(p14.get("allowed_environment_variables")))
    forbidden_env = set(_as_strings(p14.get("forbidden_environment_variables")))
    if allowed_env:
        for name in sorted(env_names - allowed_env):
            findings.append(_finding("ARCH-14", "unapproved_environment_variable", "block", name, sorted(allowed_env), name))
    for name in sorted(env_names & forbidden_env):
        findings.append(_finding("ARCH-14", "forbidden_environment_variable", "block", name, sorted(forbidden_env), name))
    if bool(p14.get("forbid_committed_env_files", False)):
        configs = _flatten_inventory(_obs_values(observations, "ARCH-14", "configuration_inventory"))
        for path in sorted(x for x in configs if Path(x).name == ".env" or Path(x).name.startswith(".env.")):
            findings.append(_finding("ARCH-14", "committed_env_file", "block", path, "no committed .env files", path, [path]))

    # Any exact evidence hash explicitly pinned by the human Architecture Contract is authoritative.
    for section_id, section in sorted(sections.items()):
        for binding in _evidence_bindings(section.get("contract", {})):
            observed = evidence.get(binding["path"])
            if observed is None:
                candidate = (root_path / binding["path"]).resolve()
                try:
                    candidate.relative_to(root_path)
                except ValueError:
                    candidate = Path("__outside_project_root__")
                if candidate.is_file() and not candidate.is_symlink():
                    h = hashlib.sha256()
                    with candidate.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            h.update(chunk)
                    observed = h.hexdigest()
            if observed is None:
                findings.append(_finding(section_id, "architecture_evidence_missing", "block", binding["path"], binding["hash"], "missing", [binding["path"]]))
            elif observed.lower() != binding["hash"]:
                findings.append(_finding(section_id, "architecture_evidence_hash_mismatch", "block", binding["path"], binding["hash"], observed, [binding["path"]]))

    # Discovery drift remains advisory unless covered by a machine contract above.
    for discrepancy in discrepancies:
        if discrepancy["type"] in {"evidence_hash_changed", "observed_evidence_not_bound_in_contract", "observed_evidence_partially_unbound"}:
            findings.append(_finding(discrepancy["section_id"], discrepancy["type"], "warn", discrepancy["subject"], "review architecture evidence", discrepancy["details"]))

    dedup: dict[str, dict[str, Any]] = {item["finding_hash"]: item for item in findings}
    return sorted(dedup.values(), key=lambda x: ({"block": 0, "warn": 1, "info": 2}[x["severity"]], x["section_id"], x["finding_code"], x["subject"]))


def architecture_target_check_from_sections(sections: dict[str, dict[str, Any]], target: str) -> dict[str, Any]:
    """Evaluate one normalized project-relative target against path/module boundaries."""
    path = _normalize_path(target)
    p3 = sections.get("ARCH-03", {}).get("payload", {})
    forbidden = _contract_list(p3, "forbidden_paths")
    allowed_roots = _contract_list(p3, "allowed_write_roots")
    if forbidden and _matches(path, forbidden):
        return {"allowed": False, "reason": "architecture_forbidden_path", "section_id": "ARCH-03", "target": path, "expected": {"forbidden_paths": forbidden}}
    if allowed_roots:
        patterns = allowed_roots + [root.rstrip("/") + "/**" for root in allowed_roots]
        if not _matches(path, patterns):
            return {"allowed": False, "reason": "architecture_write_root_violation", "section_id": "ARCH-03", "target": path, "expected": {"allowed_write_roots": allowed_roots}}
    p5 = sections.get("ARCH-05", {}).get("payload", {})
    forbidden_modules = _contract_list(p5, "forbidden_module_paths")
    if forbidden_modules and _matches(path, forbidden_modules):
        return {"allowed": False, "reason": "architecture_forbidden_module", "section_id": "ARCH-05", "target": path, "expected": {"forbidden_module_paths": forbidden_modules}}
    return {"allowed": True, "reason": "architecture_target_allowed", "section_id": None, "target": path}


def architecture_target_check(root: Path | str, target: str) -> dict[str, Any]:
    """Check one target without mutating architecture authority or source."""
    root_path = Path(root).resolve()
    with connect_read_only(root_path) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            return {"allowed": True, "reason": "architecture_not_evaluable_no_active_baseline", "enforced": False, "target": _normalize_path(target)}
        sections = _baseline_sections(connection, baseline["id"])
    result = architecture_target_check_from_sections(sections, target)
    result.update({"enforced": True, "baseline_id": baseline["id"], "baseline_hash": baseline["baseline_hash"]})
    return result


def architecture_compliance_check(
    root: Path | str,
    *,
    task_id: str | None = None,
    changed_files: list[str] | None = None,
    mode: str = "manual",
    refresh_scan: bool = True,
    created_by: str = "system:architecture-compliance",
) -> dict[str, Any]:
    """Evaluate the active human Architecture Contract against current static evidence."""
    import uuid
    from .architecture_discovery import architecture_scan

    root_path = Path(root).resolve()
    changed = sorted({_normalize_path(x) for x in (changed_files or []) if str(x).strip()})
    with connect(root_path) as connection:
        baseline = _active_baseline(connection)
    if not baseline:
        payload = {"mode": mode, "task_id": task_id, "baseline": None, "changed_files": changed, "status": "not_evaluable"}
        run_hash = _sha(payload)
        with connect(root_path, immediate=True) as connection:
            existing = connection.execute("SELECT id FROM architecture_compliance_runs WHERE run_hash=?", (run_hash,)).fetchone()
            if existing:
                run_id = int(existing[0])
            else:
                cur = connection.execute(
                    """INSERT INTO architecture_compliance_runs(run_uuid,engine_version,mode,task_id,status,changed_files_json,run_hash,created_by)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), COMPLIANCE_ENGINE_VERSION, mode, task_id, "not_evaluable", _canonical(changed), run_hash, created_by),
                )
                run_id = int(cur.lastrowid)
        return {"ok": True, "enforced": False, "status": "not_evaluable", "reason": "no_active_architecture_baseline", "run_id": run_id, "task_id": task_id, "changed_files": changed, "findings": [], "blocking_count": 0, "warning_count": 0}

    scan: dict[str, Any] | None = None
    if refresh_scan:
        scan = architecture_scan(root_path, created_by=created_by)
    with connect(root_path) as connection:
        if scan is None:
            latest = _latest_scan(connection, baseline["id"])
            if latest:
                scan = {"scan_id": latest["id"], "scan_hash": latest["scan_hash"]}
        if scan is None:
            raise RuntimeError("architecture_compliance_requires_completed_scan")
        scan_id = int(scan.get("scan_id", scan.get("id")))
        scan_row = _latest_scan(connection, baseline["id"])
        if not scan_row or scan_row["id"] != scan_id:
            row = connection.execute("SELECT id,scan_hash,active_baseline_id,active_baseline_hash FROM architecture_scan_runs WHERE id=? AND status='completed'", (scan_id,)).fetchone()
            if not row:
                raise RuntimeError("architecture_compliance_scan_not_found")
            scan_row = {"id": int(row[0]), "scan_hash": str(row[1] or ""), "active_baseline_id": row[2], "active_baseline_hash": row[3]}
        if int(scan_row["active_baseline_id"] or 0) != baseline["id"] or str(scan_row["active_baseline_hash"] or "") != baseline["baseline_hash"]:
            raise RuntimeError("architecture_compliance_scan_baseline_mismatch")
        sections = _baseline_sections(connection, baseline["id"])
        observations = _observations(connection, scan_id)
        evidence = _evidence_map(connection, scan_id)
        discrepancies = _discrepancies(connection, scan_id)

    findings = _evaluate_machine_contract(sections, observations, evidence, discrepancies, changed, root_path)
    blocking = sum(1 for item in findings if item["severity"] == "block")
    warnings = sum(1 for item in findings if item["severity"] == "warn")
    status = "block" if blocking else "warn" if warnings else "pass"
    identity = {
        "engine_version": COMPLIANCE_ENGINE_VERSION,
        "mode": mode,
        "task_id": task_id,
        "baseline_id": baseline["id"],
        "baseline_hash": baseline["baseline_hash"],
        "scan_id": scan_id,
        "scan_hash": scan_row["scan_hash"],
        "changed_files": changed,
        "finding_hashes": [item["finding_hash"] for item in findings],
        "status": status,
    }
    run_hash = _sha(identity)
    with connect(root_path, immediate=True) as connection:
        existing = connection.execute("SELECT id FROM architecture_compliance_runs WHERE run_hash=?", (run_hash,)).fetchone()
        if existing:
            run_id = int(existing[0])
        else:
            cur = connection.execute(
                """INSERT INTO architecture_compliance_runs(run_uuid,engine_version,mode,task_id,baseline_id,baseline_hash,scan_id,scan_hash,status,finding_count,warning_count,blocking_count,changed_files_json,run_hash,created_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), COMPLIANCE_ENGINE_VERSION, mode, task_id, baseline["id"], baseline["baseline_hash"], scan_id, scan_row["scan_hash"], status, len(findings), warnings, blocking, _canonical(changed), run_hash, created_by),
            )
            run_id = int(cur.lastrowid)
            for item in findings:
                connection.execute(
                    """INSERT INTO architecture_compliance_findings(run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (run_id, item["section_id"], item["finding_code"], item["severity"], item["subject"], _canonical(item["expected"]), _canonical(item["observed"]), _canonical(item["evidence_paths"]), item["finding_hash"]),
                )
    return {
        "ok": blocking == 0,
        "enforced": True,
        "status": status,
        "run_id": run_id,
        "task_id": task_id,
        "baseline_id": baseline["id"],
        "baseline_hash": baseline["baseline_hash"],
        "scan_id": scan_id,
        "scan_hash": scan_row["scan_hash"],
        "changed_files": changed,
        "finding_count": len(findings),
        "warning_count": warnings,
        "blocking_count": blocking,
        "findings": findings,
        "architecture_change_proposal_available": blocking > 0,
        "architecture_change_proposal_source_run_id": run_id if blocking > 0 else None,
        "architecture_change_proposal_note": "Create a proposal/ADR draft; human review/approval and a separate Architecture Baseline lifecycle remain required." if blocking > 0 else None,
    }


def architecture_compliance_get(root: Path | str, *, run_id: int | None = None, read_only: bool = True) -> dict[str, Any]:
    """Return one compliance run plus redacted findings."""
    connector = connect_read_only if read_only else connect
    with connector(Path(root).resolve()) as connection:
        if run_id is None:
            row = connection.execute("SELECT * FROM architecture_compliance_runs ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = connection.execute("SELECT * FROM architecture_compliance_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return {"ok": False, "status": "missing", "run_id": run_id}
        result = dict(row)
        result["changed_files"] = json.loads(result.pop("changed_files_json"))
        rows = connection.execute("SELECT section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash FROM architecture_compliance_findings WHERE run_id=? ORDER BY CASE severity WHEN 'block' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,section_id,finding_code,subject", (result["id"],)).fetchall()
        result["findings"] = []
        for finding_row in rows:
            item = dict(finding_row)
            item["expected"] = json.loads(item.pop("expected_json"))
            item["observed"] = json.loads(item.pop("observed_json"))
            item["evidence_paths"] = json.loads(item.pop("evidence_paths_json"))
            result["findings"].append(item)
    result["ok"] = result["status"] in {"pass", "warn", "not_evaluable"}
    result["enforced"] = result["status"] != "not_evaluable"
    return result


def architecture_compliance_findings_get(root: Path | str, *, run_id: int | None = None, severity: str | None = None) -> list[dict[str, Any]]:
    """Return findings from a selected/latest compliance run without mutation authority."""
    report = architecture_compliance_get(root, run_id=run_id, read_only=True)
    findings = list(report.get("findings") or [])
    if severity:
        if severity not in SEVERITIES:
            raise RuntimeError("invalid architecture compliance severity")
        findings = [item for item in findings if item["severity"] == severity]
    return findings


def architecture_compliance_status_get(root: Path | str) -> dict[str, Any]:
    """Return whether architecture compliance is enforceable and the latest result."""
    root_path = Path(root).resolve()
    with connect_read_only(root_path) as connection:
        baseline = _active_baseline(connection)
        latest = connection.execute("SELECT id,status,blocking_count,warning_count,baseline_hash,scan_hash,created_at FROM architecture_compliance_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "ok": True,
        "enforced": baseline is not None,
        "active_baseline": baseline,
        "latest": dict(latest) if latest else None,
        "authority": "human_activated_architecture_contract",
        "waiver_authority_exposed": False,
        "approval_authority_exposed": False,
    }
