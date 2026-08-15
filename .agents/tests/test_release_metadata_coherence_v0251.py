"""Path: .agents/tests/test_release_metadata_coherence_v0251.py
Purpose: Verify fail-closed release metadata coherence behavior introduced in v0.25.1.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "agentos" / "release_coherence.py"
    spec = importlib.util.spec_from_file_location("release_coherence_v0251", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".agents/config").mkdir(parents=True)
    root.joinpath("VERSION").write_text("0.25.1\n", encoding="utf-8")
    for name in ["README.md", "README.vi.md", "README.en.md", "RELEASE_NOTES.md"]:
        root.joinpath(name).write_text("AgentOS v0.25.1 — Release Metadata Coherence\n", encoding="utf-8")
    _write_json(
        root / ".agents/config/governance.json",
        {
            "version": "0.25.1",
            "documentation_policy": {
                "current_release_name": "Release Metadata Coherence",
                "current_schema": 49,
                "current_release_identity_files": ["README.md", "README.vi.md", "README.en.md", "RELEASE_NOTES.md"],
            },
            "release_metadata_coherence_policy": {
                "version": 1,
                "source_of_truth": "VERSION",
                "fail_closed": True,
            },
        },
    )
    _write_json(root / "MANIFEST.json", {"release": "0.25.1", "file_count": 8, "files": []})
    _write_json(
        root / "PACKAGE_COMPLETENESS.json",
        {
            "release": "0.25.1",
            "schema": 49,
            "authoritative_file_count": 8,
            "required_top_level": [
                "VERSION",
                "README.md",
                "README.vi.md",
                "README.en.md",
                "RELEASE_NOTES.md",
                "MANIFEST.json",
                "PACKAGE_COMPLETENESS.json",
            ],
        },
    )
    return root


def test_coherent_release_passes(tmp_path: Path) -> None:
    module = _load_module()
    result = module.check_release_metadata_coherence(_fixture(tmp_path), runtime_version="0.25.1", package_version="0.25.1", schema_version=49)
    assert result["ok"] is True
    assert result["findings"] == []


def test_stale_package_release_fails_closed(tmp_path: Path) -> None:
    module = _load_module()
    root = _fixture(tmp_path)
    payload = json.loads((root / "PACKAGE_COMPLETENESS.json").read_text(encoding="utf-8"))
    payload["release"] = "0.23.2"
    _write_json(root / "PACKAGE_COMPLETENESS.json", payload)
    result = module.check_release_metadata_coherence(root, runtime_version="0.25.1", package_version="0.25.1", schema_version=49)
    assert result["ok"] is False
    assert "package_release_mismatch" in {item["code"] for item in result["findings"]}


def test_stale_package_schema_fails_closed(tmp_path: Path) -> None:
    module = _load_module()
    root = _fixture(tmp_path)
    payload = json.loads((root / "PACKAGE_COMPLETENESS.json").read_text(encoding="utf-8"))
    payload["schema"] = 46
    _write_json(root / "PACKAGE_COMPLETENESS.json", payload)
    result = module.check_release_metadata_coherence(root, runtime_version="0.25.1", package_version="0.25.1", schema_version=49)
    assert "package_schema_mismatch" in {item["code"] for item in result["findings"]}


def test_validation_report_cannot_be_clean_main_requirement(tmp_path: Path) -> None:
    module = _load_module()
    root = _fixture(tmp_path)
    payload = json.loads((root / "PACKAGE_COMPLETENESS.json").read_text(encoding="utf-8"))
    payload["required_top_level"].append("VALIDATION_REPORT.json")
    _write_json(root / "PACKAGE_COMPLETENESS.json", payload)
    result = module.check_release_metadata_coherence(root, runtime_version="0.25.1", package_version="0.25.1", schema_version=49)
    assert "excluded_metadata_required" in {item["code"] for item in result["findings"]}


def test_runtime_version_must_equal_version_file(tmp_path: Path) -> None:
    module = _load_module()
    result = module.check_release_metadata_coherence(_fixture(tmp_path), runtime_version="0.25.0", package_version="0.25.1", schema_version=49)
    assert "runtime_version_mismatch" in {item["code"] for item in result["findings"]}


def test_identity_document_must_match_current_release(tmp_path: Path) -> None:
    module = _load_module()
    root = _fixture(tmp_path)
    root.joinpath("README.en.md").write_text("AgentOS v0.25.0 — Schema Bootstrap Baseline\n", encoding="utf-8")
    result = module.check_release_metadata_coherence(root, runtime_version="0.25.1", package_version="0.25.1", schema_version=49)
    assert "identity_file_mismatch" in {item["code"] for item in result["findings"]}


def test_agentos_package_version_must_equal_version_file(tmp_path: Path) -> None:
    module = _load_module()
    result = module.check_release_metadata_coherence(
        _fixture(tmp_path),
        runtime_version="0.25.1",
        package_version="0.23.3",
        schema_version=49,
    )
    assert "package_runtime_version_mismatch" in {item["code"] for item in result["findings"]}
