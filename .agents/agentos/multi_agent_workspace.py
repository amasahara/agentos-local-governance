"""
File: .agents/agentos/multi_agent_workspace.py

Purpose:
    Provide isolated Git worktrees and human-gated controlled integration for AgentOS v0.27.3.

Responsibilities:
    - Bind executor task/session ownership to detached Git worktrees outside the primary repository.
    - Collect immutable diff/hash evidence and enforce architecture, security, and test gates.
    - Detect primary/workspace conflicts before controlled integration.
    - Require human review and approval before atomic integration into the primary repository.
    - Preserve primary AgentOS state, leases, audit authority, and fail-closed rollback semantics.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .concurrency import acquire_resource, file_hash, release_resource
from .db import connect, connect_read_only
from .external_audit import append_signed_event
from .policy import load_policy

MIGRATION_VERSION = 61
WORKSPACE_VERSION = 1
_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "database_schema": 61,
    "workspace_version": 1,
    "workspace_roles": ["executor"],
    "workspace_base": "project_sibling",
    "require_clean_primary_on_provision": True,
    "require_workspace_before_executor_start": True,
    "require_sealed_workspace_before_executor_complete": True,
    "require_worker_plan_file_subset": True,
    "require_test_receipt_after_collection": True,
    "require_architecture_candidate_gate": True,
    "require_security_candidate_gate": True,
    "symlink_changes_allowed": False,
    "automatic_merge": False,
    "automatic_branch_merge": False,
    "human_review_required": True,
    "human_approval_required": True,
    "mcp_mutation_allowed": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    data = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _human(identity: str) -> str:
    value = str(identity or "").strip()
    if not value or value.lower() in {"ai", "agent", "assistant", "model", "llm", "system"}:
        raise PermissionError("human_identity_required")
    return value


def _policy(root: Path) -> dict[str, Any]:
    out = dict(_DEFAULT_POLICY)
    configured = load_policy(root).get("isolated_workspace_integration_policy", {})
    if isinstance(configured, dict):
        out.update(configured)
    if not out.get("enabled", True):
        raise PermissionError("isolated_workspace_integration_disabled")
    if out.get("automatic_merge") or out.get("automatic_branch_merge"):
        raise RuntimeError("automatic_integration_must_remain_disabled")
    if out.get("mcp_mutation_allowed"):
        raise RuntimeError("workspace_mcp_mutation_must_remain_disabled")
    return out


def migration_61(c) -> None:
    """Create additive schema 61 workspace/integration state."""
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS multi_agent_workspaces(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id) ON DELETE CASCADE,
            worker_id INTEGER NOT NULL UNIQUE REFERENCES multi_agent_workers(id) ON DELETE CASCADE,
            worker_key TEXT NOT NULL,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            session_id TEXT NOT NULL,
            workspace_path TEXT NOT NULL UNIQUE,
            base_commit TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('provisioned','collected','sealed','released','invalid')),
            diff_manifest_hash TEXT,
            collected_at TEXT,
            sealed_at TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            released_at TEXT
        );
        CREATE TABLE IF NOT EXISTS multi_agent_workspace_files(
            workspace_id INTEGER NOT NULL REFERENCES multi_agent_workspaces(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            change_type TEXT NOT NULL CHECK(change_type IN ('add','modify','delete')),
            base_sha256 TEXT,
            workspace_sha256 TEXT,
            size_bytes INTEGER,
            PRIMARY KEY(workspace_id,path)
        );
        CREATE TABLE IF NOT EXISTS multi_agent_workspace_file_versions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES multi_agent_workspaces(id) ON DELETE CASCADE,
            path TEXT NOT NULL,
            previous_hash TEXT,
            content_hash TEXT NOT NULL,
            task_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS multi_agent_integration_proposals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL REFERENCES multi_agent_workspaces(id),
            supervisor_id INTEGER NOT NULL REFERENCES multi_agent_supervisor_runs(id),
            worker_id INTEGER NOT NULL REFERENCES multi_agent_workers(id),
            parent_task_id TEXT NOT NULL REFERENCES tasks(id),
            base_commit TEXT NOT NULL,
            diff_manifest_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','reviewed','approved','rejected','applied','failed')),
            conflict_status TEXT NOT NULL,
            architecture_status TEXT NOT NULL,
            security_status TEXT NOT NULL,
            test_status TEXT NOT NULL,
            proposal_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            reviewed_by TEXT,
            approved_by TEXT,
            applied_by TEXT,
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            approved_at TEXT,
            applied_at TEXT
        );
        CREATE TABLE IF NOT EXISTS multi_agent_integration_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proposal_id INTEGER REFERENCES multi_agent_integration_proposals(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES multi_agent_workspaces(id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            event_json TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            external_event_hash TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_multi_agent_workspace_supervisor ON multi_agent_workspaces(supervisor_id,status);
        CREATE INDEX IF NOT EXISTS idx_multi_agent_integration_supervisor ON multi_agent_integration_proposals(supervisor_id,status);
        """
    )


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        raise RuntimeError("git_executable_required")
    proc = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, shell=False)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git_command_failed:{' '.join(args)}:{proc.stderr.strip()}")
    return proc


def _repo_root(root: Path) -> Path:
    root = root.resolve()
    reported = Path(_git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if reported != root:
        raise RuntimeError("agentos_root_must_equal_git_toplevel")
    return root


def _workspace_base(root: Path) -> Path:
    digest = _sha(str(root.resolve()))[:12]
    return root.resolve().parent / f".{root.name}.agentos-worktrees" / digest


def _worker_row(c, supervisor_id: int, worker_key: str):
    row = c.execute(
        "SELECT w.*,s.parent_task_id,s.status AS supervisor_status FROM multi_agent_workers w JOIN multi_agent_supervisor_runs s ON s.id=w.supervisor_id WHERE w.supervisor_id=? AND w.worker_key=?",
        (int(supervisor_id), str(worker_key)),
    ).fetchone()
    if not row:
        raise ValueError("worker_not_found")
    return row


def _workspace_row(c, supervisor_id: int, worker_key: str):
    row = c.execute(
        "SELECT ws.*,w.plan_id,w.plan_hash,w.role,w.status AS worker_status,s.parent_task_id,s.status AS supervisor_status FROM multi_agent_workspaces ws JOIN multi_agent_workers w ON w.id=ws.worker_id JOIN multi_agent_supervisor_runs s ON s.id=ws.supervisor_id WHERE ws.supervisor_id=? AND ws.worker_key=?",
        (int(supervisor_id), str(worker_key)),
    ).fetchone()
    if not row:
        raise ValueError("workspace_not_found")
    return row


def _plan_files(c, plan_id: int) -> set[str]:
    row = c.execute("SELECT plan_json FROM task_plans WHERE id=?", (int(plan_id),)).fetchone()
    if not row:
        raise RuntimeError("worker_plan_not_found")
    try:
        payload = json.loads(row[0])
    except Exception:
        payload = {}
    raw = payload.get("expected_files") or payload.get("files") or []
    return {str(x).replace("\\", "/").strip() for x in raw if str(x).strip()}


def _record_event(root: Path, event_type: str, payload: dict[str, Any], *, proposal_id: int | None = None, workspace_id: int | None = None, task_id: str | None = None, session_id: str | None = None) -> None:
    event = {"event_type": event_type, "proposal_id": proposal_id, "workspace_id": workspace_id, "payload": payload, "created_at": _now()}
    event_json = _canonical(event)
    event_hash = _sha(event_json)
    signed = append_signed_event(root, f"workspace.{event_type}", payload, task_id, session_id)
    with connect(root) as c:
        c.execute(
            "INSERT INTO multi_agent_integration_events(proposal_id,workspace_id,event_type,event_json,event_hash,external_event_hash,created_at) VALUES(?,?,?,?,?,?,?)",
            (proposal_id, workspace_id, event_type, event_json, event_hash, signed.get("event_hash"), _now()),
        )


def provision_workspace(root: Path, supervisor_id: int, worker_key: str, created_by: str) -> dict[str, Any]:
    """Provision one detached worktree for an assigned executor worker.

    Args:
        root: Primary governed repository root.
        supervisor_id: Existing supervisor run identifier.
        worker_key: Existing worker assignment key.
        created_by: Human operator identity.
    Returns:
        Workspace identifier, base commit, status, and operator-visible physical path.
    """
    root = _repo_root(root)
    policy = _policy(root)
    human = _human(created_by)
    if policy.get("require_clean_primary_on_provision", True):
        if _git(root, "status", "--porcelain", "--untracked-files=all").stdout.strip():
            raise PermissionError("primary_worktree_must_be_clean_for_workspace_provision")
    with connect_read_only(root) as c:
        worker = _worker_row(c, supervisor_id, worker_key)
        if str(worker["role"]) not in set(policy.get("workspace_roles", ["executor"])):
            raise PermissionError("worker_role_does_not_require_workspace")
        if c.execute("SELECT 1 FROM multi_agent_workspaces WHERE worker_id=?", (int(worker["id"]),)).fetchone():
            raise PermissionError("worker_workspace_already_exists")
    key = str(worker_key)
    if not _SAFE_KEY.fullmatch(key) or key in {".", ".."}:
        raise ValueError("unsafe_worker_key")
    base_commit = _git(root, "rev-parse", "HEAD").stdout.strip()
    target = (_workspace_base(root) / f"supervisor-{int(supervisor_id)}" / key).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError("workspace_path_already_exists")
    _git(root, "worktree", "add", "--detach", str(target), base_commit)
    try:
        if _git(target, "status", "--porcelain", "--untracked-files=all").stdout.strip():
            raise RuntimeError("new_workspace_not_clean")
        with connect(root) as c:
            worker = _worker_row(c, supervisor_id, worker_key)
            cur = c.execute(
                "INSERT INTO multi_agent_workspaces(supervisor_id,worker_id,worker_key,task_id,session_id,workspace_path,base_commit,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,'provisioned',?,?)",
                (int(supervisor_id), int(worker["id"]), key, str(worker["task_id"]), str(worker["session_id"]), str(target), base_commit, human, _now()),
            )
            workspace_id = int(cur.lastrowid)
    except Exception:
        _git(root, "worktree", "remove", "--force", str(target), check=False)
        raise
    _record_event(root, "workspace_provisioned", {"worker_key": key, "base_commit": base_commit, "workspace_path_hash": _sha(str(target))}, workspace_id=workspace_id, task_id=str(worker["task_id"]), session_id=str(worker["session_id"]))
    return {"workspace_id": workspace_id, "supervisor_id": int(supervisor_id), "worker_key": key, "status": "provisioned", "base_commit": base_commit, "workspace_path": str(target)}


def workspace_binding(root: Path, task_id: str, session_id: str) -> dict[str, Any] | None:
    """Return active workspace binding for one exact worker task/session.

    Input: primary AgentOS root plus worker task/session identifiers.
    Output: active workspace binding, or None when no schema-61 workspace is bound.
    Compatibility: historical/pre-v0.27.3 databases intentionally behave as unbound.
    """
    try:
        with connect_read_only(root) as c:
            row = c.execute(
                "SELECT ws.id,ws.workspace_path,ws.status,ws.worker_key,ws.supervisor_id FROM multi_agent_workspaces ws WHERE ws.task_id=? AND ws.session_id=? AND ws.status IN ('provisioned','collected','sealed') ORDER BY ws.id DESC LIMIT 1",
                (str(task_id), str(session_id)),
            ).fetchone()
    except Exception as exc:
        if "no such table: multi_agent_workspaces" in str(exc).lower():
            return None
        raise
    if not row:
        return None
    path = Path(str(row["workspace_path"])).resolve()
    if not path.is_dir():
        raise RuntimeError("bound_workspace_missing")
    return {"workspace_id": int(row["id"]), "path": path, "status": str(row["status"]), "worker_key": str(row["worker_key"]), "supervisor_id": int(row["supervisor_id"])}


def executor_workspace_required(root: Path, task_id: str, session_id: str) -> bool:
    """Return whether schema-61 policy requires an exact executor task/session to be worktree-bound.

    Args:
        root: Primary governed repository root.
        task_id: Worker task identifier.
        session_id: Worker session identifier.
    Returns:
        True only for an assigned executor under enabled v0.27.3 workspace policy.
    """
    configured = load_policy(root).get("isolated_workspace_integration_policy", {})
    if not isinstance(configured, dict) or not configured.get("enabled", False):
        return False
    try:
        with connect_read_only(root) as c:
            row = c.execute(
                "SELECT 1 FROM multi_agent_workers w JOIN multi_agent_supervisor_runs s ON s.id=w.supervisor_id WHERE w.task_id=? AND w.session_id=? AND w.role='executor' AND w.status<>'removed' AND s.status NOT IN ('cancelled') LIMIT 1",
                (str(task_id), str(session_id)),
            ).fetchone()
    except Exception as exc:
        if "no such table" in str(exc).lower():
            return False
        raise
    return bool(row)


def workspace_execution_root(root: Path, task_id: str, session_id: str, *, for_write: bool = False) -> Path:
    """Resolve the physical execution root while keeping governance state rooted at the primary repository.

    Args:
        root: Primary governed repository root.
        task_id: Worker task identifier.
        session_id: Worker session identifier.
        for_write: Whether a write-capable route is requested.
    Returns:
        Bound worktree root for governed executors, otherwise the primary root for non-worker tasks.
    """
    binding = workspace_binding(root, task_id, session_id)
    if not binding:
        if executor_workspace_required(root, task_id, session_id):
            raise PermissionError("executor_workspace_binding_required")
        return root.resolve()
    if for_write and binding["status"] == "sealed":
        raise PermissionError("sealed_workspace_is_read_only")
    return Path(binding["path"])


def workspace_atomic_write(root: Path, task_id: str, session_id: str, target: str, content: str, expected_hash: str | None, encoding: str = "utf-8") -> dict[str, Any]:
    """Write one project-relative file into the bound worktree under primary AgentOS lease/CAS authority.

    Args:
        root: Primary governed repository root.
        task_id: Worker task identifier.
        session_id: Worker session identifier.
        target: Project-relative target path.
        content: New text content.
        expected_hash: Required current hash for existing files, or None for expected absence.
        encoding: Text encoding for the payload.
    Returns:
        Atomic write result with workspace identifier and content hashes.
    """
    root = root.resolve()
    if Path(target).is_absolute():
        raise RuntimeError("workspace_write_requires_project_relative_path")
    binding = workspace_binding(root, task_id, session_id)
    if not binding:
        raise RuntimeError("worker_workspace_binding_required")
    if binding["status"] == "sealed":
        raise PermissionError("sealed_workspace_is_read_only")
    workspace = Path(binding["path"])
    path = (workspace / target).resolve()
    rel = path.relative_to(workspace).as_posix()
    lease = acquire_resource(root, task_id, session_id, "file", rel, "exclusive_write", base_hash=expected_hash, metadata={"workspace_id": binding["workspace_id"]})
    if not lease.get("acquired"):
        return lease
    try:
        current = file_hash(path)
        if expected_hash is not None and current != expected_hash:
            return {"allowed": False, "blocked": True, "reason": "workspace_stale_write_conflict", "path": rel, "expected_hash": expected_hash, "current_hash": current, "workspace_id": binding["workspace_id"]}
        if expected_hash is None and path.exists():
            raise RuntimeError("expected_hash_required_for_existing_workspace_file")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = content.encode(encoding)
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.agentos-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as h:
                h.write(payload); h.flush(); os.fsync(h.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        digest = _sha_bytes(payload)
        with connect(root, immediate=True) as c:
            c.execute("INSERT INTO multi_agent_workspace_file_versions(workspace_id,path,previous_hash,content_hash,task_id,session_id) VALUES(?,?,?,?,?,?)", (binding["workspace_id"], rel, current, digest, str(task_id), str(session_id)))
            c.execute("DELETE FROM multi_agent_workspace_files WHERE workspace_id=?", (binding["workspace_id"],))
            c.execute("UPDATE multi_agent_workspaces SET status='provisioned',diff_manifest_hash=NULL,collected_at=NULL,sealed_at=NULL WHERE id=?", (binding["workspace_id"],))
        return {"allowed": True, "workspace_id": binding["workspace_id"], "path": rel, "previous_hash": current, "content_hash": digest, "bytes_written": len(payload), "atomic": True}
    finally:
        try: release_resource(root, int(lease["lease_id"]), task_id, session_id, "workspace_atomic_write_complete")
        except Exception: pass


def _git_blob(workspace: Path, base_commit: str, rel: str) -> bytes | None:
    proc = subprocess.run(["git", "show", f"{base_commit}:{rel}"], cwd=workspace, capture_output=True, shell=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def _scan_workspace(root: Path, row: Any) -> tuple[list[dict[str, Any]], str]:
    workspace = Path(str(row["workspace_path"])).resolve()
    base_commit = str(row["base_commit"])
    diff = _git(workspace, "diff", "--name-status", "--no-renames", "-z", base_commit, "--").stdout
    parts = diff.split("\0")
    changed: dict[str, str] = {}
    i = 0
    while i + 1 < len(parts):
        status = parts[i].strip(); rel = parts[i + 1].replace("\\", "/").strip(); i += 2
        if status and rel:
            changed[rel] = {"A": "add", "D": "delete"}.get(status[0], "modify")
    untracked = _git(workspace, "ls-files", "--others", "--exclude-standard", "-z").stdout
    for rel in [x.replace("\\", "/") for x in untracked.split("\0") if x]:
        changed[rel] = "add"
    with connect_read_only(root) as c:
        allowed = _plan_files(c, int(row["plan_id"]))
    if _policy(root).get("require_worker_plan_file_subset", True):
        outside = sorted(set(changed) - allowed)
        if outside:
            raise PermissionError("workspace_changes_outside_worker_plan:" + ",".join(outside))
    files: list[dict[str, Any]] = []
    for rel in sorted(changed):
        lexical = workspace / rel
        is_symlink = lexical.is_symlink()
        candidate = lexical.resolve()
        try: candidate.relative_to(workspace)
        except ValueError as exc: raise RuntimeError("workspace_path_escape") from exc
        if is_symlink and not _policy(root).get("symlink_changes_allowed", False):
            raise PermissionError("workspace_symlink_change_forbidden:" + rel)
        base_bytes = _git_blob(workspace, base_commit, rel)
        if is_symlink:
            current_bytes = os.readlink(lexical).encode("utf-8")
        else:
            current_bytes = candidate.read_bytes() if candidate.is_file() else None
        change = "add" if base_bytes is None and current_bytes is not None else "delete" if base_bytes is not None and current_bytes is None else "modify"
        files.append({"path": rel, "change_type": change, "base_sha256": _sha_bytes(base_bytes) if base_bytes is not None else None, "workspace_sha256": _sha_bytes(current_bytes) if current_bytes is not None else None, "size_bytes": len(current_bytes) if current_bytes is not None else None})
    manifest_hash = _sha({"base_commit": base_commit, "files": files})
    return files, manifest_hash


def collect_workspace_diff(root: Path, supervisor_id: int, worker_key: str, caller_task_id: str, caller_session_id: str) -> dict[str, Any]:
    """Collect a hash-only diff manifest for the exact worker-owned worktree.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Worker assignment key.
        caller_task_id: Worker task asserting ownership.
        caller_session_id: Worker session asserting ownership.
    Returns:
        Diff manifest hash, changed paths, count, and collection status.
    """
    root = root.resolve(); _policy(root)
    with connect(root) as c:
        row = _workspace_row(c, supervisor_id, worker_key)
        if str(row["task_id"]) != str(caller_task_id) or str(row["session_id"]) != str(caller_session_id):
            raise PermissionError("workspace_owner_mismatch")
        if str(row["status"]) not in {"provisioned", "collected"}:
            raise PermissionError("workspace_not_collectable")
        snapshot = dict(row)
    files, manifest_hash = _scan_workspace(root, snapshot)
    now = _now()
    with connect(root, immediate=True) as c:
        c.execute("DELETE FROM multi_agent_workspace_files WHERE workspace_id=?", (int(snapshot["id"]),))
        for item in files:
            c.execute("INSERT INTO multi_agent_workspace_files(workspace_id,path,change_type,base_sha256,workspace_sha256,size_bytes) VALUES(?,?,?,?,?,?)", (int(snapshot["id"]), item["path"], item["change_type"], item["base_sha256"], item["workspace_sha256"], item["size_bytes"]))
        c.execute("UPDATE multi_agent_workspaces SET status='collected',diff_manifest_hash=?,collected_at=?,sealed_at=NULL WHERE id=?", (manifest_hash, now, int(snapshot["id"])))
    _record_event(root, "workspace_diff_collected", {"worker_key": worker_key, "file_count": len(files), "diff_manifest_hash": manifest_hash}, workspace_id=int(snapshot["id"]), task_id=str(caller_task_id), session_id=str(caller_session_id))
    return {"workspace_id": int(snapshot["id"]), "worker_key": worker_key, "status": "collected", "file_count": len(files), "changed_files": [x["path"] for x in files], "diff_manifest_hash": manifest_hash}


def _candidate_gates(root: Path, workspace: Path, files: list[str]) -> dict[str, Any]:
    architecture_findings: list[dict[str, Any]] = []
    security_findings: list[dict[str, Any]] = []
    try:
        from . import architecture_structural as st
        with connect_read_only(root) as c:
            baseline = st._active_baseline(c)
            sections = st._baseline_sections(c, baseline["id"]) if baseline else {}
        if baseline:
            for rel in files:
                target = st._target_structural_check_from_sections(sections, rel)
                if not target.get("allowed", True): architecture_findings.append(target)
            architecture_findings.extend(st._coding_findings(workspace, sections, files))
            architecture_findings.extend(st._edge_findings(sections, st._repository_edges(workspace, files)))
            architecture_findings.extend(st._design_artifact_findings(workspace, sections))
    except Exception as exc:
        architecture_findings.append({"severity": "block", "finding_code": "candidate_architecture_gate_error", "message": str(exc)})
    try:
        from . import architecture_quality as aq
        with connect_read_only(root) as c:
            baseline = aq._active_baseline(c)
            sections = aq._baseline_sections(c, baseline["id"]) if baseline else {}
        if baseline:
            for rel in files:
                target = aq.architecture_quality_target_check_from_sections(sections, rel)
                if not target.get("allowed", True): security_findings.append(target)
                facts = aq._facts(workspace, rel)
                if facts is not None: security_findings.extend(aq._analyze_file_against_sections(facts, sections))
    except Exception as exc:
        security_findings.append({"severity": "block", "finding_code": "candidate_security_gate_error", "message": str(exc)})
    arch_block = [x for x in architecture_findings if str(x.get("severity", "block")) == "block" or x.get("allowed") is False]
    sec_block = [x for x in security_findings if str(x.get("severity", "block")) == "block" or x.get("allowed") is False]
    return {"architecture_status": "block" if arch_block else "pass", "security_status": "block" if sec_block else "pass", "architecture_findings": architecture_findings, "security_findings": security_findings}


def _test_receipt(root: Path, task_id: str, session_id: str, collected_at: str | None) -> dict[str, Any]:
    with connect_read_only(root) as c:
        row = c.execute("SELECT id,command_json,exit_code,created_at FROM process_exec_events WHERE task_id=? AND session_id=? AND command_profile='test' AND decision='allowed' AND success=1 ORDER BY id DESC LIMIT 1", (str(task_id), str(session_id))).fetchone()
    if not row:
        return {"status": "missing", "receipt_id": None}
    if collected_at and str(row["created_at"]) < str(collected_at).replace("T", " ").replace("+00:00", "")[:19]:
        return {"status": "stale", "receipt_id": int(row["id"])}
    return {"status": "pass", "receipt_id": int(row["id"]), "exit_code": row["exit_code"]}


def seal_workspace(root: Path, supervisor_id: int, worker_key: str, caller_task_id: str, caller_session_id: str) -> dict[str, Any]:
    """Seal an unchanged collected workspace after architecture, security, and governed-test gates pass.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Worker assignment key.
        caller_task_id: Worker task asserting ownership.
        caller_session_id: Worker session asserting ownership.
    Returns:
        Sealed workspace status and gate outcomes.
    """
    root = root.resolve(); policy = _policy(root)
    with connect_read_only(root) as c:
        row = dict(_workspace_row(c, supervisor_id, worker_key))
        stored_files = [dict(r) for r in c.execute("SELECT * FROM multi_agent_workspace_files WHERE workspace_id=? ORDER BY path", (int(row["id"]),)).fetchall()]
    if str(row["task_id"]) != str(caller_task_id) or str(row["session_id"]) != str(caller_session_id): raise PermissionError("workspace_owner_mismatch")
    if str(row["status"]) != "collected": raise PermissionError("workspace_must_be_collected_before_seal")
    current_files, current_hash = _scan_workspace(root, row)
    if current_hash != str(row["diff_manifest_hash"]): raise PermissionError("workspace_changed_after_diff_collection")
    changed = [x["path"] for x in current_files]
    gates = _candidate_gates(root, Path(str(row["workspace_path"])), changed)
    test = _test_receipt(root, str(row["task_id"]), str(row["session_id"]), str(row["collected_at"] or ""))
    if policy.get("require_architecture_candidate_gate", True) and gates["architecture_status"] == "block": raise PermissionError("workspace_architecture_gate_blocked")
    if policy.get("require_security_candidate_gate", True) and gates["security_status"] == "block": raise PermissionError("workspace_security_gate_blocked")
    if policy.get("require_test_receipt_after_collection", True) and test["status"] != "pass": raise PermissionError("workspace_test_gate_not_satisfied:" + test["status"])
    with connect(root) as c:
        c.execute("UPDATE multi_agent_workspaces SET status='sealed',sealed_at=? WHERE id=?", (_now(), int(row["id"])))
    _record_event(root, "workspace_sealed", {"worker_key": worker_key, "diff_manifest_hash": current_hash, "architecture_status": gates["architecture_status"], "security_status": gates["security_status"], "test_status": test["status"], "test_receipt_id": test.get("receipt_id")}, workspace_id=int(row["id"]), task_id=str(caller_task_id), session_id=str(caller_session_id))
    return {"workspace_id": int(row["id"]), "worker_key": worker_key, "status": "sealed", "diff_manifest_hash": current_hash, "architecture_status": gates["architecture_status"], "security_status": gates["security_status"], "test_status": test["status"]}


def require_executor_workspace(root: Path, supervisor_id: int, worker_key: str, *, sealed: bool = False) -> None:
    """Require an executor worker to have an available or sealed isolated workspace.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Worker assignment key.
        sealed: When True, require immutable sealed status before worker completion.
    Returns:
        None. Raises PermissionError when the workspace requirement is not met.
    """
    with connect_read_only(root) as c:
        worker = _worker_row(c, supervisor_id, worker_key)
        if str(worker["role"]) != "executor": return
        row = c.execute("SELECT status FROM multi_agent_workspaces WHERE worker_id=?", (int(worker["id"]),)).fetchone()
    if not row: raise PermissionError("executor_workspace_required")
    status = str(row[0])
    if sealed and status != "sealed": raise PermissionError("executor_workspace_must_be_sealed")
    if not sealed and status not in {"provisioned", "collected", "sealed"}: raise PermissionError("executor_workspace_not_available")


def _primary_path_changed_since_base(root: Path, base_commit: str, rel: str) -> bool:
    """Return whether one primary path differs from the workspace base under Git semantics.

    Args:
        root: Primary Git repository root.
        base_commit: Commit pinned when the isolated workspace was provisioned.
        rel: Project-relative path to compare.
    Returns:
        True when Git reports a semantic change relative to the pinned base commit.

    Notes:
        Git, not raw worktree bytes, is the conflict authority. This avoids false
        conflicts when clean/smudge or EOL normalization makes a clean Windows
        worktree byte-different from the canonical Git blob. Raw SHA-256 hashes
        remain evidence/CAS metadata but are not used as cross-platform drift truth.
    """
    base = root.resolve()
    path = (base / rel).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise RuntimeError("primary_conflict_path_escape") from exc
    proc = _git(
        base,
        "diff",
        "--quiet",
        "--no-ext-diff",
        "--no-textconv",
        str(base_commit),
        "--",
        str(rel),
        check=False,
    )
    if proc.returncode == 0:
        return False
    if proc.returncode == 1:
        return True
    detail = (proc.stderr or proc.stdout or "").strip()
    raise RuntimeError("git_primary_conflict_check_failed:" + detail)


def _conflicts(root: Path, workspace_id: int) -> list[dict[str, Any]]:
    with connect_read_only(root) as c:
        workspace = c.execute("SELECT base_commit FROM multi_agent_workspaces WHERE id=?", (int(workspace_id),)).fetchone()
        if not workspace:
            raise ValueError("workspace_not_found")
        base_commit = str(workspace["base_commit"])
        files = [dict(r) for r in c.execute("SELECT * FROM multi_agent_workspace_files WHERE workspace_id=? ORDER BY path", (int(workspace_id),)).fetchall()]
    conflicts = []
    for item in files:
        path = (root / item["path"]).resolve(); path.relative_to(root.resolve())
        current = file_hash(path)
        if item["change_type"] == "add":
            if current is not None:
                conflicts.append({"path": item["path"], "reason": "target_exists", "current_hash": current})
            continue
        if _primary_path_changed_since_base(root, base_commit, str(item["path"])):
            conflicts.append({
                "path": item["path"],
                "reason": "primary_changed_since_workspace_base",
                "base_commit": base_commit,
                "base_blob_sha256": item["base_sha256"],
                "current_hash": current,
                "git_semantic_diff": True,
            })
    return conflicts


def create_integration_proposal(root: Path, supervisor_id: int, worker_key: str, created_by: str) -> dict[str, Any]:
    """Create a controlled integration proposal from a completed worker's sealed workspace.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Completed worker assignment key.
        created_by: Human operator identity.
    Returns:
        Draft proposal identity, pinned hashes, gate states, and conflict findings.
    """
    root = root.resolve(); human = _human(created_by); _policy(root)
    with connect_read_only(root) as c:
        ws = dict(_workspace_row(c, supervisor_id, worker_key))
        if str(ws["status"]) != "sealed": raise PermissionError("sealed_workspace_required_for_integration_proposal")
        if str(ws["worker_status"]) != "completed": raise PermissionError("completed_worker_required_for_integration_proposal")
    files, manifest_hash = _scan_workspace(root, ws)
    if manifest_hash != str(ws["diff_manifest_hash"]): raise PermissionError("sealed_workspace_changed")
    gates = _candidate_gates(root, Path(str(ws["workspace_path"])), [x["path"] for x in files])
    test = _test_receipt(root, str(ws["task_id"]), str(ws["session_id"]), str(ws["collected_at"] or ""))
    conflicts = _conflicts(root, int(ws["id"]))
    statuses = {"conflict_status": "block" if conflicts else "pass", "architecture_status": gates["architecture_status"], "security_status": gates["security_status"], "test_status": test["status"]}
    proposal_payload = {"workspace_id": int(ws["id"]), "supervisor_id": int(supervisor_id), "worker_id": int(ws["worker_id"]), "parent_task_id": str(ws["parent_task_id"]), "base_commit": str(ws["base_commit"]), "diff_manifest_hash": manifest_hash, **statuses}
    proposal_hash = _sha(proposal_payload)
    with connect(root) as c:
        cur = c.execute("INSERT INTO multi_agent_integration_proposals(workspace_id,supervisor_id,worker_id,parent_task_id,base_commit,diff_manifest_hash,status,conflict_status,architecture_status,security_status,test_status,proposal_hash,created_by,created_at) VALUES(?,?,?,?,?,?,'draft',?,?,?,?,?,?,?)", (int(ws["id"]), int(supervisor_id), int(ws["worker_id"]), str(ws["parent_task_id"]), str(ws["base_commit"]), manifest_hash, statuses["conflict_status"], statuses["architecture_status"], statuses["security_status"], statuses["test_status"], proposal_hash, human, _now()))
        pid = int(cur.lastrowid)
    _record_event(root, "integration_proposal_created", {"proposal_hash": proposal_hash, **statuses, "conflict_count": len(conflicts)}, proposal_id=pid, workspace_id=int(ws["id"]), task_id=str(ws["parent_task_id"]))
    return {"proposal_id": pid, "status": "draft", "proposal_hash": proposal_hash, **statuses, "conflicts": conflicts}


def integration_readiness(root: Path, proposal_id: int) -> dict[str, Any]:
    """Re-evaluate immutable diff and primary conflict readiness for one integration proposal.

    Args:
        root: Primary governed repository root.
        proposal_id: Controlled integration proposal identifier.
    Returns:
        Read-only readiness, reasons, conflicts, and current diff hash.
    """
    with connect_read_only(root) as c:
        row = c.execute("SELECT p.*,ws.workspace_path,ws.status AS workspace_status,ws.task_id AS worker_task_id,ws.session_id AS worker_session_id,w.plan_id,w.plan_hash,w.architecture_baseline_hash,w.status AS worker_status FROM multi_agent_integration_proposals p JOIN multi_agent_workspaces ws ON ws.id=p.workspace_id JOIN multi_agent_workers w ON w.id=p.worker_id WHERE p.id=?", (int(proposal_id),)).fetchone()
        if not row: raise ValueError("integration_proposal_not_found")
        row = dict(row)
    files, current_hash = _scan_workspace(root, row)
    conflicts = _conflicts(root, int(row["workspace_id"]))
    reasons = []
    if str(row["workspace_status"]) != "sealed": reasons.append("workspace_not_sealed")
    if current_hash != str(row["diff_manifest_hash"]): reasons.append("workspace_diff_changed")
    if conflicts: reasons.append("primary_conflict")
    for key in ("architecture_status", "security_status", "test_status"):
        if str(row[key]) != "pass": reasons.append(key + "_not_pass")
    return {"proposal_id": int(proposal_id), "status": str(row["status"]), "ready": not reasons, "reasons": reasons, "conflicts": conflicts, "file_count": len(files), "diff_manifest_hash": current_hash}


def review_integration(root: Path, proposal_id: int, reviewed_by: str) -> dict[str, Any]:
    """Record mandatory human review for a ready draft integration proposal.

    Args:
        root: Primary governed repository root.
        proposal_id: Draft integration proposal identifier.
        reviewed_by: Human reviewer identity.
    Returns:
        Reviewed proposal status.
    """
    human = _human(reviewed_by); ready = integration_readiness(root, proposal_id)
    if not ready["ready"]: raise PermissionError("integration_not_reviewable:" + ";".join(ready["reasons"]))
    with connect(root) as c:
        row = c.execute("SELECT status,workspace_id,parent_task_id FROM multi_agent_integration_proposals WHERE id=?", (int(proposal_id),)).fetchone()
        if not row or str(row["status"]) != "draft": raise PermissionError("integration_proposal_not_draft")
        c.execute("UPDATE multi_agent_integration_proposals SET status='reviewed',reviewed_by=?,reviewed_at=? WHERE id=?", (human, _now(), int(proposal_id)))
    _record_event(root, "integration_reviewed", {"reviewed_by": human}, proposal_id=int(proposal_id), workspace_id=int(row["workspace_id"]), task_id=str(row["parent_task_id"]))
    return {"proposal_id": int(proposal_id), "status": "reviewed", "reviewed_by": human}


def approve_integration(root: Path, proposal_id: int, approved_by: str) -> dict[str, Any]:
    """Record mandatory human approval for a reviewed and still-ready integration proposal.

    Args:
        root: Primary governed repository root.
        proposal_id: Reviewed integration proposal identifier.
        approved_by: Human approver identity.
    Returns:
        Approved proposal status.
    """
    human = _human(approved_by); ready = integration_readiness(root, proposal_id)
    if not ready["ready"]: raise PermissionError("integration_not_approvable:" + ";".join(ready["reasons"]))
    with connect(root) as c:
        row = c.execute("SELECT status,workspace_id,parent_task_id FROM multi_agent_integration_proposals WHERE id=?", (int(proposal_id),)).fetchone()
        if not row or str(row["status"]) != "reviewed": raise PermissionError("integration_proposal_not_reviewed")
        c.execute("UPDATE multi_agent_integration_proposals SET status='approved',approved_by=?,approved_at=? WHERE id=?", (human, _now(), int(proposal_id)))
    _record_event(root, "integration_approved", {"approved_by": human}, proposal_id=int(proposal_id), workspace_id=int(row["workspace_id"]), task_id=str(row["parent_task_id"]))
    return {"proposal_id": int(proposal_id), "status": "approved", "approved_by": human}


def reject_integration(root: Path, proposal_id: int, rejected_by: str) -> dict[str, Any]:
    """Reject a draft or reviewed integration proposal under explicit human authority.

    Args:
        root: Primary governed repository root.
        proposal_id: Integration proposal identifier.
        rejected_by: Human operator identity.
    Returns:
        Rejected proposal status.
    """
    human = _human(rejected_by)
    with connect(root) as c:
        row = c.execute("SELECT status,workspace_id,parent_task_id FROM multi_agent_integration_proposals WHERE id=?", (int(proposal_id),)).fetchone()
        if not row or str(row["status"]) not in {"draft", "reviewed"}: raise PermissionError("integration_proposal_not_rejectable")
        c.execute("UPDATE multi_agent_integration_proposals SET status='rejected',reviewed_by=COALESCE(reviewed_by,?),reviewed_at=COALESCE(reviewed_at,?) WHERE id=?", (human, _now(), int(proposal_id)))
    _record_event(root, "integration_rejected", {"rejected_by": human}, proposal_id=int(proposal_id), workspace_id=int(row["workspace_id"]), task_id=str(row["parent_task_id"]))
    return {"proposal_id": int(proposal_id), "status": "rejected"}


def _atomic_replace_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.agentos-integrate-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as h: h.write(payload); h.flush(); os.fsync(h.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def apply_integration(root: Path, proposal_id: int, applied_by: str, caller_task_id: str, caller_session_id: str) -> dict[str, Any]:
    """Apply an approved proposal using parent-task scope, CAS, leases, backup, and rollback without Git merge.

    Args:
        root: Primary governed repository root.
        proposal_id: Approved integration proposal identifier.
        applied_by: Human operator identity.
        caller_task_id: Parent task carrying integration authority.
        caller_session_id: Owning parent-task session.
    Returns:
        Applied status, file count, and explicit no-automatic-merge evidence.
    """
    root = root.resolve(); human = _human(applied_by); policy = _policy(root)
    ready = integration_readiness(root, proposal_id)
    if not ready["ready"]: raise PermissionError("integration_not_ready:" + ";".join(ready["reasons"]))
    with connect_read_only(root) as c:
        p = c.execute("SELECT p.*,ws.workspace_path,ws.task_id AS worker_task_id,ws.session_id AS worker_session_id FROM multi_agent_integration_proposals p JOIN multi_agent_workspaces ws ON ws.id=p.workspace_id WHERE p.id=?", (int(proposal_id),)).fetchone()
        if not p or str(p["status"]) != "approved": raise PermissionError("integration_proposal_not_approved")
        if str(p["parent_task_id"]) != str(caller_task_id): raise PermissionError("integration_parent_task_context_required")
        task = c.execute("SELECT owner_session_id FROM tasks WHERE id=?", (str(caller_task_id),)).fetchone()
        if task and task["owner_session_id"] and str(task["owner_session_id"]) != str(caller_session_id): raise PermissionError("integration_parent_session_owner_mismatch")
        files = [dict(r) for r in c.execute("SELECT * FROM multi_agent_workspace_files WHERE workspace_id=? ORDER BY path", (int(p["workspace_id"]),)).fetchall()]
    workspace = Path(str(p["workspace_path"])).resolve()
    leases = []
    backup_root = root / ".agents" / "runtime" / "integration-v0273" / f"proposal-{int(proposal_id)}"
    backup_root.mkdir(parents=True, exist_ok=True)
    backups: dict[str, bytes | None] = {}
    try:
        from .core import check_write
        for item in files:
            scope = check_write(root, str(caller_task_id), str(item["path"]))
            if not scope.get("allowed"):
                raise PermissionError("integration_parent_scope_blocked:" + str(item["path"]) + ":" + str(scope.get("reason")))
            lease = acquire_resource(root, str(caller_task_id), str(caller_session_id), "file", item["path"], "exclusive_write", base_hash=item["base_sha256"], metadata={"integration_proposal_id": int(proposal_id)})
            if not lease.get("acquired"): raise PermissionError("integration_resource_lease_conflict:" + item["path"])
            leases.append(int(lease["lease_id"]))
        # Recheck after all leases are held.
        conflicts = _conflicts(root, int(p["workspace_id"]))
        if conflicts: raise PermissionError("integration_conflict_after_lease")
        backup_manifest: list[dict[str, Any]] = []
        backup_files_root = backup_root / "files"
        backup_files_root.mkdir(parents=True, exist_ok=True)
        for item in files:
            target = (root / item["path"]).resolve(); target.relative_to(root)
            existing = target.read_bytes() if target.is_file() else None
            backups[item["path"]] = existing
            entry = {
                "path": str(item["path"]),
                "existed": existing is not None,
                "sha256": _sha_bytes(existing) if existing is not None else None,
            }
            backup_manifest.append(entry)
            if existing is not None:
                backup_target = (backup_files_root / str(item["path"])).resolve()
                backup_target.relative_to(backup_files_root.resolve())
                _atomic_replace_bytes(backup_target, existing)
                try:
                    os.chmod(backup_target, 0o600)
                except OSError:
                    pass
        manifest_path = backup_root / "manifest.json"
        _atomic_replace_bytes(
            manifest_path,
            json.dumps(
                {
                    "proposal_id": int(proposal_id),
                    "created_at": _now(),
                    "files": backup_manifest,
                },
                sort_keys=True,
                indent=2,
            ).encode("utf-8") + b"\n",
        )
        try:
            os.chmod(backup_root, 0o700)
            os.chmod(backup_files_root, 0o700)
            os.chmod(manifest_path, 0o600)
        except OSError:
            pass
        for item in files:
            target = (root / item["path"]).resolve(); source = (workspace / item["path"]).resolve(); source.relative_to(workspace)
            if item["change_type"] == "delete":
                if target.exists(): target.unlink()
            else:
                payload = source.read_bytes()
                if _sha_bytes(payload) != str(item["workspace_sha256"]): raise PermissionError("workspace_content_hash_changed:" + item["path"])
                _atomic_replace_bytes(target, payload)
        with connect(root) as c:
            c.execute("UPDATE multi_agent_integration_proposals SET status='applied',applied_by=?,applied_at=? WHERE id=?", (human, _now(), int(proposal_id)))
        _record_event(root, "integration_applied", {"applied_by": human, "file_count": len(files), "automatic_merge": False, "git_merge_invoked": False}, proposal_id=int(proposal_id), workspace_id=int(p["workspace_id"]), task_id=str(caller_task_id), session_id=str(caller_session_id))
        return {"proposal_id": int(proposal_id), "status": "applied", "applied_by": human, "file_count": len(files), "automatic_merge": False, "git_merge_invoked": False}
    except Exception:
        for rel, data in backups.items():
            target = (root / rel).resolve()
            try:
                if data is None:
                    if target.exists(): target.unlink()
                else:
                    _atomic_replace_bytes(target, data)
            except Exception:
                pass
        with connect(root) as c:
            c.execute("UPDATE multi_agent_integration_proposals SET status='failed' WHERE id=? AND status='approved'", (int(proposal_id),))
        raise
    finally:
        for lid in reversed(leases):
            try: release_resource(root, lid, str(caller_task_id), str(caller_session_id), "controlled_integration_complete")
            except Exception: pass


def release_workspace(root: Path, supervisor_id: int, worker_key: str, released_by: str) -> dict[str, Any]:
    """Remove a worker worktree after pending integration proposals are cleared.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Worker assignment key.
        released_by: Human operator identity.
    Returns:
        Released workspace status.
    """
    root = _repo_root(root); human = _human(released_by)
    with connect_read_only(root) as c:
        ws = dict(_workspace_row(c, supervisor_id, worker_key))
        pending = c.execute("SELECT COUNT(*) FROM multi_agent_integration_proposals WHERE workspace_id=? AND status IN ('draft','reviewed','approved')", (int(ws["id"]),)).fetchone()[0]
        if int(pending): raise PermissionError("workspace_has_pending_integration_proposal")
    path = Path(str(ws["workspace_path"]))
    _git(root, "worktree", "remove", "--force", str(path), check=False)
    with connect(root) as c:
        c.execute("UPDATE multi_agent_workspaces SET status='released',released_at=? WHERE id=?", (_now(), int(ws["id"])))
    _record_event(root, "workspace_released", {"released_by": human, "workspace_path_hash": _sha(str(path))}, workspace_id=int(ws["id"]), task_id=str(ws["task_id"]), session_id=str(ws["session_id"]))
    return {"workspace_id": int(ws["id"]), "status": "released", "worker_key": worker_key}


def workspace_status(root: Path, supervisor_id: int, worker_key: str) -> dict[str, Any]:
    """Return redacted workspace state, diff paths, and hashes without exposing its physical path.

    Args:
        root: Primary governed repository root.
        supervisor_id: Supervisor run identifier.
        worker_key: Worker assignment key.
    Returns:
        Privacy-safe workspace status suitable for CLI/MCP inspection.
    """
    with connect_read_only(root) as c:
        row = dict(_workspace_row(c, supervisor_id, worker_key))
        files = [dict(r) for r in c.execute("SELECT path,change_type,base_sha256,workspace_sha256,size_bytes FROM multi_agent_workspace_files WHERE workspace_id=? ORDER BY path", (int(row["id"]),)).fetchall()]
    return {"workspace_id": int(row["id"]), "supervisor_id": int(supervisor_id), "worker_key": worker_key, "task_id": str(row["task_id"]), "status": str(row["status"]), "base_commit": str(row["base_commit"]), "workspace_path_hash": _sha(str(row["workspace_path"])), "diff_manifest_hash": row["diff_manifest_hash"], "files": files, "physical_path_exposed": False}


def integration_status(root: Path, proposal_id: int) -> dict[str, Any]:
    """Return redacted controlled-integration proposal state plus current readiness.

    Args:
        root: Primary governed repository root.
        proposal_id: Integration proposal identifier.
    Returns:
        Proposal metadata and readiness without mutation authority.
    """
    ready = integration_readiness(root, proposal_id)
    with connect_read_only(root) as c:
        row = dict(c.execute("SELECT id,workspace_id,supervisor_id,worker_id,parent_task_id,status,proposal_hash,created_by,reviewed_by,approved_by,applied_by,created_at,reviewed_at,approved_at,applied_at FROM multi_agent_integration_proposals WHERE id=?", (int(proposal_id),)).fetchone())
    return {**row, "readiness": ready}
