from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import re
import shlex
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Any

FORBIDDEN_INSTRUCTION_FILES = {
    "CLAUDE.md", "GEMINI.md", "COPILOT.md", "CODEX.md", "CURSOR.md"
}
AMBIGUOUS_DIRS = {"misc", "other", "new_folder"}


def project_root(start: str | Path = ".") -> Path:
    p = Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / "AGENTS.md").is_file() and (candidate / ".agents").is_dir():
            return candidate
    raise RuntimeError("AgentOS project root not found (requires AGENTS.md and .agents/).")


def load_governance(root: Path) -> dict[str, Any]:
    return json.loads((root / ".agents/config/governance.json").read_text(encoding="utf-8"))


def db_connect(root: Path) -> sqlite3.Connection:
    db = root / ".agents/state/agentos.sqlite3"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tasks (
      task_id TEXT PRIMARY KEY,
      original_request TEXT NOT NULL,
      intent TEXT,
      target TEXT,
      expected_behavior TEXT,
      current_behavior TEXT,
      acceptance_criteria TEXT NOT NULL DEFAULT '[]',
      scope TEXT,
      risk TEXT NOT NULL,
      ambiguities TEXT NOT NULL DEFAULT '[]',
      assumptions TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL,
      approved INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tool_calls (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id TEXT NOT NULL,
      tool_name TEXT NOT NULL,
      normalized_args TEXT NOT NULL,
      success INTEGER,
      failure_signature TEXT,
      output_summary TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS write_audit (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id TEXT NOT NULL,
      path TEXT NOT NULL,
      allowed INTEGER NOT NULL,
      reason TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS duplicate_candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      path_a TEXT NOT NULL,
      path_b TEXT NOT NULL,
      fingerprint TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS environment_profiles (
      session_id TEXT PRIMARY KEY,
      profile_json TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    return conn


@dataclass
class ClarityAssessment:
    intent: str | None
    target: str | None
    expected_behavior: str | None
    current_behavior: str | None
    acceptance_criteria: list[str]
    scope: str | None
    risk: str
    ambiguities: list[str]
    assumptions: list[str]
    status: str


def assess_clarity(payload: dict[str, Any]) -> ClarityAssessment:
    intent = _clean(payload.get("intent"))
    target = _clean(payload.get("target"))
    expected = _clean(payload.get("expected_behavior"))
    current = _clean(payload.get("current_behavior"))
    criteria = [str(x).strip() for x in payload.get("acceptance_criteria", []) if str(x).strip()]
    scope = _clean(payload.get("scope"))
    risk = str(payload.get("risk") or "medium").lower()
    assumptions = [str(x).strip() for x in payload.get("assumptions", []) if str(x).strip()]
    destructive = bool(payload.get("destructive"))
    schema_change = bool(payload.get("schema_change"))
    permission_change = bool(payload.get("permission_change"))
    security_change = bool(payload.get("security_change"))
    ambiguities: list[str] = []

    if not intent:
        ambiguities.append("Không xác định được ý định chính.")
    if not target:
        ambiguities.append("Chưa xác định chức năng, module, file hoặc hành vi bị ảnh hưởng.")
    if not expected:
        ambiguities.append("Chưa mô tả kết quả mong muốn.")
    if intent in {"fix", "modify_existing_feature", "debug"} and not current:
        ambiguities.append("Chưa mô tả hành vi hiện tại hoặc lỗi đang xảy ra.")
    if not criteria:
        ambiguities.append("Chưa có tiêu chí nghiệm thu có thể kiểm chứng.")
    if not scope:
        ambiguities.append("Chưa xác định phạm vi thay đổi.")
    if destructive or schema_change or permission_change or security_change:
        risk = "high"
    if risk == "high" and (not criteria or not scope):
        ambiguities.append("Thay đổi rủi ro cao cần phạm vi và tiêu chí nghiệm thu rõ ràng.")

    status = "ready" if not ambiguities else "needs_clarification"
    return ClarityAssessment(
        intent, target, expected, current, criteria, scope,
        risk, ambiguities, assumptions, status
    )


def suggested_questions(a: ClarityAssessment) -> list[str]:
    qs = []
    joined = " ".join(a.ambiguities)
    if "chức năng" in joined:
        qs.append("Chức năng, màn hình, module hoặc file nào cần thay đổi?")
    if "hành vi hiện tại" in joined:
        qs.append("Hiện tại hệ thống đang hoạt động hoặc báo lỗi như thế nào?")
    if "kết quả mong muốn" in joined:
        qs.append("Kết quả chính xác bạn mong muốn sau khi sửa là gì?")
    if "tiêu chí nghiệm thu" in joined:
        qs.append("Những điều kiện nào phải đúng để xem task đã hoàn thành?")
    if "phạm vi" in joined:
        qs.append("Phạm vi thay đổi được phép gồm những phần nào?")
    if not qs:
        qs.append("Vui lòng bổ sung thông tin còn thiếu có thể làm thay đổi cách triển khai.")
    return qs[:5]


def save_task(root: Path, task_id: str, original_request: str, a: ClarityAssessment) -> None:
    with db_connect(root) as c:
        c.execute("""
        INSERT INTO tasks(task_id, original_request, intent, target, expected_behavior,
          current_behavior, acceptance_criteria, scope, risk, ambiguities, assumptions, status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(task_id) DO UPDATE SET
          original_request=excluded.original_request, intent=excluded.intent, target=excluded.target,
          expected_behavior=excluded.expected_behavior, current_behavior=excluded.current_behavior,
          acceptance_criteria=excluded.acceptance_criteria, scope=excluded.scope,
          risk=excluded.risk, ambiguities=excluded.ambiguities,
          assumptions=excluded.assumptions, status=excluded.status,
          updated_at=CURRENT_TIMESTAMP
        """, (task_id, original_request, a.intent, a.target, a.expected_behavior,
              a.current_behavior, json.dumps(a.acceptance_criteria, ensure_ascii=False),
              a.scope, a.risk, json.dumps(a.ambiguities, ensure_ascii=False),
              json.dumps(a.assumptions, ensure_ascii=False), a.status))


def approve_task(root: Path, task_id: str) -> None:
    with db_connect(root) as c:
        row = c.execute("SELECT status FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise RuntimeError("Task does not exist.")
        if row[0] != "ready":
            raise RuntimeError("Task cannot be approved until clarification status is ready.")
        c.execute("UPDATE tasks SET approved=1, updated_at=CURRENT_TIMESTAMP WHERE task_id=?", (task_id,))


def task_allows_write(root: Path, task_id: str) -> tuple[bool, str]:
    with db_connect(root) as c:
        row = c.execute("SELECT status, approved FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not row:
        return False, "unknown_task"
    if row[0] != "ready":
        return False, "task_needs_clarification"
    if not row[1]:
        return False, "task_not_approved"
    return True, "approved"


def check_write(root: Path, task_id: str, target: str | Path) -> dict[str, Any]:
    raw = Path(target)
    resolved = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()
    allowed, reason = task_allows_write(root, task_id)
    if allowed:
        try:
            resolved.relative_to(root)
        except ValueError:
            allowed, reason = False, "outside_project_root"
    if allowed and any(part in {".."} for part in raw.parts):
        allowed, reason = False, "path_traversal"
    if allowed:
        rel = resolved.relative_to(root)
        if rel.parts and rel.parts[0] in AMBIGUOUS_DIRS:
            allowed, reason = False, "ambiguous_root_directory"
    if allowed and resolved.parent == root and resolved.suffix in {".py", ".js", ".ts", ".java", ".cs", ".go", ".rs"}:
        allowed, reason = False, "source_file_at_project_root"
    with db_connect(root) as c:
        c.execute("INSERT INTO write_audit(task_id,path,allowed,reason) VALUES(?,?,?,?)",
                  (task_id, str(resolved), int(allowed), reason))
    return {"allowed": allowed, "reason": reason, "resolved_path": str(resolved)}


def instruction_check(root: Path) -> dict[str, Any]:
    found = []
    for name in FORBIDDEN_INSTRUCTION_FILES:
        found.extend(str(p.relative_to(root)) for p in root.rglob(name))
    return {"ok": not found, "duplicate_instruction_sources": sorted(found)}


def detect_environment(root: Path, session_id: str) -> dict[str, Any]:
    shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ""
    profile = {
        "platform": platform.system().lower(),
        "platform_release": platform.release(),
        "shell": shell,
        "project_root": str(root),
        "python_executable": sys.executable,
        "path_separator": os.sep,
        "default_encoding": sys.getdefaultencoding(),
        "virtual_environment": os.environ.get("VIRTUAL_ENV"),
    }
    with db_connect(root) as c:
        c.execute("""
        INSERT INTO environment_profiles(session_id, profile_json)
        VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET profile_json=excluded.profile_json
        """, (session_id, json.dumps(profile, ensure_ascii=False)))
    return profile


def normalize_args(args: Any) -> str:
    if isinstance(args, str):
        value = re.sub(r"\s+", " ", args.strip())
    else:
        value = json.dumps(args, ensure_ascii=False, sort_keys=True)
    return value


def failure_signature(error: str) -> str:
    s = error.lower()
    s = re.sub(r"[a-z]:\\[^\s'\"]+|/[^\s'\"]+", "<path>", s)
    s = re.sub(r"\b\d+\b", "<n>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:20]


def enforce_tool_budget(root: Path, task_id: str, tool_name: str, args: Any) -> dict[str, Any]:
    cfg = load_governance(root)["tool_execution_policy"]
    norm = normalize_args(args)
    with db_connect(root) as c:
        total = c.execute("SELECT COUNT(*) FROM tool_calls WHERE task_id=?", (task_id,)).fetchone()[0]
        identical = c.execute("""
          SELECT COUNT(*) FROM tool_calls WHERE task_id=? AND tool_name=? AND normalized_args=?
        """, (task_id, tool_name, norm)).fetchone()[0]
        consecutive_failures = c.execute("""
          SELECT success FROM tool_calls WHERE task_id=? ORDER BY id DESC LIMIT ?
        """, (task_id, cfg["max_consecutive_failures"])).fetchall()
    if total >= cfg["max_tool_calls_per_work_unit"]:
        return {"allowed": False, "reason": "tool_call_budget_exhausted"}
    if identical >= cfg["max_identical_tool_calls"]:
        return {"allowed": False, "reason": "identical_tool_call_already_used"}
    if len(consecutive_failures) >= cfg["max_consecutive_failures"] and all(r[0] == 0 for r in consecutive_failures):
        return {"allowed": False, "reason": "too_many_consecutive_failures"}
    return {"allowed": True, "reason": "within_budget", "normalized_args": norm}


def record_tool_call(root: Path, task_id: str, tool_name: str, args: Any,
                     success: bool, error: str | None = None, output_summary: str = "") -> dict[str, Any]:
    norm = normalize_args(args)
    sig = failure_signature(error or "") if not success else None
    cfg = load_governance(root)["tool_execution_policy"]
    if sig:
        with db_connect(root) as c:
            retries = c.execute("""
              SELECT COUNT(*) FROM tool_calls
              WHERE task_id=? AND failure_signature=?
            """, (task_id, sig)).fetchone()[0]
        if retries >= cfg["max_retries_per_failure_signature"] + 1:
            return {"recorded": False, "reason": "failure_signature_retry_budget_exhausted", "failure_signature": sig}
    with db_connect(root) as c:
        c.execute("""
          INSERT INTO tool_calls(task_id,tool_name,normalized_args,success,failure_signature,output_summary)
          VALUES(?,?,?,?,?,?)
        """, (task_id, tool_name, norm, int(success), sig, output_summary[:2000]))
    return {"recorded": True, "failure_signature": sig}


def resolve_placement(root: Path, filename: str, feature: str | None, layer: str | None,
                      temporary: bool, task_id: str | None) -> str:
    if temporary:
        if not task_id:
            raise RuntimeError("task_id is required for temporary files")
        kind = "tests" if filename.startswith("test_") else "scripts"
        return str(Path(".agents/runtime/task-workspaces") / task_id / kind / filename)
    if filename.startswith("test_") or filename.endswith(".test.js") or filename.endswith(".spec.ts"):
        return str(Path("tests") / (feature or "integration") / filename)
    base = Path("src")
    if feature:
        base /= feature
    if layer:
        base /= layer
    return str(base / filename)


def python_function_fingerprints(path: Path) -> list[tuple[str, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            clone = ast.FunctionDef(
                name="_", args=node.args, body=node.body,
                decorator_list=[], returns=node.returns, type_comment=getattr(node, "type_comment", None)
            )
            dump = ast.dump(clone, annotate_fields=False, include_attributes=False)
            out.append((node.name, hashlib.sha256(dump.encode()).hexdigest()))
    return out


def duplicate_scan(root: Path, scope: str = "src") -> list[dict[str, str]]:
    base = (root / scope).resolve()
    if not base.exists():
        return []
    seen: dict[str, tuple[Path, str]] = {}
    matches = []
    for p in base.rglob("*.py"):
        for name, fp in python_function_fingerprints(p):
            if fp in seen:
                op, oname = seen[fp]
                item = {"path_a": str(op.relative_to(root)), "symbol_a": oname,
                        "path_b": str(p.relative_to(root)), "symbol_b": name,
                        "fingerprint": fp}
                matches.append(item)
                with db_connect(root) as c:
                    c.execute("INSERT INTO duplicate_candidates(path_a,path_b,fingerprint) VALUES(?,?,?)",
                              (item["path_a"], item["path_b"], fp))
            else:
                seen[fp] = (p, name)
    return matches


def similar_symbols(root: Path, query: str, limit: int = 20) -> list[dict[str, str]]:
    terms = [x.lower() for x in re.findall(r"[A-Za-z0-9_]+", query)]
    results = []
    for p in root.rglob("*.py"):
        if ".agents" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                hay = node.name.lower().replace("_", " ")
                score = sum(1 for t in terms if t in hay)
                if score:
                    results.append({"path": str(p.relative_to(root)), "symbol": node.name, "score": str(score)})
    return sorted(results, key=lambda x: int(x["score"]), reverse=True)[:limit]


def recommended_context(root: Path, target: str, limit: int = 8) -> list[str]:
    p = (root / target).resolve()
    candidates = []
    if p.exists():
        candidates.append(str(p.relative_to(root)))
    parent = p.parent
    for name in ("urls.py", "views.py", "models.py", "forms.py", "serializers.py", "__init__.py"):
        q = parent / name
        if q.exists() and str(q.relative_to(root)) not in candidates:
            candidates.append(str(q.relative_to(root)))
    return candidates[:limit]


def prepare_change(root: Path, task_id: str, operation: str, target: str,
                   intent: str, symbols: list[str] | None = None,
                   feature: str | None = None, layer: str | None = None) -> dict[str, Any]:
    allowed, task_reason = task_allows_write(root, task_id)
    if not allowed:
        return {"allowed": False, "reason": task_reason}
    resolved_target = target
    if operation == "create":
        resolved_target = resolve_placement(root, Path(target).name, feature, layer, False, task_id)
    write = check_write(root, task_id, resolved_target)
    similar = []
    for s in symbols or [intent]:
        similar.extend(similar_symbols(root, s, limit=5))
    seen = set()
    dedup_similar = []
    for x in similar:
        key = (x["path"], x["symbol"])
        if key not in seen:
            seen.add(key)
            dedup_similar.append(x)
    dup = duplicate_scan(root, "src")
    return {
        "allowed": bool(write["allowed"]),
        "reason": write["reason"],
        "resolved_path": write["resolved_path"],
        "similar_symbols": dedup_similar[:10],
        "duplicate_risk": "high" if dup else "low",
        "duplicate_candidates": dup[:10],
        "write_policy": "allowed" if write["allowed"] else "denied",
        "recommended_context": recommended_context(root, resolved_target)
    }


def runtime_path(root: Path, task_id: str, kind: str, filename: str) -> str:
    mapping = {
        "temporary_script": "scripts",
        "temporary_test": "tests",
        "fixture": "fixtures",
        "validation_artifact": "validation-artifacts",
        "download": "downloads",
        "export": "exports",
    }
    sub = mapping.get(kind, kind)
    p = root / ".agents/runtime/task-workspaces" / task_id / sub / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)



def docs_check(root: Path) -> dict[str, Any]:
    cfg = load_governance(root)
    policy = cfg.get("documentation_policy", {})
    required = policy.get("required_docs", [])
    missing = [p for p in required if not (root / p).is_file()]

    version_file = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").is_file() else None
    config_version = str(cfg.get("version")) if cfg.get("version") is not None else None

    init_version = None
    init_path = root / ".agents/agentos/__init__.py"
    if init_path.is_file():
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_path.read_text(encoding="utf-8"))
        init_version = match.group(1) if match else None

    version_consistent = bool(version_file and version_file == config_version == init_version)

    guide_path = root / policy.get("developer_entry_point", "huong_dan.md")
    guide_text = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else ""
    bilingual_markers = {
        "vi": any(x in guide_text for x in ("Tiếng Việt", "HƯỚNG DẪN", "Mục đích")),
        "en": any(x in guide_text for x in ("English", "Purpose", "PROJECT STRUCTURE")),
    }
    bilingual_ok = all(bilingual_markers.get(lang, False) for lang in policy.get("bilingual_languages", []))

    changelog_path = root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md"
    changelog_text = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""
    changelog_has_version = bool(version_file and f"v{version_file}" in changelog_text)

    result = {
        "ok": not missing and version_consistent and bilingual_ok and changelog_has_version,
        "missing_documents": missing,
        "version": {
            "VERSION": version_file,
            "governance.json": config_version,
            "__init__.py": init_version,
            "consistent": version_consistent,
        },
        "bilingual_markers": bilingual_markers,
        "changelog_has_current_version": changelog_has_version,
    }
    return result

def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None
