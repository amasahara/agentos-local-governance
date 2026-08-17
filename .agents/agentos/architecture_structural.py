"""Path: .agents/agentos/architecture_structural.py
Purpose: Enforce human-approved structural architecture contracts for AgentOS v0.26.1.
Responsibilities:
    - Materialize schema 55 structural enforcement runs and findings.
    - Enforce explicit machine-readable rules for ARCH-02/03/04/05/12/22/23.
    - Check prospective plan structure before approval and changed source before precommit.
    - Keep all checks deterministic, local, static, and non-executing.
    - Never mutate, approve, waive, or activate Architecture Authority.
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
import tomllib
import uuid
from pathlib import Path
from typing import Any, Iterable

from .architecture_compliance import architecture_target_check_from_sections
from .db import connect, connect_read_only

MIGRATION_VERSION = 55
STRUCTURAL_ENGINE_VERSION = 1
STRUCTURAL_SECTIONS = ("ARCH-02", "ARCH-03", "ARCH-04", "ARCH-05", "ARCH-12", "ARCH-22", "ARCH-23")
SEVERITIES = {"info", "warn", "block"}
RUN_STATUSES = {"pass", "warn", "block", "not_evaluable"}
_DEPENDENCY_FILES = {
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.mod",
    "Cargo.toml",
}
_LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}

def migration_55(connection: Any) -> None:
    """Create structural enforcement state additively for schema 55."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_structural_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid TEXT NOT NULL UNIQUE,
            engine_version INTEGER NOT NULL,
            mode TEXT NOT NULL,
            task_id TEXT,
            plan_id INTEGER,
            baseline_id INTEGER,
            baseline_hash TEXT,
            status TEXT NOT NULL CHECK(status IN ('pass','warn','block','not_evaluable')),
            changed_files_json TEXT NOT NULL,
            finding_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            blocking_count INTEGER NOT NULL DEFAULT 0,
            run_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(plan_id) REFERENCES task_plans(id),
            FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id)
        );
        CREATE INDEX IF NOT EXISTS idx_arch_structural_task
            ON architecture_structural_runs(task_id,id);
        CREATE INDEX IF NOT EXISTS idx_arch_structural_baseline
            ON architecture_structural_runs(baseline_id,id);
        CREATE TABLE IF NOT EXISTS architecture_structural_findings(
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
            FOREIGN KEY(run_id) REFERENCES architecture_structural_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arch_structural_findings_run
            ON architecture_structural_findings(run_id,severity,section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_structural_findings_code
            ON architecture_structural_findings(finding_code,severity);
        """
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalize_path(value: str) -> str:
    text = str(value).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in out:
                out.append(text)
        return out
    return []


def _matches(value: str, patterns: Iterable[str]) -> bool:
    candidate = _normalize_path(value)
    return any(fnmatch.fnmatchcase(candidate, _normalize_path(pattern)) for pattern in patterns)


def _section_payload(sections: dict[str, dict[str, Any]], section_id: str) -> dict[str, Any]:
    value = sections.get(section_id, {}).get("payload", {})
    return value if isinstance(value, dict) else {}


def _active_baseline(connection: Any) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id,baseline_hash,baseline_version FROM architecture_baselines WHERE status='active' ORDER BY baseline_version DESC,id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "baseline_hash": str(row[1]), "baseline_version": int(row[2])}


def _baseline_sections(connection: Any, baseline_id: int) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """SELECT bs.section_id,sr.applicability,sr.section_hash,sr.contract_json
           FROM architecture_baseline_sections bs
           JOIN architecture_section_revisions sr ON sr.id=bs.section_revision_id
           WHERE bs.baseline_id=? ORDER BY bs.section_id""",
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
            "contract": contract if isinstance(contract, dict) else {},
            "payload": payload if isinstance(payload, dict) else {},
        }
    return result


def _finding(
    section_id: str,
    code: str,
    severity: str,
    subject: str,
    expected: Any,
    observed: Any,
    evidence_paths: Iterable[str] = (),
) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise RuntimeError(f"invalid_structural_severity:{severity}")
    item = {
        "section_id": section_id,
        "finding_code": code,
        "severity": severity,
        "subject": str(subject),
        "expected": expected,
        "observed": observed,
        "evidence_paths": sorted({_normalize_path(path) for path in evidence_paths if str(path).strip()}),
    }
    item["finding_hash"] = _sha(item)
    return item


def _edge_list(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("structural_dependency_edges_must_be_list")
    out: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError("structural_dependency_edges_must_contain_objects")
        source = str(item.get("from") or item.get("source") or "").strip()
        target = str(item.get("import") or item.get("to") or item.get("target") or "").strip()
        if not source or not target:
            raise RuntimeError("structural_dependency_edge_requires_from_and_import")
        normalized = {"from": source, "import": target}
        if normalized not in out:
            out.append(normalized)
    return out


def _edge_matches(edge: dict[str, str], rule: Any) -> bool:
    if not isinstance(rule, dict):
        return False
    source_rule = str(rule.get("from") or rule.get("source") or "*").strip() or "*"
    target_rule = str(rule.get("import") or rule.get("to") or rule.get("target") or "*").strip() or "*"
    return fnmatch.fnmatchcase(edge["from"], source_rule) and fnmatch.fnmatchcase(edge["import"], target_rule)


def _module_from_path(path: str) -> str:
    normalized = _normalize_path(path)
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    for prefix in ("src/", "lib/", "app/"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    if normalized.endswith("/__init__"):
        normalized = normalized[:-9]
    return normalized.replace("/", ".").strip(".")


def _language_for_path(path: str) -> str | None:
    return _LANGUAGE_BY_SUFFIX.get(Path(path).suffix.lower())


def _dependency_manifest(path: str) -> bool:
    name = Path(path).name
    return name in _DEPENDENCY_FILES or name.startswith("requirements") and name.endswith(".txt")


def _safe_file(root: Path, rel: str) -> Path | None:
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.is_file() or candidate.is_symlink():
        return None
    return candidate


def _python_file_facts(root: Path, rel: str) -> dict[str, Any] | None:
    path = _safe_file(root, rel)
    if path is None or path.suffix.lower() != ".py":
        return None
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeError, SyntaxError):
        return {"path": rel, "parse_error": True, "imports": [], "wildcard_imports": [], "public_missing_docstrings": [], "line_count": 0, "header": []}
    imports: list[str] = []
    wildcard: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.append(module)
            if any(alias.name == "*" for alias in node.names):
                wildcard.append(module)
    missing_docstrings: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
            if ast.get_docstring(node, clean=False) is None:
                missing_docstrings.append(node.name)
    return {
        "path": rel,
        "parse_error": False,
        "imports": sorted({item for item in imports if item}),
        "wildcard_imports": sorted({item for item in wildcard if item}),
        "public_missing_docstrings": sorted(missing_docstrings),
        "line_count": len(text.splitlines()),
        "header": text.splitlines()[:20],
    }


def _manifest_dependencies(root: Path, rel: str) -> set[str]:
    path = _safe_file(root, rel)
    if path is None:
        return set()
    name = path.name
    result: set[str] = set()
    try:
        if name.startswith("requirements") and name.endswith(".txt"):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or line.startswith(("-", "git+", "http://", "https://")):
                    continue
                token = re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0].strip()
                if token:
                    result.add(token)
        elif name == "pyproject.toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            project = data.get("project") if isinstance(data, dict) else {}
            for item in (project or {}).get("dependencies", []) if isinstance(project, dict) else []:
                token = re.split(r"[<>=!~\[;\s]", str(item), maxsplit=1)[0].strip()
                if token:
                    result.add(token)
            poetry = ((data.get("tool") or {}).get("poetry") or {}).get("dependencies", {}) if isinstance(data, dict) else {}
            if isinstance(poetry, dict):
                result.update(str(key) for key in poetry if str(key).lower() != "python")
        elif name == "package.json":
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                value = data.get(key, {}) if isinstance(data, dict) else {}
                if isinstance(value, dict):
                    result.update(str(item) for item in value)
        elif name == "go.mod":
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("require "):
                    parts = stripped.split()
                    if len(parts) >= 2:
                        result.add(parts[1])
        elif name == "Cargo.toml":
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                value = data.get(key, {}) if isinstance(data, dict) else {}
                if isinstance(value, dict):
                    result.update(str(item) for item in value)
    except (OSError, UnicodeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return set()
    return result


def _target_structural_check_from_sections(sections: dict[str, dict[str, Any]], target: str) -> dict[str, Any]:
    path = _normalize_path(target)
    base = architecture_target_check_from_sections(sections, path)
    if not base.get("allowed", True):
        return base

    p4 = _section_payload(sections, "ARCH-04")
    forbidden_components = _strings(p4.get("forbidden_component_paths"))
    allowed_components = _strings(p4.get("allowed_component_roots"))
    if forbidden_components and _matches(path, forbidden_components):
        return {"allowed": False, "reason": "architecture_forbidden_component_path", "section_id": "ARCH-04", "target": path, "expected": forbidden_components}
    if allowed_components:
        patterns = allowed_components + [item.rstrip("/") + "/**" for item in allowed_components]
        if not _matches(path, patterns):
            return {"allowed": False, "reason": "architecture_component_root_violation", "section_id": "ARCH-04", "target": path, "expected": allowed_components}

    p5 = _section_payload(sections, "ARCH-05")
    forbidden_names = set(_strings(p5.get("forbidden_module_names")))
    if Path(path).name in forbidden_names:
        return {"allowed": False, "reason": "architecture_forbidden_module_name", "section_id": "ARCH-05", "target": path, "expected": sorted(forbidden_names)}
    location_rules = p5.get("module_location_rules")
    if isinstance(location_rules, list):
        for rule in location_rules:
            if not isinstance(rule, dict):
                continue
            match = str(rule.get("match") or "").strip()
            allowed_paths = _strings(rule.get("allowed_paths") or rule.get("allowed"))
            if match and (fnmatch.fnmatchcase(path, match) or fnmatch.fnmatchcase(Path(path).name, match)):
                if allowed_paths and not _matches(path, allowed_paths):
                    return {"allowed": False, "reason": "architecture_module_location_violation", "section_id": "ARCH-05", "target": path, "expected": allowed_paths}

    p22 = _section_payload(sections, "ARCH-22")
    forbidden_files = set(_strings(p22.get("forbidden_file_names")))
    if Path(path).name in forbidden_files:
        return {"allowed": False, "reason": "architecture_forbidden_file_name", "section_id": "ARCH-22", "target": path, "expected": sorted(forbidden_files)}

    p23 = _section_payload(sections, "ARCH-23")
    forbidden_artifacts = _strings(p23.get("forbidden_artifacts"))
    if forbidden_artifacts and _matches(path, forbidden_artifacts):
        return {"allowed": False, "reason": "architecture_forbidden_design_artifact", "section_id": "ARCH-23", "target": path, "expected": forbidden_artifacts}

    return {"allowed": True, "reason": "architecture_structural_target_allowed", "section_id": None, "target": path}


def architecture_structural_target_check(root: Path | str, target: str) -> dict[str, Any]:
    """Check one write target against structural contract without mutation."""
    root_path = Path(root).resolve()
    with connect_read_only(root_path) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            return {"allowed": True, "enforced": False, "reason": "architecture_not_evaluable_no_active_baseline", "target": _normalize_path(target)}
        sections = _baseline_sections(connection, baseline["id"])
    result = _target_structural_check_from_sections(sections, target)
    result.update({"enforced": True, "baseline_id": baseline["id"], "baseline_hash": baseline["baseline_hash"]})
    return result


def _edge_findings(sections: dict[str, dict[str, Any]], edges: list[dict[str, str]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for section_id in ("ARCH-04", "ARCH-12", "ARCH-23"):
        payload = _section_payload(sections, section_id)
        forbidden_key = "forbidden_component_edges" if section_id == "ARCH-04" else "forbidden_import_edges"
        forbidden = payload.get(forbidden_key)
        if isinstance(forbidden, list):
            for edge in edges:
                for rule in forbidden:
                    if _edge_matches(edge, rule):
                        findings.append(_finding(section_id, "architecture_forbidden_structural_edge", "block", f"{edge['from']}->{edge['import']}", rule, edge))
                        break
        if section_id == "ARCH-12":
            forbidden_imports = _strings(payload.get("forbidden_imports"))
            allowed_edges = payload.get("allowed_import_edges")
            for edge in edges:
                if forbidden_imports and any(fnmatch.fnmatchcase(edge["import"], rule) for rule in forbidden_imports):
                    findings.append(_finding(section_id, "architecture_forbidden_import", "block", edge["import"], forbidden_imports, edge))
                if isinstance(allowed_edges, list) and allowed_edges and not any(_edge_matches(edge, rule) for rule in allowed_edges):
                    findings.append(_finding(section_id, "architecture_unapproved_dependency_edge", "block", f"{edge['from']}->{edge['import']}", allowed_edges, edge))
    dedup = {item["finding_hash"]: item for item in findings}
    return list(dedup.values())


def _normalize_dependency(value: str) -> str:
    """Normalize dependency identity for deterministic contract comparison."""
    return str(value).strip().lower().replace("_", "-")


def _tech_findings(sections: dict[str, dict[str, Any]], languages: Iterable[str], dependencies: Iterable[str]) -> list[dict[str, Any]]:
    payload = _section_payload(sections, "ARCH-02")
    observed_languages = {str(item).lower() for item in languages if str(item).strip()}
    observed_dependencies = {_normalize_dependency(str(item)) for item in dependencies if str(item).strip()}
    allowed_languages = {item.lower() for item in _strings(payload.get("allowed_languages"))}
    forbidden_languages = {item.lower() for item in _strings(payload.get("forbidden_languages"))}
    allowed_dependencies = {_normalize_dependency(item) for item in _strings(payload.get("allowed_dependencies"))}
    forbidden_dependencies = {_normalize_dependency(item) for item in _strings(payload.get("forbidden_dependencies"))}
    findings: list[dict[str, Any]] = []
    if allowed_languages:
        for item in sorted(observed_languages - allowed_languages):
            findings.append(_finding("ARCH-02", "architecture_unapproved_language", "block", item, sorted(allowed_languages), item))
    for item in sorted(observed_languages & forbidden_languages):
        findings.append(_finding("ARCH-02", "architecture_forbidden_language", "block", item, sorted(forbidden_languages), item))
    if allowed_dependencies:
        for item in sorted(observed_dependencies - allowed_dependencies):
            findings.append(_finding("ARCH-02", "architecture_unapproved_dependency", "block", item, sorted(allowed_dependencies), item))
    for item in sorted(observed_dependencies & forbidden_dependencies):
        findings.append(_finding("ARCH-02", "architecture_forbidden_dependency", "block", item, sorted(forbidden_dependencies), item))
    return findings


def _coding_findings(root: Path, sections: dict[str, dict[str, Any]], changed_files: list[str]) -> list[dict[str, Any]]:
    payload = _section_payload(sections, "ARCH-22")
    require_path_header = bool(payload.get("require_file_header_path", False))
    require_module_purpose = bool(payload.get("require_module_purpose", False))
    require_docstrings = bool(payload.get("require_public_symbol_docstrings", False))
    forbid_wildcard = bool(payload.get("forbid_wildcard_imports", False))
    max_lines_raw = payload.get("max_module_lines")
    max_lines = int(max_lines_raw) if isinstance(max_lines_raw, int) and max_lines_raw > 0 else None
    findings: list[dict[str, Any]] = []
    for rel in changed_files:
        facts = _python_file_facts(root, rel)
        if not facts:
            continue
        if facts["parse_error"]:
            findings.append(_finding("ARCH-22", "architecture_python_parse_error", "block", rel, "parseable Python module", "parse_error", [rel]))
            continue
        header_text = "\n".join(facts["header"])
        if require_path_header and not re.search(r"(?im)^\s*(?:#|\"\"\"|''')?\s*(?:Path|File|Đường dẫn)\s*:", header_text):
            findings.append(_finding("ARCH-22", "architecture_file_header_path_missing", "block", rel, "file header path declaration", "missing", [rel]))
        if require_module_purpose and not re.search(r"(?im)^\s*(?:#|\"\"\"|''')?\s*(?:Purpose|Mục đích(?: module)?)\s*:", header_text):
            findings.append(_finding("ARCH-22", "architecture_module_purpose_missing", "block", rel, "module purpose declaration", "missing", [rel]))
        if require_docstrings:
            for symbol in facts["public_missing_docstrings"]:
                findings.append(_finding("ARCH-22", "architecture_public_symbol_docstring_missing", "block", f"{rel}:{symbol}", "public symbol docstring", "missing", [rel]))
        if forbid_wildcard:
            for module in facts["wildcard_imports"]:
                findings.append(_finding("ARCH-22", "architecture_wildcard_import_forbidden", "block", f"{rel}:{module}", "no wildcard imports", module, [rel]))
        if max_lines is not None and facts["line_count"] > max_lines:
            findings.append(_finding("ARCH-22", "architecture_module_too_large", "block", rel, {"max_module_lines": max_lines}, facts["line_count"], [rel]))
    return findings


def _design_artifact_findings(root: Path, sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    payload = _section_payload(sections, "ARCH-23")
    required = _strings(payload.get("required_artifacts"))
    findings: list[dict[str, Any]] = []
    for pattern in required:
        matches = [path for path in root.glob(pattern) if path.is_file() and not path.is_symlink()]
        if not matches:
            findings.append(_finding("ARCH-23", "architecture_required_design_artifact_missing", "block", pattern, pattern, "missing"))
    return findings


def _repository_edges(root: Path, changed_files: list[str]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for rel in changed_files:
        facts = _python_file_facts(root, rel)
        if not facts or facts["parse_error"]:
            continue
        source = _module_from_path(rel)
        for imported in facts["imports"]:
            edge = {"from": source, "import": imported}
            if edge not in edges:
                edges.append(edge)
    return edges


def analyze_plan_structure_on_connection(
    connection: Any,
    plan: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    expected_files: list[str],
    expected_modules: list[str],
    expected_edges: list[dict[str, str]],
) -> dict[str, Any]:
    """Return structural blockers and normalized tech declarations for a prospective plan."""
    architecture = plan.get("architecture") or {}
    if not isinstance(architecture, dict):
        architecture = {}
    dependencies_present = "expected_dependencies" in plan or "expected_dependencies" in architecture
    expected_dependencies = _strings(plan.get("expected_dependencies", architecture.get("expected_dependencies")))
    expected_languages = [item.lower() for item in _strings(plan.get("expected_languages", architecture.get("expected_languages")))]
    inferred_languages = sorted({item for item in (_language_for_path(path) for path in expected_files) if item})
    all_languages = sorted(set(expected_languages) | set(inferred_languages))
    blockers: list[dict[str, Any]] = []
    if any(_dependency_manifest(path) for path in expected_files) and not dependencies_present:
        blockers.append({"code": "architecture_plan_expected_dependencies_declaration_required", "section_id": "ARCH-02"})
    for finding in _tech_findings(sections, all_languages, expected_dependencies):
        blockers.append({"code": finding["finding_code"], "section_id": finding["section_id"], "subject": finding["subject"], "expected": finding["expected"]})
    for path in expected_files:
        target = _target_structural_check_from_sections(sections, path)
        if not target.get("allowed", True):
            blockers.append({"code": target["reason"], "section_id": target.get("section_id"), "target": path, "expected": target.get("expected")})
    # The caller already canonicalizes modules, but enforce explicit module-name/location rules here as paths when possible.
    p5 = _section_payload(sections, "ARCH-05")
    forbidden_names = set(_strings(p5.get("forbidden_module_names")))
    for module in expected_modules:
        name = module.rsplit(".", 1)[-1] + ".py"
        if name in forbidden_names or module.rsplit(".", 1)[-1] in forbidden_names:
            blockers.append({"code": "architecture_forbidden_module_name", "section_id": "ARCH-05", "module": module, "expected": sorted(forbidden_names)})
    for finding in _edge_findings(sections, expected_edges):
        blockers.append({"code": finding["finding_code"], "section_id": finding["section_id"], "subject": finding["subject"], "expected": finding["expected"]})
    dedup: dict[str, dict[str, Any]] = {_sha(item): item for item in blockers}
    return {
        "expected_dependencies": expected_dependencies,
        "expected_languages": expected_languages,
        "inferred_languages": inferred_languages,
        "blockers": list(dedup.values()),
    }


def architecture_structural_check(
    root: Path | str,
    *,
    task_id: str | None = None,
    plan_id: int | None = None,
    changed_files: list[str] | None = None,
    mode: str = "manual",
    created_by: str = "system:architecture-structural",
) -> dict[str, Any]:
    """Run static structural enforcement and persist only findings/provenance, never raw source."""
    root_path = Path(root).resolve()
    changed = sorted({_normalize_path(item) for item in (changed_files or []) if str(item).strip()})
    with connect(root_path, immediate=True) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            payload = {
                "engine_version": STRUCTURAL_ENGINE_VERSION,
                "mode": mode,
                "task_id": task_id,
                "plan_id": plan_id,
                "baseline_id": None,
                "baseline_hash": None,
                "status": "not_evaluable",
                "changed_files": changed,
                "findings": [],
            }
            run_hash = _sha(payload)
            connection.execute(
                """INSERT OR IGNORE INTO architecture_structural_runs(
                   run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,
                   finding_count,warning_count,blocking_count,run_hash,created_by
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), STRUCTURAL_ENGINE_VERSION, mode, task_id, plan_id, None, None, "not_evaluable", _canonical(changed), 0, 0, 0, run_hash, created_by),
            )
            row = connection.execute("SELECT id FROM architecture_structural_runs WHERE run_hash=?", (run_hash,)).fetchone()
            return {"ok": True, "enforced": False, "status": "not_evaluable", "run_id": int(row[0]) if row else None, "baseline": None, "findings": [], "blocking_count": 0}
        sections = _baseline_sections(connection, baseline["id"])
        findings: list[dict[str, Any]] = []
        languages = sorted({item for item in (_language_for_path(path) for path in changed) if item})
        dependencies: set[str] = set()
        for rel in changed:
            target = _target_structural_check_from_sections(sections, rel)
            if not target.get("allowed", True):
                findings.append(_finding(str(target.get("section_id") or "ARCH-03"), str(target.get("reason") or "architecture_structural_target_blocked"), "block", rel, target.get("expected"), rel, [rel]))
            if _dependency_manifest(rel):
                dependencies.update(_manifest_dependencies(root_path, rel))
        findings.extend(_tech_findings(sections, languages, dependencies))
        findings.extend(_coding_findings(root_path, sections, changed))
        edges = _repository_edges(root_path, changed)
        findings.extend(_edge_findings(sections, edges))
        findings.extend(_design_artifact_findings(root_path, sections))
        dedup = {item["finding_hash"]: item for item in findings}
        findings = sorted(dedup.values(), key=lambda item: ({"block": 0, "warn": 1, "info": 2}[item["severity"]], item["section_id"], item["finding_code"], item["subject"]))
        blocking = sum(1 for item in findings if item["severity"] == "block")
        warning = sum(1 for item in findings if item["severity"] == "warn")
        status = "block" if blocking else "warn" if warning else "pass"
        payload = {
            "engine_version": STRUCTURAL_ENGINE_VERSION,
            "mode": mode,
            "task_id": task_id,
            "plan_id": plan_id,
            "baseline_id": baseline["id"],
            "baseline_hash": baseline["baseline_hash"],
            "status": status,
            "changed_files": changed,
            "findings": [{key: value for key, value in item.items() if key != "finding_hash"} for item in findings],
        }
        run_hash = _sha(payload)
        run_uuid = str(uuid.uuid4())
        connection.execute(
            """INSERT OR IGNORE INTO architecture_structural_runs(
               run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,
               finding_count,warning_count,blocking_count,run_hash,created_by
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_uuid, STRUCTURAL_ENGINE_VERSION, mode, task_id, plan_id, baseline["id"], baseline["baseline_hash"], status, _canonical(changed), len(findings), warning, blocking, run_hash, created_by),
        )
        row = connection.execute("SELECT id FROM architecture_structural_runs WHERE run_hash=?", (run_hash,)).fetchone()
        if not row:
            raise RuntimeError("architecture_structural_run_persist_failed")
        run_id = int(row[0])
        for item in findings:
            connection.execute(
                """INSERT OR IGNORE INTO architecture_structural_findings(
                   run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, item["section_id"], item["finding_code"], item["severity"], item["subject"], _canonical(item["expected"]), _canonical(item["observed"]), _canonical(item["evidence_paths"]), item["finding_hash"]),
            )
        return {
            "ok": blocking == 0,
            "enforced": True,
            "status": status,
            "run_id": run_id,
            "baseline": baseline,
            "changed_files": changed,
            "finding_count": len(findings),
            "warning_count": warning,
            "blocking_count": blocking,
            "findings": findings,
        }


def architecture_structural_findings(
    root: Path | str,
    *,
    run_id: int | None = None,
    task_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Read structural findings without mutation."""
    root_path = Path(root).resolve()
    with connect_read_only(root_path) as connection:
        selected_run = run_id
        if selected_run is None:
            if task_id:
                row = connection.execute("SELECT id FROM architecture_structural_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
            else:
                row = connection.execute("SELECT id FROM architecture_structural_runs ORDER BY id DESC LIMIT 1").fetchone()
            selected_run = int(row[0]) if row else None
        if selected_run is None:
            return {"ok": True, "run_id": None, "findings": []}
        rows = connection.execute(
            """SELECT id,run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash,created_at
               FROM architecture_structural_findings WHERE run_id=? ORDER BY id LIMIT ?""",
            (selected_run, max(1, min(int(limit), 1000))),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("expected_json", "observed_json", "evidence_paths_json"):
                item[key.removesuffix("_json")] = json.loads(item.pop(key))
            items.append(item)
        return {"ok": True, "run_id": selected_run, "findings": items}


def architecture_structural_status(root: Path | str) -> dict[str, Any]:
    """Read current structural enforcement status and authority boundaries."""
    root_path = Path(root).resolve()
    with connect_read_only(root_path) as connection:
        baseline = _active_baseline(connection)
        row = connection.execute("SELECT * FROM architecture_structural_runs ORDER BY id DESC LIMIT 1").fetchone()
        latest = dict(row) if row else None
        if latest:
            latest["changed_files"] = json.loads(latest.pop("changed_files_json"))
        return {
            "ok": True,
            "engine_version": STRUCTURAL_ENGINE_VERSION,
            "active_baseline": baseline,
            "enforced": baseline is not None,
            "sections": list(STRUCTURAL_SECTIONS),
            "latest": latest,
            "automatic_architecture_mutation": False,
            "architecture_change_required_for_blocked_structure": True,
            "approval_authority_exposed": False,
            "waiver_authority_exposed": False,
        }
