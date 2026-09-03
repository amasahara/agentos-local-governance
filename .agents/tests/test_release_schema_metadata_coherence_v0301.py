"""v0.30.1 schema/release metadata coherence regression tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from agentos.release_coherence import check_schema_bootstrap_coherence
from agentos.schema_version import CURRENT_SCHEMA_VERSION


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _good() -> dict:
    return {
        "documentation_policy": {"current_schema": 63},
        "schema_bootstrap_policy": {
            "bootstrap_schema": 46,
            "current_database_schema": 63,
            "post_baseline_migrations_at_release": list(range(47, 64)),
        },
        "architecture_planning_policy": {"database_schema": 55},
    }


def _root(tmp_path: Path, mutate=None, generated_mutate=None) -> Path:
    root = tmp_path / "repo"
    source = _good()
    if mutate:
        mutate(source)
    _write(root / ".agents/config/governance.json", source)
    _write(root / ".agents/config/policy/10-bootstrap.json", {})
    generated = copy.deepcopy(source)
    generated["schema_version"] = 63
    if generated_mutate:
        generated_mutate(generated)
    _write(root / ".agents/config/generated/governance.effective.json", generated)
    return root


def _codes(report: dict) -> set[str]:
    return {str(item.get("code")) for item in report.get("findings", [])}


def test_current_repository_schema_bootstrap_is_coherent() -> None:
    root = Path(__file__).resolve().parents[2]
    report = check_schema_bootstrap_coherence(
        root, schema_version=CURRENT_SCHEMA_VERSION
    )
    assert report["ok"] is True, report


def test_stale_current_schema_is_rejected(tmp_path: Path) -> None:
    def mutate(policy):
        policy["schema_bootstrap_policy"]["current_database_schema"] = 55
    report = check_schema_bootstrap_coherence(_root(tmp_path, mutate), schema_version=63)
    assert "schema_bootstrap_current_schema_mismatch" in _codes(report)


def test_missing_middle_migration_is_rejected(tmp_path: Path) -> None:
    def mutate(policy):
        policy["schema_bootstrap_policy"]["post_baseline_migrations_at_release"].remove(58)
    report = check_schema_bootstrap_coherence(_root(tmp_path, mutate), schema_version=63)
    assert "schema_bootstrap_migration_coverage_mismatch" in _codes(report)


def test_duplicate_migration_is_rejected(tmp_path: Path) -> None:
    def mutate(policy):
        policy["schema_bootstrap_policy"]["post_baseline_migrations_at_release"].insert(5, 52)
    report = check_schema_bootstrap_coherence(_root(tmp_path, mutate), schema_version=63)
    assert "schema_bootstrap_migration_duplicate" in _codes(report)


def test_out_of_order_migration_is_rejected(tmp_path: Path) -> None:
    def mutate(policy):
        values = policy["schema_bootstrap_policy"]["post_baseline_migrations_at_release"]
        values[5], values[6] = values[6], values[5]
    report = check_schema_bootstrap_coherence(_root(tmp_path, mutate), schema_version=63)
    assert "schema_bootstrap_migration_out_of_order" in _codes(report)


def test_migration_above_current_is_rejected(tmp_path: Path) -> None:
    def mutate(policy):
        policy["schema_bootstrap_policy"]["post_baseline_migrations_at_release"].append(64)
    report = check_schema_bootstrap_coherence(_root(tmp_path, mutate), schema_version=63)
    assert "schema_bootstrap_migration_above_current" in _codes(report)


def test_generated_top_level_schema_mismatch_is_rejected(tmp_path: Path) -> None:
    def generated_mutate(policy):
        policy["schema_version"] = 62
    report = check_schema_bootstrap_coherence(
        _root(tmp_path, generated_mutate=generated_mutate),
        schema_version=63,
    )
    assert "effective_policy_schema_mismatch" in _codes(report)


def test_stale_generated_policy_after_source_change_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    source = json.loads((root / ".agents/config/governance.json").read_text(encoding="utf-8"))
    source["schema_bootstrap_policy"]["schema_change"] = "source_changed"
    _write(root / ".agents/config/governance.json", source)
    report = check_schema_bootstrap_coherence(root, schema_version=63)
    assert "generated_policy_source_drift" in _codes(report)


def test_historical_subsystem_database_schema_is_not_current_schema_claim(tmp_path: Path) -> None:
    report = check_schema_bootstrap_coherence(_root(tmp_path), schema_version=63)
    assert report["ok"] is True, report


def test_generic_release_coherence_does_not_require_bootstrap_for_legacy_fixture(tmp_path: Path) -> None:
    from agentos.release_coherence import check_release_metadata_coherence

    root = tmp_path / "legacy"
    (root / ".agents/config").mkdir(parents=True)
    (root / "VERSION").write_text("0.25.1\n", encoding="utf-8")
    for name in ("README.md", "README.vi.md", "README.en.md", "RELEASE_NOTES.md"):
        (root / name).write_text(
            "AgentOS v0.25.1 — Release Metadata Coherence\n",
            encoding="utf-8",
        )
    _write(
        root / ".agents/config/governance.json",
        {
            "version": "0.25.1",
            "documentation_policy": {
                "current_release_name": "Release Metadata Coherence",
                "current_schema": 49,
                "current_release_identity_files": [
                    "README.md",
                    "README.vi.md",
                    "README.en.md",
                    "RELEASE_NOTES.md",
                ],
            },
            "release_metadata_coherence_policy": {
                "version": 1,
                "source_of_truth": "VERSION",
                "fail_closed": True,
            },
        },
    )
    _write(root / "MANIFEST.json", {"release": "0.25.1", "file_count": 8, "files": []})
    _write(
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
    report = check_release_metadata_coherence(
        root,
        runtime_version="0.25.1",
        package_version="0.25.1",
        schema_version=49,
    )
    assert report["ok"] is True, report
    assert report["schema_bootstrap_coherence"] is None
