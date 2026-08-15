"""
File: .agents/agentos/governance_enforcement.py

Purpose:
    Enforce one task/session-bound governance lifecycle for privileged AgentOS domain mutations.

Responsibilities:
    - Validate approved task ownership, workflow approval, policy, baseline, and drift before mutation.
    - Issue and consume one-time guarded-execution tokens for each business operation.
    - Correlate domain events with one governed operation identifier.
    - Mirror privacy-safe domain events to the Ed25519 external signed audit chain.
    - Fail closed when signed audit evidence cannot be produced.
"""
from __future__ import annotations

import contextvars
import functools
import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from .db import connect
from .drift import drift_check
from .external_audit import append_signed_event
from .policy import load_policy, local_override_status
from .tooling import append_audit_event, complete_tool, guard_tool, redact_value

T = TypeVar("T")


class GovernanceEnforcementError(RuntimeError):
    """Raised when a privileged domain operation is outside the governance boundary."""


@dataclass
class OperationContext:
    """Runtime correlation state for one governed business operation."""
    root: Path
    task_id: str
    session_id: str
    capability: str
    operation_id: str
    intent: dict[str, Any]
    domain_events: list[dict[str, Any]] = field(default_factory=list)


_CURRENT: contextvars.ContextVar[OperationContext | None] = contextvars.ContextVar("agentos_governed_operation", default=None)


def _is_agentos_project(root: Path) -> bool:
    return (root / "AGENTS.md").is_file() and (root / "VERSION").is_file() and (root / ".agents/config/governance.json").is_file()


def _json_safe(value: Any) -> Any:
    if callable(value):
        return "[CALLABLE]"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return f"[{type(value).__name__}]"


def _intent(fn_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return redact_value({"function": fn_name, "args": _json_safe(args[1:]), "kwargs": _json_safe(kwargs)})


def _intent_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _approved_step(root: Path, task_id: str) -> bool:
    """Return whether the explicit approve_task workflow gate is already complete without mutating workflow state."""
    with connect(root) as conn:
        row = conn.execute(
            "SELECT status FROM workflow_steps WHERE task_id=? AND workflow_name='default' AND step_name='approve_task'",
            (task_id,),
        ).fetchone()
    return bool(row and row["status"] == "done")


def _preflight(root: Path, task_id: str, session_id: str, capability: str) -> None:
    policy = load_policy(root)
    cfg = policy["governance_enforcement_policy"]
    allowed = set(cfg.get("privileged_capabilities", []))
    if capability not in allowed:
        raise GovernanceEnforcementError(f"capability_not_registered:{capability}")
    with connect(root) as conn:
        task = conn.execute("SELECT approved,owner_session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        raise GovernanceEnforcementError(f"task_not_found:{task_id}")
    preapproval_human_capabilities = {"human.decision.resolve"}
    if capability not in preapproval_human_capabilities:
        if not bool(task["approved"]):
            raise GovernanceEnforcementError("task_not_approved")
        if cfg.get("require_task_owner_session", True) and task["owner_session_id"] != session_id:
            raise GovernanceEnforcementError("task_not_owned_by_session")
        if cfg.get("require_workflow_approval_step", True) and not _approved_step(root, task_id):
            raise GovernanceEnforcementError("workflow_approve_task_incomplete")
    unblocker_capabilities = {
        "human.decision.resolve",
        "architecture.baseline.review", "architecture.baseline.approve",
        "architecture.baseline.activate", "architecture.baseline.reject",
    }
    if capability not in unblocker_capabilities:
        from .human_decision import clarity_gate_status, decision_gate_status
        if not clarity_gate_status(root, task_id)["ready"]:
            raise GovernanceEnforcementError("clarity_gate_pending")
        if decision_gate_status(root, task_id)["blocked"]:
            raise GovernanceEnforcementError("human_decision_pending")
    override = local_override_status(root)
    if override.get("sensitive") and override.get("status") != "approved":
        raise GovernanceEnforcementError("sensitive_local_override_not_approved")
    drift = drift_check(root, task_id=task_id)
    if cfg.get("require_initialized_baseline", True) and drift.get("baseline_state") != "initialized":
        raise GovernanceEnforcementError("governance_baseline_not_initialized")
    if cfg.get("block_on_drift", True) and drift.get("drift_detected"):
        raise GovernanceEnforcementError("unacknowledged_governance_drift")


def _audit_denial(root: Path, task_id: str, session_id: str, capability: str, intent: dict[str, Any], reason: str) -> None:
    payload = {"capability": capability, "intent_hash": _intent_hash(intent), "reason": reason, "decision": "denied"}
    append_audit_event(root, "governed_operation.denied", payload, task_id, session_id)
    append_signed_event(root, "governed_operation.denied", payload, task_id, session_id)


@contextmanager
def governed_operation(root: Path, task_id: str, session_id: str, capability: str, intent: dict[str, Any]) -> Iterator[OperationContext]:
    """Open one fail-closed governance lifecycle around a privileged business operation."""
    root = root.resolve()
    try:
        _preflight(root, task_id, session_id, capability)
    except Exception as exc:
        try:
            _audit_denial(root, task_id, session_id, capability, intent, str(exc))
        finally:
            raise
    guard_args = {"capability": capability, "intent_hash": _intent_hash(intent)}
    guard = guard_tool(root, task_id, session_id, "governed_operation", guard_args)
    if not guard.get("allowed") or not guard.get("execution_token"):
        reason = str(guard.get("reason") or "governed_operation_guard_denied")
        _audit_denial(root, task_id, session_id, capability, intent, reason)
        raise GovernanceEnforcementError(reason)
    operation_id = secrets.token_hex(16)
    token_hash = hashlib.sha256(str(guard["execution_token"]).encode()).hexdigest()
    request_payload = {"operation_id": operation_id, "capability": capability, "intent_hash": guard_args["intent_hash"], "decision": "allowed"}
    append_audit_event(root, "governed_operation.request", request_payload, task_id, session_id)
    signed_request = append_signed_event(root, "governed_operation.request", request_payload, task_id, session_id)
    with connect(root) as conn:
        conn.execute(
            "INSERT INTO governed_operations(operation_id,task_id,session_id,capability,intent_hash,execution_token_hash,status,external_request_hash) VALUES(?,?,?,?,?,?,?,?)",
            (operation_id, task_id, session_id, capability, guard_args["intent_hash"], token_hash, "running", signed_request["event_hash"]),
        )
    ctx = OperationContext(root=root, task_id=task_id, session_id=session_id, capability=capability, operation_id=operation_id, intent=intent)
    token = _CURRENT.set(ctx)
    success = False
    try:
        yield ctx
        success = True
    except Exception as exc:
        outcome = {"operation_id": operation_id, "capability": capability, "success": False, "error_type": type(exc).__name__}
        for event in ctx.domain_events:
            append_audit_event(root, "governed_operation.domain_event", {**event, "operation_success": False}, task_id, session_id)
        complete_tool(root, str(guard["execution_token"]), guard_args, False, f"{capability} failed: {type(exc).__name__}", session_id)
        signed = append_signed_event(root, "governed_operation.completed", outcome, task_id, session_id)
        with connect(root) as conn:
            conn.execute("UPDATE governed_operations SET status='failed',success=0,completed_at=CURRENT_TIMESTAMP,external_completion_hash=? WHERE operation_id=?", (signed["event_hash"], operation_id))
        raise
    finally:
        _CURRENT.reset(token)
    if success:
        for event in ctx.domain_events:
            append_audit_event(root, "governed_operation.domain_event", {**event, "operation_success": True}, task_id, session_id)
        complete_tool(root, str(guard["execution_token"]), guard_args, True, f"{capability} completed", session_id)
        outcome = {"operation_id": operation_id, "capability": capability, "success": True, "domain_event_count": len(ctx.domain_events)}
        signed = append_signed_event(root, "governed_operation.completed", outcome, task_id, session_id)
        with connect(root) as conn:
            conn.execute("UPDATE governed_operations SET status='completed',success=1,completed_at=CURRENT_TIMESTAMP,external_completion_hash=? WHERE operation_id=?", (signed["event_hash"], operation_id))


def mirror_domain_event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Mirror one domain event to signed audit and return correlation columns for the local event row."""
    ctx = _CURRENT.get()
    if ctx is None:
        return {"governed_operation_id": None, "external_event_hash": None}
    clean = redact_value(payload)
    signed_payload = {"operation_id": ctx.operation_id, "capability": ctx.capability, "domain_event_type": event_type, "payload": clean}
    signed = append_signed_event(ctx.root, "governed_operation.domain_event", signed_payload, ctx.task_id, ctx.session_id)
    ctx.domain_events.append({"operation_id": ctx.operation_id, "capability": ctx.capability, "domain_event_type": event_type, "payload": clean, "external_event_hash": signed["event_hash"]})
    return {"governed_operation_id": ctx.operation_id, "external_event_hash": signed["event_hash"]}


def governed_mutation(capability: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a public state mutation so valid AgentOS projects require governed task/session context.

    Library-style minimal roots used by isolated domain unit tests remain supported; production AgentOS roots
    are identified by AGENTS.md + VERSION + governance.json and always fail closed without context.
    """
    def decorate(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> T:
            root_value = args[0] if args else kwargs.get("root")
            if root_value is None:
                raise GovernanceEnforcementError("root_argument_required")
            root = Path(root_value).resolve()
            active = _CURRENT.get()
            explicit_task = kwargs.pop("task_id", None)
            explicit_session = kwargs.pop("session_id", None)
            if active is not None:
                if explicit_task and explicit_task != active.task_id:
                    raise GovernanceEnforcementError("nested_task_context_mismatch")
                if explicit_session and explicit_session != active.session_id:
                    raise GovernanceEnforcementError("nested_session_context_mismatch")
                return fn(*args, **kwargs)
            if not _is_agentos_project(root):
                return fn(*args, **kwargs)
            task_id = str(explicit_task or os.environ.get("AGENTOS_TASK_ID", "")).strip()
            session_id = str(explicit_session or os.environ.get("AGENTOS_SESSION_ID", "")).strip()
            if not task_id or not session_id:
                raise GovernanceEnforcementError("task_id_and_session_id_required")
            intent = _intent(fn.__name__, args, kwargs)
            with governed_operation(root, task_id, session_id, capability, intent):
                return fn(*args, **kwargs)
        return wrapped
    return decorate


def governed_operation_status(root: Path, operation_id: str) -> dict[str, Any]:
    """Return redacted read-only status for a governed operation."""
    with connect(root) as conn:
        row = conn.execute("SELECT operation_id,task_id,session_id,capability,intent_hash,status,denial_reason,external_request_hash,external_completion_hash,success,started_at,completed_at FROM governed_operations WHERE operation_id=?", (operation_id,)).fetchone()
    if not row:
        raise GovernanceEnforcementError("governed_operation_not_found")
    return dict(row)
