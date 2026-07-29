"""
File: .agents/agentos/cache.py

Purpose:
    Provide a task-scoped, content-validated file-read cache.

Responsibilities:
    - Store bounded summaries for local file reads.
    - Invalidate cache entries when file metadata or content changes.
    - Keep cache data isolated by task, path, and requested range.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .db import connect


def _metadata(path: Path) -> tuple[int, int, str]:
    data = path.read_bytes()
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size, hashlib.sha256(data).hexdigest()


def cache_store(root: Path, task_id: str, path: str, range_key: str, summary: str) -> dict[str, Any]:
    """Store or replace a validated file-read summary.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        path: Project-relative file path.
        range_key: Stable identifier for the read range.
        summary: Bounded non-sensitive summary.

    Returns:
        Stored cache identity and content hash.
    """
    relative = Path(path)
    absolute = (root.resolve() / relative).resolve()
    absolute.relative_to(root.resolve())
    mtime_ns, size, content_hash = _metadata(absolute)
    normalized = absolute.relative_to(root.resolve()).as_posix()
    with connect(root) as c:
        if not c.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
            raise RuntimeError(f"task not found: {task_id}")
        c.execute(
            """INSERT INTO file_read_cache(task_id,path,range_key,mtime_ns,size,content_hash,summary,accessed_at)
               VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(task_id,path,range_key) DO UPDATE SET
               mtime_ns=excluded.mtime_ns,size=excluded.size,content_hash=excluded.content_hash,
               summary=excluded.summary,accessed_at=CURRENT_TIMESTAMP""",
            (task_id, normalized, range_key, mtime_ns, size, content_hash, summary),
        )
    return {"stored": True, "task_id": task_id, "path": normalized, "range_key": range_key, "content_hash": content_hash}


def cache_lookup(root: Path, task_id: str, path: str, range_key: str) -> dict[str, Any]:
    """Return a cache hit only when current file identity still matches.

    Args:
        root: Project root.
        task_id: Existing task identifier.
        path: Project-relative file path.
        range_key: Stable identifier for the read range.

    Returns:
        Cache hit state and summary when valid.
    """
    absolute = (root.resolve() / path).resolve()
    try:
        normalized = absolute.relative_to(root.resolve()).as_posix()
    except ValueError:
        return {"hit": False, "reason": "outside_project_root"}
    if not absolute.is_file():
        return {"hit": False, "reason": "file_not_found"}
    mtime_ns, size, content_hash = _metadata(absolute)
    with connect(root) as c:
        row = c.execute(
            "SELECT * FROM file_read_cache WHERE task_id=? AND path=? AND range_key=?",
            (task_id, normalized, range_key),
        ).fetchone()
        if not row:
            return {"hit": False, "reason": "not_cached"}
        valid = row["mtime_ns"] == mtime_ns and row["size"] == size and row["content_hash"] == content_hash
        if not valid:
            c.execute("DELETE FROM file_read_cache WHERE task_id=? AND path=? AND range_key=?", (task_id, normalized, range_key))
            return {"hit": False, "reason": "stale"}
        c.execute(
            "UPDATE file_read_cache SET accessed_at=CURRENT_TIMESTAMP WHERE task_id=? AND path=? AND range_key=?",
            (task_id, normalized, range_key),
        )
    return {"hit": True, "path": normalized, "range_key": range_key, "summary": row["summary"], "content_hash": content_hash}
