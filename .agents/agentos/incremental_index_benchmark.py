"""
File: .agents/agentos/incremental_index_benchmark.py

Purpose:
    Measure and validate v0.23.4 Incremental Symbol Index behavior against the
    checked-in v0.23.3 full-rebuild baseline.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import shutil
import statistics
import tempfile
import time
from typing import Any, Callable

from .indexing import index_build
from .schema_version import CURRENT_SCHEMA_VERSION

VERSION = "0.23.4"
BENCHMARK_SCHEMA_VERSION = 47
BASELINE_FILE = "PERFORMANCE_BASELINE_V0233.json"
DEFAULT_BENCHMARK_FILE = "INDEX_INCREMENTAL_BENCHMARK_V0234.json"


def _summary(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "samples_ms": [round(v, 3) for v in values],
        "median_ms": round(statistics.median(values), 3) if values else None,
        "p95_ms": round(ordered[min(len(ordered)-1, max(0, round((len(ordered)-1)*0.95)))], 3) if ordered else None,
    }


def _time(fn: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter_ns()
    result = fn()
    return (time.perf_counter_ns() - started) / 1_000_000.0, result


def _copy_workload(root: Path, temp_root: Path) -> tuple[str, int]:
    source_rel = "benchmark_src"
    target = temp_root / source_rel
    copied = 0
    for label, source in (("agentos", root / ".agents/agentos"), ("tests", root / ".agents/tests")):
        if not source.exists():
            continue
        for path in sorted(source.rglob("*.py")):
            rel = path.relative_to(source)
            dst = target / label / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            copied += 1
    return source_rel, copied


def _reference(root: Path) -> dict[str, Any]:
    path = root / BASELINE_FILE
    if not path.is_file():
        return {"available": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        design = data.get("symbol_index_current_design") or {}
        return {
            "available": True,
            "version": data.get("version"),
            "environment": data.get("environment"),
            "full_rebuild_median_ms": design.get("median_ms"),
            "fixture_python_files": design.get("fixture_python_files"),
        }
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}


def run_incremental_index_benchmark(root: Path, repeats: int = 3) -> dict[str, Any]:
    """Benchmark bootstrap, no-change, one-file-change and deletion paths in temp roots."""
    if CURRENT_SCHEMA_VERSION != BENCHMARK_SCHEMA_VERSION:
        raise RuntimeError(
            "INDEX_INCREMENTAL_BENCHMARK_V0234 is frozen at schema 47; "
            "do not recapture a historical benchmark under a newer release schema"
        )
    root = root.resolve()
    repeats = max(1, int(repeats))
    bootstrap_samples: list[float] = []
    no_change_samples: list[float] = []
    changed_samples: list[float] = []
    delete_samples: list[float] = []
    contracts: list[dict[str, Any]] = []
    copied_last = 0

    for iteration in range(repeats):
        with tempfile.TemporaryDirectory(prefix="agentos-v0234-index-") as temp:
            temp_root = Path(temp)
            source_rel, copied = _copy_workload(root, temp_root)
            copied_last = copied
            from .db import connect
            with connect(temp_root):
                pass
            bootstrap_ms, bootstrap = _time(lambda: index_build(temp_root, source_rel))
            no_change_ms, no_change = _time(lambda: index_build(temp_root, source_rel))

            candidates = sorted((temp_root / source_rel).rglob("*.py"))
            changed_result: dict[str, Any] = {"files_parsed": 0}
            delete_result: dict[str, Any] = {"files_deleted": 0}
            changed_ms = 0.0
            delete_ms = 0.0
            if candidates:
                target = candidates[iteration % len(candidates)]
                payload = target.read_bytes() + f"\n# agentos-v0234-benchmark-{iteration}\n".encode()
                target.write_bytes(payload)
                changed_ms, changed_result = _time(lambda: index_build(temp_root, source_rel))
                target.unlink()
                delete_ms, delete_result = _time(lambda: index_build(temp_root, source_rel))

            bootstrap_samples.append(bootstrap_ms)
            no_change_samples.append(no_change_ms)
            changed_samples.append(changed_ms)
            delete_samples.append(delete_ms)
            contracts.append({
                "bootstrap_mode": bootstrap.get("mode"),
                "bootstrap_parsed_all": bootstrap.get("files_parsed") == bootstrap.get("files_seen"),
                "no_change_mode": no_change.get("mode"),
                "no_change_parsed_zero": no_change.get("files_parsed") == 0,
                "one_change_parsed_one": changed_result.get("files_parsed") == (1 if candidates else 0),
                "delete_removed_one": delete_result.get("files_deleted") == (1 if candidates else 0),
            })

    reference = _reference(root)
    no_change_median = _summary(no_change_samples)["median_ms"]
    baseline_median = reference.get("full_rebuild_median_ms") if reference.get("available") else None
    speedup = None
    if isinstance(baseline_median, (int, float)) and isinstance(no_change_median, (int, float)) and no_change_median > 0:
        speedup = round(float(baseline_median) / float(no_change_median), 3)

    functional_ok = all(
        item["bootstrap_mode"] == "bootstrap_full_rebuild"
        and item["bootstrap_parsed_all"]
        and item["no_change_mode"] == "incremental"
        and item["no_change_parsed_zero"]
        and item["one_change_parsed_one"]
        and item["delete_removed_one"]
        for item in contracts
    )
    return {
        "ok": functional_ok,
        "version": VERSION,
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "measurement_scope": "temporary_fixture_only",
        "measurement_status": "measured" if functional_ok else "invalid",
        "wall_clock_portable": False,
        "repeats": repeats,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},
        "fixture_python_files": copied_last,
        "bootstrap": {"mode": "bootstrap_full_rebuild", **_summary(bootstrap_samples)},
        "no_change_incremental": {"expected_files_parsed": 0, **_summary(no_change_samples)},
        "single_file_change": {"expected_files_parsed": 1 if copied_last else 0, **_summary(changed_samples)},
        "single_file_delete": {"expected_files_deleted": 1 if copied_last else 0, **_summary(delete_samples)},
        "functional_contract_samples": contracts,
        "v0233_reference": reference,
        "no_change_vs_v0233_full_rebuild_speedup": speedup,
        "timing_gate": "advisory_only_environment_not_pinned",
    }


def check_incremental_index_benchmark(root: Path, path: str | None = None) -> dict[str, Any]:
    """Validate benchmark structure and deterministic incremental behavior contracts."""
    target = root.resolve() / (path or DEFAULT_BENCHMARK_FILE)
    findings: list[str] = []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "findings": [f"benchmark_unloadable:{type(exc).__name__}"], "benchmark": str(target)}
    if data.get("version") != VERSION:
        findings.append("benchmark_version_mismatch")
    if int(data.get("schema_version", -1)) != BENCHMARK_SCHEMA_VERSION:
        findings.append("benchmark_schema_mismatch")
    if data.get("measurement_status") != "measured":
        findings.append("benchmark_not_measured")
    if data.get("measurement_scope") != "temporary_fixture_only":
        findings.append("benchmark_scope_invalid")
    for section in ("bootstrap", "no_change_incremental", "single_file_change", "single_file_delete"):
        value = data.get(section) or {}
        if not isinstance(value.get("median_ms"), (int, float)):
            findings.append(f"missing_timing:{section}")
    samples = data.get("functional_contract_samples") or []
    if not samples:
        findings.append("missing_functional_contract_samples")
    for item in samples:
        if item.get("bootstrap_mode") != "bootstrap_full_rebuild" or not item.get("bootstrap_parsed_all"):
            findings.append("bootstrap_contract_failed")
        if item.get("no_change_mode") != "incremental" or not item.get("no_change_parsed_zero"):
            findings.append("no_change_contract_failed")
        if not item.get("one_change_parsed_one"):
            findings.append("single_change_contract_failed")
        if not item.get("delete_removed_one"):
            findings.append("delete_contract_failed")
    return {"ok": not findings, "version": VERSION, "schema_version": BENCHMARK_SCHEMA_VERSION, "benchmark": path or DEFAULT_BENCHMARK_FILE, "findings": sorted(set(findings))}
