"""Path: .agents/agentos/architecture_runtime.py
Purpose: Enforce human-approved runtime/data/API/business architecture contracts for AgentOS v0.26.2.
Responsibilities:
    - Materialize schema 56 runtime-boundary enforcement runs and findings.
    - Enforce explicit machine-readable rules for ARCH-06/07/08/09/10/11/13/14.
    - Check prospective plan declarations before approval and changed source before precommit.
    - Extract bounded static facts without executing project code or using an LLM as authority.
    - Never mutate, approve, waive, or activate Architecture Authority.
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

MIGRATION_VERSION = 56
RUNTIME_ENGINE_VERSION = 1
RUNTIME_SECTIONS = (
    "ARCH-06", "ARCH-07", "ARCH-08", "ARCH-09",
    "ARCH-10", "ARCH-11", "ARCH-13", "ARCH-14",
)
SEVERITIES = {"info", "warn", "block"}
RUN_STATUSES = {"pass", "warn", "block", "not_evaluable"}
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
_URL_RE = re.compile(r"https?://[A-Za-z0-9._~%:-]+(?:/[A-Za-z0-9._~%!$&'()*+,;=:@/?#-]*)?")
_SQL_RE = re.compile(r"\b(select|insert|update|delete|merge|replace|create|alter|drop|truncate)\b(?:\s+into|\s+from|\s+table)?\s+([A-Za-z_][A-Za-z0-9_.$\[\]\"]*)?", re.I)
_SECRET_NAME_RE = re.compile(r"(?:secret|token|password|passwd|api[_-]?key|private[_-]?key|credential)", re.I)


def migration_56(connection: Any) -> None:
    """Create additive runtime-boundary enforcement state for schema 56."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_runtime_runs(
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
        CREATE INDEX IF NOT EXISTS idx_arch_runtime_task
            ON architecture_runtime_runs(task_id,id);
        CREATE INDEX IF NOT EXISTS idx_arch_runtime_baseline
            ON architecture_runtime_runs(baseline_id,id);
        CREATE TABLE IF NOT EXISTS architecture_runtime_findings(
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
            FOREIGN KEY(run_id) REFERENCES architecture_runtime_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_arch_runtime_findings_run
            ON architecture_runtime_findings(run_id,severity,section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_runtime_findings_code
            ON architecture_runtime_findings(finding_code,severity);
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
        raise RuntimeError(f"invalid_runtime_severity:{severity}")
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


def _string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _python_facts(root: Path, rel: str) -> dict[str, Any] | None:
    path = _safe_file(root, rel)
    if path is None or path.suffix.lower() != ".py":
        return None
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeError, SyntaxError):
        return {"path": rel, "parse_error": True, "calls": [], "urls": [], "env_keys": [], "sql": [], "routes": []}
    calls: set[str] = set()
    urls: set[str] = set(_URL_RE.findall(text))
    env_keys: set[str] = set()
    sql: list[dict[str, str]] = []
    routes: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name:
                calls.add(name)
            # os.getenv("KEY"), getenv("KEY")
            if name in {"os.getenv", "getenv"} and node.args:
                key = _string_constant(node.args[0])
                if key:
                    env_keys.add(key)
            # router.get("/path"), app.post("/path") and similar decorator/call forms.
            method = name.rsplit(".", 1)[-1].lower() if name else ""
            if method in _HTTP_METHODS and node.args:
                route = _string_constant(node.args[0])
                if route and route.startswith("/"):
                    routes.append({"method": method.upper(), "path": route})
        elif isinstance(node, ast.Subscript):
            # os.environ["KEY"]
            target = node.value
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "os" and target.attr == "environ":
                key = _string_constant(node.slice)
                if key:
                    env_keys.add(key)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            literal = node.value
            for match in _URL_RE.findall(literal):
                urls.add(match)
            for match in _SQL_RE.finditer(literal):
                sql.append({"operation": match.group(1).upper(), "object": (match.group(2) or "").strip('[]\"')})
    # Preserve deterministic order and deduplicate structured facts.
    sql_unique = {(_x["operation"], _x["object"]): _x for _x in sql}
    route_unique = {(_x["method"], _x["path"]): _x for _x in routes}
    return {
        "path": rel,
        "parse_error": False,
        "calls": sorted(calls),
        "urls": sorted(urls),
        "env_keys": sorted(env_keys),
        "sql": [sql_unique[k] for k in sorted(sql_unique)],
        "routes": [route_unique[k] for k in sorted(route_unique)],
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
    urls = sorted(set(_URL_RE.findall(text)))
    env_keys: set[str] = set()
    for pattern in (
        re.compile(r"\b(?:process\.env\.|Deno\.env\.get\([\"'])([A-Z][A-Z0-9_]*)"),
        re.compile(r"\b(?:ENV|ARG)\s+([A-Z][A-Z0-9_]*)\b"),
        re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}"),
    ):
        env_keys.update(match.group(1) for match in pattern.finditer(text))
    sql = []
    for match in _SQL_RE.finditer(text):
        sql.append({"operation": match.group(1).upper(), "object": (match.group(2) or "").strip('[]\"')})
    sql_unique = {(_x["operation"], _x["object"]): _x for _x in sql}
    return {
        "path": rel,
        "parse_error": False,
        "calls": [],
        "urls": urls,
        "env_keys": sorted(env_keys),
        "sql": [sql_unique[k] for k in sorted(sql_unique)],
        "routes": [],
    }


def _facts(root: Path, rel: str) -> dict[str, Any] | None:
    py = _python_facts(root, rel)
    return py if py is not None else _text_facts(root, rel)


def _rules(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = payload.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuntimeError(f"runtime_contract_{key}_must_be_list")
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


def _matches_any(values: Iterable[str], pattern: str) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for value in values)


def _forbidden_calls(findings: list[dict[str, Any]], section_id: str, payload: dict[str, Any], key: str, facts: dict[str, Any], code: str) -> None:
    patterns = _strings(payload.get(key))
    for call in facts.get("calls", []):
        if patterns and _matches(call, patterns):
            findings.append(_finding(section_id, code, "block", call, {"forbidden_calls": patterns}, call, [facts["path"]]))


def _host(url: str) -> str:
    value = url.split("://", 1)[-1].split("/", 1)[0]
    return value.rsplit("@", 1)[-1].split(":", 1)[0].lower()


def _analyze_file_against_sections(facts: dict[str, Any], sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    rel = facts["path"]
    if facts.get("parse_error"):
        findings.append(_finding("ARCH-06", "architecture_runtime_parse_error", "block", rel, "parseable_source", "parse_error", [rel]))
        return findings

    # ARCH-06 Request Flow
    p06 = sections.get("ARCH-06", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-06", p06, "forbidden_call_patterns", facts, "architecture_request_flow_forbidden_call")
    _required_calls(findings, "ARCH-06", p06, "required_calls_by_path", facts, "architecture_request_flow_required_call_missing")

    # ARCH-07 Authentication
    p07 = sections.get("ARCH-07", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-07", p07, "forbidden_auth_calls", facts, "architecture_authentication_forbidden_call")
    _required_calls(findings, "ARCH-07", p07, "required_auth_calls_by_path", facts, "architecture_authentication_guard_missing")

    # ARCH-08 Authorization
    p08 = sections.get("ARCH-08", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-08", p08, "forbidden_authorization_calls", facts, "architecture_authorization_forbidden_call")
    _required_calls(findings, "ARCH-08", p08, "required_authorization_calls_by_path", facts, "architecture_authorization_guard_missing")

    # ARCH-09 Database/Data boundary
    p09 = sections.get("ARCH-09", {}).get("payload", {})
    allowed_ops = {item.upper() for item in _strings(p09.get("allowed_sql_operations"))}
    forbidden_ops = {item.upper() for item in _strings(p09.get("forbidden_sql_operations"))}
    allowed_objects = _strings(p09.get("allowed_data_objects"))
    write_paths = _strings(p09.get("data_write_allowed_paths"))
    write_ops = {"INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE", "CREATE", "ALTER", "DROP", "TRUNCATE"}
    for item in facts.get("sql", []):
        op = str(item.get("operation") or "").upper()
        obj = str(item.get("object") or "")
        if op in forbidden_ops or (allowed_ops and op not in allowed_ops):
            findings.append(_finding("ARCH-09", "architecture_data_operation_forbidden", "block", f"{op}:{obj}", {"allowed": sorted(allowed_ops), "forbidden": sorted(forbidden_ops)}, item, [rel]))
        if obj and allowed_objects and not _matches(obj, allowed_objects):
            findings.append(_finding("ARCH-09", "architecture_data_object_forbidden", "block", obj, {"allowed_data_objects": allowed_objects}, item, [rel]))
        if op in write_ops and write_paths and not _matches(rel, write_paths):
            findings.append(_finding("ARCH-09", "architecture_data_write_boundary_violation", "block", rel, {"data_write_allowed_paths": write_paths}, item, [rel]))

    # ARCH-10 API architecture
    p10 = sections.get("ARCH-10", {}).get("payload", {})
    allowed_methods = {item.upper() for item in _strings(p10.get("allowed_http_methods"))}
    allowed_prefixes = _strings(p10.get("allowed_route_prefixes"))
    forbidden_routes = _strings(p10.get("forbidden_routes"))
    for route in facts.get("routes", []):
        method = str(route.get("method") or "").upper()
        path = str(route.get("path") or "")
        if allowed_methods and method not in allowed_methods:
            findings.append(_finding("ARCH-10", "architecture_api_method_forbidden", "block", f"{method} {path}", sorted(allowed_methods), route, [rel]))
        if allowed_prefixes and not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in allowed_prefixes):
            findings.append(_finding("ARCH-10", "architecture_api_route_outside_contract", "block", path, {"allowed_route_prefixes": allowed_prefixes}, route, [rel]))
        if forbidden_routes and _matches(path, forbidden_routes):
            findings.append(_finding("ARCH-10", "architecture_api_route_forbidden", "block", path, {"forbidden_routes": forbidden_routes}, route, [rel]))

    # ARCH-11 Business flow
    p11 = sections.get("ARCH-11", {}).get("payload", {})
    _forbidden_calls(findings, "ARCH-11", p11, "forbidden_business_calls", facts, "architecture_business_flow_forbidden_call")
    _required_calls(findings, "ARCH-11", p11, "required_business_guard_calls_by_path", facts, "architecture_business_flow_guard_missing")

    # ARCH-13 External services
    p13 = sections.get("ARCH-13", {}).get("payload", {})
    allowed_hosts = [item.lower() for item in _strings(p13.get("allowed_hosts"))]
    forbidden_hosts = [item.lower() for item in _strings(p13.get("forbidden_hosts"))]
    allowed_schemes = {item.lower() for item in _strings(p13.get("allowed_url_schemes"))}
    for url in facts.get("urls", []):
        host = _host(url)
        scheme = url.split(":", 1)[0].lower()
        if allowed_schemes and scheme not in allowed_schemes:
            findings.append(_finding("ARCH-13", "architecture_external_service_scheme_forbidden", "block", url, sorted(allowed_schemes), scheme, [rel]))
        if forbidden_hosts and _matches(host, forbidden_hosts):
            findings.append(_finding("ARCH-13", "architecture_external_service_forbidden", "block", host, {"forbidden_hosts": forbidden_hosts}, url, [rel]))
        elif allowed_hosts and not _matches(host, allowed_hosts):
            findings.append(_finding("ARCH-13", "architecture_external_service_unapproved", "block", host, {"allowed_hosts": allowed_hosts}, url, [rel]))

    # ARCH-14 Configuration / secret boundaries
    p14 = sections.get("ARCH-14", {}).get("payload", {})
    allowed_env = _strings(p14.get("allowed_env_vars"))
    forbidden_env = _strings(p14.get("forbidden_env_vars"))
    secret_env = _strings(p14.get("secret_env_vars"))
    secret_allowed_paths = _strings(p14.get("secret_access_allowed_paths"))
    for key in facts.get("env_keys", []):
        if forbidden_env and _matches(key, forbidden_env):
            findings.append(_finding("ARCH-14", "architecture_config_env_forbidden", "block", key, {"forbidden_env_vars": forbidden_env}, key, [rel]))
        elif allowed_env and not _matches(key, allowed_env):
            findings.append(_finding("ARCH-14", "architecture_config_env_unapproved", "block", key, {"allowed_env_vars": allowed_env}, key, [rel]))
        is_secret = (secret_env and _matches(key, secret_env)) or (not secret_env and bool(_SECRET_NAME_RE.search(key)))
        if is_secret and secret_allowed_paths and not _matches(rel, secret_allowed_paths):
            findings.append(_finding("ARCH-14", "architecture_secret_access_boundary_violation", "block", key, {"secret_access_allowed_paths": secret_allowed_paths}, {"path": rel, "env_key": key}, [rel]))

    return findings


def _plan_list(plan: dict[str, Any], name: str) -> list[Any]:
    value = plan.get(name)
    if value is None:
        architecture = plan.get("architecture") if isinstance(plan.get("architecture"), dict) else {}
        value = architecture.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{name}_must_be_list")
    return value


def analyze_plan_runtime_on_connection(connection: Any, plan: dict[str, Any], sections: dict[str, dict[str, Any]], affected_sections: Iterable[str]) -> dict[str, Any]:
    """Validate declared runtime/data/API/business effects before plan persistence."""
    affected = set(affected_sections)
    relevant = affected & set(RUNTIME_SECTIONS)
    if not relevant:
        return {"ready": True, "blockers": [], "declarations": {}, "enforced_sections": []}
    blockers: list[dict[str, Any]] = []
    declarations = {
        "expected_runtime_calls": _strings(_plan_list(plan, "expected_runtime_calls"), field="expected_runtime_calls"),
        "expected_data_operations": _plan_list(plan, "expected_data_operations"),
        "expected_api_routes": _plan_list(plan, "expected_api_routes"),
        "expected_external_services": _strings(_plan_list(plan, "expected_external_services"), field="expected_external_services"),
        "expected_config_keys": _strings(_plan_list(plan, "expected_config_keys"), field="expected_config_keys"),
        "expected_business_calls": _strings(_plan_list(plan, "expected_business_calls"), field="expected_business_calls"),
    }
    # Require explicit declarations only for affected boundary families, even if empty.
    required_fields = {
        "ARCH-06": "expected_runtime_calls",
        "ARCH-07": "expected_runtime_calls",
        "ARCH-08": "expected_runtime_calls",
        "ARCH-09": "expected_data_operations",
        "ARCH-10": "expected_api_routes",
        "ARCH-11": "expected_business_calls",
        "ARCH-13": "expected_external_services",
        "ARCH-14": "expected_config_keys",
    }
    architecture = plan.get("architecture") if isinstance(plan.get("architecture"), dict) else {}
    for section_id in sorted(relevant):
        field = required_fields[section_id]
        if field not in plan and field not in architecture:
            blockers.append({"code": "architecture_runtime_plan_declaration_required", "section_id": section_id, "field": field})

    p06 = sections.get("ARCH-06", {}).get("payload", {})
    p07 = sections.get("ARCH-07", {}).get("payload", {})
    p08 = sections.get("ARCH-08", {}).get("payload", {})
    p11 = sections.get("ARCH-11", {}).get("payload", {})
    call_patterns = [
        ("ARCH-06", "forbidden_call_patterns", p06),
        ("ARCH-07", "forbidden_auth_calls", p07),
        ("ARCH-08", "forbidden_authorization_calls", p08),
        ("ARCH-11", "forbidden_business_calls", p11),
    ]
    all_calls = [*declarations["expected_runtime_calls"], *declarations["expected_business_calls"]]
    for section_id, key, payload in call_patterns:
        if section_id not in relevant:
            continue
        forbidden = _strings(payload.get(key))
        for call in all_calls:
            if forbidden and _matches(call, forbidden):
                blockers.append({"code": "architecture_runtime_plan_forbidden_call", "section_id": section_id, "call": call, "rule": key})

    if "ARCH-09" in relevant:
        p09 = sections.get("ARCH-09", {}).get("payload", {})
        allowed_ops = {item.upper() for item in _strings(p09.get("allowed_sql_operations"))}
        forbidden_ops = {item.upper() for item in _strings(p09.get("forbidden_sql_operations"))}
        allowed_objects = _strings(p09.get("allowed_data_objects"))
        for raw in declarations["expected_data_operations"]:
            if not isinstance(raw, dict):
                blockers.append({"code": "architecture_runtime_plan_data_operation_invalid", "section_id": "ARCH-09", "observed": raw})
                continue
            op = str(raw.get("operation") or "").upper()
            obj = str(raw.get("object") or raw.get("table") or "")
            if not op:
                blockers.append({"code": "architecture_runtime_plan_data_operation_invalid", "section_id": "ARCH-09", "observed": raw})
                continue
            if op in forbidden_ops or (allowed_ops and op not in allowed_ops):
                blockers.append({"code": "architecture_runtime_plan_data_operation_forbidden", "section_id": "ARCH-09", "operation": raw})
            if obj and allowed_objects and not _matches(obj, allowed_objects):
                blockers.append({"code": "architecture_runtime_plan_data_object_forbidden", "section_id": "ARCH-09", "operation": raw})

    if "ARCH-10" in relevant:
        p10 = sections.get("ARCH-10", {}).get("payload", {})
        allowed_methods = {item.upper() for item in _strings(p10.get("allowed_http_methods"))}
        prefixes = _strings(p10.get("allowed_route_prefixes"))
        forbidden_routes = _strings(p10.get("forbidden_routes"))
        for raw in declarations["expected_api_routes"]:
            if not isinstance(raw, dict):
                blockers.append({"code": "architecture_runtime_plan_api_route_invalid", "section_id": "ARCH-10", "observed": raw})
                continue
            method = str(raw.get("method") or "").upper()
            path = str(raw.get("path") or "")
            if not method or not path.startswith("/"):
                blockers.append({"code": "architecture_runtime_plan_api_route_invalid", "section_id": "ARCH-10", "observed": raw})
                continue
            if allowed_methods and method not in allowed_methods:
                blockers.append({"code": "architecture_runtime_plan_api_method_forbidden", "section_id": "ARCH-10", "route": raw})
            if prefixes and not any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes):
                blockers.append({"code": "architecture_runtime_plan_api_route_outside_contract", "section_id": "ARCH-10", "route": raw})
            if forbidden_routes and _matches(path, forbidden_routes):
                blockers.append({"code": "architecture_runtime_plan_api_route_forbidden", "section_id": "ARCH-10", "route": raw})

    if "ARCH-13" in relevant:
        p13 = sections.get("ARCH-13", {}).get("payload", {})
        allowed_hosts = [item.lower() for item in _strings(p13.get("allowed_hosts"))]
        forbidden_hosts = [item.lower() for item in _strings(p13.get("forbidden_hosts"))]
        for service in declarations["expected_external_services"]:
            host = _host(service) if "://" in service else service.lower()
            if forbidden_hosts and _matches(host, forbidden_hosts):
                blockers.append({"code": "architecture_runtime_plan_external_service_forbidden", "section_id": "ARCH-13", "service": service})
            elif allowed_hosts and not _matches(host, allowed_hosts):
                blockers.append({"code": "architecture_runtime_plan_external_service_unapproved", "section_id": "ARCH-13", "service": service})

    if "ARCH-14" in relevant:
        p14 = sections.get("ARCH-14", {}).get("payload", {})
        allowed_env = _strings(p14.get("allowed_env_vars"))
        forbidden_env = _strings(p14.get("forbidden_env_vars"))
        for key in declarations["expected_config_keys"]:
            if forbidden_env and _matches(key, forbidden_env):
                blockers.append({"code": "architecture_runtime_plan_config_forbidden", "section_id": "ARCH-14", "key": key})
            elif allowed_env and not _matches(key, allowed_env):
                blockers.append({"code": "architecture_runtime_plan_config_unapproved", "section_id": "ARCH-14", "key": key})

    return {"ready": not blockers, "blockers": blockers, "declarations": declarations, "enforced_sections": sorted(relevant)}


def architecture_runtime_target_check(root: Path | str, target: str) -> dict[str, Any]:
    """Apply target-only boundary rules before a project write occurs."""
    root = Path(root).resolve()
    rel = _normalize_path(target)
    with connect_read_only(root) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            return {"allowed": True, "enforced": False, "reason": "architecture_runtime_no_active_baseline", "target": rel}
        sections = _baseline_sections(connection, baseline["id"])
    # Target-only hard boundary: secret/config files may be confined to declared paths.
    p14 = sections.get("ARCH-14", {}).get("payload", {})
    forbidden_paths = _strings(p14.get("forbidden_config_paths"))
    if forbidden_paths and _matches(rel, forbidden_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_config_path_forbidden", "section_id": "ARCH-14", "target": rel, "expected": {"forbidden_config_paths": forbidden_paths}}
    data_write_paths = _strings(sections.get("ARCH-09", {}).get("payload", {}).get("data_write_allowed_paths"))
    data_path_patterns = _strings(sections.get("ARCH-09", {}).get("payload", {}).get("data_access_file_patterns"))
    if data_path_patterns and _matches(rel, data_path_patterns) and data_write_paths and not _matches(rel, data_write_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_data_access_path_forbidden", "section_id": "ARCH-09", "target": rel, "expected": {"data_write_allowed_paths": data_write_paths}}
    return {"allowed": True, "enforced": True, "reason": "architecture_runtime_target_allowed", "section_id": None, "target": rel}


def architecture_runtime_check(root: Path | str, *, task_id: str | None = None, plan_id: int | None = None, changed_files: Iterable[str] = (), mode: str = "manual", created_by: str = "system:architecture-runtime") -> dict[str, Any]:
    """Run deterministic post-change runtime boundary checks and persist findings."""
    root = Path(root).resolve()
    files = sorted({_normalize_path(item) for item in changed_files if str(item).strip()})
    with connect(root, immediate=True) as connection:
        baseline = _active_baseline(connection)
        if not baseline:
            payload = {"engine_version": RUNTIME_ENGINE_VERSION, "mode": mode, "task_id": task_id, "plan_id": plan_id, "baseline_id": None, "baseline_hash": None, "changed_files": files, "status": "not_evaluable", "fact_count": 0, "findings": []}
            run_hash = _sha(payload)
            connection.execute(
                """INSERT OR IGNORE INTO architecture_runtime_runs(
                   run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,fact_count,finding_count,warning_count,blocking_count,run_hash,created_by
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), RUNTIME_ENGINE_VERSION, mode, task_id, plan_id, None, None, "not_evaluable", _canonical(files), 0, 0, 0, 0, run_hash, created_by),
            )
            row = connection.execute("SELECT id FROM architecture_runtime_runs WHERE run_hash=?", (run_hash,)).fetchone()
            return {"ok": True, "enforced": False, "status": "not_evaluable", "run_id": int(row[0]), "findings": [], "fact_count": 0, "baseline": None}
        sections = _baseline_sections(connection, baseline["id"])
        findings: list[dict[str, Any]] = []
        facts_count = 0
        for rel in files:
            target = architecture_runtime_target_check_from_sections(sections, rel)
            if not target.get("allowed", True):
                findings.append(_finding(str(target.get("section_id") or "ARCH-14"), str(target.get("reason") or "architecture_runtime_target_blocked"), "block", rel, target.get("expected"), rel, [rel]))
            facts = _facts(root, rel)
            if facts is None:
                continue
            facts_count += 1
            findings.extend(_analyze_file_against_sections(facts, sections))
        blocking = sum(1 for item in findings if item["severity"] == "block")
        warnings = sum(1 for item in findings if item["severity"] == "warn")
        status = "block" if blocking else "warn" if warnings else "pass"
        run_payload = {"engine_version": RUNTIME_ENGINE_VERSION, "mode": mode, "task_id": task_id, "plan_id": plan_id, "baseline_id": baseline["id"], "baseline_hash": baseline["baseline_hash"], "changed_files": files, "fact_count": facts_count, "status": status, "findings": [item["finding_hash"] for item in findings]}
        run_hash = _sha(run_payload)
        connection.execute(
            """INSERT OR IGNORE INTO architecture_runtime_runs(
               run_uuid,engine_version,mode,task_id,plan_id,baseline_id,baseline_hash,status,changed_files_json,fact_count,finding_count,warning_count,blocking_count,run_hash,created_by
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), RUNTIME_ENGINE_VERSION, mode, task_id, plan_id, baseline["id"], baseline["baseline_hash"], status, _canonical(files), facts_count, len(findings), warnings, blocking, run_hash, created_by),
        )
        row = connection.execute("SELECT id FROM architecture_runtime_runs WHERE run_hash=?", (run_hash,)).fetchone()
        if not row:
            raise RuntimeError("architecture_runtime_run_persist_failed")
        run_id = int(row[0])
        for item in findings:
            connection.execute(
                """INSERT OR IGNORE INTO architecture_runtime_findings(
                   run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (run_id, item["section_id"], item["finding_code"], item["severity"], item["subject"], _canonical(item["expected"]), _canonical(item["observed"]), _canonical(item["evidence_paths"]), item["finding_hash"]),
            )
        return {"ok": blocking == 0, "enforced": True, "status": status, "run_id": run_id, "baseline": baseline, "fact_count": facts_count, "findings": findings, "blocking_count": blocking, "warning_count": warnings}


def architecture_runtime_target_check_from_sections(sections: dict[str, dict[str, Any]], target: str) -> dict[str, Any]:
    """Apply target-only runtime rules against already loaded baseline sections."""
    rel = _normalize_path(target)
    p14 = sections.get("ARCH-14", {}).get("payload", {})
    forbidden_paths = _strings(p14.get("forbidden_config_paths"))
    if forbidden_paths and _matches(rel, forbidden_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_config_path_forbidden", "section_id": "ARCH-14", "target": rel, "expected": {"forbidden_config_paths": forbidden_paths}}
    p09 = sections.get("ARCH-09", {}).get("payload", {})
    data_write_paths = _strings(p09.get("data_write_allowed_paths"))
    data_patterns = _strings(p09.get("data_access_file_patterns"))
    if data_patterns and _matches(rel, data_patterns) and data_write_paths and not _matches(rel, data_write_paths):
        return {"allowed": False, "enforced": True, "reason": "architecture_data_access_path_forbidden", "section_id": "ARCH-09", "target": rel, "expected": {"data_write_allowed_paths": data_write_paths}}
    return {"allowed": True, "enforced": True, "reason": "architecture_runtime_target_allowed", "section_id": None, "target": rel}


def architecture_runtime_findings(root: Path | str, *, run_id: int | None = None, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Read persisted runtime-boundary findings without executing a new scan."""
    with connect_read_only(Path(root).resolve()) as connection:
        if run_id is None:
            if task_id:
                row = connection.execute("SELECT id FROM architecture_runtime_runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
            else:
                row = connection.execute("SELECT id FROM architecture_runtime_runs ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return []
            run_id = int(row[0])
        rows = connection.execute(
            """SELECT id,run_id,section_id,finding_code,severity,subject,expected_json,observed_json,evidence_paths_json,finding_hash,created_at
               FROM architecture_runtime_findings WHERE run_id=? ORDER BY id LIMIT ?""",
            (run_id, max(1, min(int(limit), 1000))),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for key in ("expected_json", "observed_json", "evidence_paths_json"):
                item[key[:-5]] = json.loads(item.pop(key))
            out.append(item)
        return out


def architecture_runtime_status(root: Path | str) -> dict[str, Any]:
    """Read current v0.26.2 runtime-boundary status and authority invariants."""
    with connect_read_only(Path(root).resolve()) as connection:
        baseline = _active_baseline(connection)
        row = connection.execute("SELECT * FROM architecture_runtime_runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "ok": True,
        "version": "0.26.2",
        "schema": MIGRATION_VERSION,
        "engine_version": RUNTIME_ENGINE_VERSION,
        "sections": list(RUNTIME_SECTIONS),
        "active_baseline": baseline,
        "latest_run": dict(row) if row else None,
        "static_analysis_only": True,
        "project_code_execution": False,
        "llm_runtime_authority": False,
        "approval_authority_exposed": False,
        "waiver_authority_exposed": False,
        "automatic_architecture_mutation": False,
        "architecture_change_required_for_blocked_boundary": True,
    }
