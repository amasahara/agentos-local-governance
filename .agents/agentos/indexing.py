"""
File: .agents/agentos/indexing.py

Purpose:
    Build and query a project-local Python symbol index incrementally.

Responsibilities:
    - Parse Python source through AST and store deterministic fingerprints.
    - Persist content-hash file state so unchanged files are not reparsed.
    - Remove stale symbols for deleted files and replace only changed-file rows.
    - Bootstrap safely from the historical full-rebuild index format.
    - Fail atomically on parse/decode errors without partially mutating the index.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sqlite3
from typing import Any

from .db import connect

INDEX_SCHEMA_VERSION = 47


def migration_47(c: sqlite3.Connection) -> None:
    """Add deterministic file-state metadata required by the incremental symbol index.

    Args:
        c: Open AgentOS SQLite connection receiving migration 47.
    Returns:
        None.
    """
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbol_index_state(
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            source_rel TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1,
            last_mode TEXT NOT NULL,
            last_files INTEGER NOT NULL DEFAULT 0,
            last_symbols INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS symbol_index_files(
            path TEXT PRIMARY KEY,
            source_rel TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            symbol_count INTEGER NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_index_files_source
            ON symbol_index_files(source_rel,path);
        """
    )


def _fingerprint(node: ast.AST) -> str:
    """Return the deterministic AST fingerprint used by duplicate detection."""
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def _safe_source(root: Path, source: str) -> tuple[Path, str]:
    """Resolve one project-local source tree and reject path escape.

    Args:
        root: Project root.
        source: Project-relative source directory.
    Returns:
        Resolved source path and normalized project-relative source string.
    Raises:
        RuntimeError: If the source is absolute or escapes the project root.
    """
    root_resolved = root.resolve()
    raw = Path(source)
    if raw.is_absolute():
        raise RuntimeError("index source must be project-relative")
    base = (root_resolved / raw).resolve()
    try:
        rel = base.relative_to(root_resolved).as_posix()
    except ValueError as exc:
        raise RuntimeError("index source escaped project root") from exc
    return base, rel or "."


def _collect_files(root: Path, base: Path) -> tuple[list[tuple[str, Path]], int]:
    """Collect deterministic project-local Python paths without following escaped symlinks."""
    root_resolved = root.resolve()
    files: list[tuple[str, Path]] = []
    skipped_symlinks = 0
    if not base.exists():
        return files, skipped_symlinks
    for path in sorted(base.rglob("*.py")):
        if path.is_symlink():
            skipped_symlinks += 1
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            skipped_symlinks += 1
            continue
        if not resolved.is_file():
            continue
        files.append((resolved.relative_to(root_resolved).as_posix(), resolved))
    return files, skipped_symlinks


def _parse_symbols(rel: str, payload: bytes) -> list[tuple[str, str, str, int, int, str, str]]:
    """Parse one immutable byte payload into symbol-index rows.

    Args:
        rel: Project-relative file path.
        payload: Exact bytes whose hash will be recorded.
    Returns:
        Rows suitable for insertion into ``symbol_index``.
    Raises:
        UnicodeDecodeError: If source is not UTF-8.
        SyntaxError: If Python AST parsing fails.
    """
    text = payload.decode("utf-8")
    tree = ast.parse(text, filename=rel)
    rows: list[tuple[str, str, str, int, int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            signature = node.name
            rows.append(
                (
                    rel,
                    node.name,
                    kind,
                    int(node.lineno),
                    int(getattr(node, "end_lineno", node.lineno)),
                    signature,
                    _fingerprint(node),
                )
            )
    return rows


def index_build(root: Path, source: str = "src", *, force_full: bool = False) -> dict[str, Any]:
    """Build or incrementally update the Python symbol index for a source tree.

    The first run after migration 47 performs a bootstrap full rebuild because the
    historical ``symbol_index`` table has no trusted per-file content hashes. Later
    runs hash every candidate file for correctness but parse only new/changed files.

    Args:
        root: Project root.
        source: Project-relative source directory.
        force_full: Force a deterministic full rebuild and reseed file metadata.
    Returns:
        Backward-compatible ``files``/``symbols`` counts plus incremental telemetry.
    Raises:
        RuntimeError: If the source escapes the project or source parsing fails.
    """
    root = root.resolve()
    base, source_rel = _safe_source(root, source)
    candidates, skipped_symlinks = _collect_files(root, base)

    # Serialize index mutations. Parsing occurs from the exact bytes whose hashes are
    # stored, so an index row can never be committed against a different payload.
    with connect(root, immediate=True) as c:
        migration_47(c)
        state = c.execute("SELECT * FROM symbol_index_state WHERE singleton=1").fetchone()
        previous_rows = c.execute(
            "SELECT path,source_rel,content_hash,size,mtime_ns,symbol_count FROM symbol_index_files"
        ).fetchall()
        previous = {str(row["path"]): dict(row) for row in previous_rows}

        bootstrap = state is None
        source_changed = bool(state is not None and str(state["source_rel"]) != source_rel)
        full = bool(force_full or bootstrap or source_changed)
        mode = "full_rebuild" if force_full or source_changed else ("bootstrap_full_rebuild" if bootstrap else "incremental")

        current_paths = {rel for rel, _ in candidates}
        deleted = sorted(set(previous) - current_paths) if not full else sorted(set(previous) - current_paths)
        prepared: dict[str, dict[str, Any]] = {}
        unchanged = 0
        added = 0
        changed = 0

        # Parse before mutating any symbol rows. One bad changed file aborts the whole
        # transaction and preserves the previously valid index.
        for rel, path in candidates:
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            stat = path.stat()
            old = previous.get(rel)
            must_parse = full or old is None or str(old["content_hash"]) != digest
            if not must_parse:
                unchanged += 1
                continue
            try:
                symbols = _parse_symbols(rel, payload)
            except (UnicodeDecodeError, SyntaxError) as exc:
                raise RuntimeError(f"cannot index {rel}: {type(exc).__name__}: {exc}") from exc
            prepared[rel] = {
                "hash": digest,
                "size": len(payload),
                "mtime_ns": int(stat.st_mtime_ns),
                "symbols": symbols,
            }
            if old is None:
                added += 1
            else:
                changed += 1

        if full:
            c.execute("DELETE FROM symbol_index")
            c.execute("DELETE FROM symbol_index_files")
        else:
            for rel in deleted:
                c.execute("DELETE FROM symbol_index WHERE path=?", (rel,))
                c.execute("DELETE FROM symbol_index_files WHERE path=?", (rel,))
            for rel in prepared:
                c.execute("DELETE FROM symbol_index WHERE path=?", (rel,))

        for rel, item in prepared.items():
            for row in item["symbols"]:
                c.execute(
                    "INSERT OR REPLACE INTO symbol_index(path,qualname,kind,line_start,line_end,signature,fingerprint) VALUES(?,?,?,?,?,?,?)",
                    row,
                )
            c.execute(
                """
                INSERT INTO symbol_index_files(path,source_rel,content_hash,size,mtime_ns,symbol_count,indexed_at)
                VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(path) DO UPDATE SET
                    source_rel=excluded.source_rel,
                    content_hash=excluded.content_hash,
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    symbol_count=excluded.symbol_count,
                    indexed_at=CURRENT_TIMESTAMP
                """,
                (rel, source_rel, item["hash"], item["size"], item["mtime_ns"], len(item["symbols"])),
            )

        total_symbols = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index").fetchone()["n"])
        total_files = len(candidates)
        generation = 1 if state is None else int(state["generation"]) + 1
        c.execute(
            """
            INSERT INTO symbol_index_state(singleton,source_rel,generation,last_mode,last_files,last_symbols,updated_at)
            VALUES(1,?,?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(singleton) DO UPDATE SET
                source_rel=excluded.source_rel,
                generation=excluded.generation,
                last_mode=excluded.last_mode,
                last_files=excluded.last_files,
                last_symbols=excluded.last_symbols,
                updated_at=CURRENT_TIMESTAMP
            """,
            (source_rel, generation, mode, total_files, total_symbols),
        )

    return {
        "files": total_files,
        "symbols": total_symbols,
        "mode": mode,
        "source": source_rel,
        "files_seen": total_files,
        "files_parsed": len(prepared),
        "files_unchanged": unchanged if not full else 0,
        "files_added": added,
        "files_changed": changed,
        "files_deleted": len(deleted),
        "skipped_symlinks": skipped_symlinks,
        "generation": generation,
        "schema": INDEX_SCHEMA_VERSION,
    }


def index_status(root: Path) -> dict[str, Any]:
    """Return privacy-safe incremental-index state and aggregate counts."""
    with connect(root.resolve()) as c:
        migration_47(c)
        state = c.execute("SELECT * FROM symbol_index_state WHERE singleton=1").fetchone()
        files = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index_files").fetchone()["n"])
        symbols = int(c.execute("SELECT COUNT(*) AS n FROM symbol_index").fetchone()["n"])
    return {
        "ok": True,
        "initialized": state is not None,
        "source": str(state["source_rel"]) if state else None,
        "generation": int(state["generation"]) if state else 0,
        "last_mode": str(state["last_mode"]) if state else None,
        "files": files,
        "symbols": symbols,
        "schema": INDEX_SCHEMA_VERSION,
    }


def index_query(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find indexed symbols matching a query."""
    like = f"%{query}%"
    with connect(root) as c:
        rows = c.execute(
            "SELECT path,qualname,kind,line_start,line_end,signature,fingerprint FROM symbol_index WHERE qualname LIKE ? ORDER BY CASE WHEN qualname=? THEN 0 ELSE 1 END,path,qualname LIMIT ?",
            (like, query, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def duplicate_report(root: Path) -> list[dict[str, Any]]:
    """Return groups of symbols with identical AST fingerprints."""
    with connect(root) as c:
        fps = c.execute("SELECT fingerprint FROM symbol_index GROUP BY fingerprint HAVING COUNT(*) > 1").fetchall()
        out = []
        for fp in fps:
            rows = c.execute(
                "SELECT path,qualname FROM symbol_index WHERE fingerprint=? ORDER BY path,qualname",
                (fp["fingerprint"],),
            ).fetchall()
            out.append({"fingerprint": fp["fingerprint"], "symbols": [dict(r) for r in rows]})
    return out
