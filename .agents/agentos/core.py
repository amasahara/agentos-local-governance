"""
File: .agents/agentos/core.py

Purpose:
    Implement AgentOS runtime governance and composite workflows.

Responsibilities:
    - Manage tasks and approvals.
    - Enforce project-root write containment.
    - Prepare code changes using placement, reuse, and context checks.
    - Record and retrieve evidence-grounded claims.
    - Provide project status and documentation checks.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import __version__
from .db import SCHEMA_VERSION, connect
from .indexing import duplicate_report, index_query
from .policy import CLAIM_TYPES, RISK_LEVELS, load_policy


def start_task(root: Path, task_id: str, request: str) -> dict[str, Any]:
    """Create a governance task.

    Args:
        root: Project root.
        task_id: Unique task identifier.
        request: Original user request.

    Returns:
        Created task metadata.
    """
    with connect(root) as c:
        c.execute("INSERT INTO tasks(id,request) VALUES(?,?)", (task_id, request))
    return {"task_id": task_id, "approved": False}


def approve_task(root: Path, task_id: str, scope: list[str]) -> dict[str, Any]:
    """Approve an existing task for a bounded write scope.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        scope: Project-relative paths or directory prefixes.

    Returns:
        Approval metadata.
    """
    from .human_decision import clarity_gate_status
    gate = clarity_gate_status(root, task_id)
    if not gate["ready"]:
        raise RuntimeError("clarity_gate_blocked: structured clarity assessment and all blocking human decisions must be resolved")
    with connect(root) as c:
        cur = c.execute("UPDATE tasks SET approved=1,approved_scope=? WHERE id=?", (json.dumps(scope), task_id))
        if cur.rowcount != 1:
            raise RuntimeError(f"task not found: {task_id}")
    return {"task_id": task_id, "approved": True, "scope": scope}


def _task(root: Path, task_id: str) -> dict[str, Any]:
    with connect(root) as c:
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise RuntimeError(f"task not found: {task_id}")
    return dict(row)


def _relative_resolved(root: Path, target: str) -> tuple[Path, str | None]:
    base = root.resolve()
    candidate = Path(target)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    try:
        rel = resolved.relative_to(base).as_posix()
    except ValueError:
        return resolved, None
    return resolved, rel


def check_write(root: Path, task_id: str, target: str) -> dict[str, Any]:
    """Check whether a task may write a project-relative target.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        target: Requested path.

    Returns:
        Write decision with a stable reason code.
    """
    task = _task(root, task_id)
    _, rel = _relative_resolved(root, target)
    allowed = False
    reason = "outside_project_root"
    if rel is not None:
        if not task["approved"]:
            reason = "task_not_approved"
        else:
            from .human_decision import clarity_gate_status, decision_gate_status
            clarity_gate = clarity_gate_status(root, task_id)
            decision_gate = decision_gate_status(root, task_id)
            if not clarity_gate["ready"]:
                reason = "clarity_gate_pending" if not decision_gate["blocked"] else "human_decision_pending"
            else:
                scope = json.loads(task["approved_scope"])
                allowed = any(rel == s.rstrip("/") or rel.startswith(s.rstrip("/") + "/") for s in scope)
                reason = "approved_scope" if allowed else "outside_approved_scope"
                if allowed:
                    from .architecture_structural import architecture_structural_target_check
                    architecture = architecture_structural_target_check(root, rel)
                    if architecture.get("enforced") and not architecture.get("allowed", True):
                        allowed = False
                        reason = str(architecture.get("reason") or "architecture_structural_blocked")
                    if allowed:
                        from .architecture_runtime import architecture_runtime_target_check
                        runtime_boundary = architecture_runtime_target_check(root, rel)
                        if runtime_boundary.get("enforced") and not runtime_boundary.get("allowed", True):
                            allowed = False
                            reason = str(runtime_boundary.get("reason") or "architecture_runtime_blocked")
    with connect(root) as c:
        c.execute("INSERT INTO write_audit(task_id,target,allowed,reason) VALUES(?,?,?,?)", (task_id, target, int(allowed), reason))
    return {"allowed": allowed, "reason": reason, "target": rel or target}


def resolve_placement(root: Path, filename: str, intent: str, feature: str | None = None, layer: str | None = None, file_kind: str | None = None, temporary: bool = False, task_id: str | None = None) -> str:
    """Resolve a deterministic project-relative placement for a new file.

    Args:
        root: Project root.
        filename: Requested file name.
        intent: Intended responsibility.
        feature: Optional feature or bounded context.
        layer: Optional architecture layer.
        file_kind: Optional source, test, script, or documentation kind.
        temporary: Whether the file is task-scoped runtime material.
        task_id: Task identifier required for temporary files.

    Returns:
        Project-relative path.
    """
    del root, intent
    if temporary:
        if not task_id:
            raise RuntimeError("task_id is required for temporary placement")
        bucket = "tests" if file_kind == "test" else "scripts" if file_kind == "script" else "fixtures"
        return f".agents/runtime/task-workspaces/{task_id}/{bucket}/{filename}"
    if file_kind == "test":
        return f"tests/{feature + '/' if feature else ''}{filename}"
    if file_kind == "script":
        return f"scripts/{filename}"
    parts = ["src"]
    if feature:
        parts.append(feature)
    if layer:
        parts.append(layer)
    parts.append(filename)
    return "/".join(parts)


def _recommended_context(root: Path, target: str, symbols: list[str], limit: int = 10) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with connect(root) as c:
        rows = c.execute("SELECT path,qualname,line_start,line_end FROM symbol_index WHERE path=? ORDER BY line_start", (target,)).fetchall()
        for row in rows:
            items.append({**dict(row), "reason": "same_file_symbol"})
    for symbol in symbols:
        for match in index_query(root, symbol, limit=5):
            if match["path"] != target:
                items.append({"path": match["path"], "qualname": match["qualname"], "line_start": match["line_start"], "line_end": match["line_end"], "reason": "similar_symbol_elsewhere"})
    seen: set[tuple[str, str]] = set()
    out = []
    for item in items:
        key = (item["path"], item["qualname"])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out[:limit]


def prepare_change(root: Path, task_id: str, operation: str, target: str, intent: str, symbols: list[str] | None = None, feature: str | None = None, layer: str | None = None, file_kind: str | None = None, temporary: bool = False) -> dict[str, Any]:
    """Prepare a bounded code change before execution.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        operation: Create or modify.
        target: Requested path or filename.
        intent: Intended change.
        symbols: Symbols involved in the change.
        feature: Optional feature for create placement.
        layer: Optional architecture layer for create placement.
        file_kind: Optional file classification.
        temporary: Whether a created file is task-scoped.

    Returns:
        Composite preparation report.

    Raises:
        RuntimeError: Task or operation is invalid.
    """
    _task(root, task_id)
    if operation not in {"create", "modify"}:
        raise RuntimeError("operation must be create or modify")
    symbols = symbols or []
    effective_target = resolve_placement(root, Path(target).name, intent, feature, layer, file_kind, temporary, task_id) if operation == "create" else target
    similar = []
    for symbol in symbols:
        similar.extend(index_query(root, symbol, limit=5))
    seen = set()
    similar = [m for m in similar if not ((m["path"], m["qualname"]) in seen or seen.add((m["path"], m["qualname"]))) ]
    duplicates = [d for d in duplicate_report(root) if any(s["path"] == effective_target for s in d["symbols"])]
    write = check_write(root, task_id, effective_target)
    blockers = [] if write["allowed"] else [write["reason"]]
    return {
        "task_id": task_id,
        "operation": operation,
        "intent": intent,
        "requested_target": target,
        "effective_target": effective_target,
        "placement": {"required": operation == "create", "resolved_path": effective_target},
        "similar_symbols": similar,
        "duplicate_candidates": duplicates,
        "recommended_context": _recommended_context(root, effective_target, symbols),
        "write": write,
        "ready": not blockers,
        "blockers": blockers,
    }


def record_tool_execution(root: Path, task_id: str, tool_name: str, input_data: dict[str, Any], success: bool, output_summary: str, classification: str | None = None) -> dict[str, Any]:
    """Reject unguarded evidence recording in v0.9.0.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        tool_name: Tool identifier.
        input_data: Tool input metadata.
        success: Whether execution succeeded.
        output_summary: Execution summary.
        classification: Deprecated caller-supplied classification.

    Returns:
        Never returns normally.

    Raises:
        RuntimeError: Direct evidence recording is forbidden.
    """
    del root, task_id, tool_name, input_data, success, output_summary, classification
    raise RuntimeError("direct record-tool is disabled in v0.9.0; use guard-tool followed by complete-tool")

def record_claim(root: Path, task_id: str, claim_text: str, claim_type: str, risk: str, evidence_tool_call_ids: list[int] | None = None) -> dict[str, Any]:
    """Record a claim linked atomically to valid supporting evidence.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        claim_text: Conclusion being asserted.
        claim_type: Controlled claim category.
        risk: Low, medium, or high.
        evidence_tool_call_ids: Supporting tool-call identifiers.

    Returns:
        Claim identifier and evidence metadata.
    """
    _task(root, task_id)
    policy = load_policy(root)["claim_policy"]
    text = claim_text.strip()
    if not text:
        raise RuntimeError("claim_text must not be empty")
    if claim_type not in CLAIM_TYPES:
        raise RuntimeError("invalid claim_type")
    if risk not in RISK_LEVELS:
        raise RuntimeError("invalid risk")
    ids = list(dict.fromkeys(evidence_tool_call_ids or []))
    required = risk == "high" or (risk == "medium" and claim_type in set(policy["require_evidence_for_medium_types"]))
    if required and not ids:
        raise RuntimeError("evidence is required for this claim")
    with connect(root) as c:
        for call_id in ids:
            row = c.execute("SELECT task_id,success,classification FROM tool_calls WHERE id=?", (call_id,)).fetchone()
            if not row:
                raise RuntimeError(f"tool_call {call_id} not found")
            if row["task_id"] != task_id:
                raise RuntimeError(f"tool_call {call_id} belongs to another task")
            if not row["success"]:
                raise RuntimeError(f"tool_call {call_id} was not successful")
            if row["classification"] != "local" and not policy.get("allow_network_evidence", False):
                raise RuntimeError(f"tool_call {call_id} is not local evidence")
        cur = c.execute("INSERT INTO claims(task_id,claim_text,claim_type,risk) VALUES(?,?,?,?)", (task_id, text, claim_type, risk))
        claim_id = int(cur.lastrowid)
        for call_id in ids:
            c.execute("INSERT INTO claim_evidence(claim_id,tool_call_id,evidence_role) VALUES(?,?,?)", (claim_id, call_id, "supports"))
    return {"claim_id": claim_id, "task_id": task_id, "claim_type": claim_type, "risk": risk, "evidence_count": len(ids), "linked_evidence": ids}


def list_claims(root: Path, task_id: str) -> list[dict[str, Any]]:
    """List claims for a task with evidence counts.

    Args:
        root: Project root.
        task_id: Existing task identifier.

    Returns:
        Claims ordered by identifier.
    """
    _task(root, task_id)
    with connect(root) as c:
        rows = c.execute("""
            SELECT c.id,c.claim_text,c.claim_type,c.risk,c.created_at,COUNT(ce.tool_call_id) AS evidence_count
            FROM claims c LEFT JOIN claim_evidence ce ON ce.claim_id=c.id
            WHERE c.task_id=? GROUP BY c.id ORDER BY c.id
        """, (task_id,)).fetchall()
    return [dict(r) for r in rows]


def show_claim(root: Path, claim_id: int) -> dict[str, Any]:
    """Return a claim and all linked tool evidence.

    Args:
        root: Project root.
        claim_id: Claim identifier.

    Returns:
        Claim record and evidence records.
    """
    with connect(root) as c:
        claim = c.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim:
            raise RuntimeError(f"claim not found: {claim_id}")
        evidence = c.execute("""
            SELECT tc.id AS tool_call_id,tc.tool_name,tc.classification,tc.success,tc.output_summary,ce.evidence_role
            FROM claim_evidence ce JOIN tool_calls tc ON tc.id=ce.tool_call_id
            WHERE ce.claim_id=? ORDER BY tc.id
        """, (claim_id,)).fetchall()
    return {"claim": dict(claim), "evidence": [dict(r) for r in evidence]}


def docs_check(root: Path) -> dict[str, Any]:
    """Check current documentation identity, schema, release name, and local links."""
    required = ["README.md", "AGENTS.md", "huong_dan.md", ".agents/docs/USAGE.md", ".agents/docs/PROJECT_STRUCTURE.md", ".agents/docs/RULES_WORKFLOW_CHANGELOG.md", "VERSION"]
    missing = [rel for rel in required if not (root / rel).exists()]
    version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else None
    policy = load_policy(root) if not missing else {}
    policy_version = policy.get("version")
    changelog = (root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md").read_text(encoding="utf-8") if (root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md").exists() else ""
    guide = (root / "huong_dan.md").read_text(encoding="utf-8") if (root / "huong_dan.md").exists() else ""
    consistent = version == policy_version == __version__
    doc_policy = policy.get("documentation_policy", {})
    history_begin = doc_policy.get("history_begin", "AGENTOS_VERSION_HISTORY_BEGIN")
    history_end = doc_policy.get("history_end", "AGENTOS_VERSION_HISTORY_END")
    stale: list[str] = []
    schema_mismatches: list[str] = []
    release_identity_mismatches: list[str] = []
    broken_local_links: list[str] = []

    current_version_files = doc_policy.get("current_version_files", ["README.md", "README.vi.md", "README.en.md", "huong_dan.md", "AGENTS.md"])
    for rel in current_version_files:
        path = root / str(rel)
        if not path.exists() or not version:
            continue
        current_text = path.read_text(encoding="utf-8")
        while f"<!-- {history_begin} -->" in current_text and f"<!-- {history_end} -->" in current_text:
            before, rest = current_text.split(f"<!-- {history_begin} -->", 1)
            _, after = rest.split(f"<!-- {history_end} -->", 1)
            current_text = before + after
        for marker in ("Current version:", "Current release:", "Phiên bản hiện tại:"):
            for line in current_text.splitlines():
                if marker in line and version not in line:
                    stale.append(f"{rel}: {line.strip()}")

    expected_schema = int(doc_policy.get("current_schema", SCHEMA_VERSION))
    current_schema_files = doc_policy.get("current_schema_files", ["README.md", "huong_dan.md"])
    if not isinstance(current_schema_files, list):
        current_schema_files = ["README.md", "huong_dan.md"]
    for rel in current_schema_files:
        path = root / str(rel)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "Database schema:" in line or "Schema database:" in line:
                    if str(expected_schema) not in line:
                        schema_mismatches.append(f"{rel}: {line.strip()}")

    release_name = str(doc_policy.get("current_release_name") or "").strip()
    identity_files = doc_policy.get("current_release_identity_files", ["README.md", "README.vi.md", "README.en.md", "RELEASE_NOTES.md"])
    if release_name and version:
        for rel in identity_files:
            path = root / str(rel)
            if not path.is_file():
                release_identity_mismatches.append(f"{rel}: missing")
                continue
            current_text = path.read_text(encoding="utf-8")
            if version not in current_text or release_name not in current_text:
                release_identity_mismatches.append(f"{rel}: expected {version} — {release_name}")

    link_files = doc_policy.get("local_link_check_files", ["README.md", "README.vi.md", "README.en.md", "UPGRADE_FROM_0.24.1.md"])
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for rel in link_files:
        doc_path = root / str(rel)
        if not doc_path.is_file():
            broken_local_links.append(f"{rel}: missing")
            continue
        current_text = doc_path.read_text(encoding="utf-8")
        for match in link_pattern.finditer(current_text):
            target = match.group(1).strip()
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            target = target.split()[0].strip("<>").split("#", 1)[0]
            if not target:
                continue
            candidate = (doc_path.parent / target).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                broken_local_links.append(f"{rel}: outside-root link {target}")
                continue
            if not candidate.exists():
                broken_local_links.append(f"{rel}: {target}")

    content_ok = not stale and not schema_mismatches and not release_identity_mismatches and not broken_local_links
    ok = not missing and consistent and bool(version and version in changelog) and "Tiếng Việt" in guide and "English" in guide and content_ok
    return {
        "ok": ok,
        "missing_documents": missing,
        "version": {"VERSION": version, "governance.json": policy_version, "__init__.py": __version__, "consistent": consistent},
        "bilingual_markers": {"vi": "Tiếng Việt" in guide, "en": "English" in guide},
        "changelog_has_current_version": bool(version and version in changelog),
        "content_consistency": {
            "ok": content_ok,
            "stale_current_version_references": stale,
            "schema_mismatches": schema_mismatches,
            "release_identity_mismatches": release_identity_mismatches,
            "broken_local_links": broken_local_links,
        },
    }


def instruction_check(root: Path) -> dict[str, Any]:
    """Verify that AGENTS.md is the only coding-agent instruction authority.

    Args:
        root: Project root.

    Returns:
        Instruction-source report.
    """
    exact = ["CLAUDE.md", "GEMINI.md", "COPILOT.md", "CODEX.md", "CURSOR.md", ".agents/README.md", ".clinerules", ".windsurfrules", "INSTRUCTIONS.md", "AI_RULES.md", ".github/copilot-instructions.md"]
    patterns = [".cursor/rules/*.mdc", ".windsurf/rules/*", "**/*instructions*.md", "**/*agent-rules*.md"]
    found = {p for p in exact if (root / p).exists()}
    for pattern in patterns:
        for path in root.glob(pattern):
            rel = path.relative_to(root).as_posix()
            if rel not in {"AGENTS.md", ".agents/docs/PROJECT_STRUCTURE.md"} and ".agents/runtime/" not in rel:
                found.add(rel)
    return {"ok": (root / "AGENTS.md").exists() and not found, "duplicate_instruction_sources": sorted(found)}

def db_status(root: Path) -> dict[str, Any]:
    """Return current database migration status.

    Args:
        root: Project root.

    Returns:
        Current and required schema versions.
    """
    with connect(root) as c:
        current = c.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]
    return {"current": current, "required": SCHEMA_VERSION, "is_current": current == SCHEMA_VERSION}


def project_status(root: Path, task_id: str | None = None) -> dict[str, Any]:
    """Return aggregate project, task, workflow, and drift status.

    Args:
        root: Project root.
        task_id: Optional task identifier.

    Returns:
        Aggregate status report.
    """
    from .drift import drift_check
    from .workflow import current_task_id, workflow_status

    active = task_id or current_task_id(root)
    result: dict[str, Any] = {
        "version": __version__,
        "instruction": instruction_check(root),
        "documentation": docs_check(root),
        "database": db_status(root),
        "drift": drift_check(root, task_id=active),
        "current_task": active,
    }
    if active:
        result["task"] = _task(root, active)
        result["workflow"] = workflow_status(root, active)
    return result
