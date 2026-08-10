#!/usr/bin/env python3
"""One-command AgentOS v0.23.3 -> v0.23.4 Incremental Symbol Index upgrader."""
from __future__ import annotations
import ast
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

BASELINE = "0.23.3"
TARGET = "0.23.4"
SCHEMA = 47
PAYLOAD = {'.agents/agentos/indexing.py': '"""\nFile: .agents/agentos/indexing.py\n\nPurpose:\n    Build and query a project-local Python symbol index incrementally.\n\nResponsibilities:\n    - Parse Python source through AST and store deterministic fingerprints.\n    - Persist content-hash file state so unchanged files are not reparsed.\n    - Remove stale symbols for deleted files and replace only changed-file rows.\n    - Bootstrap safely from the historical full-rebuild index format.\n    - Fail atomically on parse/decode errors without partially mutating the index.\n"""\nfrom __future__ import annotations\n\nimport ast\nimport hashlib\nfrom pathlib import Path\nimport sqlite3\nfrom typing import Any\n\nfrom .db import connect\n\nINDEX_SCHEMA_VERSION = 47\n\n\ndef migration_47(c: sqlite3.Connection) -> None:\n    """Add deterministic file-state metadata required by the incremental symbol index.\n\n    Args:\n        c: Open AgentOS SQLite connection receiving migration 47.\n    Returns:\n        None.\n    """\n    c.executescript(\n        """\n        CREATE TABLE IF NOT EXISTS symbol_index_state(\n            singleton INTEGER PRIMARY KEY CHECK(singleton=1),\n            source_rel TEXT NOT NULL,\n            generation INTEGER NOT NULL DEFAULT 1,\n            last_mode TEXT NOT NULL,\n            last_files INTEGER NOT NULL DEFAULT 0,\n            last_symbols INTEGER NOT NULL DEFAULT 0,\n            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n        );\n        CREATE TABLE IF NOT EXISTS symbol_index_files(\n            path TEXT PRIMARY KEY,\n            source_rel TEXT NOT NULL,\n            content_hash TEXT NOT NULL,\n            size INTEGER NOT NULL,\n            mtime_ns INTEGER NOT NULL,\n            symbol_count INTEGER NOT NULL,\n            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n        );\n        CREATE INDEX IF NOT EXISTS idx_symbol_index_files_source\n            ON symbol_index_files(source_rel,path);\n        """\n    )\n\n\ndef _fingerprint(node: ast.AST) -> str:\n    """Return the deterministic AST fingerprint used by duplicate detection."""\n    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()\n\n\ndef _safe_source(root: Path, source: str) -> tuple[Path, str]:\n    """Resolve one project-local source tree and reject path escape.\n\n    Args:\n        root: Project root.\n        source: Project-relative source directory.\n    Returns:\n        Resolved source path and normalized project-relative source string.\n    Raises:\n        RuntimeError: If the source is absolute or escapes the project root.\n    """\n    root_resolved = root.resolve()\n    raw = Path(source)\n    if raw.is_absolute():\n        raise RuntimeError("index source must be project-relative")\n    base = (root_resolved / raw).resolve()\n    try:\n        rel = base.relative_to(root_resolved).as_posix()\n    except ValueError as exc:\n        raise RuntimeError("index source escaped project root") from exc\n    return base, rel or "."\n\n\ndef _collect_files(root: Path, base: Path) -> tuple[list[tuple[str, Path]], int]:\n    """Collect deterministic project-local Python paths without following escaped symlinks."""\n    root_resolved = root.resolve()\n    files: list[tuple[str, Path]] = []\n    skipped_symlinks = 0\n    if not base.exists():\n        return files, skipped_symlinks\n    for path in sorted(base.rglob("*.py")):\n        if path.is_symlink():\n            skipped_symlinks += 1\n            continue\n        try:\n            resolved = path.resolve(strict=True)\n            resolved.relative_to(root_resolved)\n        except (OSError, ValueError):\n            skipped_symlinks += 1\n            continue\n        if not resolved.is_file():\n            continue\n        files.append((resolved.relative_to(root_resolved).as_posix(), resolved))\n    return files, skipped_symlinks\n\n\ndef _parse_symbols(rel: str, payload: bytes) -> list[tuple[str, str, str, int, int, str, str]]:\n    """Parse one immutable byte payload into symbol-index rows.\n\n    Args:\n        rel: Project-relative file path.\n        payload: Exact bytes whose hash will be recorded.\n    Returns:\n        Rows suitable for insertion into ``symbol_index``.\n    Raises:\n        UnicodeDecodeError: If source is not UTF-8.\n        SyntaxError: If Python AST parsing fails.\n    """\n    text = payload.decode("utf-8")\n    tree = ast.parse(text, filename=rel)\n    rows: list[tuple[str, str, str, int, int, str, str]] = []\n    for node in ast.walk(tree):\n        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):\n            kind = "class" if isinstance(node, ast.ClassDef) else "function"\n            signature = node.name\n            rows.append(\n                (\n                    rel,\n                    node.name,\n                    kind,\n                    int(node.lineno),\n                    int(getattr(node, "end_lineno", node.lineno)),\n                    signature,\n                    _fingerprint(node),\n                )\n            )\n    return rows\n\n\ndef index_build(root: Path, source: str = "src", *, force_full: bool = False) -> dict[str, Any]:\n    """Build or incrementally update the Python symbol index for a source tree.\n\n    The first run after migration 47 performs a bootstrap full rebuild because the\n    historical ``symbol_index`` table has no trusted per-file content hashes. Later\n    runs hash every candidate file for correctness but parse only new/changed files.\n\n    Args:\n        root: Project root.\n        source: Project-relative source directory.\n        force_full: Force a deterministic full rebuild and reseed file metadata.\n    Returns:\n        Backward-compatible ``files``/``symbols`` counts plus incremental telemetry.\n    Raises:\n        RuntimeError: If the source escapes the project or source parsing fails.\n    """\n    root = root.resolve()\n    base, source_rel = _safe_source(root, source)\n    candidates, skipped_symlinks = _collect_files(root, base)\n\n    # Serialize index mutations. Parsing occurs from the exact bytes whose hashes are\n    # stored, so an index row can never be committed against a different payload.\n    with connect(root, immediate=True) as c:\n        migration_47(c)\n        state = c.execute("SELECT * FROM symbol_index_state WHERE singleton=1").fetchone()\n        previous_rows = c.execute(\n            "SELECT path,source_rel,content_hash,size,mtime_ns,symbol_count FROM symbol_index_files"\n        ).fetchall()\n        previous = {str(row["path"]): dict(row) for row in previous_rows}\n\n        bootstrap = state is None\n        source_changed = bool(state is not None and str(state["source_rel"]) != source_rel)\n        full = bool(force_full or bootstrap or source_changed)\n        mode = "full_rebuild" if force_full or source_changed else ("bootstrap_full_rebuild" if bootstrap else "incremental")\n\n        current_paths = {rel for rel, _ in candidates}\n        deleted = sorted(set(previous) - current_paths) if not full else sorted(set(previous) - current_paths)\n        prepared: dict[str, dict[str, Any]] = {}\n        unchanged = 0\n        added = 0\n        changed = 0\n\n        # Parse before mutating any symbol rows. One bad changed file aborts the whole\n        # transaction and preserves the previously valid index.\n        for rel, path in candidates:\n            payload = path.read_bytes()\n            digest = hashlib.sha256(payload).hexdigest()\n            stat = path.stat()\n            old = previous.get(rel)\n            must_parse = full or old is None or str(old["content_hash"]) != digest\n            if not must_parse:\n                unchanged += 1\n                continue\n            try:\n                symbols = _parse_symbols(rel, payload)\n            except (UnicodeDecodeError, SyntaxError) as exc:\n                raise RuntimeError(f"cannot index {rel}: {type(exc).__name__}: {exc}") from exc\n            prepared[rel] = {\n                "hash": digest,\n                "size": len(payload),\n                "mtime_ns": int(stat.st_mtime_ns),\n                "symbols": symbols,\n            }\n            if old is None:\n                added += 1\n            else:\n                changed += 1\n\n        if full:\n            c.execute("DELETE FROM symbol_index")\n            c.execute("DELETE FROM symbol_index_files")\n        else:\n            for rel in deleted:\n                c.execute("DELETE FROM symbol_index WHERE path=?", (rel,))\n                c.execute("DELETE FROM symbol_index_files WHERE path=?", (rel,))\n            for rel in prepared:\n                c.execute("DELETE FROM symbol_index WHERE path=?", (rel,))\n\n        for rel, item in prepared.items():\n            for row in item["symbols"]:\n                c.execute(\n                    "INSERT OR REPLACE INTO symbol_index(path,qualname,kind,line_start,line_end,signature,fingerprint) VALUES(?,?,?,?,?,?,?)",\n                    row,\n                )\n            c.execute(\n                """\n                INSERT INTO symbol_index_files(path,source_rel,content_hash,size,mtime_ns,symbol_count,indexed_at)\n                VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)\n                ON CONFLICT(path) DO UPDATE SET\n                    source_rel=excluded.source_rel,\n                    content_hash=excluded.content_hash,\n                    size=excluded.size,\n                    mtime_ns=excluded.mtime_ns,\n                    symbol_count=excluded.symbol_count,\n                    indexed_at=CURRENT_TIMESTAMP\n                """,\n                (rel, source_rel, item["hash"], item["size"], item["mtime_ns"], len(item["symbols"])),\n            )\n\n        total_symbols = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index").fetchone()["n"])\n        total_files = len(candidates)\n        generation = 1 if state is None else int(state["generation"]) + 1\n        c.execute(\n            """\n            INSERT INTO symbol_index_state(singleton,source_rel,generation,last_mode,last_files,last_symbols,updated_at)\n            VALUES(1,?,?,?,?,?,CURRENT_TIMESTAMP)\n            ON CONFLICT(singleton) DO UPDATE SET\n                source_rel=excluded.source_rel,\n                generation=excluded.generation,\n                last_mode=excluded.last_mode,\n                last_files=excluded.last_files,\n                last_symbols=excluded.last_symbols,\n                updated_at=CURRENT_TIMESTAMP\n            """,\n            (source_rel, generation, mode, total_files, total_symbols),\n        )\n\n    return {\n        "files": total_files,\n        "symbols": total_symbols,\n        "mode": mode,\n        "source": source_rel,\n        "files_seen": total_files,\n        "files_parsed": len(prepared),\n        "files_unchanged": unchanged if not full else 0,\n        "files_added": added,\n        "files_changed": changed,\n        "files_deleted": len(deleted),\n        "skipped_symlinks": skipped_symlinks,\n        "generation": generation,\n        "schema": INDEX_SCHEMA_VERSION,\n    }\n\n\ndef index_status(root: Path) -> dict[str, Any]:\n    """Return privacy-safe incremental-index state and aggregate counts."""\n    with connect(root.resolve()) as c:\n        migration_47(c)\n        state = c.execute("SELECT * FROM symbol_index_state WHERE singleton=1").fetchone()\n        files = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index_files").fetchone()["n"])\n        symbols = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index").fetchone()["n"])\n    return {\n        "ok": True,\n        "initialized": state is not None,\n        "source": str(state["source_rel"]) if state else None,\n        "generation": int(state["generation"]) if state else 0,\n        "last_mode": str(state["last_mode"]) if state else None,\n        "files": files,\n        "symbols": symbols,\n        "schema": INDEX_SCHEMA_VERSION,\n    }\n\n\ndef index_query(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:\n    """Find indexed symbols matching a query."""\n    like = f"%{query}%"\n    with connect(root) as c:\n        rows = c.execute(\n            "SELECT path,qualname,kind,line_start,line_end,signature,fingerprint FROM symbol_index WHERE qualname LIKE ? ORDER BY CASE WHEN qualname=? THEN 0 ELSE 1 END,path,qualname LIMIT ?",\n            (like, query, limit),\n        ).fetchall()\n    return [dict(row) for row in rows]\n\n\ndef duplicate_report(root: Path) -> list[dict[str, Any]]:\n    """Return groups of symbols with identical AST fingerprints."""\n    with connect(root) as c:\n        fps = c.execute("SELECT fingerprint FROM symbol_index GROUP BY fingerprint HAVING COUNT(*) > 1").fetchall()\n        out = []\n        for fp in fps:\n            rows = c.execute(\n                "SELECT path,qualname FROM symbol_index WHERE fingerprint=? ORDER BY path,qualname",\n                (fp["fingerprint"],),\n            ).fetchall()\n            out.append({"fingerprint": fp["fingerprint"], "symbols": [dict(r) for r in rows]})\n    return out\n', '.agents/agentos/incremental_index_benchmark.py': '"""\nFile: .agents/agentos/incremental_index_benchmark.py\n\nPurpose:\n    Measure and validate v0.23.4 Incremental Symbol Index behavior against the\n    checked-in v0.23.3 full-rebuild baseline.\n"""\nfrom __future__ import annotations\n\nimport json\nfrom pathlib import Path\nimport platform\nimport shutil\nimport statistics\nimport tempfile\nimport time\nfrom typing import Any, Callable\n\nfrom .indexing import index_build\nfrom .schema_version import CURRENT_SCHEMA_VERSION\n\nVERSION = "0.23.4"\nBASELINE_FILE = "PERFORMANCE_BASELINE_V0233.json"\nDEFAULT_BENCHMARK_FILE = "INDEX_INCREMENTAL_BENCHMARK_V0234.json"\n\n\ndef _summary(values: list[float]) -> dict[str, Any]:\n    ordered = sorted(values)\n    return {\n        "samples_ms": [round(v, 3) for v in values],\n        "median_ms": round(statistics.median(values), 3) if values else None,\n        "p95_ms": round(ordered[min(len(ordered)-1, max(0, round((len(ordered)-1)*0.95)))], 3) if ordered else None,\n    }\n\n\ndef _time(fn: Callable[[], Any]) -> tuple[float, Any]:\n    started = time.perf_counter_ns()\n    result = fn()\n    return (time.perf_counter_ns() - started) / 1_000_000.0, result\n\n\ndef _copy_workload(root: Path, temp_root: Path) -> tuple[str, int]:\n    source_rel = "benchmark_src"\n    target = temp_root / source_rel\n    copied = 0\n    for label, source in (("agentos", root / ".agents/agentos"), ("tests", root / ".agents/tests")):\n        if not source.exists():\n            continue\n        for path in sorted(source.rglob("*.py")):\n            rel = path.relative_to(source)\n            dst = target / label / rel\n            dst.parent.mkdir(parents=True, exist_ok=True)\n            shutil.copy2(path, dst)\n            copied += 1\n    return source_rel, copied\n\n\ndef _reference(root: Path) -> dict[str, Any]:\n    path = root / BASELINE_FILE\n    if not path.is_file():\n        return {"available": False}\n    try:\n        data = json.loads(path.read_text(encoding="utf-8"))\n        design = data.get("symbol_index_current_design") or {}\n        return {\n            "available": True,\n            "version": data.get("version"),\n            "environment": data.get("environment"),\n            "full_rebuild_median_ms": design.get("median_ms"),\n            "fixture_python_files": design.get("fixture_python_files"),\n        }\n    except Exception as exc:\n        return {"available": False, "error": f"{type(exc).__name__}: {exc}"}\n\n\ndef run_incremental_index_benchmark(root: Path, repeats: int = 3) -> dict[str, Any]:\n    """Benchmark bootstrap, no-change, one-file-change and deletion paths in temp roots."""\n    root = root.resolve()\n    repeats = max(1, int(repeats))\n    bootstrap_samples: list[float] = []\n    no_change_samples: list[float] = []\n    changed_samples: list[float] = []\n    delete_samples: list[float] = []\n    contracts: list[dict[str, Any]] = []\n    copied_last = 0\n\n    for iteration in range(repeats):\n        with tempfile.TemporaryDirectory(prefix="agentos-v0234-index-") as temp:\n            temp_root = Path(temp)\n            source_rel, copied = _copy_workload(root, temp_root)\n            copied_last = copied\n            from .db import connect\n            with connect(temp_root):\n                pass\n            bootstrap_ms, bootstrap = _time(lambda: index_build(temp_root, source_rel))\n            no_change_ms, no_change = _time(lambda: index_build(temp_root, source_rel))\n\n            candidates = sorted((temp_root / source_rel).rglob("*.py"))\n            changed_result: dict[str, Any] = {"files_parsed": 0}\n            delete_result: dict[str, Any] = {"files_deleted": 0}\n            changed_ms = 0.0\n            delete_ms = 0.0\n            if candidates:\n                target = candidates[iteration % len(candidates)]\n                payload = target.read_bytes() + f"\\n# agentos-v0234-benchmark-{iteration}\\n".encode()\n                target.write_bytes(payload)\n                changed_ms, changed_result = _time(lambda: index_build(temp_root, source_rel))\n                target.unlink()\n                delete_ms, delete_result = _time(lambda: index_build(temp_root, source_rel))\n\n            bootstrap_samples.append(bootstrap_ms)\n            no_change_samples.append(no_change_ms)\n            changed_samples.append(changed_ms)\n            delete_samples.append(delete_ms)\n            contracts.append({\n                "bootstrap_mode": bootstrap.get("mode"),\n                "bootstrap_parsed_all": bootstrap.get("files_parsed") == bootstrap.get("files_seen"),\n                "no_change_mode": no_change.get("mode"),\n                "no_change_parsed_zero": no_change.get("files_parsed") == 0,\n                "one_change_parsed_one": changed_result.get("files_parsed") == (1 if candidates else 0),\n                "delete_removed_one": delete_result.get("files_deleted") == (1 if candidates else 0),\n            })\n\n    reference = _reference(root)\n    no_change_median = _summary(no_change_samples)["median_ms"]\n    baseline_median = reference.get("full_rebuild_median_ms") if reference.get("available") else None\n    speedup = None\n    if isinstance(baseline_median, (int, float)) and isinstance(no_change_median, (int, float)) and no_change_median > 0:\n        speedup = round(float(baseline_median) / float(no_change_median), 3)\n\n    functional_ok = all(\n        item["bootstrap_mode"] == "bootstrap_full_rebuild"\n        and item["bootstrap_parsed_all"]\n        and item["no_change_mode"] == "incremental"\n        and item["no_change_parsed_zero"]\n        and item["one_change_parsed_one"]\n        and item["delete_removed_one"]\n        for item in contracts\n    )\n    return {\n        "ok": functional_ok,\n        "version": VERSION,\n        "schema_version": CURRENT_SCHEMA_VERSION,\n        "measurement_scope": "temporary_fixture_only",\n        "measurement_status": "measured" if functional_ok else "invalid",\n        "wall_clock_portable": False,\n        "repeats": repeats,\n        "environment": {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()},\n        "fixture_python_files": copied_last,\n        "bootstrap": {"mode": "bootstrap_full_rebuild", **_summary(bootstrap_samples)},\n        "no_change_incremental": {"expected_files_parsed": 0, **_summary(no_change_samples)},\n        "single_file_change": {"expected_files_parsed": 1 if copied_last else 0, **_summary(changed_samples)},\n        "single_file_delete": {"expected_files_deleted": 1 if copied_last else 0, **_summary(delete_samples)},\n        "functional_contract_samples": contracts,\n        "v0233_reference": reference,\n        "no_change_vs_v0233_full_rebuild_speedup": speedup,\n        "timing_gate": "advisory_only_environment_not_pinned",\n    }\n\n\ndef check_incremental_index_benchmark(root: Path, path: str | None = None) -> dict[str, Any]:\n    """Validate benchmark structure and deterministic incremental behavior contracts."""\n    target = root.resolve() / (path or DEFAULT_BENCHMARK_FILE)\n    findings: list[str] = []\n    try:\n        data = json.loads(target.read_text(encoding="utf-8"))\n    except Exception as exc:\n        return {"ok": False, "findings": [f"benchmark_unloadable:{type(exc).__name__}"], "benchmark": str(target)}\n    if data.get("version") != VERSION:\n        findings.append("benchmark_version_mismatch")\n    if int(data.get("schema_version", -1)) != CURRENT_SCHEMA_VERSION:\n        findings.append("benchmark_schema_mismatch")\n    if data.get("measurement_status") != "measured":\n        findings.append("benchmark_not_measured")\n    if data.get("measurement_scope") != "temporary_fixture_only":\n        findings.append("benchmark_scope_invalid")\n    for section in ("bootstrap", "no_change_incremental", "single_file_change", "single_file_delete"):\n        value = data.get(section) or {}\n        if not isinstance(value.get("median_ms"), (int, float)):\n            findings.append(f"missing_timing:{section}")\n    samples = data.get("functional_contract_samples") or []\n    if not samples:\n        findings.append("missing_functional_contract_samples")\n    for item in samples:\n        if item.get("bootstrap_mode") != "bootstrap_full_rebuild" or not item.get("bootstrap_parsed_all"):\n            findings.append("bootstrap_contract_failed")\n        if item.get("no_change_mode") != "incremental" or not item.get("no_change_parsed_zero"):\n            findings.append("no_change_contract_failed")\n        if not item.get("one_change_parsed_one"):\n            findings.append("single_change_contract_failed")\n        if not item.get("delete_removed_one"):\n            findings.append("delete_contract_failed")\n    return {"ok": not findings, "version": VERSION, "schema_version": CURRENT_SCHEMA_VERSION, "benchmark": path or DEFAULT_BENCHMARK_FILE, "findings": sorted(set(findings))}\n', '.agents/tests/test_incremental_index_v0234.py': '"""Regression tests for v0.23.4 Incremental Symbol Index."""\nfrom __future__ import annotations\n\nfrom pathlib import Path\nimport sqlite3\nimport pytest\n\nfrom agentos.db import connect\nfrom agentos.indexing import index_build, index_query, index_status\n\n\ndef _project(tmp_path: Path) -> Path:\n    root = tmp_path / "project"\n    src = root / "src"\n    src.mkdir(parents=True)\n    (src / "a.py").write_bytes(b"def alpha():\\n    return 1\\n")\n    (src / "b.py").write_bytes(b"class Beta:\\n    pass\\n")\n    return root\n\n\ndef test_schema_47_adds_incremental_index_state(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    with connect(root) as conn:\n        version = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()["v"]\n        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=\'table\'")}\n    assert version == 47\n    assert {"symbol_index_state", "symbol_index_files"} <= tables\n\n\ndef test_bootstrap_then_no_change_parses_zero_files(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    first = index_build(root)\n    second = index_build(root)\n    assert first["mode"] == "bootstrap_full_rebuild"\n    assert first["files_parsed"] == 2\n    assert second["mode"] == "incremental"\n    assert second["files_parsed"] == 0\n    assert second["files_unchanged"] == 2\n    assert second["symbols"] == first["symbols"]\n\n\ndef test_single_change_replaces_only_changed_file(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    index_build(root)\n    (root / "src/a.py").write_bytes(b"def gamma():\\n    return 2\\n")\n    result = index_build(root)\n    assert result["files_parsed"] == 1\n    assert result["files_changed"] == 1\n    assert not index_query(root, "alpha")\n    assert index_query(root, "gamma")\n    assert index_query(root, "Beta")\n\n\ndef test_deleted_file_removes_stale_symbols_without_reparse(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    index_build(root)\n    (root / "src/b.py").unlink()\n    result = index_build(root)\n    assert result["files_deleted"] == 1\n    assert result["files_parsed"] == 0\n    assert not index_query(root, "Beta")\n    assert index_query(root, "alpha")\n\n\ndef test_parse_failure_is_atomic(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    index_build(root)\n    before = index_status(root)\n    (root / "src/a.py").write_bytes(b"def broken(:\\n")\n    with pytest.raises(RuntimeError, match="cannot index src/a.py"):\n        index_build(root)\n    after = index_status(root)\n    assert after["generation"] == before["generation"]\n    assert index_query(root, "alpha")\n\n\ndef test_source_change_and_force_full_rebuild(tmp_path: Path) -> None:\n    root = _project(tmp_path)\n    other = root / "other"\n    other.mkdir()\n    (other / "c.py").write_bytes(b"def charlie():\\n    return 3\\n")\n    index_build(root)\n    switched = index_build(root, "other")\n    assert switched["mode"] == "full_rebuild"\n    assert not index_query(root, "alpha")\n    assert index_query(root, "charlie")\n    forced = index_build(root, "other", force_full=True)\n    assert forced["mode"] == "full_rebuild"\n    assert forced["files_parsed"] == 1\n', '.agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md': '# AgentOS v0.23.4 — Incremental Symbol Index\n\n## Mục tiêu\n\nv0.23.4 thay full symbol-index rebuild bằng cập nhật tăng dần có content-hash, nhưng không đánh đổi correctness để lấy tốc độ.\n\n## Invariant\n\n- Schema tăng **46 → 47** để lưu `symbol_index_state` và `symbol_index_files`.\n- Lần đầu sau upgrade chạy `bootstrap_full_rebuild`; không tin symbol rows cũ khi chưa có file hash.\n- Mỗi lần scan vẫn SHA-256 bytes của file để phát hiện thay đổi chính xác; file không đổi **không AST parse**.\n- File mới/đổi được parse từ đúng bytes dùng để hash rồi thay thế riêng symbol rows của file đó.\n- File bị xóa làm xóa symbol rows tương ứng mà không parse lại file khác.\n- Parse/decode error fail-closed và rollback toàn transaction; index cũ vẫn nguyên vẹn.\n- Đổi source root hoặc `index-build --full` sẽ full rebuild có chủ đích.\n- Symlink file bị bỏ qua; source path không được thoát khỏi project root.\n- Không thay đổi SOURCE/TARGET database authority, privacy, secret, signed-audit hoặc Context Control Plane.\n\n## CLI\n\n```bash\nagentos index-build src\nagentos index-build src --full\nagentos index-status\nagentos index-benchmark-run --repeats 3 --output INDEX_INCREMENTAL_BENCHMARK_V0234.json\nagentos index-benchmark-check\n```\n\n`index-build` giữ tương thích các field `files` và `symbols`, đồng thời thêm telemetry incremental.\n\n## Benchmark contract\n\nBenchmark chạy hoàn toàn trong temporary fixture và bắt buộc xác nhận:\n\n1. bootstrap parse toàn bộ file;\n2. no-change incremental parse 0 file;\n3. đổi một file parse đúng 1 file;\n4. xóa một file xóa đúng state/symbol của file đó.\n\nTiming so với `PERFORMANCE_BASELINE_V0233.json` chỉ advisory vì wall-clock chưa environment-pinned.\n', 'RELEASE_NOTES_V0234.md': '# AgentOS Local Governance v0.23.4 — Incremental Symbol Index\n\nv0.23.4 converts the historical full-rebuild Python symbol index into a deterministic content-hash incremental index.\n\n## Changes\n\n- Schema 46 → 47 with persistent per-file index state.\n- `index-build` is incremental by default; `--full` forces rebuild.\n- First post-upgrade build bootstraps metadata with one full rebuild.\n- Unchanged files are hashed but not AST-parsed.\n- Changed/new files replace only their own symbol rows; deleted files remove stale rows.\n- Parse failures are transaction-atomic and preserve the previously valid index.\n- New `index-status`, `index-benchmark-run`, and `index-benchmark-check` commands.\n- Benchmark compares no-change incremental behavior to v0.23.3 full-rebuild baseline without introducing environment-specific hard timing thresholds.\n- SOURCE/TARGET, human approval, signed-audit, privacy/secret/key and lossless Context Control Plane invariants are unchanged.\n', 'UPGRADE_FROM_0.23.3.md': '# Upgrade v0.23.3 → v0.23.4\n\nWindows / Linux / macOS use the same Python updater:\n\n```bash\npython tools/apply_v0234.py .\n```\n\nThe updater is fail-closed, backs up patched files, migrates schema 46→47 on validation, captures `INDEX_INCREMENTAL_BENCHMARK_V0234.json` in temporary fixtures, and runs the v0.23.4 targeted regression test.\n\nAfter success, run the full repository suite before publishing:\n\n```bash\npython -m pytest -q .agents/tests\n```\n\nOn a direct Python pytest invocation, ensure `.agents` is on `PYTHONPATH` if your shell does not inherit it from the AgentOS launcher.\n', 'INDEX_INCREMENTAL_BENCHMARK_V0234.json': '{\n  "ok": false,\n  "version": "0.23.4",\n  "schema_version": 47,\n  "measurement_scope": "temporary_fixture_only",\n  "measurement_status": "unmeasured_template",\n  "note": "tools/apply_v0234.py captures the measured benchmark automatically after upgrade"\n}\n', 'tools/validate_v0234.py': '#!/usr/bin/env python3\n"""Validate AgentOS v0.23.4 Incremental Symbol Index release structure."""\nfrom __future__ import annotations\nimport argparse\nimport json\nfrom pathlib import Path\n\nVERSION = "0.23.4"\nSCHEMA = 47\n\n\ndef validate(root: Path) -> dict[str, object]:\n    root = root.resolve()\n    findings: list[str] = []\n    required = (\n        ".agents/agentos/indexing.py",\n        ".agents/agentos/incremental_index_benchmark.py",\n        ".agents/tests/test_incremental_index_v0234.py",\n        ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",\n        "UPGRADE_FROM_0.23.3.md",\n        "RELEASE_NOTES_V0234.md",\n        "INDEX_INCREMENTAL_BENCHMARK_V0234.json",\n    )\n    version_path = root / "VERSION"\n    if not version_path.is_file() or version_path.read_text(encoding="utf-8").strip() != VERSION:\n        findings.append("version")\n    schema_path = root / ".agents/agentos/schema_version.py"\n    if not schema_path.is_file() or "CURRENT_SCHEMA_VERSION = 47" not in schema_path.read_text(encoding="utf-8"):\n        findings.append("schema")\n    for rel in required:\n        if not (root / rel).is_file():\n            findings.append(f"missing:{rel}")\n    index_text = (root / ".agents/agentos/indexing.py").read_text(encoding="utf-8") if (root / ".agents/agentos/indexing.py").is_file() else ""\n    for marker in ("symbol_index_files", "bootstrap_full_rebuild", "files_unchanged", "force_full"):\n        if marker not in index_text:\n            findings.append(f"index_marker:{marker}")\n    db_text = (root / ".agents/agentos/db.py").read_text(encoding="utf-8") if (root / ".agents/agentos/db.py").is_file() else ""\n    if "migration_47" not in db_text:\n        findings.append("migration_47_registration")\n    policy_path = root / ".agents/config/governance.json"\n    try:\n        policy = json.loads(policy_path.read_text(encoding="utf-8"))\n        if policy.get("version") != VERSION:\n            findings.append("governance_version")\n        if int((policy.get("documentation_policy") or {}).get("current_schema", -1)) != SCHEMA:\n            findings.append("governance_schema")\n        index_policy = policy.get("incremental_symbol_index_policy") or {}\n        if index_policy.get("unchanged_file_ast_parse") != "forbidden":\n            findings.append("index_policy")\n    except Exception:\n        findings.append("governance_invalid")\n    benchmark_findings: list[str] = []\n    try:\n        bench = json.loads((root / "INDEX_INCREMENTAL_BENCHMARK_V0234.json").read_text(encoding="utf-8"))\n        if bench.get("version") != VERSION or int(bench.get("schema_version", -1)) != SCHEMA:\n            benchmark_findings.append("benchmark_version_schema")\n        if bench.get("measurement_status") != "measured" or bench.get("ok") is not True:\n            benchmark_findings.append("benchmark_not_measured")\n    except Exception as exc:\n        benchmark_findings.append(f"benchmark_invalid:{type(exc).__name__}")\n    return {\n        "ok": not findings and not benchmark_findings,\n        "version": VERSION,\n        "schema": SCHEMA,\n        "findings": findings,\n        "benchmark_findings": benchmark_findings,\n    }\n\n\ndef main() -> int:\n    ap = argparse.ArgumentParser()\n    ap.add_argument("root", nargs="?", default=".")\n    args = ap.parse_args()\n    result = validate(Path(args.root))\n    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))\n    return 0 if result["ok"] else 2\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'}


def _read_preserve(path: Path) -> tuple[str, str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline


def _write_preserve(path: Path, text: str, newline: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = text if newline == "\n" else text.replace("\n", "\r\n")
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(raw)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one baseline pattern, got {count}")
    return text.replace(old, new, 1)


def _patch(path: Path, patches: list[tuple[str, str, str]], dry_run: bool) -> None:
    text, newline = _read_preserve(path)
    updated = text
    for old, new, label in patches:
        updated = _replace_once(updated, old, new, label)
    if not dry_run:
        _write_preserve(path, updated, newline)


def _prepend_changelog(path: Path, entry: str, dry_run: bool) -> None:
    text, newline = _read_preserve(path)
    if entry.strip() in text:
        return
    text = _replace_once(text, "# Changelog\n", "# Changelog\n" + entry, f"{path.name} changelog header")
    if not dry_run:
        _write_preserve(path, text, newline)


def _backup(root: Path, rels: list[str]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / f".agents/runtime/upgrade-backups/v0.23.3-to-v0.23.4-{stamp}"
    for rel in rels:
        src = root / rel
        if src.exists():
            dst = base / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return base


def _write_payload(root: Path, dry_run: bool) -> list[str]:
    written=[]
    for rel, content in PAYLOAD.items():
        path=root/rel
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        written.append(rel)
    return written


def _patch_docs(root: Path, dry_run: bool) -> None:
    _patch(root / "README.md", [
        ("**Current release: v0.23.3 — Consolidation Cockpit & Performance Baseline**", "**Current release: v0.23.4 — Incremental Symbol Index**", "README release header"),
        ("Database schema: **46** (unchanged). MCP adds read-only cockpit/baseline inspection only; benchmark execution remains CLI/operator-only and all write-heavy measurements run in temporary fixtures.", "Database schema: **47**. v0.23.4 adds deterministic per-file content-hash state for the local Python symbol index. MCP authority is unchanged; index mutation/benchmark execution remain local CLI/operator functions.", "README schema summary"),
        ("See [UPGRADE_FROM_0.23.2.md](UPGRADE_FROM_0.23.2.md).", "See [UPGRADE_FROM_0.23.3.md](UPGRADE_FROM_0.23.3.md).", "README upgrade link"),
        ("## Node documentation\n- [Consolidation Cockpit & Performance Baseline]", "## Node documentation\n- [Incremental Symbol Index](.agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md)\n- [Consolidation Cockpit & Performance Baseline]", "README node doc"),
    ], dry_run)
    _patch(root / "README.vi.md", [
        ("# AgentOS Local Governance v0.23.3 — Consolidation Cockpit & Performance Baseline", "# AgentOS Local Governance v0.23.4 — Incremental Symbol Index", "README.vi header"),
        ("## v0.23.3\n", "## v0.23.4\n\nv0.23.4 chuyển `index-build` sang incremental mặc định: file không đổi vẫn được SHA-256 để bảo đảm correctness nhưng không AST-parse; file mới/đổi chỉ thay symbol rows của chính file đó; file xóa loại stale rows. Lần đầu sau migration 47 bootstrap full rebuild để seed metadata.\n\n## v0.23.3\n", "README.vi section"),
    ], dry_run)
    _patch(root / "README.en.md", [
        ("# AgentOS Local Governance v0.23.3 — Consolidation Cockpit & Performance Baseline", "# AgentOS Local Governance v0.23.4 — Incremental Symbol Index", "README.en header"),
        ("v0.23.3 adds a read-only end-to-end consolidation cockpit", "v0.23.4 adds a deterministic content-hash incremental Python symbol index. Unchanged files are not AST-parsed; changed/new files replace only their own rows and deleted files remove stale rows. Schema is **47**.\n\n## v0.23.3 foundation\n\nv0.23.3 adds a read-only end-to-end consolidation cockpit", "README.en section"),
    ], dry_run)
    _patch(root / "huong_dan.md", [
        ("Current version: **0.23.3**. Database schema: **46**.", "Current version: **0.23.4**. Database schema: **47**.", "guide landing version"),
    ], dry_run)
    _patch(root / "huong_dan.vi.md", [
        ("# Hướng dẫn AgentOS v0.23.3", "# Hướng dẫn AgentOS v0.23.4", "guide.vi header"),
    ], dry_run)
    _patch(root / "huong_dan.en.md", [
        ("# AgentOS v0.23.3 Developer Guide", "# AgentOS v0.23.4 Developer Guide", "guide.en header"),
    ], dry_run)
    entry = """## 0.23.4 — Incremental Symbol Index\n- Replaced repeated full symbol-index rebuilds with deterministic per-file content-hash incremental updates.\n- Added schema 47 file-state metadata, bootstrap full rebuild, deletion cleanup and atomic parse-failure rollback.\n- Added no-change/change/delete benchmark contracts against the measured v0.23.3 full-rebuild baseline.\n- Preserved all SOURCE/TARGET, privacy, signed-audit, human approval and lossless Context Control Plane invariants.\n\n"""
    _prepend_changelog(root / "CHANGELOG.md", entry, dry_run)
    rules = """## v0.23.4 — Incremental Symbol Index\n- **Decision:** persist content hashes for indexed Python files and parse only new/changed bytes.\n- **Safety:** first post-upgrade run bootstraps metadata with a full rebuild; parse failure rolls back the transaction; source path escape is blocked.\n- **Performance contract:** no-change parse count is zero; one-file change parses one file; deleted files remove stale rows. Timing remains advisory until environment-pinned.\n- **Authority:** no MCP mutation is added and database/privacy/context governance boundaries are unchanged.\n\n"""
    _prepend_changelog(root / ".agents/docs/RULES_WORKFLOW_CHANGELOG.md", rules, dry_run)


def _classify_indexing_source(text: str) -> dict[str, object]:
    """Classify the local indexing implementation by Python semantics, not formatting.

    The v0.23.3 baseline is accepted when ``index_build`` still represents the
    historical whole-tree implementation: it scans ``*.py`` and writes the
    ``symbol_index`` table, while v0.23.4 state markers are absent. Quoting,
    whitespace, comments and CRLF/LF differences are intentionally ignored.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise RuntimeError(f"indexing.py cannot be parsed: {exc}") from exc

    fn = next(
        (node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "index_build"),
        None,
    )
    if fn is None:
        raise RuntimeError("indexing.py baseline is unsupported: index_build() missing")

    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    has_symbol_index_write = any("symbol_index" in value for value in string_literals)
    has_python_tree_scan = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rglob"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "*.py"
        for node in ast.walk(fn)
    )
    target_markers = {
        "symbol_index_files",
        "symbol_index_state",
        "bootstrap_full_rebuild",
        "files_unchanged",
    }
    has_target_markers = any(marker in text for marker in target_markers)
    has_force_full = any(arg.arg == "force_full" for arg in fn.args.args + fn.args.kwonlyargs)

    if has_target_markers or has_force_full:
        return {
            "mode": "incremental_or_partial_v0234",
            "has_symbol_index_write": has_symbol_index_write,
            "has_python_tree_scan": has_python_tree_scan,
        }
    if has_symbol_index_write and has_python_tree_scan:
        return {
            "mode": "v0233_full_rebuild_semantic",
            "has_symbol_index_write": True,
            "has_python_tree_scan": True,
        }
    return {
        "mode": "unsupported",
        "has_symbol_index_write": has_symbol_index_write,
        "has_python_tree_scan": has_python_tree_scan,
    }


V0233_INDEXING_BASELINE = '"""\nFile: .agents/agentos/indexing.py\n\nPurpose:\n    Build and query a project-local Python symbol index.\n\nResponsibilities:\n    - Parse Python source through AST.\n    - Store qualified symbols and deterministic fingerprints.\n    - Return bounded symbol matches and duplicate candidates.\n"""\nfrom __future__ import annotations\n\nimport ast\nimport hashlib\nfrom pathlib import Path\nfrom typing import Any\n\nfrom .db import connect\n\n\ndef _fingerprint(node: ast.AST) -> str:\n    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()\n\n\ndef index_build(root: Path, source: str = "src") -> dict[str, int]:\n    """Rebuild the Python symbol index for a source tree.\n\n    Args:\n        root: Project root.\n        source: Project-relative source directory.\n\n    Returns:\n        Counts of indexed files and symbols.\n    """\n    base = root.resolve() / source\n    files = 0\n    symbols = 0\n    with connect(root) as c:\n        c.execute("DELETE FROM symbol_index")\n        for path in sorted(base.rglob("*.py")) if base.exists() else []:\n            files += 1\n            tree = ast.parse(path.read_text(encoding="utf-8"))\n            rel = path.relative_to(root.resolve()).as_posix()\n            for node in ast.walk(tree):\n                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):\n                    kind = "class" if isinstance(node, ast.ClassDef) else "function"\n                    signature = node.name\n                    c.execute(\n                        "INSERT OR REPLACE INTO symbol_index(path,qualname,kind,line_start,line_end,signature,fingerprint) VALUES(?,?,?,?,?,?,?)",\n                        (rel, node.name, kind, node.lineno, getattr(node, "end_lineno", node.lineno), signature, _fingerprint(node)),\n                    )\n                    symbols += 1\n    return {"files": files, "symbols": symbols}\n\n\ndef index_query(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:\n    """Find indexed symbols matching a query.\n\n    Args:\n        root: Project root.\n        query: Symbol search text.\n        limit: Maximum number of results.\n\n    Returns:\n        Matching symbol records ordered deterministically.\n    """\n    like = f"%{query}%"\n    with connect(root) as c:\n        rows = c.execute(\n            "SELECT path,qualname,kind,line_start,line_end,signature,fingerprint FROM symbol_index WHERE qualname LIKE ? ORDER BY CASE WHEN qualname=? THEN 0 ELSE 1 END,path,qualname LIMIT ?",\n            (like, query, limit),\n        ).fetchall()\n    return [dict(row) for row in rows]\n\n\ndef duplicate_report(root: Path) -> list[dict[str, Any]]:\n    """Return groups of symbols with identical AST fingerprints.\n\n    Args:\n        root: Project root.\n\n    Returns:\n        Duplicate candidate groups.\n    """\n    with connect(root) as c:\n        fps = c.execute("SELECT fingerprint FROM symbol_index GROUP BY fingerprint HAVING COUNT(*) > 1").fetchall()\n        out = []\n        for fp in fps:\n            rows = c.execute("SELECT path,qualname FROM symbol_index WHERE fingerprint=? ORDER BY path,qualname", (fp["fingerprint"],)).fetchall()\n            out.append({"fingerprint": fp["fingerprint"], "symbols": [dict(r) for r in rows]})\n    return out\n'

def _repair_partial_indexing(root: Path) -> dict[str, object]:
    """Repair the known partial-overlay state before normal v0.23.4 preflight.

    This state occurs when the v0.23.4 payload overwrote indexing.py while the
    authoritative VERSION/schema/governance files are still v0.23.3/schema 46.
    The repair backs up the partial file, restores the canonical v0.23.3 indexing
    baseline, and lets the normal fail-closed upgrader re-apply v0.23.4 atomically.
    """
    version_path = root / "VERSION"
    schema_path = root / ".agents/agentos/schema_version.py"
    policy_path = root / ".agents/config/governance.json"
    indexing_path = root / ".agents/agentos/indexing.py"
    if not all(path.is_file() for path in (version_path, schema_path, policy_path, indexing_path)):
        return {"status": "not_applicable_missing_files"}
    version = version_path.read_text(encoding="utf-8").strip()
    schema_text = schema_path.read_text(encoding="utf-8")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "not_applicable_invalid_governance"}
    current_text = indexing_path.read_text(encoding="utf-8")
    state = _classify_indexing_source(current_text)
    if state.get("mode") != "incremental_or_partial_v0234":
        return {"status": "not_needed", "indexing_state": state}
    if version != BASELINE or "CURRENT_SCHEMA_VERSION = 46" not in schema_text or policy.get("version") != BASELINE:
        raise RuntimeError(
            "partial v0.23.4 indexing detected, but VERSION/schema/governance are not the known recoverable v0.23.3 state"
        )
    required_markers = (
        "def migration_47", "symbol_index_files", "symbol_index_state",
        "bootstrap_full_rebuild", "def index_status", "force_full",
    )
    missing = [marker for marker in required_markers if marker not in current_text]
    if missing:
        raise RuntimeError(f"partial indexing.py is not the known v0.23.4 payload; missing markers: {missing}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / f".agents/runtime/upgrade-recovery/v0.23.4-partial-indexing-{stamp}/indexing.py"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(indexing_path, backup)
    indexing_path.write_text(V0233_INDEXING_BASELINE, encoding="utf-8", newline="\n")
    restored = _classify_indexing_source(indexing_path.read_text(encoding="utf-8"))
    if restored.get("mode") != "v0233_full_rebuild_semantic":
        raise RuntimeError("failed to restore canonical v0.23.3 indexing baseline")
    return {
        "status": "repaired_partial_indexing",
        "backup": backup.relative_to(root).as_posix(),
        "before": state,
        "after": restored,
    }

def _preflight(root: Path) -> dict[str, object]:
    version_path=root/"VERSION"
    if not version_path.is_file():
        raise RuntimeError("VERSION missing")
    current=version_path.read_text(encoding="utf-8").strip()
    if current not in {BASELINE, TARGET}:
        raise RuntimeError(f"upgrade requires VERSION {BASELINE} or {TARGET}; found {current!r}")
    if current == TARGET:
        return {"version": current, "already_target": True}
    required=(
        ".agents/agentos/indexing.py", ".agents/agentos/db.py", ".agents/agentos/cli.py",
        ".agents/agentos/cli_runtime.py", ".agents/agentos/mcp_runtime.py",
        ".agents/agentos/release_integrity.py", ".agents/agentos/performance_baseline.py",
        ".agents/agentos/schema_version.py", ".agents/agentos/__init__.py",
        ".agents/config/governance.json", "PERFORMANCE_BASELINE_V0233.json",
        "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
        "CHANGELOG.md", ".agents/docs/RULES_WORKFLOW_CHANGELOG.md",
    )
    missing=[rel for rel in required if not (root/rel).is_file()]
    if missing:
        raise RuntimeError(f"required v0.23.3 files missing: {missing}")
    schema=(root/".agents/agentos/schema_version.py").read_text(encoding="utf-8")
    if "CURRENT_SCHEMA_VERSION = 46" not in schema:
        raise RuntimeError("v0.23.4 requires v0.23.3 schema 46 baseline")
    indexing=(root/".agents/agentos/indexing.py").read_text(encoding="utf-8")
    index_state=_classify_indexing_source(indexing)
    if index_state["mode"] != "v0233_full_rebuild_semantic":
        raise RuntimeError(
            "indexing.py semantic baseline is unsupported for v0.23.4: "
            + json.dumps(index_state, ensure_ascii=False, sort_keys=True)
        )
    policy=json.loads((root/".agents/config/governance.json").read_text(encoding="utf-8"))
    if policy.get("version") != BASELINE:
        raise RuntimeError(f"governance baseline must be {BASELINE}; found {policy.get('version')!r}")
    perf=json.loads((root/"PERFORMANCE_BASELINE_V0233.json").read_text(encoding="utf-8"))
    if perf.get("version") != BASELINE or perf.get("measurement_status") != "measured":
        raise RuntimeError("measured PERFORMANCE_BASELINE_V0233.json is required before v0.23.4")
    return {
        "version": current,
        "already_target": False,
        "indexing_baseline": index_state,
        "v0233_symbol_index_median_ms": (perf.get("symbol_index_current_design") or {}).get("median_ms"),
    }


def _apply_patches(root: Path, dry_run: bool) -> None:
    _patch(root/".agents/agentos/schema_version.py", [("CURRENT_SCHEMA_VERSION = 46", "CURRENT_SCHEMA_VERSION = 47", "schema version")], dry_run)
    _patch(root/".agents/agentos/db.py", [
        ("    from .context_evaluation import migration_46\n    return [migration_32, migration_33, migration_34, migration_35, migration_36, migration_37, migration_38, migration_39, migration_40, _m41, migration_42, migration_43, migration_44, migration_45, migration_46]",
         "    from .context_evaluation import migration_46\n    from .indexing import migration_47\n    return [migration_32, migration_33, migration_34, migration_35, migration_36, migration_37, migration_38, migration_39, migration_40, _m41, migration_42, migration_43, migration_44, migration_45, migration_46, migration_47]", "migration 47 registration"),
    ], dry_run)
    _patch(root/".agents/agentos/cli.py", [
        ("from .indexing import duplicate_report, index_build, index_query", "from .indexing import duplicate_report, index_build, index_query, index_status\nfrom .incremental_index_benchmark import DEFAULT_BENCHMARK_FILE, check_incremental_index_benchmark, run_incremental_index_benchmark", "CLI index imports"),
        ('    a=s.add_parser("index-build"); a.add_argument("source",nargs="?",default="src"); _task_arg(a)\n    a=s.add_parser("index-query")', '    a=s.add_parser("index-build"); a.add_argument("source",nargs="?",default="src"); a.add_argument("--full",action="store_true"); _task_arg(a)\n    s.add_parser("index-status")\n    a=s.add_parser("index-benchmark-run"); a.add_argument("--repeats",type=int,default=3); a.add_argument("--output",default=DEFAULT_BENCHMARK_FILE)\n    a=s.add_parser("index-benchmark-check"); a.add_argument("--path",default=DEFAULT_BENCHMARK_FILE)\n    a=s.add_parser("index-query")', "CLI index parsers"),
        ('        elif args.cmd=="index-build": result=index_build(root,args.source); complete_automated_step(root,tid,"build_or_update_local_index","index-build",result)\n        elif args.cmd=="index-query":', '        elif args.cmd=="index-build": result=index_build(root,args.source,force_full=args.full); complete_automated_step(root,tid,"build_or_update_local_index","index-build",result)\n        elif args.cmd=="index-status": result=index_status(root)\n        elif args.cmd=="index-benchmark-run":\n            result=run_incremental_index_benchmark(root,args.repeats)\n            output=(root/args.output).resolve()\n            try: output.relative_to(root)\n            except ValueError as exc: raise RuntimeError("index benchmark output must stay inside project root") from exc\n            output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\\n",encoding="utf-8")\n            result={**result,"output":output.relative_to(root).as_posix()}\n        elif args.cmd=="index-benchmark-check": result=check_incremental_index_benchmark(root,args.path)\n        elif args.cmd=="index-query":', "CLI index dispatch"),
    ], dry_run)
    _patch(root/".agents/agentos/cli_runtime.py", [
        ('VERSION = "0.23.3"', 'VERSION = "0.23.4"', "CLI runtime version"),
        ('AgentOS Local Governance v0.23.3 — unified CLI runtime', 'AgentOS Local Governance v0.23.4 — unified CLI runtime', "CLI help version"),
    ], dry_run)
    _patch(root/".agents/agentos/mcp_runtime.py", [('VERSION = "0.23.3"', 'VERSION = "0.23.4"', "MCP runtime version")], dry_run)
    _patch(root/".agents/agentos/__init__.py", [('0.23.3','0.23.4','package version')], dry_run)
    _patch(root/".agents/agentos/performance_baseline.py", [
        ('VERSION = "0.23.3"\nDEFAULT_BASELINE_FILE = "PERFORMANCE_BASELINE_V0233.json"', 'VERSION = "0.23.3"\nBASELINE_SCHEMA_VERSION = 46\nDEFAULT_BASELINE_FILE = "PERFORMANCE_BASELINE_V0233.json"', "historical baseline schema constant"),
        ('    if int(baseline.get("schema_version", -1)) != CURRENT_SCHEMA_VERSION:\n        findings.append("baseline_schema_mismatch")', '    if int(baseline.get("schema_version", -1)) != BASELINE_SCHEMA_VERSION:\n        findings.append("baseline_schema_mismatch")', "historical baseline schema check"),
        ('    if migration.get("chain_length") not in (None, CURRENT_SCHEMA_VERSION):', '    if migration.get("chain_length") not in (None, BASELINE_SCHEMA_VERSION):', "historical baseline migration check"),
        ('    root = root.resolve()\n    repeats = max(1, int(repeats))', '    if CURRENT_SCHEMA_VERSION != BASELINE_SCHEMA_VERSION:\n        raise RuntimeError("PERFORMANCE_BASELINE_V0233 is frozen at schema 46; use index-benchmark-run for v0.23.4+")\n    root = root.resolve()\n    repeats = max(1, int(repeats))', "freeze historical baseline capture"),
    ], dry_run)
    _patch(root/".agents/agentos/release_integrity.py", [
        ('    "PERFORMANCE_BASELINE_V0233.json",\n    ".github/workflows/agentos-release-validation.yml",', '    "PERFORMANCE_BASELINE_V0233.json",\n    "tools/apply_v0234.py",\n    "tools/validate_v0234.py",\n    ".agents/tests/test_incremental_index_v0234.py",\n    ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",\n    "UPGRADE_FROM_0.23.3.md",\n    "INDEX_INCREMENTAL_BENCHMARK_V0234.json",\n    ".github/workflows/agentos-release-validation.yml",', "v0.23.4 release files"),
        ('    ".agents/agentos/mcp_consolidation_cockpit.py",\n)', '    ".agents/agentos/mcp_consolidation_cockpit.py",\n    ".agents/agentos/indexing.py",\n    ".agents/agentos/incremental_index_benchmark.py",\n)', "v0.23.4 extension files"),
        ('    "consolidation_cockpit_policy",\n)', '    "consolidation_cockpit_policy",\n    "incremental_symbol_index_policy",\n)', "v0.23.4 policy section"),
        ('    except Exception as exc:\n        findings.append(_finding("performance_baseline_unloadable", f"cannot validate performance baseline: {exc}", "PERFORMANCE_BASELINE_V0233.json"))\n\n    version =', '    except Exception as exc:\n        findings.append(_finding("performance_baseline_unloadable", f"cannot validate performance baseline: {exc}", "PERFORMANCE_BASELINE_V0233.json"))\n    try:\n        from .incremental_index_benchmark import check_incremental_index_benchmark\n        index_benchmark = check_incremental_index_benchmark(root)\n        for code in index_benchmark.get("findings", []):\n            findings.append(_finding("incremental_index_benchmark_invalid", str(code), "INDEX_INCREMENTAL_BENCHMARK_V0234.json"))\n    except Exception as exc:\n        findings.append(_finding("incremental_index_benchmark_unloadable", f"cannot validate incremental index benchmark: {exc}", "INDEX_INCREMENTAL_BENCHMARK_V0234.json"))\n    version =', "v0.23.4 benchmark release gate"),
        ('version != "0.23.3"', 'version != "0.23.4"', "release VERSION comparison"),
        ('expected VERSION 0.23.3', 'expected VERSION 0.23.4', "release VERSION message"),
        ('policy.get("version") != "0.23.3"', 'policy.get("version") != "0.23.4"', "release governance comparison"),
        ('governance.json version must be 0.23.3', 'governance.json version must be 0.23.4', "release governance message"),
        ('    "PERFORMANCE_BASELINE_V0233.json",\n)', '    "PERFORMANCE_BASELINE_V0233.json",\n    ".agents/docs/INCREMENTAL_SYMBOL_INDEX_V0234.md",\n    "UPGRADE_FROM_0.23.3.md",\n    "INDEX_INCREMENTAL_BENCHMARK_V0234.json",\n)', "v0.23.4 docs registration"),
        ('numbers and therefore cannot be chained as the current-release gate. v0.23.3', 'numbers and therefore cannot be chained as the current-release gate. v0.23.4', "docs current version"),
    ], dry_run)
    _patch_docs(root, dry_run)


def _update_governance(root: Path, dry_run: bool) -> None:
    path=root/".agents/config/governance.json"
    policy=json.loads(path.read_text(encoding="utf-8"))
    policy["version"]=TARGET
    policy.setdefault("documentation_policy", {})["current_schema"]=SCHEMA
    policy["incremental_symbol_index_policy"]={
        "mode":"content_hash_incremental",
        "bootstrap_after_migration":"full_rebuild_required",
        "unchanged_file_hash_check":"required",
        "unchanged_file_ast_parse":"forbidden",
        "changed_file_replace_scope":"same_file_only",
        "deleted_file_stale_symbol_cleanup":"required",
        "parse_failure":"transaction_rollback_fail_closed",
        "source_path_escape":"forbidden",
        "symlink_file_indexing":"skipped",
        "force_full_rebuild":"operator_cli_only",
        "mcp_mutation":"forbidden",
        "timing_threshold":"advisory_until_environment_pinned",
    }
    if not dry_run:
        path.write_text(json.dumps(policy,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        (root/"VERSION").write_text(TARGET+"\n",encoding="utf-8")
        shutil.copy2(root/"RELEASE_NOTES_V0234.md", root/"RELEASE_NOTES.md")


def _run(root: Path, cmd: list[str], env: dict[str,str] | None=None) -> dict[str, object]:
    cp=subprocess.run(cmd,cwd=root,text=True,capture_output=True,env=env)
    return {"command":cmd,"returncode":cp.returncode,"stdout":cp.stdout,"stderr":cp.stderr,"ok":cp.returncode==0}


def _capture_benchmark(root: Path, repeats: int) -> dict[str, object]:
    env=os.environ.copy(); env["PYTHONPATH"]=str(root/".agents") + (os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code='from pathlib import Path; import json,sys; from agentos.incremental_index_benchmark import run_incremental_index_benchmark,check_incremental_index_benchmark; r=Path(sys.argv[1]); d=run_incremental_index_benchmark(r,int(sys.argv[2])); (r/"INDEX_INCREMENTAL_BENCHMARK_V0234.json").write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+"\\n",encoding="utf-8"); print(json.dumps({"benchmark":d,"check":check_incremental_index_benchmark(r)},ensure_ascii=False))'
    result=_run(root,[sys.executable,"-c",code,str(root),str(repeats)],env)
    if not result["ok"]: return result
    try: result["result"]=json.loads(str(result["stdout"]).strip().splitlines()[-1])
    except Exception: pass
    return result


def apply(root: Path, *, dry_run: bool=False, repeats: int=3, run_tests: bool=True) -> dict[str, object]:
    root=root.resolve()
    recovery = {"status": "dry_run_not_mutated"} if dry_run else _repair_partial_indexing(root)
    if dry_run:
        # Inspect without mutating. A recoverable partial indexing payload is accepted
        # by simulating the canonical v0.23.3 indexing baseline for preflight only.
        index_path = root / ".agents/agentos/indexing.py"
        original = index_path.read_text(encoding="utf-8") if index_path.is_file() else None
        state = _classify_indexing_source(original) if original is not None else {"mode": "missing"}
        if state.get("mode") == "incremental_or_partial_v0234":
            index_path.write_text(V0233_INDEXING_BASELINE, encoding="utf-8", newline="\n")
            try:
                pre = _preflight(root)
            finally:
                index_path.write_text(original, encoding="utf-8", newline="\n")
            recovery = {"status": "recoverable_partial_indexing", "before": state}
        else:
            pre = _preflight(root)
    else:
        pre=_preflight(root)
    already_target = bool(pre["already_target"])
    if already_target:
        # Resume/finalize a previously applied target tree without patching again.
        written=[]
        backup=None
    changed=[
        "VERSION",".agents/agentos/indexing.py",".agents/agentos/db.py",".agents/agentos/cli.py",
        ".agents/agentos/cli_runtime.py",".agents/agentos/mcp_runtime.py",".agents/agentos/release_integrity.py",
        ".agents/agentos/performance_baseline.py",".agents/agentos/schema_version.py",".agents/agentos/__init__.py",
        ".agents/config/governance.json","README.md","README.vi.md","README.en.md","huong_dan.md","huong_dan.vi.md","huong_dan.en.md",
        "CHANGELOG.md",".agents/docs/RULES_WORKFLOW_CHANGELOG.md","RELEASE_NOTES.md","MANIFEST.json","CHECKSUMS.sha256",
    ]
    if not already_target:
        backup=None
        if not dry_run:
            backup=str(_backup(root,changed).relative_to(root))
        written=_write_payload(root,dry_run)
        _apply_patches(root,dry_run)
        _update_governance(root,dry_run)
        # Store the exact resilient updater used for this release as the canonical
        # repository upgrader before manifest/checksum generation.
        canonical_updater = root / "tools/apply_v0234.py"
        this_updater = Path(__file__).resolve()
        if this_updater != canonical_updater.resolve():
            canonical_updater.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(this_updater, canonical_updater)
    if dry_run:
        return {"ok":True,"baseline":BASELINE if not already_target else TARGET,"target":TARGET,"schema":SCHEMA,"dry_run":True,"recovery":recovery,"preflight":pre,"payload_files":written}

    # Compile first so syntax faults fail before migration/benchmark work.
    compile_files=[root/rel for rel in written if rel.endswith(".py")]
    compile_files += [root/".agents/agentos/db.py",root/".agents/agentos/cli.py",root/".agents/agentos/cli_runtime.py",root/".agents/agentos/mcp_runtime.py",root/".agents/agentos/release_integrity.py",root/".agents/agentos/performance_baseline.py"]
    compile_result=_run(root,[sys.executable,"-m","py_compile",*[str(p) for p in compile_files]])
    if not compile_result["ok"]:
        return {"ok":False,"error":"compile_failed","backup":backup,"compile":compile_result}

    benchmark=_capture_benchmark(root,repeats)
    if not benchmark["ok"]:
        return {"ok":False,"error":"benchmark_failed","backup":backup,"benchmark":benchmark}

    # Rebuild release manifest after measured benchmark and all file changes.
    manifest=_run(root,[sys.executable,"tools/build_manifest.py",str(root)]) if (root/"tools/build_manifest.py").is_file() else {"ok":False,"error":"build_manifest_missing"}
    if not manifest.get("ok"):
        return {"ok":False,"error":"manifest_rebuild_failed","backup":backup,"manifest":manifest}

    env=os.environ.copy(); env["PYTHONPATH"]=str(root/".agents") + (os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    tests={"ok":True,"status":"skipped"}
    if run_tests:
        tests=_run(root,[sys.executable,"-m","pytest","-q",".agents/tests/test_incremental_index_v0234.py"],env)
        if not tests["ok"]:
            return {"ok":False,"error":"targeted_tests_failed","backup":backup,"benchmark":benchmark,"targeted_tests":tests,"final_version":TARGET}
    validation=_run(root,[sys.executable,"tools/validate_v0234.py",str(root)],env)
    integrity=_run(root,[sys.executable,"-c",'from pathlib import Path; import json,sys; from agentos.release_integrity import check_release_integrity; print(json.dumps(check_release_integrity(Path(sys.argv[1])),ensure_ascii=False))',str(root)],env)
    return {
        "ok":bool(validation["ok"] and integrity["ok"]),
        "baseline":BASELINE,"target":TARGET,"schema":SCHEMA,"backup":backup,
        "recovery":recovery,"preflight":pre,"benchmark":benchmark,"targeted_tests":tests,
        "validation":validation,"release_integrity":integrity,"final_version":TARGET,
    }


def main() -> int:
    ap=argparse.ArgumentParser(description="Repair partial v0.23.4 overlay state and complete AgentOS v0.23.3 -> v0.23.4 in one command")
    ap.add_argument("root",nargs="?",default=".")
    ap.add_argument("--dry-run",action="store_true")
    ap.add_argument("--repeats",type=int,default=3)
    ap.add_argument("--skip-tests",action="store_true")
    args=ap.parse_args()
    try:
        result=apply(Path(args.root),dry_run=args.dry_run,repeats=args.repeats,run_tests=not args.skip_tests)
    except Exception as exc:
        result={"ok":False,"error":type(exc).__name__,"message":str(exc),"root":str(Path(args.root).resolve())}
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
