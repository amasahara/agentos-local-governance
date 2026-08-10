"""
File: .agents/agentos/performance_baseline.py

Purpose:
    Capture a reproducible v0.23.3 performance baseline without changing the
    governed project or its consolidation authority.

Responsibilities:
    - Time a fresh schema-1-to-current migration in an isolated temporary root.
    - Time the current full-rebuild symbol index implementation in an isolated
      temporary root using a copy of the repository's Python workload.
    - Time read-only cockpit aggregation against the real local state database.
    - Record repository/workload and environment metadata required to interpret
      timings without pretending wall-clock values are portable across hosts.
    - Validate structural regression contracts; wall-clock thresholds remain
      disabled until an environment is explicitly pinned by a later policy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import tempfile
import time
from typing import Any, Callable

from .consolidation_cockpit import consolidation_status
from .schema_version import CURRENT_SCHEMA_VERSION

VERSION = "0.23.3"
DEFAULT_BASELINE_FILE = "PERFORMANCE_BASELINE_V0233.json"


def _percentile(values: list[float], q: float) -> float:
    """Return a deterministic nearest-rank-style percentile for small samples."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return ordered[idx]


def _summary(samples: list[float]) -> dict[str, Any]:
    """Return stable timing summary in milliseconds."""
    return {
        "samples_ms": [round(value, 3) for value in samples],
        "median_ms": round(statistics.median(samples), 3) if samples else None,
        "p95_ms": round(_percentile(samples, 0.95), 3) if samples else None,
    }


def _time_call(fn: Callable[[], Any], repeats: int) -> tuple[list[float], Any]:
    samples: list[float] = []
    last: Any = None
    for _ in range(max(1, repeats)):
        started = time.perf_counter_ns()
        last = fn()
        samples.append((time.perf_counter_ns() - started) / 1_000_000.0)
    return samples, last


def _python_workload(root: Path) -> dict[str, Any]:
    roots = [root / ".agents" / "agentos", root / ".agents" / "tests"]
    files = sorted({path for base in roots if base.exists() for path in base.rglob("*.py")})
    return {
        "files": files,
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def _migration_chain_length() -> tuple[int | None, str | None]:
    try:
        from .db import _all_migrations

        return len(_all_migrations()), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _fresh_migration_once() -> dict[str, Any]:
    """Run all current migrations in a throw-away project root."""
    from .db import connect

    with tempfile.TemporaryDirectory(prefix="agentos-v0233-migration-") as temp:
        temp_root = Path(temp)
        with connect(temp_root) as conn:
            observed = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version),0) AS version FROM schema_migrations"
                ).fetchone()["version"]
            )
        db_path = temp_root / ".agents/state/agentos.db"
        return {
            "schema_observed": observed,
            "database_bytes": db_path.stat().st_size if db_path.exists() else 0,
        }


def _prepare_index_fixture(root: Path, temp_root: Path) -> tuple[str, int]:
    """Copy only Python files into a temporary source tree for index benchmarking."""
    source_rel = "benchmark_src"
    target = temp_root / source_rel
    copied = 0
    for label, source in (
        ("agentos", root / ".agents" / "agentos"),
        ("tests", root / ".agents" / "tests"),
    ):
        if not source.exists():
            continue
        for path in source.rglob("*.py"):
            rel = path.relative_to(source)
            destination = target / label / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied += 1
    return source_rel, copied


def _index_build_measurement(root: Path, repeats: int) -> tuple[dict[str, Any], str | None]:
    try:
        from .db import connect
        from .indexing import index_build

        with tempfile.TemporaryDirectory(prefix="agentos-v0233-index-") as temp:
            temp_root = Path(temp)
            source_rel, copied = _prepare_index_fixture(root, temp_root)
            # Pre-initialize schema so index timings measure the current DELETE +
            # parse + insert design rather than first-run migration cost.
            with connect(temp_root):
                pass
            samples, last = _time_call(
                lambda: index_build(temp_root, source_rel), max(1, repeats)
            )
            return {
                "mode": "full_rebuild",
                "known_behavior": "DELETE symbol_index then parse all Python files in selected source tree",
                "fixture_python_files": copied,
                "last_result": last,
                **_summary(samples),
            }, None
    except Exception as exc:
        return {
            "mode": "full_rebuild",
            "known_behavior": "DELETE symbol_index then parse all Python files in selected source tree",
            "fixture_python_files": None,
            "last_result": None,
            "samples_ms": [],
            "median_ms": None,
            "p95_ms": None,
        }, f"{type(exc).__name__}: {exc}"


def _migration_measurement(repeats: int) -> tuple[dict[str, Any], str | None]:
    try:
        samples, last = _time_call(_fresh_migration_once, max(1, repeats))
        return {**last, **_summary(samples)}, None
    except Exception as exc:
        return {
            "schema_observed": None,
            "database_bytes": None,
            "samples_ms": [],
            "median_ms": None,
            "p95_ms": None,
        }, f"{type(exc).__name__}: {exc}"


def _environment() -> dict[str, Any]:
    """Return non-secret environment metadata needed to interpret local timings."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
    }


def run_performance_baseline(root: Path, repeats: int = 3) -> dict[str, Any]:
    """Measure the current v0.23.3 performance baseline non-destructively.

    Args:
        root: Materialized AgentOS project root.
        repeats: Number of local timing samples per benchmark.

    Returns:
        Structured baseline. All write-heavy measurements run only in temporary
        roots; the governed project database is read only via the cockpit.
    """
    root = root.resolve()
    repeats = max(1, int(repeats))
    workload = _python_workload(root)
    migration_count, migration_count_error = _migration_chain_length()
    migration, migration_error = _migration_measurement(repeats)
    symbol_index, index_error = _index_build_measurement(root, repeats)
    cockpit_samples, cockpit_result = _time_call(
        lambda: consolidation_status(root), repeats
    )

    manifest_count = None
    manifest = root / "MANIFEST.json"
    if manifest.is_file():
        try:
            manifest_count = len(
                json.loads(manifest.read_text(encoding="utf-8")).get("files", [])
            )
        except Exception:
            manifest_count = None

    benchmark_files = (
        "CONTEXT_TRANSPORT_BENCHMARK.json",
        "ADAPTIVE_TOKEN_BUDGET_BENCHMARK.json",
        "CONTEXT_EXPANSION_EVALUATION_BENCHMARK.json",
    )
    existing_context_benchmarks = {
        name: (root / name).is_file() for name in benchmark_files
    }
    errors = {
        key: value
        for key, value in {
            "migration_chain": migration_count_error,
            "fresh_migration": migration_error,
            "symbol_index": index_error,
        }.items()
        if value
    }
    return {
        "ok": not errors,
        "version": VERSION,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "measurement_scope": "local_non_destructive",
        "measurement_status": "measured" if not errors else "partial",
        "wall_clock_portable": False,
        "repeats": repeats,
        "environment": _environment(),
        "repository": {
            "authoritative_manifest_file_count": manifest_count,
            "python_file_count": workload["file_count"],
            "python_bytes": workload["bytes"],
        },
        "migration": {
            "chain_length": migration_count,
            "fresh_database": migration,
        },
        "symbol_index_current_design": symbol_index,
        "cockpit": {
            **_summary(cockpit_samples),
            "database_present": bool(cockpit_result.get("database_present")),
            "overall_state": cockpit_result.get("overall_state"),
        },
        "existing_context_benchmarks": existing_context_benchmarks,
        "errors": errors,
        "regression_contract": {
            "schema_must_equal": CURRENT_SCHEMA_VERSION,
            "migration_chain_must_equal_schema": True,
            "symbol_index_baseline_mode": "full_rebuild",
            "required_measurements": [
                "migration.fresh_database",
                "symbol_index_current_design",
                "cockpit",
            ],
            "timing_thresholds_environment_pinned": False,
            "project_state_mutation_allowed": False,
        },
    }


def load_baseline(root: Path, path: str | None = None) -> dict[str, Any]:
    """Read the checked-in baseline artifact without executing benchmarks."""
    target = root.resolve() / (path or DEFAULT_BASELINE_FILE)
    return json.loads(target.read_text(encoding="utf-8"))


def check_performance_baseline(root: Path, path: str | None = None) -> dict[str, Any]:
    """Validate structural baseline invariants and benchmark completeness."""
    baseline = load_baseline(root, path)
    findings: list[str] = []
    if baseline.get("version") != VERSION:
        findings.append("baseline_version_mismatch")
    if int(baseline.get("schema_version", -1)) != CURRENT_SCHEMA_VERSION:
        findings.append("baseline_schema_mismatch")
    if baseline.get("measurement_status") != "measured":
        findings.append("baseline_not_measured")
    contract = baseline.get("regression_contract") or {}
    if contract.get("project_state_mutation_allowed") is not False:
        findings.append("baseline_must_be_non_destructive")
    migration = baseline.get("migration") or {}
    if migration.get("chain_length") not in (None, CURRENT_SCHEMA_VERSION):
        findings.append("migration_chain_length_mismatch")
    fresh = migration.get("fresh_database") or {}
    if not isinstance(fresh.get("median_ms"), (int, float)) or not isinstance(fresh.get("p95_ms"), (int, float)):
        findings.append("missing_fresh_migration_timing")
    design = baseline.get("symbol_index_current_design") or {}
    if design.get("mode") != "full_rebuild":
        findings.append("unexpected_symbol_index_baseline_mode")
    if not isinstance(design.get("median_ms"), (int, float)) or not isinstance(design.get("p95_ms"), (int, float)):
        findings.append("missing_symbol_index_timing")
    cockpit = baseline.get("cockpit") or {}
    if not isinstance(cockpit.get("median_ms"), (int, float)) or not isinstance(cockpit.get("p95_ms"), (int, float)):
        findings.append("missing_cockpit_timing")
    return {
        "ok": not findings,
        "version": VERSION,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "baseline": path or DEFAULT_BASELINE_FILE,
        "measurement_status": baseline.get("measurement_status"),
        "findings": findings,
    }
