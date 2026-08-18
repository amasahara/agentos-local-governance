"""Path: .agents/agentos/architecture_quality.py
Purpose: Enforce human-approved quality, security, and operational architecture contracts for AgentOS v0.26.3.
Responsibilities:
    - Materialize schema 57 quality/operational enforcement runs and findings.
    - Enforce explicit machine-readable rules for ARCH-15..ARCH-21.
    - Check prospective plan declarations and changed-source evidence without executing project code.
    - Keep Architecture Authority human-owned; never approve, waive, activate, or mutate architecture.
"""
from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Iterable

from .db import connect, connect_read_only

MIGRATION_VERSION = 57
QUALITY_ENGINE_VERSION = 1
QUALITY_SECTIONS = ("ARCH-15", "ARCH-16", "ARCH-17", "ARCH-18", "ARCH-19", "ARCH-20", "ARCH-21")
SEVERITIES = {"info", "warn", "block"}
_SENSITIVE_RE = re.compile(r"(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|credential)", re.I)
_DOCKER_FROM_RE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", re.I | re.M)
_DOCKER_USER_RE = re.compile(r"^\s*USER\s+([^\s#]+)", re.I | re.M)
_PRIVILEGED_RE = re.compile(r"(?:--privileged\b|\bprivileged\s*:\s*true\b)", re.I)


def migration_57(connection: Any) -> None:
    """Create additive quality/operational enforcement state for schema 57."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_quality_runs(
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
            fact_count INTEGER NOT NULL DEFAULT 0,
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
        CREATE INDEX IF NOT EXISTS idx_arch_quality_task
            ON architecture_quality_runs(task_id,id);
        CREATE INDEX IF NOT EXISTS idx_arch_quality_baseline
            ON architecture_quality_runs(baseline_id,id);
        CREATE TABLE IF NOT EXISTS architecture_quality_findings(
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
            FOREIGN KEY(run_id) REFERENCES architecture_quality_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arch_quality_findings_run
            ON architecture_quality_findings(run_id,severity,section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_quality_findings_code
            ON architecture_quality_findings(finding_code,severity);
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


def _strings(value: Any, *, field: str | None = None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        if field:
            raise RuntimeError(f"{field}_must_be_list")
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if not text:
            if field:
                raise RuntimeError(f"{field}_must_contain_nonempty_strings")
            continue
        if text not in out:
            out.append(text)
    return out


def _matches(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, str(pattern)) for pattern in patterns)


def _matches_any(values: Iterable[str], pattern: str) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for value in values)


def _safe_file(root: Path, rel: str) -> Path | None:
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.is_file() or candidate.is_symlink():
        return None
    return candidate


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
            "payload": payload if isinstance(payload, dict) else {},
        }
    return result


def _finding(section_id: str, code: str, severity: str, subject: str, expected: Any, observed: Any, evidence_paths: Iterable[str] = ()) -> dict[str, Any]:
    if severity not in SEVERITIES:
        raise RuntimeError(f"invalid_quality_severity:{severity}")
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


def _call_name(node: ast.Call) -> str:
    def dotted(value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            base = dotted(value.value)
            return f"{base}.{value.attr}" if base else value.attr
        return ""
    return dotted(node.func)


def _expr_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _is_true(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_false(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _handler_is_broad(handler: ast.ExceptHandler) -> bool:
    value = handler.type
    if value is None:
        return False
    if isinstance(value, ast.Name):
        return value.id in {"Exception", "BaseException"}
    if isinstance(value, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id in {"Exception", "BaseException"} for item in value.elts)
    return False


def _python_facts(root: Path, rel: str) -> dict[str, Any] | None:
    path = _safe_file(root, rel)
    if path is None or path.suffix.lower() != ".py":
        return None
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeError, SyntaxError):
        return {
            "path": rel, "kind": "python", "parse_error": True, "calls": [], "logging_calls": [],
            "sensitive_log_arguments": [], "bare_except": 0, "broad_except": 0, "shell_true_calls": [],
            "tls_verify_false_calls": [], "secret_literals": [], "async_calls": [], "line_count": 0,
            "container_base_images": [], "container_users": [], "privileged_container": False,
        }
    calls: set[str] = set()
    logging_calls: set[str] = set()
    sensitive_logs: set[str] = set()
    shell_true: set[str] = set()
    verify_false: set[str] = set()
    secret_literals: set[str] = set()
    async_calls: set[str] = set()
    bare_except = 0
    broad_except = 0
    logging_leafs = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name:
                calls.add(name)
            leaf = name.rsplit(".", 1)[-1].lower() if name else ""
            if leaf in logging_leafs and (name.startswith("logging.") or "." in name):
                logging_calls.add(name)
                arg_text = " ".join(_expr_text(arg) for arg in node.args)
                if _SENSITIVE_RE.search(arg_text):
                    sensitive_logs.add(f"{name}:{arg_text[:160]}")
            for keyword in node.keywords:
                if keyword.arg == "shell" and _is_true(keyword.value):
                    shell_true.add(name or "<call>")
                if keyword.arg == "verify" and _is_false(keyword.value):
                    verify_false.add(name or "<call>")
        elif isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare_except += 1
            elif _handler_is_broad(node):
                broad_except += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value):
                continue
            targets: list[ast.AST] = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = _expr_text(target)
                if name and _SENSITIVE_RE.search(name):
                    secret_literals.add(name)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = _call_name(child)
                    if name:
                        async_calls.add(name)

    return {
        "path": rel,
        "kind": "python",
        "parse_error": False,
        "calls": sorted(calls),
        "logging_calls": sorted(logging_calls),
        "sensitive_log_arguments": sorted(sensitive_logs),
        "bare_except": bare_except,
        "broad_except": broad_except,
        "shell_true_calls": sorted(shell_true),
        "tls_verify_false_calls": sorted(verify_false),
        "secret_literals": sorted(secret_literals),
        "async_calls": sorted(async_calls),
        "line_count": len(text.splitlines()),
        "container_base_images": [],
        "container_users": [],
        "privileged_container": False,
    }


def _text_facts(root: Path, rel: str) -> dict[str, Any] | None:
    path = _safe_file(root, rel)
    if path is None:
        return None
    try:
        if path.stat().st_size > 2_000_000:
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    bases = sorted(set(match.group(1) for match in _DOCKER_FROM_RE.finditer(text)))
    users = sorted(set(match.group(1) for match in _DOCKER_USER_RE.finditer(text)))
    return {
        "path": rel,
        "kind": "text",
        "parse_error": False,
        "calls": [],
        "logging_calls": [],
        "sensitive_log_arguments": [],
        "bare_except": 0,
        "broad_except": 0,
        "shell_true_calls": [],
        "tls_verify_false_calls": [],
        "secret_literals": [],
        "async_calls": [],
        "line_count": len(text.splitlines()),
        "container_base_images": bases,
        "container_users": users,
        "privileged_container": bool(_PRIVILEGED_RE.search(text)),
    }


def _facts(root: Path, rel: str) -> dict[str, Any] | None:
    py = _python_facts(root, rel)
    return py if py is not None else _text_facts(root, rel)


def _rules(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = payload.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError(f"quality_contract_{key}_must_be_list")
    return [item for item in raw if isinstance(item, dict)]


def _path_rule_applies(rel: str, rule: dict[str, Any]) -> bool:
    patterns = _strings(rule.get("paths") or rule.get("path_patterns"))
    return not patterns or _matches(rel, patterns)


def _required_calls(findings: list[dict[str, Any]], section_id: str, payload: dict[str, Any], key: str, facts: dict[str, Any], code: str) -> None:
    rel = facts["path"]
    calls = facts.get("calls", [])
    for rule in _rules(payload, key):
        if not _path_rule_applies(rel, rule):
            continue
        required = _strings(rule.get("calls"))
        missing = [pattern for pattern in required if not _matches_any(calls, pattern)]
        if missing:
            findings.append(_finding(section_id, code, str(rule.get("severity") or "block"), rel, {"required_calls": required}, {"calls": calls, "missing": missing}, [rel]))


def _forbidden_calls(findings: list[dict[str, Any]], section_id: str, patterns: list[str], facts: dict[str, Any], code: str) -> None:
    if not patterns:
        return
    for call in facts.get("calls", []):
        if _matches(call, patterns):
            findings.append(_finding(section_id, code, "block", call, {"forbidden_calls": patterns}, call, [facts["path"]]))


def _positive_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"{field}_must_be_positive_integer")
    return value


def _analyze_file_against_sections(facts: dict[str, Any], sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel = facts["path"]
    if facts.get("parse_error"):
        findings.append(_finding("ARCH-21", "architecture_quality_parse_error", "block", rel, "parseable_source", "parse_error", [rel]))
        return findings

    # ARCH-15 Logging
    p15 = sections.get("ARCH-15", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-15", _strings(p15.get("forbidden_logging_calls")), facts, "architecture_logging_call_forbidden")
    _required_calls(findings, "ARCH-15", p15, "required_logging_calls_by_path", facts, "architecture_logging_required_call_missing")
    if p15.get("forbid_sensitive_log_arguments") is True:
        for item in facts.get("sensitive_log_arguments", []):
            findings.append(_finding("ARCH-15", "architecture_sensitive_logging_forbidden", "block", rel, "no_sensitive_log_arguments", item, [rel]))

    # ARCH-16 Error handling
    p16 = sections.get("ARCH-16", {}).get("payload", {})
    if p16.get("forbid_bare_except") is True and facts.get("bare_except", 0):
        findings.append(_finding("ARCH-16", "architecture_bare_except_forbidden", "block", rel, 0, facts.get("bare_except"), [rel]))
    if p16.get("forbid_broad_exception_catch") is True and facts.get("broad_except", 0):
        findings.append(_finding("ARCH-16", "architecture_broad_exception_catch_forbidden", "block", rel, 0, facts.get("broad_except"), [rel]))
    _forbidden_calls(findings, "ARCH-16", _strings(p16.get("forbidden_error_calls")), facts, "architecture_error_call_forbidden")
    _required_calls(findings, "ARCH-16", p16, "required_error_calls_by_path", facts, "architecture_error_handler_required_call_missing")

    # ARCH-17 Security
    p17 = sections.get("ARCH-17", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-17", _strings(p17.get("forbidden_call_patterns")), facts, "architecture_security_call_forbidden")
    _required_calls(findings, "ARCH-17", p17, "required_security_calls_by_path", facts, "architecture_security_guard_missing")
    if p17.get("forbid_shell_true") is True:
        for item in facts.get("shell_true_calls", []):
            findings.append(_finding("ARCH-17", "architecture_shell_true_forbidden", "block", item, "shell=false", True, [rel]))
    if p17.get("forbid_tls_verify_false") is True:
        for item in facts.get("tls_verify_false_calls", []):
            findings.append(_finding("ARCH-17", "architecture_tls_verify_false_forbidden", "block", item, "verify=true", False, [rel]))
    if p17.get("forbid_secret_literals") is True:
        for item in facts.get("secret_literals", []):
            findings.append(_finding("ARCH-17", "architecture_secret_literal_forbidden", "block", item, "secret_resolver_reference", "literal_assignment", [rel]))

    # ARCH-18 Performance
    p18 = sections.get("ARCH-18", {}).get("payload", {})
    max_lines = _positive_int(p18.get("max_python_file_lines"), field="ARCH-18.max_python_file_lines")
    if max_lines and facts.get("kind") == "python" and int(facts.get("line_count", 0)) > max_lines:
        findings.append(_finding("ARCH-18", "architecture_performance_file_size_budget_exceeded", "block", rel, {"max_python_file_lines": max_lines}, {"line_count": facts.get("line_count")}, [rel]))
    blocking_patterns = _strings(p18.get("forbidden_blocking_calls_in_async"))
    for call in facts.get("async_calls", []):
        if blocking_patterns and _matches(call, blocking_patterns):
            findings.append(_finding("ARCH-18", "architecture_async_blocking_call_forbidden", "block", call, {"forbidden_blocking_calls_in_async": blocking_patterns}, call, [rel]))
    _required_calls(findings, "ARCH-18", p18, "required_performance_calls_by_path", facts, "architecture_performance_guard_missing")

    # ARCH-19 Scalability
    p19 = sections.get("ARCH-19", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-19", _strings(p19.get("forbidden_scalability_calls")), facts, "architecture_scalability_call_forbidden")
    _required_calls(findings, "ARCH-19", p19, "required_scalability_calls_by_path", facts, "architecture_scalability_guard_missing")

    # ARCH-20 Deployment
    p20 = sections.get("ARCH-20", {}).get("payload", {})
    # Path-level deployment restrictions are evaluated once by the target gate.
    allowed_images = _strings(p20.get("allowed_container_base_images"))
    forbidden_images = _strings(p20.get("forbidden_container_base_images"))
    for image in facts.get("container_base_images", []):
        if forbidden_images and _matches(image, forbidden_images):
            findings.append(_finding("ARCH-20", "architecture_container_base_image_forbidden", "block", image, {"forbidden_container_base_images": forbidden_images}, image, [rel]))
        elif allowed_images and not _matches(image, allowed_images):
            findings.append(_finding("ARCH-20", "architecture_container_base_image_unapproved", "block", image, {"allowed_container_base_images": allowed_images}, image, [rel]))
    if p20.get("require_non_root_container_user") is True and facts.get("container_base_images"):
        users = [str(item).lower() for item in facts.get("container_users", [])]
        if not users or any(user in {"root", "0", "0:0"} for user in users):
            findings.append(_finding("ARCH-20", "architecture_container_non_root_user_required", "block", rel, "non-root USER", users or "missing", [rel]))
    if p20.get("forbid_privileged_container") is True and facts.get("privileged_container"):
        findings.append(_finding("ARCH-20", "architecture_privileged_container_forbidden", "block", rel, False, True, [rel]))

    # ARCH-21 per-file testing rules
    p21 = sections.get("ARCH-21", {}).get("payload", {})
    forbidden_test_paths = _strings(p21.get("forbidden_test_paths"))
    if forbidden_test_paths and _matches(rel, forbidden_test_paths):
        findings.append(_finding("ARCH-21", "architecture_test_path_forbidden", "block", rel, {"forbidden_test_paths": forbidden_test_paths}, rel, [rel]))
    return findings


def _aggregate_test_findings(files: list[str], sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    payload = sections.get("ARCH-21", {}).get("payload", {})
    for rule in _rules(payload, "required_test_changes_by_source"):
        source_patterns = _strings(rule.get("source_paths"))
        test_patterns = _strings(rule.get("test_paths"))
        matched_sources = [rel for rel in files if source_patterns and _matches(rel, source_patterns)]
        if not matched_sources:
            continue
        matched_tests = [rel for rel in files if test_patterns and _matches(rel, test_patterns)]
        if not matched_tests:
            findings.append(_finding(
                "ARCH-21",
                "architecture_required_test_change_missing",
                str(rule.get("severity") or "block"),
                ",".join(matched_sources),
                {"test_paths": test_patterns},
                {"changed_files": files, "matched_sources": matched_sources},
                matched_sources,
            ))
    minimum = _positive_int(payload.get("minimum_changed_test_files"), field="ARCH-21.minimum_changed_test_files")
    if minimum:
        test_patterns = _strings(payload.get("test_file_patterns")) or ["tests/*", "tests/**", "test_*.py", "**/test_*.py", "**/*.test.*", "**/*.spec.*"]
        count = sum(1 for rel in files if _matches(rel, test_patterns))
        if count < minimum:
            findings.append(_finding("ARCH-21", "architecture_minimum_test_changes_not_met", "block", "changed_test_files", {"minimum": minimum, "patterns": test_patterns}, count, files))
    return findings


def analyze_plan_quality_on_connection(connection: Any, plan: dict[str, Any], sections: dict[str, dict[str, Any]], affected_sections: Iterable[str]) -> dict[str, Any]:
    """Require explicit quality/operational declarations for affected ARCH-15..21 sections."""
    del connection
    relevant = sorted(set(str(item) for item in affected_sections) & set(QUALITY_SECTIONS))
    fields = {
        "ARCH-15": "expected_logging_changes",
        "ARCH-16": "expected_error_handling_changes",
        "ARCH-17": "expected_security_changes",
        "ARCH-18": "expected_performance_impacts",
        "ARCH-19": "expected_scalability_impacts",
        "ARCH-20": "expected_deployment_changes",
        "ARCH-21": "expected_test_suites",
    }
    declarations: dict[str, list[str]] = {}
    blockers: list[dict[str, Any]] = []
    for section_id in relevant:
        field = fields[section_id]
        raw = plan.get(field)
        if section_id == "ARCH-21" and raw is None:
            raw = plan.get("tests")
        values = _strings(raw, field=field)
        declarations[field] = values
        section = sections.get(section_id, {})
        if section.get("applicability") == "not_applicable":
            continue
        if not values:
            blockers.append({"code": "architecture_quality_plan_declaration_required", "section_id": section_id, "field": field})
    return {"ready": not blockers, "blockers": blockers, "declarations": declarations, "enforced_sections": relevant}


def architecture_quality_target_check_from_sections(sections: dict[str, dict[str, Any]], target: str) -> dict[str, Any]:
    """Apply target-only quality/operational rules against already loaded sections."""
    rel = _normalize_path(target)
    p17 = sections.get("ARCH-17", {}).get("payload", {})
    forbidden_security_paths = _strings(p17.get("forbidden_security_paths"))
    if forbidden_security_paths and _matches(rel, forbidden_security_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_security_path_forbidden", "section_id": "ARCH-17", "target": rel, "expected": {"forbidden_security_paths": forbidden_security_paths}}
    p20 = sections.get("ARCH-20", {}).get("payload", {})
    forbidden_deployment_paths = _strings(p20.get("forbidden_deployment_paths"))
    if forbidden_deployment_paths and _matches(rel, forbidden_deployment_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_deployment_path_forbidden", "section_id": "ARCH-20", "target": rel, "expected": {"forbidden_deployment_paths": forbidden_deployment_paths}}
    return {"allowed": True, "enforced": True, "reason": "architecture_quality_target_allowed", "section_id": None, "target": rel}


def architecture_quality_target_check(root: Path | str, target: str) -> dict[str, Any]:
    """Apply target-only quality/operational boundary rules before a write."""
    root = Path(root).resolve()
    rel = _normalize_path(target)
    with connect_read_only(root) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            return {"allowed": True, "enforced": False, "reason": "architecture_quality_no_active_baseline", "target": rel}
        sections = _baseline_sections(connection, baseline["id"])
    return architecture_quality_target_check_from_sections(sections, rel)


def architecture_quality_check(root: Path | str, *, task_id: str | None = None, plan_id: int | None = None, changed_files: Iterable[str] = (), mode: str = "manual", created_by: str = "system:architecture-quality") -> dict[str, Any]:
    """Run deterministic quality/operational checks and persist findings."""
    root = Path(root).resolve()
    files = sorted({_normalize_path(item) for item in changed_files if str(item).strip()})
    with connect(root, immediate=True) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            payload = {"engine_version": QUALITY_ENGINE_VERSION, "mode": mode, "task_id": task_id, "plan_id": plan_id, "baseline_id": None, "baseline_hash": None, "changed_files": files, "status": "not_evaluable", "fact_count": 0, "findings": []}
            run_hash = _sha(payload)
            connection.execute(
                """INSERT OR IGNORE INTO architecture_quality_runs(
                   run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,fact_count,finding_count,warning_count,blocking_count,run_hash,created_by
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), QUALITY_ENGINE_VERSION, mode, task_id, plan_id, None, None, "not_evaluable", _canonical(files), 0, 0, 0, 0, run_hash, created_by),
            )
            row = connection.execute("SELECT id FROM architecture_quality_runs WHERE run_hash=?", (run_hash,)).fetchone()
            return {"ok": True, "enforced": False, "status": "not_evaluable", "run_id": int(row[0]), "findings": [], "fact_count": 0, "baseline": None}

        sections = _baseline_sections(connection, baseline["id"])
        findings: list[dict[str, Any]] = []
        facts_count = 0
        for rel in files:
            target = architecture_quality_target_check_from_sections(sections, rel)
            if not target.get("allowed", True):
                findings.append(_finding(str(target.get("section_id") or "ARCH-20"), str(target.get("reason") or "architecture_quality_target_blocked"), "block", rel, target.get("expected"), rel, [rel]))
            facts = _facts(root, rel)
            if facts is None:
                continue
            facts_count += 1
            findings.extend(_analyze_file_against_sections(facts, sections))
        findings.extend(_aggregate_test_findings(files, sections))
        blocking = sum(1 for item in findings if item["severity"] == "block")
        warnings = sum(1 for item in findings if item["severity"] == "warn")
        status = "block" if blocking else "warn" if warnings else "pass"
        run_payload = {"engine_version": QUALITY_ENGINE_VERSION, "mode": mode, "task_id": task_id, "plan_id": plan_id, "baseline_id": baseline["id"], "baseline_hash": baseline["baseline_hash"], "changed_files": files, "fact_count": facts_count, "status": status, "findings": [item["finding_hash"] for item in findings]}
        run_hash = _sha(run_payload)
        connection.execute(
            """INSERT OR IGNORE INTO architecture_quality_runs(
               run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,fact_count,finding_count,warning_count,blocking_count,run_hash,created_by
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), QUALITY_ENGINE_VERSION, mode, task_id, plan_id, baseline["id"], baseline["baseline_hash"], status, _canonical(files), facts_count, len(findings), warnings, blocking, run_hash, created_by),
        )
        row = connection.execute("SELECT id FROM architecture_quality_runs WHERE run_hash=?", (run_hash,)).fetchone()
        if not row:
            raise RuntimeError("architecture_quality_run_persist_failed")
        run_id = int(row[0])
        for item in findings:
            connection.execute(
                """INSERT OR IGNORE INTO architecture_quality_findings(
                   run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, item["section_id"], item["finding_code"], item["severity"], item["subject"], _canonical(item["expected"]), _canonical(item["observed"]), _canonical(item["evidence_paths"]), item["finding_hash"]),
            )
        return {"ok": blocking == 0, "enforced": True, "status": status, "run_id": run_id, "baseline": baseline, "fact_count": facts_count, "findings": findings, "blocking_count": blocking, "warning_count": warnings}


def architecture_quality_findings(root: Path | str, *, run_id: int | None = None, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Read persisted quality/operational findings without executing a new scan."""
    with connect_read_only(Path(root).resolve()) as connection:
        if run_id is None:
            if task_id:
                row = connection.execute("SELECT id FROM architecture_quality_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
            else:
                row = connection.execute("SELECT id FROM architecture_quality_runs ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return []
            run_id = int(row[0])
        rows = connection.execute(
            """SELECT id,run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash,created_at
               FROM architecture_quality_findings WHERE run_id=? ORDER BY id LIMIT ?""",
            (run_id, max(1, min(int(limit), 1000))),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("expected_json", "observed_json", "evidence_paths_json"):
                item[key[:-5]] = json.loads(item.pop(key))
            out.append(item)
        return out


def architecture_quality_status(root: Path | str) -> dict[str, Any]:
    """Read current v0.26.3 quality/operational status and authority invariants."""
    with connect_read_only(Path(root).resolve()) as connection:
        baseline = _active_baseline(connection)
        row = connection.execute("SELECT * FROM architecture_quality_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "ok": True,
        "version": "0.26.3",
        "schema": MIGRATION_VERSION,
        "engine_version": QUALITY_ENGINE_VERSION,
        "sections": list(QUALITY_SECTIONS),
        "active_baseline": baseline,
        "latest_run": dict(row) if row else None,
        "static_analysis_only": True,
        "project_code_execution": False,
        "network_access": False,
        "llm_quality_authority": False,
        "approval_authority_exposed": False,
        "waiver_authority_exposed": False,
        "automatic_architecture_mutation": False,
        "architecture_change_required_for_blocked_quality_rule": True,
    }
