"""Path: .agents/agentos/architecture_discovery.py
Purpose: Deterministic read-only project architecture discovery and source-evidence binding for AgentOS v0.25.4.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator
from datetime import datetime, timezone

from .db import connect, connect_read_only

MIGRATION_VERSION = 51
SCANNER_VERSION = 2
MAX_SCAN_FILE_BYTES = 2 * 1024 * 1024


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

EXCLUDED_DIR_NAMES = {
    ".git", ".agents", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "vendor",
    "dist", "build", "target", "coverage", ".coverage", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "__pycache__", "backups",
}

LANGUAGE_BY_SUFFIX = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".cs": "C#", ".c": "C", ".h": "C/C++", ".cc": "C++", ".cpp": "C++", ".hpp": "C++",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".scala": "Scala", ".sh": "Shell",
    ".ps1": "PowerShell", ".sql": "SQL", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".vue": "Vue", ".svelte": "Svelte", ".dart": "Dart", ".r": "R",
}

DEPENDENCY_FILES = {
    "pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements.in",
    "package.json", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "composer.json", "Package.swift",
}

CONFIG_NAMES = {
    ".env", ".env.example", ".env.sample", "config.py", "settings.py", "settings.json",
    "config.json", "config.yaml", "config.yml", "application.yml", "application.yaml",
    "application.properties", "appsettings.json", "tox.ini", "pytest.ini", "mypy.ini",
    "ruff.toml", ".pre-commit-config.yaml",
}

DEPLOYMENT_NAMES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "Procfile", "fly.toml", "vercel.json", "netlify.toml", "serverless.yml", "serverless.yaml",
    "Chart.yaml", "values.yaml", "values.yml",
}

MIGRATION_RE = re.compile(r"(^|/)(migrations?|alembic|schema)(/|$)|(^|/)[0-9]{3,}[_-].*\.(sql|py)$", re.I)
TEST_RE = re.compile(r"(^|/)(tests?|specs?)(/|$)|(^|/)(test_.*|.*_test|.*\.spec|.*\.test)\.", re.I)
CLI_LITERAL_RE = re.compile(r"\.add_parser\(\s*[\"']([^\"']+)[\"']")
MCP_NAME_RE = re.compile(r"[\"']name[\"']\s*:\s*[\"'](agentos\.[a-zA-Z0-9_.-]+)[\"']")
URL_HOST_RE = re.compile(r"https?://([A-Za-z0-9.-]+)(?::[0-9]+)?(?:[/\s\"']|$)", re.I)
ENV_GET_RE = re.compile(r"(?:os\.getenv\(|os\.environ\.get\(|os\.environ\[)\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def migration_51(connection: Any) -> None:
    """Create v0.25.3 architecture-discovery/evidence tables.

    Input: SQLite-compatible connection already inside the AgentOS migration transaction.
    Output: None; schema is extended additively to version 51.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS architecture_scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_uuid TEXT NOT NULL UNIQUE,
            scanner_version INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
            source_root TEXT NOT NULL,
            source_root_hash TEXT NOT NULL,
            active_baseline_id INTEGER,
            active_baseline_hash TEXT,
            scan_hash TEXT UNIQUE,
            observation_count INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            discrepancy_count INTEGER NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY(active_baseline_id) REFERENCES architecture_baselines(id)
        );

        CREATE TABLE IF NOT EXISTS architecture_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            section_id TEXT NOT NULL,
            observation_kind TEXT NOT NULL,
            subject TEXT NOT NULL,
            value_json TEXT NOT NULL,
            observation_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(scan_id, observation_hash),
            FOREIGN KEY(scan_id) REFERENCES architecture_scan_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS architecture_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            observation_id INTEGER NOT NULL,
            section_id TEXT NOT NULL,
            evidence_kind TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            locator_json TEXT NOT NULL,
            evidence_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(scan_id, evidence_hash),
            FOREIGN KEY(scan_id) REFERENCES architecture_scan_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(observation_id) REFERENCES architecture_observations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS architecture_discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER NOT NULL,
            baseline_id INTEGER,
            section_id TEXT NOT NULL,
            discrepancy_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            observed_hash TEXT,
            contract_section_hash TEXT,
            severity TEXT NOT NULL CHECK(severity IN ('info','warn')),
            status TEXT NOT NULL CHECK(status IN ('observed','acknowledged')) DEFAULT 'observed',
            details_json TEXT NOT NULL,
            discrepancy_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(scan_id, discrepancy_hash),
            FOREIGN KEY(scan_id) REFERENCES architecture_scan_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(baseline_id) REFERENCES architecture_baselines(id)
        );

        CREATE INDEX IF NOT EXISTS idx_arch_obs_scan_section
            ON architecture_observations(scan_id, section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_evidence_scan_section
            ON architecture_evidence(scan_id, section_id);
        CREATE INDEX IF NOT EXISTS idx_arch_evidence_path
            ON architecture_evidence(source_path, source_hash);
        CREATE INDEX IF NOT EXISTS idx_arch_discrepancy_scan_section
            ON architecture_discrepancies(scan_id, section_id);
        """
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _norm_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_source_root(root: Path, source_root: str | Path | None) -> Path:
    project_root = root.resolve()
    candidate = (project_root / source_root).resolve() if source_root and not Path(source_root).is_absolute() else Path(source_root or project_root).resolve()
    if not _inside(candidate, project_root):
        raise ValueError("architecture_scan_source_root_outside_project")
    if not candidate.exists() or not candidate.is_dir():
        raise ValueError("architecture_scan_source_root_missing")
    return candidate


def _is_excluded_dir(path: Path, source_root: Path) -> bool:
    rel_parts = path.relative_to(source_root).parts if path != source_root else ()
    if any(part in EXCLUDED_DIR_NAMES for part in rel_parts):
        return True
    # Preserve AgentOS code discovery while excluding mutable runtime/state/cache subtrees.
    rel = path.relative_to(source_root).as_posix() if path != source_root else ""
    return rel.startswith(".agents/runtime") or rel.startswith(".agents/state") or rel.startswith(".agents/cache")


def _iter_files(source_root: Path) -> Iterator[Path]:
    for current, dirs, files in os.walk(source_root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if not Path(current_path, d).is_symlink()
            and not _is_excluded_dir(Path(current_path, d), source_root)
        )
        for name in sorted(files):
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.stat().st_size > MAX_SCAN_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _dependency_names(rel: str, text: str) -> list[str]:
    name = Path(rel).name
    found: set[str] = set()
    if name.startswith("requirements"):
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            token = re.split(r"[<>=!~;\[\s]", line, maxsplit=1)[0].strip()
            if token:
                found.add(token)
    elif name == "package.json":
        try:
            obj = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                val = obj.get(key, {})
                if isinstance(val, dict):
                    found.update(str(x) for x in val)
        except json.JSONDecodeError:
            pass
    elif name == "pyproject.toml":
        try:
            import tomllib
            obj = tomllib.loads(text)
            deps = obj.get("project", {}).get("dependencies", [])
            if isinstance(deps, list):
                for dep in deps:
                    token = re.split(r"[<>=!~;\[\s]", str(dep), maxsplit=1)[0].strip()
                    if token:
                        found.add(token)
            opt = obj.get("project", {}).get("optional-dependencies", {})
            if isinstance(opt, dict):
                for group in opt.values():
                    if isinstance(group, list):
                        for dep in group:
                            token = re.split(r"[<>=!~;\[\s]", str(dep), maxsplit=1)[0].strip()
                            if token:
                                found.add(token)
        except Exception:
            pass
    elif name == "go.mod":
        for match in re.finditer(r"(?m)^\s*([a-zA-Z0-9_.-]+\.[^\s]+)\s+v[0-9]", text):
            found.add(match.group(1))
    elif name == "Cargo.toml":
        in_deps = False
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("["):
                in_deps = "dependencies" in line
                continue
            if in_deps and "=" in line and not line.startswith("#"):
                found.add(line.split("=", 1)[0].strip())
    return sorted(found)


@dataclass(frozen=True)
class Evidence:
    kind: str
    path: str
    source_hash: str
    locator: dict[str, Any]


@dataclass(frozen=True)
class Observation:
    section_id: str
    kind: str
    subject: str
    value: Any
    evidence: tuple[Evidence, ...]

    @property
    def observation_hash(self) -> str:
        return _sha256_json({
            "section_id": self.section_id,
            "kind": self.kind,
            "subject": self.subject,
            "value": self.value,
        })


def _ev(path: str, source_hash: str, kind: str = "source_file", **locator: Any) -> Evidence:
    return Evidence(kind=kind, path=path, source_hash=source_hash, locator=locator)


def discover_source(root: Path, source_root: Path) -> tuple[list[Observation], dict[str, str]]:
    """Statically discover deterministic project architecture observations.

    Input: project root and validated source root contained within it.
    Output: observations plus source-path->SHA256 map. No project file is modified or executed.
    """
    file_hashes: dict[str, str] = {}
    texts: dict[str, str] = {}
    language_files: dict[str, list[str]] = defaultdict(list)
    top_level: set[str] = set()
    dependency_data: dict[str, list[str]] = {}
    tests: list[str] = []
    configs: list[str] = []
    migrations: list[str] = []
    ci: list[str] = []
    deployments: list[str] = []
    python_imports: dict[str, list[dict[str, Any]]] = {}
    cli_commands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mcp_tools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    module_paths: set[str] = set()
    external_domains: dict[str, set[str]] = defaultdict(set)
    environment_variables: dict[str, set[str]] = defaultdict(set)

    for path in _iter_files(source_root):
        data = _read_bytes(path)
        if data is None:
            continue
        rel = _norm_rel(path, root)
        source_rel = _norm_rel(path, source_root)
        digest = _sha256_bytes(data)
        file_hashes[rel] = digest
        if source_rel and "/" in source_rel:
            top_level.add(source_rel.split("/", 1)[0])
        lang = LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
        if lang:
            language_files[lang].append(rel)
        text = _decode_text(data)
        if text is None:
            continue
        texts[rel] = text
        if path.name in DEPENDENCY_FILES or path.name.startswith("requirements") and path.suffix in {".txt", ".in"}:
            dependency_data[rel] = _dependency_names(rel, text)
        if TEST_RE.search("/" + source_rel):
            tests.append(rel)
        if path.name in CONFIG_NAMES or path.name.startswith(".env."):
            configs.append(rel)
        if MIGRATION_RE.search("/" + source_rel):
            migrations.append(rel)
        if source_rel.startswith(".github/workflows/") or source_rel.startswith(".gitlab-ci") or path.name in {"Jenkinsfile", "azure-pipelines.yml"}:
            ci.append(rel)
        if path.name in DEPLOYMENT_NAMES or any(part.lower() in {"k8s", "kubernetes", "helm", "deploy", "deployment"} for part in path.parts):
            deployments.append(rel)
        if path.suffix.lower() == ".py":
            module_paths.add(rel)
            try:
                tree = ast.parse(text, filename=rel)
                imports: list[dict[str, Any]] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append({"module": alias.name, "line": int(node.lineno)})
                    elif isinstance(node, ast.ImportFrom):
                        module = "." * int(node.level) + (node.module or "")
                        imports.append({"module": module, "line": int(node.lineno)})
                if imports:
                    python_imports[rel] = sorted(imports, key=lambda x: (x["module"], x["line"]))
            except SyntaxError:
                pass
        runtime_literal_suffixes = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".rb", ".php", ".swift", ".scala", ".sh", ".ps1", ".json", ".yaml", ".yml", ".toml", ".ini", ".properties"}
        if path.suffix.lower() in runtime_literal_suffixes or path.name in CONFIG_NAMES or path.name in DEPLOYMENT_NAMES:
            for match in URL_HOST_RE.finditer(text):
                host = match.group(1).lower().rstrip(".")
                if host:
                    external_domains[host].add(rel)
            for match in ENV_GET_RE.finditer(text):
                environment_variables[match.group(1)].add(rel)
        for match in CLI_LITERAL_RE.finditer(text):
            cli_commands[match.group(1)].append({"path": rel, "offset": match.start()})
        for match in MCP_NAME_RE.finditer(text):
            mcp_tools[match.group(1)].append({"path": rel, "offset": match.start()})

    observations: list[Observation] = []
    if language_files:
        value = {lang: len(paths) for lang, paths in sorted(language_files.items())}
        evidence = tuple(_ev(p, file_hashes[p], language=lang) for lang, paths in sorted(language_files.items()) for p in sorted(paths))
        observations.append(Observation("ARCH-02", "language_inventory", "languages", value, evidence))
    if dependency_data:
        all_deps = sorted({d for deps in dependency_data.values() for d in deps})
        evidence = tuple(_ev(p, file_hashes[p], manifest=Path(p).name) for p in sorted(dependency_data))
        observations.append(Observation("ARCH-02", "dependency_inventory", "declared_dependencies", {"dependencies": all_deps, "manifests": sorted(dependency_data)}, evidence))
    if top_level:
        dir_fingerprint = _sha256_json(sorted(top_level))
        observations.append(Observation("ARCH-03", "folder_inventory", "source_top_level", sorted(top_level), (Evidence("derived_tree", ".", dir_fingerprint, {"source_root": _norm_rel(source_root, root)}),)))
    if module_paths:
        module_list = sorted(module_paths)
        observations.append(Observation("ARCH-05", "module_inventory", "python_modules", module_list, tuple(_ev(p, file_hashes[p]) for p in module_list)))
    for rel, imports in sorted(python_imports.items()):
        observations.append(Observation("ARCH-12", "python_imports", rel, imports, (_ev(rel, file_hashes[rel], lines=sorted({x["line"] for x in imports})),)))
    if external_domains:
        domains = sorted(external_domains)
        paths = sorted({p for values in external_domains.values() for p in values})
        observations.append(Observation("ARCH-13", "external_service_domains", "domains", domains, tuple(_ev(p, file_hashes[p]) for p in paths)))
    if environment_variables:
        names = sorted(environment_variables)
        paths = sorted({p for values in environment_variables.values() for p in values})
        observations.append(Observation("ARCH-14", "environment_variables", "environment_variable_names", names, tuple(_ev(p, file_hashes[p]) for p in paths)))
    if configs:
        observations.append(Observation("ARCH-14", "configuration_inventory", "configuration_files", sorted(configs), tuple(_ev(p, file_hashes[p]) for p in sorted(configs))))
    if migrations:
        observations.append(Observation("ARCH-09", "migration_inventory", "migration_files", sorted(set(migrations)), tuple(_ev(p, file_hashes[p]) for p in sorted(set(migrations)))))
    if tests:
        observations.append(Observation("ARCH-21", "test_inventory", "test_files", sorted(set(tests)), tuple(_ev(p, file_hashes[p]) for p in sorted(set(tests)))))
    if ci:
        observations.append(Observation("ARCH-20", "ci_inventory", "ci_files", sorted(set(ci)), tuple(_ev(p, file_hashes[p]) for p in sorted(set(ci)))))
    if deployments:
        observations.append(Observation("ARCH-20", "deployment_inventory", "deployment_files", sorted(set(deployments)), tuple(_ev(p, file_hashes[p]) for p in sorted(set(deployments)))))
    if cli_commands:
        flattened = {name: sorted(entries, key=lambda x: (x["path"], x["offset"])) for name, entries in sorted(cli_commands.items())}
        paths = sorted({entry["path"] for entries in flattened.values() for entry in entries})
        observations.append(Observation("ARCH-10", "cli_surface", "cli_commands", flattened, tuple(_ev(p, file_hashes[p]) for p in paths)))
    if mcp_tools:
        flattened = {name: sorted(entries, key=lambda x: (x["path"], x["offset"])) for name, entries in sorted(mcp_tools.items())}
        paths = sorted({entry["path"] for entries in flattened.values() for entry in entries})
        observations.append(Observation("ARCH-10", "mcp_surface", "mcp_tools", flattened, tuple(_ev(p, file_hashes[p]) for p in paths)))

    observations.sort(key=lambda x: (x.section_id, x.kind, x.subject, x.observation_hash))
    return observations, file_hashes


def _active_baseline(connection: Any) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id, baseline_hash FROM architecture_baselines WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    return {"id": int(row[0]), "hash": str(row[1])}


def _baseline_sections(connection: Any, baseline_id: int) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT b.section_id, r.applicability, r.section_hash, r.contract_json
        FROM architecture_baseline_sections b
        JOIN architecture_section_revisions r ON r.id=b.section_revision_id
        WHERE b.baseline_id=?
        ORDER BY b.section_id
        """,
        (baseline_id,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            contract = json.loads(row[3]) if row[3] else {}
        except json.JSONDecodeError:
            contract = {}
        result[str(row[0])] = {
            "applicability": str(row[1]),
            "section_hash": str(row[2]),
            "contract": contract,
        }
    return result


def _declared_evidence_paths(value: Any) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_path", "path"} and isinstance(item, str):
                paths.add(item.replace("\\", "/"))
            elif key in {"evidence", "evidence_bindings"}:
                paths.update(_declared_evidence_paths(item))
            elif isinstance(item, (dict, list)):
                paths.update(_declared_evidence_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.update(_declared_evidence_paths(item))
    return paths


def _previous_evidence(connection: Any, source_root: str) -> dict[str, str]:
    row = connection.execute(
        "SELECT id FROM architecture_scan_runs WHERE status='completed' AND source_root=? ORDER BY id DESC LIMIT 1",
        (source_root,),
    ).fetchone()
    if not row:
        return {}
    rows = connection.execute(
        "SELECT source_path, source_hash FROM architecture_evidence WHERE scan_id=?",
        (int(row[0]),),
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def _discrepancies(
    connection: Any,
    observations: list[Observation],
    baseline: dict[str, Any] | None,
    source_root_rel: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous = _previous_evidence(connection, source_root_rel)
    current_paths: dict[str, str] = {}
    by_section: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_section[obs.section_id].append(obs)
        for ev in obs.evidence:
            current_paths[ev.path] = ev.source_hash

    def add(section_id: str, dtype: str, subject: str, observed_hash: str | None, contract_hash: str | None, severity: str, details: Any) -> None:
        payload = {
            "section_id": section_id, "type": dtype, "subject": subject,
            "observed_hash": observed_hash, "contract_hash": contract_hash,
            "details": details,
        }
        result.append({
            "section_id": section_id,
            "discrepancy_type": dtype,
            "subject": subject,
            "observed_hash": observed_hash,
            "contract_section_hash": contract_hash,
            "severity": severity,
            "details": details,
            "discrepancy_hash": _sha256_json(payload),
        })

    changed = sorted(p for p, h in current_paths.items() if p in previous and previous[p] != h)
    for path in changed:
        sections = sorted({obs.section_id for obs in observations if any(ev.path == path for ev in obs.evidence)}) or ["ARCH-27"]
        for section_id in sections:
            add(section_id, "evidence_hash_changed", path, current_paths[path], None, "info", {"previous_hash": previous[path], "current_hash": current_paths[path]})

    if baseline:
        sections = _baseline_sections(connection, baseline["id"])
        for section_id, obs_list in sorted(by_section.items()):
            section = sections.get(section_id)
            if not section:
                continue
            if section["applicability"] == "not_applicable" and obs_list:
                add(section_id, "observed_for_not_applicable_section", section_id,
                    _sha256_json([o.observation_hash for o in obs_list]), section["section_hash"], "warn",
                    {"observation_kinds": sorted({o.kind for o in obs_list})})
                continue
            declared = _declared_evidence_paths(section["contract"])
            observed_paths = sorted({ev.path for o in obs_list for ev in o.evidence if ev.path != "."})
            if observed_paths and not declared:
                add(section_id, "observed_evidence_not_bound_in_contract", section_id,
                    _sha256_json(observed_paths), section["section_hash"], "info",
                    {"observed_path_count": len(observed_paths), "sample_paths": observed_paths[:20]})
            elif observed_paths and declared:
                unbound = sorted(p for p in observed_paths if p not in declared)
                if unbound:
                    add(section_id, "observed_evidence_partially_unbound", section_id,
                        _sha256_json(unbound), section["section_hash"], "info",
                        {"unbound_path_count": len(unbound), "sample_paths": unbound[:20]})

    return sorted(result, key=lambda x: (x["section_id"], x["discrepancy_type"], x["subject"]))


def architecture_scan(root: Path | str, *, source_root: Path | str | None = None, created_by: str) -> dict[str, Any]:
    """Run a deterministic local scan and persist observations/evidence only.

    Input: AgentOS project root, optional contained source root, and explicit actor.
    Output: scan summary. Source, architecture working copy, baseline, rules, and workflow are never modified.
    """
    import uuid

    project_root = Path(root).resolve()
    if not str(created_by).strip():
        raise ValueError("architecture_scan_created_by_required")
    scan_root = _resolve_source_root(project_root, source_root)
    scan_root_rel = _norm_rel(scan_root, project_root) if scan_root != project_root else "."
    observations, file_hashes = discover_source(project_root, scan_root)
    source_root_hash = _sha256_json({"root": scan_root_rel, "files": sorted(file_hashes.items())})

    with connect(project_root) as connection:
        baseline = _active_baseline(connection)
        discrepancies = _discrepancies(connection, observations, baseline, scan_root_rel)
        evidence_specs = [
            {
                "observation_hash": obs.observation_hash,
                "section_id": obs.section_id,
                "kind": ev.kind,
                "path": ev.path,
                "source_hash": ev.source_hash,
                "locator": ev.locator,
            }
            for obs in observations for ev in obs.evidence
        ]
        scan_hash = _sha256_json({
            "scanner_version": SCANNER_VERSION,
            "source_root": scan_root_rel,
            "source_root_hash": source_root_hash,
            "active_baseline_hash": baseline["hash"] if baseline else None,
            "observations": [o.observation_hash for o in observations],
            "evidence": [_sha256_json(x) for x in evidence_specs],
        })
        existing = connection.execute(
            "SELECT id FROM architecture_scan_runs WHERE scan_hash=? AND status='completed'",
            (scan_hash,),
        ).fetchone()
        if existing:
            cursor = connection.execute("SELECT * FROM architecture_scan_runs WHERE id=?", (int(existing[0]),))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("architecture_scan_idempotent_row_missing")
            return _row_dict(cursor, row) | {"idempotent": True}

        created_at = _now_utc()
        cur = connection.execute(
            """
            INSERT INTO architecture_scan_runs(
              scan_uuid, scanner_version, status, source_root, source_root_hash,
              active_baseline_id, active_baseline_hash, scan_hash, created_by, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (str(uuid.uuid4()), SCANNER_VERSION, "running", scan_root_rel, source_root_hash,
             baseline["id"] if baseline else None, baseline["hash"] if baseline else None,
             scan_hash, created_by, created_at),
        )
        scan_id = int(cur.lastrowid)
        observation_ids: dict[str, int] = {}
        evidence_count = 0
        for obs in observations:
            cur = connection.execute(
                """INSERT INTO architecture_observations(
                    scan_id, section_id, observation_kind, subject, value_json, observation_hash, created_at
                ) VALUES(?,?,?,?,?,?,?)""",
                (scan_id, obs.section_id, obs.kind, obs.subject, _canonical_json(obs.value), obs.observation_hash, created_at),
            )
            observation_id = int(cur.lastrowid)
            observation_ids[obs.observation_hash] = observation_id
            for ev in obs.evidence:
                eh = _sha256_json({
                    "observation_hash": obs.observation_hash, "section_id": obs.section_id,
                    "kind": ev.kind, "path": ev.path, "source_hash": ev.source_hash,
                    "locator": ev.locator,
                })
                connection.execute(
                    """INSERT OR IGNORE INTO architecture_evidence(
                      scan_id, observation_id, section_id, evidence_kind, source_path,
                      source_hash, locator_json, evidence_hash, created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (scan_id, observation_id, obs.section_id, ev.kind, ev.path, ev.source_hash,
                     _canonical_json(ev.locator), eh, created_at),
                )
                evidence_count += 1
        for d in discrepancies:
            connection.execute(
                """INSERT INTO architecture_discrepancies(
                  scan_id, baseline_id, section_id, discrepancy_type, subject, observed_hash,
                  contract_section_hash, severity, status, details_json, discrepancy_hash, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (scan_id, baseline["id"] if baseline else None, d["section_id"], d["discrepancy_type"],
                 d["subject"], d["observed_hash"], d["contract_section_hash"], d["severity"], "observed",
                 _canonical_json(d["details"]), d["discrepancy_hash"], created_at),
            )
        completed_at = _now_utc()
        connection.execute(
            """UPDATE architecture_scan_runs SET status='completed', observation_count=?, evidence_count=?,
               discrepancy_count=?, completed_at=? WHERE id=?""",
            (len(observations), evidence_count, len(discrepancies), completed_at, scan_id),
        )
        connection.commit()
    return architecture_scan_get(project_root, scan_id=scan_id, read_only=True) | {"idempotent": False}


def _row_dict(cursor: Any, row: Any) -> dict[str, Any]:
    return {str(desc[0]): row[idx] for idx, desc in enumerate(cursor.description)}


def architecture_scan_get(root: Path | str, *, scan_id: int | None = None, read_only: bool = True) -> dict[str, Any]:
    """Return one persisted scan summary without exposing source contents."""
    opener = connect_read_only if read_only else connect
    with opener(Path(root).resolve()) as connection:
        if scan_id is None:
            cursor = connection.execute("SELECT * FROM architecture_scan_runs ORDER BY id DESC LIMIT 1")
        else:
            cursor = connection.execute("SELECT * FROM architecture_scan_runs WHERE id=?", (scan_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("architecture_scan_not_found")
        return _row_dict(cursor, row)


def architecture_observations_get(root: Path | str, *, scan_id: int, section_id: str | None = None) -> list[dict[str, Any]]:
    """Return observation metadata/value JSON; never raw source bytes."""
    with connect_read_only(Path(root).resolve()) as connection:
        sql = "SELECT id,scan_id,section_id,observation_kind,subject,value_json,observation_hash,created_at FROM architecture_observations WHERE scan_id=?"
        args: list[Any] = [scan_id]
        if section_id:
            sql += " AND section_id=?"; args.append(section_id)
        sql += " ORDER BY section_id,observation_kind,subject,id"
        cursor = connection.execute(sql, tuple(args))
        rows = []
        for row in cursor.fetchall():
            item = _row_dict(cursor, row)
            item["value"] = json.loads(item.pop("value_json"))
            rows.append(item)
        return rows


def architecture_evidence_get(root: Path | str, *, scan_id: int, section_id: str | None = None) -> list[dict[str, Any]]:
    """Return evidence paths, hashes, and locators only."""
    with connect_read_only(Path(root).resolve()) as connection:
        sql = "SELECT id,scan_id,observation_id,section_id,evidence_kind,source_path,source_hash,locator_json,evidence_hash,created_at FROM architecture_evidence WHERE scan_id=?"
        args: list[Any] = [scan_id]
        if section_id:
            sql += " AND section_id=?"; args.append(section_id)
        sql += " ORDER BY section_id,source_path,id"
        cursor = connection.execute(sql, tuple(args))
        rows = []
        for row in cursor.fetchall():
            item = _row_dict(cursor, row)
            item["locator"] = json.loads(item.pop("locator_json"))
            rows.append(item)
        return rows


def architecture_discrepancies_get(root: Path | str, *, scan_id: int, section_id: str | None = None) -> list[dict[str, Any]]:
    """Return advisory discovery discrepancies. v0.25.3 does not enforce drift."""
    with connect_read_only(Path(root).resolve()) as connection:
        sql = "SELECT id,scan_id,baseline_id,section_id,discrepancy_type,subject,observed_hash,contract_section_hash,severity,status,details_json,discrepancy_hash,created_at FROM architecture_discrepancies WHERE scan_id=?"
        args: list[Any] = [scan_id]
        if section_id:
            sql += " AND section_id=?"; args.append(section_id)
        sql += " ORDER BY section_id,severity,discrepancy_type,subject,id"
        cursor = connection.execute(sql, tuple(args))
        rows = []
        for row in cursor.fetchall():
            item = _row_dict(cursor, row)
            item["details"] = json.loads(item.pop("details_json"))
            rows.append(item)
        return rows
