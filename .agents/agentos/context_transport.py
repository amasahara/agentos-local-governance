"""
File: .agents/agentos/context_transport.py

Purpose:
    Compile canonical AgentOS context into requirement-preserving, token-budgeted
    transport packages for LLM consumption without delegating summarization authority
    to an LLM.

Responsibilities:
    - Preserve the original user request and protected authority/control content losslessly.
    - Build a stable extractive Requirement Ledger.
    - Deterministically compress only the evidence plane.
    - Enforce tokenizer/model budgets with fail-closed protected-content handling.
    - Persist auditable transport manifests, expansion handles, and evaluation metrics.
    - Verify source freshness, authority hashes, plan/scope hashes, and transport integrity.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .context_runtime import context_status
from .db import connect
from .planning import active_plan
from .policy import load_policy

MIGRATION_VERSION = 44
TRANSPORT_VERSION = 1

REQUIREMENT_KINDS = (
    "objective",
    "constraint",
    "prohibition",
    "deliverable",
    "acceptance_criterion",
)

DEFAULT_MODEL_PROFILES: dict[str, dict[str, int | str]] = {
    "generic-16k": {"context_capacity": 16384, "tokenizer": "auto"},
    "generic-32k": {"context_capacity": 32768, "tokenizer": "auto"},
    "generic-64k": {"context_capacity": 65536, "tokenizer": "auto"},
    "generic-128k": {"context_capacity": 131072, "tokenizer": "auto"},
    "generic-200k": {"context_capacity": 200000, "tokenizer": "auto"},
}

CRITICAL_POLICY_SECTIONS = (
    "instruction_policy",
    "filesystem_policy",
    "tool_policy",
    "proxy_policy",
    "external_audit_policy",
    "knowledge_runtime",
    "multi_agent_policy",
    "controlled_target_insert_policy",
    "identity_resolution_policy",
    "reconciliation_recovery_policy",
    "secret_resolver_policy",
    "lineage_key_lifecycle_policy",
    "data_subject_rights_policy",
    "privacy_boundary_policy",
    "context_transport_policy",
)

PROHIBITION_PATTERNS = (
    r"\bkh[oô]ng\s+(?:được|cho phép|được phép|bao giờ|tự)\b",
    r"\bcấm\b",
    r"\btuyệt đối không\b",
    r"\bforbid(?:den)?\b",
    r"\bmust not\b",
    r"\bdo not\b",
    r"\bnever\b",
    r"\bblocked\b",
)
CONSTRAINT_PATTERNS = (
    r"\bphải\b",
    r"\bbắt buộc\b",
    r"\bchỉ\b",
    r"\bgiữ nguyên\b",
    r"\bđảm bảo\b",
    r"\brequire(?:d)?\b",
    r"\bmust\b",
    r"\bonly\b",
    r"\bpreserve\b",
)
DELIVERABLE_PATTERNS = (
    r"\bcập nhật\b",
    r"\bbổ sung\b",
    r"\btạo\b",
    r"\btriển khai\b",
    r"\bxây\b",
    r"\bupdate\b",
    r"\badd\b",
    r"\bimplement\b",
    r"\bbuild\b",
)
ACCEPTANCE_PATTERNS = (
    r"\bmục tiêu\b",
    r"\bacceptance\b",
    r"\bpass\b",
    r"\b100%\b",
    r"\b2\s*[–-]\s*4x\b",
    r"\b2\s*[-–]\s*4\s*x\b",
)


class ContextTransportError(RuntimeError):
    """Raised when a transport package cannot be produced or verified safely."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _nowless_transport_hash(manifest: dict[str, Any]) -> str:
    """Hash transport content while excluding lifecycle fields and the self-check flag.

    The integrity flag is derived by recomputing this hash and therefore cannot
    participate in its own digest. All other preservation-gate fields remain
    covered by the transport hash.
    """
    payload = json.loads(json.dumps(manifest))
    payload.pop("transport_hash", None)
    payload.pop("status", None)
    gate = payload.get("preservation_gate")
    if isinstance(gate, dict):
        gate.pop("transport_integrity", None)
    return _sha256_text(_canonical_json(payload))


def _file_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _file_hash(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _task_row(root: Path, task_id: str) -> dict[str, Any]:
    with connect(root) as c:
        row = c.execute(
            "SELECT id,request,approved_scope,approved,task_state FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    if not row:
        raise ContextTransportError(f"task_not_found:{task_id}")
    return dict(row)


def _policy(root: Path) -> dict[str, Any]:
    return load_policy(root)


def _transport_policy(root: Path) -> dict[str, Any]:
    cfg = _policy(root).get("context_transport_policy", {})
    return cfg if isinstance(cfg, dict) else {}


def migration_44(c: Any) -> None:
    """Create persistent state for v0.23.0 context transport.

    Args:
        c: Open SQLite connection receiving migration 44.

    Returns:
        None.
    """
    c.executescript(
        """
        CREATE TABLE context_transport_packs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_revision INTEGER NOT NULL,
            transport_version INTEGER NOT NULL,
            status TEXT NOT NULL,
            model_profile TEXT NOT NULL,
            tokenizer_id TEXT NOT NULL,
            original_request_hash TEXT NOT NULL,
            authority_hash TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            plan_hash TEXT,
            source_freshness_hash TEXT NOT NULL,
            transport_hash TEXT,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            control_tokens INTEGER NOT NULL,
            evidence_tokens INTEGER NOT NULL,
            token_budget INTEGER NOT NULL,
            saved_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            preservation_rate REAL NOT NULL,
            manifest_json TEXT NOT NULL,
            failure_reason TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id, transport_revision)
        );
        CREATE INDEX idx_context_transport_task
            ON context_transport_packs(task_id,status,transport_revision);

        CREATE TABLE context_requirement_ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            requirement_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            source_kind TEXT NOT NULL,
            exact_text TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            span_start INTEGER,
            span_end INTEGER,
            protected INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id, context_revision, requirement_id)
        );
        CREATE INDEX idx_context_requirement_task
            ON context_requirement_ledger(task_id,context_revision,kind,ordinal);

        CREATE TABLE context_expansion_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            handle_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            source_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX idx_context_expansion_pack
            ON context_expansion_events(transport_pack_id,created_at);

        CREATE TABLE context_transport_evaluations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transport_pack_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            raw_tokens INTEGER NOT NULL,
            transport_tokens INTEGER NOT NULL,
            compression_ratio REAL NOT NULL,
            protected_requirement_count INTEGER NOT NULL,
            preserved_requirement_count INTEGER NOT NULL,
            requirement_preservation_rate REAL NOT NULL,
            context_miss_count INTEGER NOT NULL,
            expansion_request_count INTEGER NOT NULL,
            task_success_rate REAL,
            test_pass_rate REAL,
            rework_count INTEGER,
            tool_call_count INTEGER NOT NULL,
            metrics_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        CREATE INDEX idx_context_transport_eval_task
            ON context_transport_evaluations(task_id,created_at);
        """
    )


@dataclass(frozen=True)
class TokenBudget:
    """Resolved model context budget after non-input reservations."""

    profile: str
    context_capacity: int
    reserved_output: int
    system_tool_overhead: int
    safety_margin: int

    @property
    def input_budget(self) -> int:
        return self.context_capacity - self.reserved_output - self.system_tool_overhead - self.safety_margin


class Tokenizer:
    """Minimal tokenizer abstraction used by the transport compiler."""

    tokenizer_id = "abstract"
    exact = False

    def count(self, text: str) -> int:
        """Count tokens for text."""
        raise NotImplementedError


class HeuristicTokenizer(Tokenizer):
    """Conservative multilingual tokenizer fallback with no network dependency."""

    tokenizer_id = "multilingual_heuristic_v1"
    exact = False

    def count(self, text: str) -> int:
        """Estimate tokens conservatively for Latin, Vietnamese, CJK, and punctuation."""
        if not text:
            return 0
        cjk = sum(1 for ch in text if "\u3400" <= ch <= "\u9fff")
        non_cjk = len(text) - cjk
        lexical = len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))
        char_estimate = math.ceil(non_cjk / 3.2) + cjk
        lexical_estimate = math.ceil(lexical * 1.15)
        return max(1, char_estimate, lexical_estimate)


class TiktokenTokenizer(Tokenizer):
    """Exact tokenizer wrapper when a local tiktoken encoding is available."""

    exact = True

    def __init__(self, model_name: str | None = None, encoding_name: str | None = None) -> None:
        import tiktoken  # type: ignore

        if encoding_name:
            self._encoding = tiktoken.get_encoding(encoding_name)
            self.tokenizer_id = f"tiktoken:{encoding_name}"
        elif model_name:
            self._encoding = tiktoken.encoding_for_model(model_name)
            self.tokenizer_id = f"tiktoken:model:{model_name}"
        else:
            self._encoding = tiktoken.get_encoding("cl100k_base")
            self.tokenizer_id = "tiktoken:cl100k_base"

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


def resolve_tokenizer(model_profile: str, cfg: dict[str, Any]) -> Tokenizer:
    """Resolve an exact local tokenizer when possible, otherwise use fallback."""
    profiles = dict(DEFAULT_MODEL_PROFILES)
    profiles.update(cfg.get("model_profiles", {}) if isinstance(cfg.get("model_profiles"), dict) else {})
    profile = profiles.get(model_profile, {})
    requested = str(profile.get("tokenizer", "auto"))
    model_name = profile.get("model_name")
    encoding_name = profile.get("encoding")
    if requested in {"auto", "tiktoken"}:
        try:
            return TiktokenTokenizer(
                str(model_name) if model_name else None,
                str(encoding_name) if encoding_name else None,
            )
        except Exception:
            if requested == "tiktoken" and bool(cfg.get("exact_tokenizer_required", False)):
                raise ContextTransportError("exact_tokenizer_unavailable")
    return HeuristicTokenizer()


def resolve_budget(
    model_profile: str,
    cfg: dict[str, Any],
    reserved_output: int | None = None,
    system_tool_overhead: int | None = None,
    safety_margin: int | None = None,
) -> TokenBudget:
    """Resolve input budget as capacity minus all mandatory reservations."""
    profiles = dict(DEFAULT_MODEL_PROFILES)
    profiles.update(cfg.get("model_profiles", {}) if isinstance(cfg.get("model_profiles"), dict) else {})
    if model_profile not in profiles:
        raise ContextTransportError(f"unknown_model_profile:{model_profile}")
    profile = profiles[model_profile]
    budget = TokenBudget(
        profile=model_profile,
        context_capacity=int(profile["context_capacity"]),
        reserved_output=int(reserved_output if reserved_output is not None else cfg.get("reserved_output_tokens", 8192)),
        system_tool_overhead=int(system_tool_overhead if system_tool_overhead is not None else cfg.get("system_tool_overhead_tokens", 8192)),
        safety_margin=int(safety_margin if safety_margin is not None else cfg.get("safety_margin_tokens", 4096)),
    )
    if budget.input_budget <= 0:
        raise ContextTransportError("invalid_model_token_budget")
    return budget


def _split_exact_spans(text: str) -> list[tuple[int, int, str]]:
    """Split request into exact non-overlapping requirement-sized spans."""
    spans: list[tuple[int, int, str]] = []
    # Sentence/list-boundary extraction preserves characters exactly inside each span.
    for match in re.finditer(r"[^\n.!?;]+(?:[.!?;]+|$)|[^\n]+", text, flags=re.UNICODE):
        raw = match.group(0)
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        exact = raw[left:right]
        if not exact:
            continue
        start = match.start() + left
        end = match.start() + right
        spans.append((start, end, exact))
    # A list-heavy request may produce large spans; split on arrows/colon-separated clauses conservatively.
    refined: list[tuple[int, int, str]] = []
    for start, end, exact in spans:
        if len(exact) <= 700:
            refined.append((start, end, exact))
            continue
        cursor = 0
        for part in re.finditer(r"[^,]+(?:,|$)", exact, flags=re.UNICODE):
            raw = part.group(0)
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip(" ,"))
            piece = raw[left:right]
            if piece:
                ps = start + part.start() + left
                pe = start + part.start() + right
                refined.append((ps, pe, piece))
            cursor = part.end()
        if cursor == 0:
            refined.append((start, end, exact))
    return refined


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    lower = text.lower()
    return any(re.search(pattern, lower, flags=re.UNICODE | re.IGNORECASE) for pattern in patterns)


def _classify_requirement(text: str, ordinal: int) -> str:
    if _matches_any(text, PROHIBITION_PATTERNS):
        return "prohibition"
    if _matches_any(text, ACCEPTANCE_PATTERNS):
        return "acceptance_criterion"
    if _matches_any(text, CONSTRAINT_PATTERNS):
        return "constraint"
    if _matches_any(text, DELIVERABLE_PATTERNS):
        return "deliverable"
    return "objective" if ordinal == 1 else "deliverable"


def _requirement_id(kind: str, exact_text: str) -> str:
    prefix = {
        "objective": "OBJ",
        "constraint": "CON",
        "prohibition": "PRO",
        "deliverable": "DEL",
        "acceptance_criterion": "ACC",
    }[kind]
    return f"REQ-{prefix}-{_sha256_text(exact_text)[:12].upper()}"


def build_requirement_ledger(request: str, plan_json: str | None = None) -> list[dict[str, Any]]:
    """Build stable IDs from exact request spans and exact active-plan requirement values."""
    ledger: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    ordinal = 0
    for start, end, exact in _split_exact_spans(request):
        ordinal += 1
        kind = _classify_requirement(exact, ordinal)
        key = (kind, exact)
        if key in seen:
            continue
        seen.add(key)
        ledger.append(
            {
                "requirement_id": _requirement_id(kind, exact),
                "kind": kind,
                "ordinal": ordinal,
                "source_kind": "original_request",
                "exact_text": exact,
                "text_hash": _sha256_text(exact),
                "span_start": start,
                "span_end": end,
                "protected": True,
            }
        )
    if plan_json:
        try:
            plan = json.loads(plan_json)
        except json.JSONDecodeError:
            plan = None
        if isinstance(plan, dict):
            key_kind = {
                "constraints": "constraint",
                "prohibitions": "prohibition",
                "deliverables": "deliverable",
                "acceptance_criteria": "acceptance_criterion",
                "acceptance": "acceptance_criterion",
                "objectives": "objective",
                "objective": "objective",
            }
            for key, kind in key_kind.items():
                value = plan.get(key)
                items = value if isinstance(value, list) else [value] if isinstance(value, str) else []
                for item in items:
                    if not isinstance(item, str) or not item:
                        continue
                    pair = (kind, item)
                    if pair in seen:
                        continue
                    seen.add(pair)
                    ordinal += 1
                    ledger.append(
                        {
                            "requirement_id": _requirement_id(kind, item),
                            "kind": kind,
                            "ordinal": ordinal,
                            "source_kind": "active_plan",
                            "exact_text": item,
                            "text_hash": _sha256_text(item),
                            "span_start": None,
                            "span_end": None,
                            "protected": True,
                        }
                    )
    return ledger


def _requirement_terms(ledger: list[dict[str, Any]]) -> set[str]:
    text = "\n".join(item["exact_text"] for item in ledger)
    return {
        token.lower()
        for token in re.findall(r"[\w.-]{3,}", text, flags=re.UNICODE)
        if token.lower() not in {"the", "and", "with", "that", "this", "cho", "các", "với", "được", "phải", "không"}
    }


def _policy_projection(root: Path, ledger: list[dict[str, Any]]) -> dict[str, Any]:
    policy = _policy(root)
    terms = _requirement_terms(ledger)
    selected: dict[str, Any] = {}
    for key in CRITICAL_POLICY_SECTIONS:
        if key in policy:
            selected[key] = policy[key]
    for key, value in policy.items():
        if key in selected:
            continue
        key_terms = set(re.findall(r"[a-z0-9_]{3,}", key.lower()))
        if terms & key_terms:
            selected[key] = value
    return selected


def _control_plane(root: Path, task: dict[str, Any], ledger: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str]]:
    agents_path = root / "AGENTS.md"
    governance_path = root / ".agents/config/governance.json"
    if not agents_path.is_file() or not governance_path.is_file():
        raise ContextTransportError("required_authority_source_missing")
    agents_text = _file_text(agents_path)
    governance_text = _file_text(governance_path)
    plan = active_plan(root, str(task["id"]))
    plan_json = str(plan.get("plan_json")) if plan and plan.get("plan_json") is not None else None
    # planning.active_plan removes plan_json and exposes parsed plan; fetch exact stored JSON separately.
    if plan:
        with connect(root) as c:
            row = c.execute("SELECT plan_json,plan_hash,revision FROM task_plans WHERE id=?", (plan["id"],)).fetchone()
        if row:
            plan_json = str(row["plan_json"])
            plan_hash = str(row["plan_hash"])
            plan_revision = int(row["revision"])
        else:
            plan_json = None
            plan_hash = None
            plan_revision = None
    else:
        plan_hash = None
        plan_revision = None
    approved_scope_raw = str(task.get("approved_scope") or "[]")
    projection = _policy_projection(root, ledger)
    projection_json = _canonical_json(projection)
    control = {
        "original_user_request": str(task["request"]),
        "original_user_request_hash": _sha256_text(str(task["request"])),
        "requirement_ledger": ledger,
        "instruction_authority": {
            "path": "AGENTS.md",
            "verbatim": agents_text,
            "content_hash": _sha256_text(agents_text),
        },
        "policy_authority": {
            "path": ".agents/config/governance.json",
            "source_hash": _sha256_text(governance_text),
            "projection": projection,
            "projection_hash": _sha256_text(projection_json),
            "projection_codec": "deterministic_json_key_projection_v1",
        },
        "approved_scope": {
            "raw": approved_scope_raw,
            "hash": _sha256_text(approved_scope_raw),
        },
        "active_plan": {
            "revision": plan_revision,
            "verbatim_json": plan_json,
            "plan_hash": plan_hash,
        },
    }
    authority_hash = _sha256_text(
        "\n".join(
            [
                control["instruction_authority"]["content_hash"],
                control["policy_authority"]["source_hash"],
                control["policy_authority"]["projection_hash"],
            ]
        )
    )
    hashes = {
        "authority_hash": authority_hash,
        "scope_hash": control["approved_scope"]["hash"],
        "plan_hash": plan_hash or "",
    }
    return control, hashes


def _source_freshness_hash(canonical_manifest: dict[str, Any]) -> str:
    rows = [
        f"{src.get('path','')}:{src.get('content_hash','')}"
        for src in canonical_manifest.get("sources", [])
    ]
    return _sha256_text("\n".join(sorted(rows)))


def _raw_context_text(control: dict[str, Any], canonical_manifest: dict[str, Any]) -> str:
    pieces = [_canonical_json(control)]
    for src in canonical_manifest.get("sources", []):
        pieces.append(str(src.get("excerpt") or ""))
    for item in canonical_manifest.get("knowledge_sources", []):
        pieces.append(str(item.get("text") or item.get("title") or ""))
    return "\n".join(pieces)


def _exact_dedup(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: dict[str, str] = {}
    kept: list[dict[str, Any]] = []
    deduped: list[dict[str, Any]] = []
    for item in items:
        text = str(item.get("raw_text") or "")
        digest = _sha256_text(text)
        if digest in seen:
            deduped.append({**item, "duplicate_of": seen[digest], "codec": "exact_dedup"})
            continue
        seen[digest] = str(item["candidate_id"])
        kept.append(item)
    return kept, deduped


def _python_signature_projection(path: Path, terms: set[str], max_nodes: int = 16) -> tuple[str, dict[str, Any]] | None:
    try:
        source = _file_text(path)
        tree = ast.parse(source)
    except Exception:
        return None
    lines = source.splitlines()
    candidates: list[tuple[int, int, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        name = getattr(node, "name", "")
        names = {x.lower() for x in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", name)}
        score = len(names & terms)
        # Include dependencies when referenced names overlap requirements.
        dep_names = {
            n.id.lower()
            for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.id, str)
        }
        score += min(3, len(dep_names & terms))
        candidates.append((-score, int(getattr(node, "lineno", 1)), node))
    candidates.sort(key=lambda x: (x[0], x[1], getattr(x[2], "name", "")))
    selected = candidates[:max_nodes]
    if not selected:
        return None
    out_lines: list[str] = []
    windows: list[dict[str, Any]] = []
    for neg_score, line_start, node in selected:
        line_end = int(getattr(node, "end_lineno", line_start))
        # Requirements ask for symbol windows/signatures/dependency windows. Keep
        # exact signature plus a bounded exact body window, never delete words.
        cap_end = min(line_end, line_start + 31)
        chunk = "\n".join(lines[line_start - 1 : cap_end])
        out_lines.append(chunk)
        windows.append(
            {
                "symbol": getattr(node, "name", ""),
                "line_start": line_start,
                "line_end": cap_end,
                "relevance_score": -neg_score,
            }
        )
    return "\n\n".join(out_lines), {"codec": "python_symbol_dependency_windows_v1", "windows": windows}


def _json_projection(text: str, terms: set[str]) -> tuple[str, dict[str, Any]] | None:
    try:
        value = json.loads(text)
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    selected: dict[str, Any] = {}
    for key, val in value.items():
        key_terms = set(re.findall(r"[a-z0-9_]{3,}", str(key).lower()))
        if key in CRITICAL_POLICY_SECTIONS or terms & key_terms:
            selected[str(key)] = val
    if not selected:
        return None
    projected = _canonical_json(selected)
    return projected, {"codec": "json_policy_key_projection_v1", "keys": sorted(selected)}


def _log_aggregate(text: str) -> tuple[str, dict[str, Any]] | None:
    lines = text.splitlines()
    if len(lines) < 6:
        return None
    counts: dict[str, int] = {}
    order: list[str] = []
    for line in lines:
        normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ][0-9:.+Z-]+\b", "<TIMESTAMP>", line)
        normalized = re.sub(r"\b[0-9a-fA-F]{16,}\b", "<HEX>", normalized)
        if normalized not in counts:
            order.append(normalized)
            counts[normalized] = 0
        counts[normalized] += 1
    if len(order) >= len(lines) * 0.9:
        return None
    out = [f"{line} [count={counts[line]}]" if counts[line] > 1 else line for line in order]
    return "\n".join(out), {"codec": "log_repeat_aggregation_v1", "source_lines": len(lines), "aggregate_lines": len(out)}


def _project_candidate(root: Path, item: dict[str, Any], terms: set[str]) -> dict[str, Any]:
    text = str(item.get("raw_text") or "")
    path_text = str(item.get("path") or "")
    suffix = Path(path_text).suffix.lower()
    projected = text
    meta: dict[str, Any] = {"codec": "identity_exact_excerpt"}
    path = root / path_text if path_text else None
    if suffix == ".py" and path and path.is_file():
        result = _python_signature_projection(path, terms)
        if result and len(result[0]) < len(text):
            projected, meta = result
    elif suffix == ".json":
        result = _json_projection(text, terms)
        if result and len(result[0]) < len(text):
            projected, meta = result
    elif suffix in {".log", ".txt"}:
        result = _log_aggregate(text)
        if result and len(result[0]) < len(text):
            projected, meta = result
    return {**item, "projected_text": projected, "projection": meta}


def _candidate_score(item: dict[str, Any], terms: set[str]) -> float:
    text = f"{item.get('path','')}\n{item.get('raw_text','')}".lower()
    overlap = sum(1 for term in terms if term in text)
    base = float(item.get("relevance_score") or 0.0)
    kind_bonus = 4.0 if item.get("kind") == "source" else 2.0
    return base + overlap * 3.0 + kind_bonus


def _canonical_candidates(canonical_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, src in enumerate(canonical_manifest.get("sources", [])):
        items.append(
            {
                "candidate_id": f"SRC-{index:04d}",
                "kind": "source",
                "path": str(src.get("path") or ""),
                "source_hash": str(src.get("content_hash") or ""),
                "raw_text": str(src.get("excerpt") or ""),
                "relevance_score": float(src.get("relevance_score") or 0.0),
                "canonical_index": index,
            }
        )
    for index, item in enumerate(canonical_manifest.get("knowledge_sources", [])):
        text = str(item.get("text") or item.get("title") or "")
        items.append(
            {
                "candidate_id": f"KNW-{index:04d}",
                "kind": "knowledge",
                "path": str(item.get("source_path") or item.get("kind") or "knowledge"),
                "source_hash": _sha256_text(text),
                "raw_text": text,
                "relevance_score": float(item.get("score") or 0.0),
                "canonical_index": index,
            }
        )
    return items


def _handle_for(item: dict[str, Any], reason: str, canonical_revision: int) -> dict[str, Any]:
    seed = f"{canonical_revision}:{item['candidate_id']}:{item.get('source_hash','')}:{reason}"
    return {
        "handle_id": f"EXP-{_sha256_text(seed)[:16].upper()}",
        "candidate_id": item["candidate_id"],
        "kind": item["kind"],
        "path": item.get("path"),
        "source_hash": item.get("source_hash"),
        "canonical_index": item.get("canonical_index"),
        "canonical_revision": canonical_revision,
        "reason": reason,
        "expandable": True,
    }


def _evidence_plane(
    root: Path,
    canonical_manifest: dict[str, Any],
    canonical_revision: int,
    ledger: list[dict[str, Any]],
    tokenizer: Tokenizer,
    evidence_budget: int,
) -> tuple[dict[str, Any], int, int]:
    terms = _requirement_terms(ledger)
    original_items = _canonical_candidates(canonical_manifest)
    raw_tokens = sum(tokenizer.count(str(item.get("raw_text") or "")) for item in original_items)

    # Ladder 1: exact deduplication.
    dedup_kept, deduped = _exact_dedup(original_items)

    # Ladder 2 + 3: metadata normalization and structure-aware projection.
    projected = [_project_candidate(root, item, terms) for item in dedup_kept]

    # Ladder 4: requirement-aware deterministic ranking.
    for item in projected:
        item["rank_score"] = _candidate_score(item, terms)
        item["projected_tokens"] = tokenizer.count(str(item["projected_text"]))
    projected.sort(key=lambda item: (-float(item["rank_score"]), str(item["candidate_id"])))

    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    handles: list[dict[str, Any]] = []
    used = 0
    for item in projected:
        cost = int(item["projected_tokens"])
        if cost <= max(0, evidence_budget - used):
            included.append(
                {
                    "candidate_id": item["candidate_id"],
                    "kind": item["kind"],
                    "path": item.get("path"),
                    "source_hash": item.get("source_hash"),
                    "source_handle": {
                        "kind": item["kind"],
                        "path": item.get("path"),
                        "source_hash": item.get("source_hash"),
                        "canonical_index": item.get("canonical_index"),
                        "canonical_revision": canonical_revision,
                    },
                    "codec": item["projection"]["codec"],
                    "projection": item["projection"],
                    "rank_score": item["rank_score"],
                    "tokens": cost,
                    "excerpt": item["projected_text"],
                }
            )
            used += cost
        else:
            handle = _handle_for(item, "token_budget_omission", canonical_revision)
            omitted.append({"candidate_id": item["candidate_id"], "reason": "token_budget_omission", "handle_id": handle["handle_id"]})
            handles.append(handle)

    # Ladder 5: every exact duplicate receives an expansion handle rather than disappearing silently.
    for item in deduped:
        handle = _handle_for(item, "exact_duplicate", canonical_revision)
        omitted.append({"candidate_id": item["candidate_id"], "reason": "exact_duplicate", "duplicate_of": item["duplicate_of"], "handle_id": handle["handle_id"]})
        handles.append(handle)

    return {
        "compression_ladder": [
            "exact_dedup",
            "metadata_normalization",
            "structural_projection",
            "requirement_aware_ranking",
            "omission_handles",
            "fail_closed",
        ],
        "included": included,
        "omitted": omitted,
        "expansion_index": handles,
        "candidate_count": len(original_items),
        "included_count": len(included),
        "omitted_count": len(omitted),
    }, raw_tokens, used


def _persist_ledger(root: Path, task_id: str, context_revision: int, ledger: list[dict[str, Any]]) -> None:
    with connect(root, immediate=True) as c:
        for item in ledger:
            c.execute(
                """
                INSERT OR IGNORE INTO context_requirement_ledger(
                    task_id,context_revision,requirement_id,kind,ordinal,source_kind,
                    exact_text,text_hash,span_start,span_end,protected
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id,
                    context_revision,
                    item["requirement_id"],
                    item["kind"],
                    item["ordinal"],
                    item["source_kind"],
                    item["exact_text"],
                    item["text_hash"],
                    item["span_start"],
                    item["span_end"],
                    1,
                ),
            )


def _next_transport_revision(root: Path, task_id: str) -> int:
    with connect(root) as c:
        row = c.execute(
            "SELECT COALESCE(MAX(transport_revision),0)+1 AS n FROM context_transport_packs WHERE task_id=?",
            (task_id,),
        ).fetchone()
    return int(row["n"])


def _preservation_check(control: dict[str, Any], task: dict[str, Any], ledger: list[dict[str, Any]]) -> dict[str, Any]:
    request = str(task["request"])
    original_ok = control["original_user_request"] == request and control["original_user_request_hash"] == _sha256_text(request)
    ledger_ok = True
    preserved = 0
    for item in ledger:
        exact = item["exact_text"]
        valid_hash = item["text_hash"] == _sha256_text(exact)
        if item["source_kind"] == "original_request":
            start, end = item["span_start"], item["span_end"]
            valid_span = isinstance(start, int) and isinstance(end, int) and request[start:end] == exact
        else:
            valid_span = exact in str(control["active_plan"].get("verbatim_json") or "")
        if valid_hash and valid_span:
            preserved += 1
        else:
            ledger_ok = False
    total = len(ledger)
    rate = 1.0 if total == 0 else preserved / total
    return {
        "original_request": original_ok,
        "requirement_ledger": ledger_ok,
        "protected_requirement_count": total,
        "preserved_requirement_count": preserved,
        "requirement_preservation_rate": rate,
        "scope": control["approved_scope"]["hash"] == _sha256_text(str(task.get("approved_scope") or "[]")),
        "instruction_authority": control["instruction_authority"]["content_hash"] == _sha256_text(control["instruction_authority"]["verbatim"]),
        "plan": (
            control["active_plan"]["plan_hash"] is None
            or _sha256_text(str(control["active_plan"]["verbatim_json"])) == control["active_plan"]["plan_hash"]
        ),
    }


def compile_transport_pack(
    root: Path,
    task_id: str,
    model_profile: str = "generic-128k",
    reserved_output: int | None = None,
    system_tool_overhead: int | None = None,
    safety_margin: int | None = None,
    shadow: bool = False,
) -> dict[str, Any]:
    """Compile a requirement-preserving transport from the active canonical Context Pack.

    The control plane is never truncated. If protected content does not fit, the
    compiler persists a FAILED record and raises a fail-closed error.
    """
    root = root.resolve()
    cfg = _transport_policy(root)
    task = _task_row(root, task_id)
    if not bool(task.get("approved")):
        raise ContextTransportError("task_not_approved")
    canonical = context_status(root, task_id)
    if not canonical.get("exists"):
        raise ContextTransportError("canonical_context_missing")
    if canonical.get("stale"):
        raise ContextTransportError("canonical_context_stale")
    canonical_manifest = canonical["manifest"]
    context_revision = int(canonical["revision"])

    with connect(root) as c:
        plan_row = c.execute(
            "SELECT plan_json FROM task_plans WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    plan_json = str(plan_row["plan_json"]) if plan_row else None
    ledger = build_requirement_ledger(str(task["request"]), plan_json)
    control, control_hashes = _control_plane(root, task, ledger)
    tokenizer = resolve_tokenizer(model_profile, cfg)
    budget = resolve_budget(model_profile, cfg, reserved_output, system_tool_overhead, safety_margin)
    control_tokens = tokenizer.count(_canonical_json(control))
    raw_context_tokens = tokenizer.count(_raw_context_text(control, canonical_manifest))
    revision = _next_transport_revision(root, task_id)
    freshness_hash = _source_freshness_hash(canonical_manifest)

    gate = _preservation_check(control, task, ledger)
    gate["policy_authority"] = (
        control["policy_authority"]["source_hash"] == _file_hash(root / ".agents/config/governance.json")
        and control["policy_authority"]["projection_hash"] == _sha256_text(_canonical_json(control["policy_authority"]["projection"]))
    )
    gate["source_freshness"] = not bool(canonical.get("stale"))
    gate["context_revision"] = int(canonical["revision"]) == context_revision
    gate["control_plane_fits_budget"] = control_tokens <= budget.input_budget
    gate["preservation_rate_100_percent"] = abs(float(gate["requirement_preservation_rate"]) - 1.0) < 1e-12

    # Integrity is intentionally checked only after the complete transport has
    # been assembled. A pack cannot transition to READY before that check.
    if not all(bool(value) for key, value in gate.items() if key not in {"protected_requirement_count", "preserved_requirement_count", "requirement_preservation_rate"}):
        failure = "protected_content_exceeds_model_budget" if not gate["control_plane_fits_budget"] else "requirement_preservation_gate_failed"
        failed_manifest = {
            "transport_version": TRANSPORT_VERSION,
            "task_id": task_id,
            "context_revision": context_revision,
            "transport_revision": revision,
            "status": "FAILED",
            "failure_reason": failure,
            "model_profile": model_profile,
            "tokenizer": {"id": tokenizer.tokenizer_id, "exact": tokenizer.exact},
            "budget": {
                "context_capacity": budget.context_capacity,
                "reserved_output": budget.reserved_output,
                "system_tool_overhead": budget.system_tool_overhead,
                "safety_margin": budget.safety_margin,
                "input_budget": budget.input_budget,
                "control_tokens": control_tokens,
            },
            "preservation_gate": gate,
        }
        with connect(root, immediate=True) as c:
            c.execute(
                """
                INSERT INTO context_transport_packs(
                    task_id,context_revision,transport_revision,transport_version,status,model_profile,tokenizer_id,
                    original_request_hash,authority_hash,scope_hash,plan_hash,source_freshness_hash,transport_hash,
                    raw_tokens,transport_tokens,control_tokens,evidence_tokens,token_budget,saved_tokens,compression_ratio,
                    preservation_rate,manifest_json,failure_reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id, context_revision, revision, TRANSPORT_VERSION, "FAILED", model_profile, tokenizer.tokenizer_id,
                    _sha256_text(str(task["request"])), control_hashes["authority_hash"], control_hashes["scope_hash"], control_hashes["plan_hash"] or None,
                    freshness_hash, None, raw_context_tokens, control_tokens, control_tokens, 0, budget.input_budget,
                    max(0, raw_context_tokens-control_tokens), (raw_context_tokens / max(1, control_tokens)),
                    float(gate["requirement_preservation_rate"]), _canonical_json(failed_manifest), failure,
                ),
            )
        raise ContextTransportError(failure)

    _persist_ledger(root, task_id, context_revision, ledger)
    evidence_budget = budget.input_budget - control_tokens
    evidence, raw_evidence_tokens, evidence_tokens = _evidence_plane(
        root, canonical_manifest, context_revision, ledger, tokenizer, evidence_budget
    )
    manifest: dict[str, Any] = {
        "transport_version": TRANSPORT_VERSION,
        "task_id": task_id,
        "context_revision": context_revision,
        "transport_revision": revision,
        "task_revision": {
            "request_hash": control["original_user_request_hash"],
            "scope_hash": control_hashes["scope_hash"],
            "active_plan_revision": control["active_plan"]["revision"],
            "active_plan_hash": control_hashes["plan_hash"] or None,
        },
        "status": "PREPARED",
        "model_profile": model_profile,
        "tokenizer": {"id": tokenizer.tokenizer_id, "exact": tokenizer.exact},
        "budget": {
            "context_capacity": budget.context_capacity,
            "reserved_output": budget.reserved_output,
            "system_tool_overhead": budget.system_tool_overhead,
            "safety_margin": budget.safety_margin,
            "input_budget": budget.input_budget,
        },
        "control_plane": control,
        "evidence_plane": evidence,
        "authority_hashes": {
            "combined": control_hashes["authority_hash"],
            "agents": control["instruction_authority"]["content_hash"],
            "governance_source": control["policy_authority"]["source_hash"],
            "governance_projection": control["policy_authority"]["projection_hash"],
        },
        "scope_hash": control_hashes["scope_hash"],
        "plan_hash": control_hashes["plan_hash"] or None,
        "source_freshness_hash": freshness_hash,
        "canonical_context_hash": canonical["content_hash"],
        "preservation_gate": gate,
        "metrics": {
            "raw_tokens": raw_context_tokens,
            "raw_evidence_tokens": raw_evidence_tokens,
            "transport_tokens": control_tokens + evidence_tokens,
            "control_tokens": control_tokens,
            "evidence_tokens": evidence_tokens,
            "saved_tokens": max(0, raw_context_tokens - (control_tokens + evidence_tokens)),
            "compression_ratio": raw_context_tokens / max(1, control_tokens + evidence_tokens),
            "protected_requirement_count": gate["protected_requirement_count"],
            "preserved_requirement_count": gate["preserved_requirement_count"],
            "requirement_preservation_rate": gate["requirement_preservation_rate"],
        },
    }
    # The final hash covers the exact transport payload except lifecycle status,
    # the hash field itself, and the derived integrity-check boolean. Only after
    # recomputation succeeds may the pack transition from PREPARED to READY.
    manifest["transport_hash"] = _nowless_transport_hash(manifest)
    gate["transport_integrity"] = _nowless_transport_hash(manifest) == manifest["transport_hash"]
    if not gate["transport_integrity"]:
        raise ContextTransportError("transport_integrity_gate_failed")
    manifest["status"] = "SHADOW_READY" if shadow else "READY"
    transport_tokens = int(manifest["metrics"]["transport_tokens"])
    if transport_tokens > budget.input_budget:
        raise ContextTransportError("transport_budget_internal_error")
    with connect(root, immediate=True) as c:
        if not shadow:
            c.execute("UPDATE context_transport_packs SET status='SUPERSEDED' WHERE task_id=? AND status='READY'", (task_id,))
        c.execute(
            """
            INSERT INTO context_transport_packs(
                task_id,context_revision,transport_revision,transport_version,status,model_profile,tokenizer_id,
                original_request_hash,authority_hash,scope_hash,plan_hash,source_freshness_hash,transport_hash,
                raw_tokens,transport_tokens,control_tokens,evidence_tokens,token_budget,saved_tokens,compression_ratio,
                preservation_rate,manifest_json,failure_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)
            """,
            (
                task_id, context_revision, revision, TRANSPORT_VERSION, manifest["status"], model_profile, tokenizer.tokenizer_id,
                control["original_user_request_hash"], control_hashes["authority_hash"], control_hashes["scope_hash"], control_hashes["plan_hash"] or None,
                freshness_hash, manifest["transport_hash"], raw_context_tokens, transport_tokens, control_tokens, evidence_tokens,
                budget.input_budget, int(manifest["metrics"]["saved_tokens"]), float(manifest["metrics"]["compression_ratio"]),
                float(gate["requirement_preservation_rate"]), _canonical_json(manifest),
            ),
        )
        pack_id = int(c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    return {**manifest, "pack_id": pack_id, "ok": True}


def _pack_row(root: Path, task_id: str, revision: int | None = None, allow_shadow: bool = False) -> dict[str, Any]:
    statuses = ("READY", "SHADOW_READY") if allow_shadow else ("READY",)
    placeholders = ",".join("?" for _ in statuses)
    sql = f"SELECT * FROM context_transport_packs WHERE task_id=? AND status IN ({placeholders})"
    args: list[Any] = [task_id, *statuses]
    if revision is not None:
        sql += " AND transport_revision=?"
        args.append(revision)
    sql += " ORDER BY transport_revision DESC LIMIT 1"
    with connect(root) as c:
        row = c.execute(sql, tuple(args)).fetchone()
    if not row:
        raise ContextTransportError("transport_pack_not_found")
    return dict(row)


def _current_authority_state(root: Path, task_id: str) -> dict[str, Any]:
    task = _task_row(root, task_id)
    agents = _file_text(root / "AGENTS.md")
    governance = _file_text(root / ".agents/config/governance.json")
    with connect(root) as c:
        plan = c.execute(
            "SELECT plan_hash FROM task_plans WHERE task_id=? AND status='active' ORDER BY revision DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    return {
        "request_hash": _sha256_text(str(task["request"])),
        "scope_hash": _sha256_text(str(task.get("approved_scope") or "[]")),
        "agents_hash": _sha256_text(agents),
        "governance_hash": _sha256_text(governance),
        "plan_hash": str(plan["plan_hash"]) if plan else None,
    }


def context_transport_get(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Return one verified READY transport package without granting mutation authority."""
    root = root.resolve()
    row = _pack_row(root, task_id, revision)
    manifest = json.loads(row["manifest_json"])
    if _nowless_transport_hash(manifest) != row["transport_hash"]:
        raise ContextTransportError("transport_integrity_hash_mismatch")
    current = _current_authority_state(root, task_id)
    canonical = context_status(root, task_id)
    stale_reasons: list[str] = []
    if current["request_hash"] != row["original_request_hash"]:
        stale_reasons.append("original_request_changed")
    if current["scope_hash"] != row["scope_hash"]:
        stale_reasons.append("approved_scope_changed")
    if current["plan_hash"] != row["plan_hash"]:
        stale_reasons.append("active_plan_changed")
    if current["agents_hash"] != manifest["authority_hashes"]["agents"]:
        stale_reasons.append("agents_authority_changed")
    if current["governance_hash"] != manifest["authority_hashes"]["governance_source"]:
        stale_reasons.append("governance_authority_changed")
    if not canonical.get("exists") or canonical.get("stale"):
        stale_reasons.append("canonical_context_stale")
    elif int(canonical["revision"]) != int(row["context_revision"]):
        stale_reasons.append("canonical_context_revision_changed")
    return {
        "ok": not stale_reasons,
        "pack_id": row["id"],
        "task_id": task_id,
        "transport_revision": row["transport_revision"],
        "context_revision": row["context_revision"],
        "status": row["status"],
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "transport_hash": row["transport_hash"],
        "manifest": manifest,
    }


def context_transport_explain(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Explain codecs, preservation gates, omissions, and current freshness."""
    pack = context_transport_get(root, task_id, revision)
    manifest = pack["manifest"]
    evidence = manifest["evidence_plane"]
    return {
        "ok": pack["ok"],
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "stale": pack["stale"],
        "stale_reasons": pack["stale_reasons"],
        "preservation_gate": manifest["preservation_gate"],
        "compression_ladder": evidence["compression_ladder"],
        "included_evidence": [
            {
                "candidate_id": item["candidate_id"],
                "path": item.get("path"),
                "codec": item["codec"],
                "rank_score": item["rank_score"],
                "tokens": item["tokens"],
            }
            for item in evidence["included"]
        ],
        "omitted_evidence": evidence["omitted"],
        "expandable_count": len(evidence["expansion_index"]),
        "metrics": manifest["metrics"],
        "budget": manifest["budget"],
    }


def _find_handle(manifest: dict[str, Any], handle_id: str) -> dict[str, Any]:
    for handle in manifest.get("evidence_plane", {}).get("expansion_index", []):
        if handle.get("handle_id") == handle_id:
            return handle
    raise ContextTransportError("expansion_handle_not_found")


def context_expand(
    root: Path,
    task_id: str,
    handle_id: str,
    revision: int | None = None,
    max_lines: int = 240,
    record_event: bool = True,
) -> dict[str, Any]:
    """Expand one omission handle read-only with source-hash verification."""
    root = root.resolve()
    pack = context_transport_get(root, task_id, revision)
    if not pack["ok"]:
        raise ContextTransportError("transport_pack_stale")
    manifest = pack["manifest"]
    handle = _find_handle(manifest, handle_id)
    context_revision = int(handle["canonical_revision"])
    with connect(root) as c:
        row = c.execute(
            "SELECT manifest_json,content_hash FROM context_packs WHERE task_id=? AND revision=?",
            (task_id, context_revision),
        ).fetchone()
    if not row:
        raise ContextTransportError("canonical_context_revision_missing")
    canonical = json.loads(row["manifest_json"])
    kind = handle["kind"]
    index = int(handle["canonical_index"])
    if kind == "source":
        src = canonical.get("sources", [])[index]
        path = root / str(src["path"])
        if not path.is_file():
            raise ContextTransportError("expansion_source_missing")
        current_hash = _file_hash(path)
        if current_hash != handle["source_hash"]:
            raise ContextTransportError("expansion_source_hash_mismatch")
        lines = _file_text(path).splitlines()
        excerpt = "\n".join(lines[: max(1, int(max_lines))])
        source_hash = current_hash
        source = {"path": src["path"], "line_start": 1, "line_end": min(len(lines), max_lines)}
    else:
        item = canonical.get("knowledge_sources", [])[index]
        excerpt = str(item.get("text") or item.get("title") or "")
        source_hash = _sha256_text(excerpt)
        if source_hash != handle["source_hash"]:
            raise ContextTransportError("expansion_knowledge_hash_mismatch")
        source = {"kind": item.get("kind"), "id": item.get("id")}
    if record_event:
        with connect(root, immediate=True) as c:
            c.execute(
                "INSERT INTO context_expansion_events(transport_pack_id,handle_id,task_id,outcome,source_hash) VALUES(?,?,?,?,?)",
                (pack["pack_id"], handle_id, task_id, "expanded", source_hash),
            )
    return {
        "ok": True,
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "handle_id": handle_id,
        "source": source,
        "source_hash": source_hash,
        "excerpt": excerpt,
        "read_only": True,
    }


def context_requirement_get(
    root: Path,
    task_id: str,
    requirement_id: str | None = None,
    context_revision: int | None = None,
) -> dict[str, Any]:
    """Return exact Requirement Ledger entries for inspection."""
    if context_revision is None:
        pack = _pack_row(root.resolve(), task_id)
        context_revision = int(pack["context_revision"])
    sql = "SELECT requirement_id,kind,ordinal,source_kind,exact_text,text_hash,span_start,span_end,protected FROM context_requirement_ledger WHERE task_id=? AND context_revision=?"
    args: list[Any] = [task_id, context_revision]
    if requirement_id:
        sql += " AND requirement_id=?"
        args.append(requirement_id)
    sql += " ORDER BY ordinal,requirement_id"
    with connect(root) as c:
        rows = [dict(r) for r in c.execute(sql, tuple(args)).fetchall()]
    if requirement_id and not rows:
        raise ContextTransportError("requirement_not_found")
    return {"ok": True, "task_id": task_id, "context_revision": context_revision, "requirements": rows, "count": len(rows)}


def context_token_report(root: Path, task_id: str, revision: int | None = None) -> dict[str, Any]:
    """Return token budget, savings, and tokenizer details for a READY pack."""
    pack = context_transport_get(root, task_id, revision)
    m = pack["manifest"]
    return {
        "ok": pack["ok"],
        "task_id": task_id,
        "transport_revision": pack["transport_revision"],
        "stale": pack["stale"],
        "tokenizer": m["tokenizer"],
        "budget": m["budget"],
        **m["metrics"],
    }


def _task_outcome_metrics(root: Path, task_id: str) -> tuple[float | None, float | None, int | None]:
    with connect(root) as c:
        row = c.execute(
            "SELECT outcome,test_pass_rate,rework_count FROM task_outcomes WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    if not row:
        return None, None, None
    outcome = str(row["outcome"] or "").lower()
    success = 1.0 if outcome in {"success", "passed", "complete", "completed"} else 0.0 if outcome else None
    return success, row["test_pass_rate"], row["rework_count"]


def evaluate_transport_pack(root: Path, task_id: str, revision: int | None = None, persist: bool = True) -> dict[str, Any]:
    """Compare canonical and transport contexts using v0.23.0 evaluation metrics."""
    pack = context_transport_get(root, task_id, revision)
    manifest = pack["manifest"]
    metrics = dict(manifest["metrics"])
    handles = manifest["evidence_plane"]["expansion_index"]
    candidate_ids = {item["candidate_id"] for item in manifest["evidence_plane"]["included"]}
    candidate_ids.update(item["candidate_id"] for item in handles)
    context_miss_count = max(0, int(manifest["evidence_plane"]["candidate_count"]) - len(candidate_ids))
    with connect(root) as c:
        expansion_count = int(c.execute(
            "SELECT COUNT(*) AS n FROM context_expansion_events WHERE transport_pack_id=?",
            (pack["pack_id"],),
        ).fetchone()["n"])
        tool_call_count = int(c.execute(
            "SELECT COUNT(*) AS n FROM tool_calls WHERE task_id=?",
            (task_id,),
        ).fetchone()["n"])
    task_success, test_pass, rework = _task_outcome_metrics(root, task_id)
    result = {
        "raw_tokens": int(metrics["raw_tokens"]),
        "transport_tokens": int(metrics["transport_tokens"]),
        "compression_ratio": float(metrics["compression_ratio"]),
        "protected_requirement_count": int(metrics["protected_requirement_count"]),
        "preserved_requirement_count": int(metrics["preserved_requirement_count"]),
        "requirement_preservation_rate": float(metrics["requirement_preservation_rate"]),
        "context_miss_count": context_miss_count,
        "expansion_request_count": expansion_count,
        "task_success_rate": task_success,
        "test_pass_rate": test_pass,
        "rework_count": rework,
        "tool_call_count": tool_call_count,
    }
    if persist:
        with connect(root, immediate=True) as c:
            c.execute(
                """
                INSERT INTO context_transport_evaluations(
                    transport_pack_id,task_id,raw_tokens,transport_tokens,compression_ratio,
                    protected_requirement_count,preserved_requirement_count,requirement_preservation_rate,
                    context_miss_count,expansion_request_count,task_success_rate,test_pass_rate,rework_count,
                    tool_call_count,metrics_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pack["pack_id"], task_id, result["raw_tokens"], result["transport_tokens"], result["compression_ratio"],
                    result["protected_requirement_count"], result["preserved_requirement_count"], result["requirement_preservation_rate"],
                    result["context_miss_count"], result["expansion_request_count"], result["task_success_rate"],
                    result["test_pass_rate"], result["rework_count"], result["tool_call_count"], _canonical_json(result),
                ),
            )
    return {"ok": True, "task_id": task_id, "transport_revision": pack["transport_revision"], **result}


def sync_schema(root: Path) -> dict[str, Any]:
    """Open the central database so migration 44 is applied through db.connect()."""
    with connect(root) as c:
        version = int(c.execute("SELECT COALESCE(MAX(version),0) AS v FROM schema_migrations").fetchone()["v"])
        foreign_keys = int(c.execute("PRAGMA foreign_keys").fetchone()[0])
    return {"ok": version == MIGRATION_VERSION and foreign_keys == 1, "schema": version, "foreign_keys": foreign_keys}
