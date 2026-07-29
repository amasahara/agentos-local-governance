"""
File: .agents/agentos/documentation.py

Purpose:
    Enforce source-file header and public-symbol documentation contracts.

Responsibilities:
    - Scan Python source files under a bounded project-relative scope.
    - Validate File, Purpose, and Responsibilities header fields.
    - Validate public class, function, and method docstrings.
    - Emit deterministic findings suitable for CLI and CI gates.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _finding(path: str, code: str, message: str, symbol: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path, "severity": "error", "code": code, "message": message}
    if symbol:
        result["symbol"] = symbol
    return result


def _public(name: str) -> bool:
    return not name.startswith("_")


def documentation_scan(root: Path, scope: str = "src") -> dict[str, Any]:
    """Scan Python files for required module and public-symbol documentation.

    Args:
        root: Project root.
        scope: Project-relative file or directory to scan.

    Returns:
        Pass/fail status, scanned file count, and structured findings.
    """
    project = root.resolve()
    target = (project / scope).resolve()
    try:
        target.relative_to(project)
    except ValueError as exc:
        raise RuntimeError("documentation scope is outside project root") from exc
    files = [target] if target.is_file() else sorted(target.rglob("*.py")) if target.exists() else []
    findings: list[dict[str, Any]] = []
    for file in files:
        rel = file.relative_to(project).as_posix()
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            findings.append(_finding(rel, "source_parse_error", str(exc)))
            continue
        module_doc = ast.get_docstring(tree, clean=False) or ""
        if not module_doc:
            findings.append(_finding(rel, "missing_file_header", "Python source file is missing a module documentation header."))
        else:
            expected = f"File: {rel}"
            if expected not in module_doc:
                findings.append(_finding(rel, "invalid_file_path_header", f"Module header must contain '{expected}'."))
            if "Purpose:" not in module_doc:
                findings.append(_finding(rel, "missing_module_purpose", "Module header is missing Purpose."))
            if "Responsibilities:" not in module_doc:
                findings.append(_finding(rel, "missing_module_responsibilities", "Module header is missing Responsibilities."))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and _public(node.name):
                if not ast.get_docstring(node):
                    findings.append(_finding(rel, "missing_symbol_docstring", "Public symbol is missing a docstring.", node.name))
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _public(child.name) and not ast.get_docstring(child):
                        findings.append(_finding(rel, "missing_symbol_docstring", "Public method is missing a docstring.", f"{node.name}.{child.name}"))
    return {"status": "passed" if not findings else "failed", "ok": not findings, "scope": scope, "scanned_files": len(files), "findings": findings}
