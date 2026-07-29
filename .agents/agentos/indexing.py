"""
File: .agents/agentos/indexing.py

Purpose:
    Build and query a project-local Python symbol index.

Responsibilities:
    - Parse Python source through AST.
    - Store qualified symbols and deterministic fingerprints.
    - Return bounded symbol matches and duplicate candidates.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from .db import connect


def _fingerprint(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def index_build(root: Path, source: str = "src") -> dict[str, int]:
    """Rebuild the Python symbol index for a source tree.

    Args:
        root: Project root.
        source: Project-relative source directory.

    Returns:
        Counts of indexed files and symbols.
    """
    base = root.resolve() / source
    files = 0
    symbols = 0
    with connect(root) as c:
        c.execute("DELETE FROM symbol_index")
        for path in sorted(base.rglob("*.py")) if base.exists() else []:
            files += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(root.resolve()).as_posix()
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    signature = node.name
                    c.execute(
                        "INSERT OR REPLACE INTO symbol_index(path,qualname,kind,line_start,line_end,signature,fingerprint) VALUES(?,?,?,?,?,?,?)",
                        (rel, node.name, kind, node.lineno, getattr(node, "end_lineno", node.lineno), signature, _fingerprint(node)),
                    )
                    symbols += 1
    return {"files": files, "symbols": symbols}


def index_query(root: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Find indexed symbols matching a query.

    Args:
        root: Project root.
        query: Symbol search text.
        limit: Maximum number of results.

    Returns:
        Matching symbol records ordered deterministically.
    """
    like = f"%{query}%"
    with connect(root) as c:
        rows = c.execute(
            "SELECT path,qualname,kind,line_start,line_end,signature,fingerprint FROM symbol_index WHERE qualname LIKE ? ORDER BY CASE WHEN qualname=? THEN 0 ELSE 1 END,path,qualname LIMIT ?",
            (like, query, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def duplicate_report(root: Path) -> list[dict[str, Any]]:
    """Return groups of symbols with identical AST fingerprints.

    Args:
        root: Project root.

    Returns:
        Duplicate candidate groups.
    """
    with connect(root) as c:
        fps = c.execute("SELECT fingerprint FROM symbol_index GROUP BY fingerprint HAVING COUNT(*) > 1").fetchall()
        out = []
        for fp in fps:
            rows = c.execute("SELECT path,qualname FROM symbol_index WHERE fingerprint=? ORDER BY path,qualname", (fp["fingerprint"],)).fetchall()
            out.append({"fingerprint": fp["fingerprint"], "symbols": [dict(r) for r in rows]})
    return out
