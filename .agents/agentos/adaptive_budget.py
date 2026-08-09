"""
File: .agents/agentos/adaptive_budget.py

Purpose:
    Resolve deterministic model profiles and adaptive token budgets for AgentOS
    requirement-preserving LLM transport without network discovery or model authority.

Responsibilities:
    - Validate data-only model profiles and pin them by canonical SHA-256 hash.
    - Derive adaptive output, overhead, safety, input, and evidence budgets.
    - Use local token observations only to increase protective headroom.
    - Persist profile snapshots, budget decisions, and token calibration evidence.
    - Expose read-only profile/budget/calibration inspection helpers.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .db import connect
from .policy import load_policy

MIGRATION_VERSION = 45
BUDGET_ALGORITHM_VERSION = "adaptive_budget_v1"
PROFILE_SCHEMA_VERSION = 1

ALLOWED_TOKENIZERS = {"auto", "heuristic", "tiktoken"}
ALLOWED_BUDGET_MODES = {"adaptive", "fixed"}
ALLOWED_OBSERVATION_SOURCES = {
    "runtime_report", "provider_usage", "tokenizer_probe",
    "operator_verified", "benchmark", "local_runtime",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _round_up(value: float | int, quantum: int = 256) -> int:
    n = max(0, int(math.ceil(float(value))))
    return ((n + quantum - 1) // quantum) * quantum


def _default_profile(name: str, capacity: int) -> dict[str, Any]:
    """Return conservative data-only defaults for one generic context capacity."""
    if capacity < 8_192:
        output_min = max(1, capacity // 16)
        output_default = max(output_min, capacity // 8)
        output_max = max(output_default, capacity // 4)
        overhead = max(1, capacity // 8)
        safety_min = max(1, capacity // 16)
        evidence_min = max(1, capacity // 8)
    elif capacity <= 16_384:
        output_min, output_default, output_max = 1024, 2048, 4096
        overhead, safety_min, evidence_min = 2048, 1024, 1024
    elif capacity <= 32_768:
        output_min, output_default, output_max = 2048, 4096, 8192
        overhead, safety_min, evidence_min = 4096, 2048, 2048
    elif capacity <= 65_536:
        output_min, output_default, output_max = 4096, 8192, 12288
        overhead, safety_min, evidence_min = 6144, 3072, 4096
    elif capacity <= 131_072:
        output_min, output_default, output_max = 4096, 8192, 16384
        overhead, safety_min, evidence_min = 8192, 4096, 8192
    else:
        output_min, output_default, output_max = 8192, 12288, 24576
        overhead, safety_min, evidence_min = 8192, 8192, 12288
    return {
        "profile_version": PROFILE_SCHEMA_VERSION,
        "name": name,
        "enabled": True,
        "context_capacity": int(capacity),
        "tokenizer": "auto",
        "reserved_output_min": output_min,
        "reserved_output_default": output_default,
        "reserved_output_max": output_max,
        "system_tool_overhead": overhead,
        "safety_margin_min": safety_min,
        "safety_margin_ratio_ppm": 50_000,
        "minimum_evidence_tokens": evidence_min,
    }


BUILTIN_MODEL_PROFILES: dict[str, dict[str, Any]] = {
    name: _default_profile(name, capacity)
    for name, capacity in (
        ("generic-16k", 16_384),
        ("generic-32k", 32_768),
        ("generic-64k", 65_536),
        ("generic-128k", 131_072),
        ("generic-200k", 200_000),
    )
}


class AdaptiveBudgetError(RuntimeError):
    """Raised when a model profile or adaptive budget is unsafe or invalid."""


@dataclass(frozen=True)
class ModelProfile:
    """Normalized immutable model-profile definition used by transport compilation."""

    name: str
    profile_version: int
    context_capacity: int
    tokenizer: str
    model_name: str | None
    encoding: str | None
    reserved_output_min: int
    reserved_output_default: int
    reserved_output_max: int
    system_tool_overhead: int
    safety_margin_min: int
    safety_margin_ratio_ppm: int
    minimum_evidence_tokens: int
    profile_hash: str

    def public_dict(self) -> dict[str, Any]:
        """Return the complete data-only profile representation."""
        value = asdict(self)
        return value


@dataclass(frozen=True)
class AdaptiveBudgetDecision:
    """Deterministic budget decision for one transport revision."""

    model_profile: str
    model_profile_hash: str
    mode: str
    algorithm_version: str
    context_capacity: int
    reserved_output: int
    system_tool_overhead: int
    safety_margin: int
    calibration_headroom: int
    input_budget: int
    control_tokens: int
    evidence_budget: int
    evidence_floor: int
    evidence_floor_satisfied: bool
    pressure_score: float
    observed_output_p95: int
    input_underestimation_p95: int
    output_reserve_saturated: bool

    def public_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible decision object."""
        return asdict(self)


def migration_45(c: Any) -> None:
    """Create v0.23.1 adaptive model-profile and token-budget state.

    Args:
        c: Open SQLite connection receiving migration 45.

    Returns:
        None.
    """
    c.executescript(
        """
        CREATE TABLE context_model_profile_snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            profile_hash TEXT NOT NULL,
            profile_version INTEGER NOT NULL,
            context_capacity INTEGER NOT NULL,
            tokenizer_policy TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_name,profile_hash)
        );
        CREATE INDEX idx_context_profile_snapshot_name
            ON context_model_profile_snapshots(profile_name,created_at);

        CREATE TABLE context_budget_decisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            context_revision INTEGER NOT NULL,
            transport_revision INTEGER NOT NULL,
            model_profile TEXT NOT NULL,
            model_profile_hash TEXT NOT NULL,
            budget_mode TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            control_tokens INTEGER NOT NULL,
            reserved_output INTEGER NOT NULL,
            system_tool_overhead INTEGER NOT NULL,
            safety_margin INTEGER NOT NULL,
            calibration_headroom INTEGER NOT NULL,
            input_budget INTEGER NOT NULL,
            evidence_budget INTEGER NOT NULL,
            evidence_floor INTEGER NOT NULL,
            evidence_floor_satisfied INTEGER NOT NULL,
            pressure_score REAL NOT NULL,
            decision_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            UNIQUE(task_id,transport_revision)
        );
        CREATE INDEX idx_context_budget_task
            ON context_budget_decisions(task_id,transport_revision,created_at);
        CREATE INDEX idx_context_budget_profile
            ON context_budget_decisions(model_profile,created_at);

        CREATE TABLE context_token_observations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            transport_pack_id INTEGER,
            model_profile TEXT NOT NULL,
            model_profile_hash TEXT NOT NULL,
            tokenizer_id TEXT NOT NULL,
            predicted_input_tokens INTEGER NOT NULL,
            observed_input_tokens INTEGER NOT NULL,
            predicted_output_reserve INTEGER NOT NULL,
            observed_output_tokens INTEGER,
            underestimation_tokens INTEGER NOT NULL,
            underestimation_ratio REAL NOT NULL,
            source TEXT NOT NULL,
            observation_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(transport_pack_id) REFERENCES context_transport_packs(id),
            UNIQUE(transport_pack_id,source)
        );
        CREATE INDEX idx_context_token_observation_profile
            ON context_token_observations(model_profile,tokenizer_id,created_at);
        CREATE INDEX idx_context_token_observation_task
            ON context_token_observations(task_id,created_at);

        ALTER TABLE context_transport_packs ADD COLUMN model_profile_hash TEXT;
        ALTER TABLE context_transport_packs ADD COLUMN budget_mode TEXT NOT NULL DEFAULT 'fixed';
        ALTER TABLE context_transport_packs ADD COLUMN budget_decision_id INTEGER;
        """
    )


def _transport_cfg(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    cfg = policy.get("context_transport_policy", {})
    return cfg if isinstance(cfg, dict) else {}


def _adaptive_cfg(root: Path) -> dict[str, Any]:
    policy = load_policy(root)
    cfg = policy.get("adaptive_token_budget_policy", {})
    return cfg if isinstance(cfg, dict) else {}


def _profile_source(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    profiles = {name: dict(value) for name, value in BUILTIN_MODEL_PROFILES.items()}
    configured = cfg.get("model_profiles", {})
    if isinstance(configured, dict):
        for name, value in configured.items():
            if isinstance(value, dict):
                base = dict(profiles.get(str(name), _default_profile(str(name), int(value.get("context_capacity", 0) or 0))))
                base.update(value)
                base["name"] = str(name)
                profiles[str(name)] = base
    return profiles


def _normalized_profile(name: str, raw: dict[str, Any]) -> ModelProfile:
    if not raw.get("enabled", True):
        raise AdaptiveBudgetError(f"model_profile_disabled:{name}")
    capacity = int(raw.get("context_capacity", 0) or 0)
    if capacity < 128:
        raise AdaptiveBudgetError(f"invalid_model_context_capacity:{name}")
    tokenizer = str(raw.get("tokenizer", "auto"))
    if tokenizer not in ALLOWED_TOKENIZERS:
        raise AdaptiveBudgetError(f"unsupported_tokenizer_policy:{tokenizer}")
    model_name = raw.get("model_name")
    encoding = raw.get("encoding")
    if model_name is not None and not isinstance(model_name, str):
        raise AdaptiveBudgetError("model_name_must_be_string")
    if encoding is not None and not isinstance(encoding, str):
        raise AdaptiveBudgetError("encoding_must_be_string")

    defaults = _default_profile(name, capacity)
    merged = {**defaults, **raw, "name": name, "context_capacity": capacity, "tokenizer": tokenizer}
    numeric = {
        key: int(merged[key])
        for key in (
            "reserved_output_min",
            "reserved_output_default",
            "reserved_output_max",
            "system_tool_overhead",
            "safety_margin_min",
            "safety_margin_ratio_ppm",
            "minimum_evidence_tokens",
        )
    }
    if min(numeric.values()) < 0:
        raise AdaptiveBudgetError(f"negative_model_profile_budget_value:{name}")
    if not (
        numeric["reserved_output_min"]
        <= numeric["reserved_output_default"]
        <= numeric["reserved_output_max"]
    ):
        raise AdaptiveBudgetError(f"invalid_output_reserve_bounds:{name}")
    if numeric["reserved_output_max"] >= capacity:
        raise AdaptiveBudgetError(f"output_reserve_exceeds_context_capacity:{name}")
    if numeric["safety_margin_ratio_ppm"] > 500_000:
        raise AdaptiveBudgetError(f"safety_margin_ratio_too_large:{name}")

    canonical = {
        "profile_version": int(merged.get("profile_version", PROFILE_SCHEMA_VERSION)),
        "name": name,
        "context_capacity": capacity,
        "tokenizer": tokenizer,
        "model_name": model_name,
        "encoding": encoding,
        **numeric,
    }
    profile_hash = _sha256_text(_canonical_json(canonical))
    return ModelProfile(profile_hash=profile_hash, **canonical)


def resolve_model_profile(root: Path, name: str) -> ModelProfile:
    """Resolve and validate one local data-only model profile.

    Args:
        root: Governed AgentOS root.
        name: Exact profile name from the built-in/configured registry.

    Returns:
        Normalized immutable profile with canonical hash.

    Raises:
        AdaptiveBudgetError: If the profile is unknown, disabled, or unsafe.
    """
    cfg = _transport_cfg(root)
    profiles = _profile_source(cfg)
    if name not in profiles:
        raise AdaptiveBudgetError(f"unknown_model_profile:{name}")
    return _normalized_profile(name, profiles[name])


def model_profiles_get(root: Path, name: str | None = None) -> dict[str, Any]:
    """Return validated model profiles without network/provider discovery."""
    cfg = _transport_cfg(root)
    source = _profile_source(cfg)
    names = [name] if name is not None else sorted(source)
    profiles: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for item in names:
        if item not in source:
            errors.append({"name": str(item), "error": "unknown_model_profile"})
            continue
        try:
            profiles.append(_normalized_profile(str(item), source[str(item)]).public_dict())
        except AdaptiveBudgetError as exc:
            errors.append({"name": str(item), "error": str(exc)})
    return {
        "ok": not errors,
        "network_discovery": False,
        "provider_api_discovery": False,
        "profiles": profiles,
        "errors": errors,
    }


def _percentile(values: Iterable[int], percentile: float) -> int:
    ordered = sorted(max(0, int(v)) for v in values)
    if not ordered:
        return 0
    rank = max(0, min(len(ordered) - 1, int(math.ceil(percentile * len(ordered)) - 1)))
    return ordered[rank]


def calibration_stats(root: Path, profile: ModelProfile, tokenizer_id: str, limit: int | None = None) -> dict[str, Any]:
    """Return bounded local calibration statistics for one profile/tokenizer pair."""
    cfg = _adaptive_cfg(root)
    max_samples = int(limit or cfg.get("calibration_window", 32) or 32)
    max_samples = max(1, min(max_samples, 512))
    with connect(root) as c:
        rows = c.execute(
            """
            SELECT underestimation_tokens,observed_output_tokens
              FROM context_token_observations
             WHERE model_profile=? AND model_profile_hash=? AND tokenizer_id=?
             ORDER BY id DESC LIMIT ?
            """,
            (profile.name, profile.profile_hash, tokenizer_id, max_samples),
        ).fetchall()
    under = [int(r["underestimation_tokens"] or 0) for r in rows]
    outputs = [int(r["observed_output_tokens"] or 0) for r in rows if r["observed_output_tokens"] is not None]
    return {
        "sample_count": len(rows),
        "input_underestimation_p95": _percentile(under, 0.95),
        "observed_output_p95": _percentile(outputs, 0.95),
        "input_underestimation_max": max(under, default=0),
        "observed_output_max": max(outputs, default=0),
    }


def _pressure_score(ledger: list[dict[str, Any]], plan_json: str | None) -> float:
    counts = {kind: 0 for kind in ("objective", "constraint", "prohibition", "deliverable", "acceptance_criterion")}
    for item in ledger:
        kind = str(item.get("kind") or "")
        if kind in counts:
            counts[kind] += 1
    plan_steps = 0
    if plan_json:
        try:
            parsed = json.loads(plan_json)
            if isinstance(parsed, dict):
                steps = parsed.get("steps") or parsed.get("plan") or []
                if isinstance(steps, list):
                    plan_steps = len(steps)
            elif isinstance(parsed, list):
                plan_steps = len(parsed)
        except Exception:
            plan_steps = 0
    raw = (
        counts["objective"] * 0.08
        + counts["constraint"] * 0.025
        + counts["prohibition"] * 0.015
        + counts["deliverable"] * 0.12
        + counts["acceptance_criterion"] * 0.10
        + plan_steps * 0.03
    )
    return round(max(0.0, min(1.0, raw)), 6)


def resolve_adaptive_budget(
    root: Path,
    profile: ModelProfile,
    tokenizer_id: str,
    control_tokens: int,
    ledger: list[dict[str, Any]],
    plan_json: str | None,
    *,
    mode: str,
    reserved_output_override: int | None = None,
    system_tool_overhead_override: int | None = None,
    safety_margin_override: int | None = None,
) -> AdaptiveBudgetDecision:
    """Derive one bounded budget without altering any protected content.

    Calibration can only increase output reserve or safety headroom. It cannot
    reduce the profile's configured safety floor.
    """
    if mode not in ALLOWED_BUDGET_MODES:
        raise AdaptiveBudgetError(f"unsupported_budget_mode:{mode}")
    cfg = _adaptive_cfg(root)
    calibration = calibration_stats(root, profile, tokenizer_id)
    pressure = _pressure_score(ledger, plan_json)

    if mode == "fixed":
        transport_cfg = _transport_cfg(root)
        reserved_output = int(
            reserved_output_override
            if reserved_output_override is not None
            else transport_cfg.get("reserved_output_tokens", profile.reserved_output_default)
        )
        system_tool_overhead = int(
            system_tool_overhead_override
            if system_tool_overhead_override is not None
            else transport_cfg.get("system_tool_overhead_tokens", profile.system_tool_overhead)
        )
        safety_margin = int(
            safety_margin_override
            if safety_margin_override is not None
            else transport_cfg.get("safety_margin_tokens", profile.safety_margin_min)
        )
        calibration_headroom = 0
        output_saturated = False
        algorithm = "fixed_v0230_compat"
    else:
        span = max(0, profile.reserved_output_max - profile.reserved_output_min)
        pressure_reserve = _round_up(profile.reserved_output_min + span * pressure)
        output_guard = int(cfg.get("output_calibration_guard_tokens", 512) or 512)
        calibrated_output = int(calibration["observed_output_p95"]) + output_guard if calibration["observed_output_p95"] else 0
        desired_output = max(profile.reserved_output_default, pressure_reserve, calibrated_output)
        output_saturated = desired_output > profile.reserved_output_max
        reserved_output = min(profile.reserved_output_max, desired_output)
        if reserved_output_override is not None:
            explicit_output = int(reserved_output_override)
            if explicit_output < 0:
                raise AdaptiveBudgetError("negative_reserved_output_override")
            output_saturated = output_saturated or explicit_output > profile.reserved_output_max
            reserved_output = min(profile.reserved_output_max, max(reserved_output, explicit_output))

        if system_tool_overhead_override is not None:
            explicit_overhead = int(system_tool_overhead_override)
            if explicit_overhead < 0:
                raise AdaptiveBudgetError("negative_system_tool_overhead_override")
            system_tool_overhead = max(profile.system_tool_overhead, explicit_overhead)
        else:
            system_tool_overhead = profile.system_tool_overhead
        ratio_margin = math.ceil(profile.context_capacity * profile.safety_margin_ratio_ppm / 1_000_000)
        under_p95 = int(calibration["input_underestimation_p95"])
        calibration_guard = int(cfg.get("input_calibration_guard_tokens", 512) or 512)
        max_headroom = int(
            cfg.get("max_calibration_headroom_tokens", max(2048, profile.context_capacity // 8))
            or max(2048, profile.context_capacity // 8)
        )
        calibration_headroom = min(max_headroom, under_p95 + calibration_guard if under_p95 else 0)
        safety_margin = max(profile.safety_margin_min, ratio_margin, calibration_headroom)
        if safety_margin_override is not None:
            # Adaptive overrides are monotonic-protective: an operator may add
            # headroom but cannot reduce the profile/ratio/calibration decision.
            explicit_safety = int(safety_margin_override)
            if explicit_safety < 0:
                raise AdaptiveBudgetError("negative_safety_margin_override")
            safety_margin = max(safety_margin, explicit_safety)
        algorithm = BUDGET_ALGORITHM_VERSION

    if min(reserved_output, system_tool_overhead, safety_margin) < 0:
        raise AdaptiveBudgetError("negative_token_budget_component")
    input_budget = profile.context_capacity - reserved_output - system_tool_overhead - safety_margin
    if input_budget <= 0:
        raise AdaptiveBudgetError("invalid_model_token_budget")
    evidence_budget = max(0, input_budget - max(0, int(control_tokens)))
    evidence_floor = profile.minimum_evidence_tokens
    return AdaptiveBudgetDecision(
        model_profile=profile.name,
        model_profile_hash=profile.profile_hash,
        mode=mode,
        algorithm_version=algorithm,
        context_capacity=profile.context_capacity,
        reserved_output=reserved_output,
        system_tool_overhead=system_tool_overhead,
        safety_margin=safety_margin,
        calibration_headroom=calibration_headroom,
        input_budget=input_budget,
        control_tokens=max(0, int(control_tokens)),
        evidence_budget=evidence_budget,
        evidence_floor=evidence_floor,
        evidence_floor_satisfied=evidence_budget >= evidence_floor,
        pressure_score=pressure,
        observed_output_p95=int(calibration["observed_output_p95"]),
        input_underestimation_p95=int(calibration["input_underestimation_p95"]),
        output_reserve_saturated=output_saturated,
    )


def persist_profile_snapshot(root: Path, profile: ModelProfile) -> int:
    """Persist an immutable profile definition snapshot and return its row id."""
    definition = profile.public_dict()
    with connect(root, immediate=True) as c:
        c.execute(
            """
            INSERT OR IGNORE INTO context_model_profile_snapshots(
                profile_name,profile_hash,profile_version,context_capacity,tokenizer_policy,definition_json
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                profile.name,
                profile.profile_hash,
                profile.profile_version,
                profile.context_capacity,
                profile.tokenizer,
                _canonical_json(definition),
            ),
        )
        row = c.execute(
            "SELECT id FROM context_model_profile_snapshots WHERE profile_name=? AND profile_hash=?",
            (profile.name, profile.profile_hash),
        ).fetchone()
    return int(row["id"])


def persist_budget_decision(
    root: Path,
    task_id: str,
    context_revision: int,
    transport_revision: int,
    decision: AdaptiveBudgetDecision,
) -> int:
    """Persist one immutable budget decision and return its row id."""
    payload = decision.public_dict()
    with connect(root, immediate=True) as c:
        c.execute(
            """
            INSERT INTO context_budget_decisions(
                task_id,context_revision,transport_revision,model_profile,model_profile_hash,budget_mode,
                algorithm_version,control_tokens,reserved_output,system_tool_overhead,safety_margin,
                calibration_headroom,input_budget,evidence_budget,evidence_floor,evidence_floor_satisfied,
                pressure_score,decision_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task_id,
                context_revision,
                transport_revision,
                decision.model_profile,
                decision.model_profile_hash,
                decision.mode,
                decision.algorithm_version,
                decision.control_tokens,
                decision.reserved_output,
                decision.system_tool_overhead,
                decision.safety_margin,
                decision.calibration_headroom,
                decision.input_budget,
                decision.evidence_budget,
                decision.evidence_floor,
                1 if decision.evidence_floor_satisfied else 0,
                decision.pressure_score,
                _canonical_json(payload),
            ),
        )
        row_id = int(c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    return row_id


def budget_history_get(root: Path, task_id: str, limit: int = 20) -> dict[str, Any]:
    """Return recent persisted budget decisions for one task."""
    n = max(1, min(int(limit), 200))
    with connect(root) as c:
        rows = [
            dict(r)
            for r in c.execute(
                """
                SELECT id,task_id,context_revision,transport_revision,model_profile,model_profile_hash,
                       budget_mode,algorithm_version,control_tokens,reserved_output,system_tool_overhead,
                       safety_margin,calibration_headroom,input_budget,evidence_budget,evidence_floor,
                       evidence_floor_satisfied,pressure_score,created_at
                  FROM context_budget_decisions
                 WHERE task_id=? ORDER BY transport_revision DESC LIMIT ?
                """,
                (task_id, n),
            ).fetchall()
        ]
    return {"ok": True, "task_id": task_id, "decisions": rows, "count": len(rows)}


def token_calibration_get(root: Path, model_profile: str, tokenizer_id: str, limit: int = 32) -> dict[str, Any]:
    """Return local calibration statistics without raw prompts or outputs."""
    profile = resolve_model_profile(root, model_profile)
    stats = calibration_stats(root, profile, tokenizer_id, limit)
    return {
        "ok": True,
        "model_profile": model_profile,
        "model_profile_hash": profile.profile_hash,
        "tokenizer_id": tokenizer_id,
        **stats,
    }


def record_token_observation(
    root: Path,
    task_id: str,
    observed_input_tokens: int,
    observed_output_tokens: int | None = None,
    revision: int | None = None,
    source: str = "runtime_report",
) -> dict[str, Any]:
    """Record numeric runtime token usage for future protective calibration.

    No prompt, response, credential, or source evidence text is persisted.
    Observations can only increase future safety/output reservations; they are
    never used to relax the protected control plane.
    """
    observed_input = int(observed_input_tokens)
    observed_output = int(observed_output_tokens) if observed_output_tokens is not None else None
    if observed_input < 0 or (observed_output is not None and observed_output < 0):
        raise AdaptiveBudgetError("negative_token_observation")
    if source not in ALLOWED_OBSERVATION_SOURCES:
        raise AdaptiveBudgetError("invalid_token_observation_source")
    sql = "SELECT * FROM context_transport_packs WHERE task_id=? AND status IN ('READY','SHADOW_READY')"
    args: list[Any] = [task_id]
    if revision is not None:
        sql += " AND transport_revision=?"
        args.append(int(revision))
    sql += " ORDER BY transport_revision DESC LIMIT 1"
    with connect(root) as c:
        row = c.execute(sql, tuple(args)).fetchone()
    if not row:
        raise AdaptiveBudgetError("transport_pack_not_found")
    manifest = json.loads(row["manifest_json"])
    profile_name = str(row["model_profile"])
    profile_hash = str(row["model_profile_hash"] or manifest.get("model_profile_hash") or "")
    if len(profile_hash) != 64:
        raise AdaptiveBudgetError("transport_pack_missing_model_profile_hash")
    tokenizer_id = str(row["tokenizer_id"])
    predicted_input = int(row["transport_tokens"])
    predicted_output = int(manifest.get("budget", {}).get("reserved_output", 0) or 0)
    under = max(0, observed_input - predicted_input)
    ratio = under / max(1, predicted_input)
    identity = {
        "task_id": task_id,
        "transport_pack_id": int(row["id"]),
        "model_profile": profile_name,
        "model_profile_hash": profile_hash,
        "tokenizer_id": tokenizer_id,
        "predicted_input_tokens": predicted_input,
        "observed_input_tokens": observed_input,
        "predicted_output_reserve": predicted_output,
        "observed_output_tokens": observed_output,
        "source": source,
    }
    observation_hash = _sha256_text(_canonical_json(identity))
    idempotent = False
    with connect(root, immediate=True) as c:
        existing = c.execute(
            "SELECT observation_hash FROM context_token_observations WHERE transport_pack_id=? AND source=?",
            (int(row["id"]), source),
        ).fetchone()
        if existing:
            if str(existing["observation_hash"]) != observation_hash:
                raise AdaptiveBudgetError("token_observation_source_already_recorded")
            idempotent = True
        else:
            c.execute(
                """
                INSERT INTO context_token_observations(
                    task_id,transport_pack_id,model_profile,model_profile_hash,tokenizer_id,
                    predicted_input_tokens,observed_input_tokens,predicted_output_reserve,observed_output_tokens,
                    underestimation_tokens,underestimation_ratio,source,observation_hash
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id,
                    int(row["id"]),
                    profile_name,
                    profile_hash,
                    tokenizer_id,
                    predicted_input,
                    observed_input,
                    predicted_output,
                    observed_output,
                    under,
                    ratio,
                    source,
                    observation_hash,
                ),
            )
    return {
        "ok": True,
        "task_id": task_id,
        "transport_revision": int(row["transport_revision"]),
        "model_profile": profile_name,
        "model_profile_hash": profile_hash,
        "tokenizer_id": tokenizer_id,
        "underestimation_tokens": under,
        "underestimation_ratio": ratio,
        "observed_output_tokens": observed_output,
        "observation_hash": observation_hash,
        "idempotent": idempotent,
        "content_persisted": False,
    }
