from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_release_identity_is_v0290_schema62():
    import agentos
    from agentos.db import SCHEMA_VERSION
    from agentos.schema_version import CURRENT_SCHEMA_VERSION
    from agentos.completion_verification import MIGRATION_VERSION

    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.29.0"
    assert agentos.__version__ == "0.29.0"
    assert SCHEMA_VERSION == 62
    assert CURRENT_SCHEMA_VERSION == 62
    assert MIGRATION_VERSION == 62


def test_migration62_is_registered_last():
    from agentos.db import _all_migrations

    migrations = _all_migrations()
    assert len(migrations) == 62
    assert migrations[-1].__name__ == "migration_62"


def test_fresh_database_materializes_schema62():
    from agentos.db import connect

    with TemporaryDirectory() as td:
        root = Path(td) / "project"
        (root / ".agents").mkdir(parents=True)

        with connect(root) as c:
            versions = [int(row[0]) for row in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
            tables = {str(row[0]) for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert versions == list(range(1, 63))
    assert "completion_verification_requests" in tables
    assert "completion_verification_attempts" in tables


def test_v0290_policy_activation_is_fail_closed():
    from agentos.policy import load_policy, validate_policy

    policy = load_policy(ROOT)
    completion = policy["completion_verification_policy"]
    assert policy["version"] == "0.29.0"
    assert completion["independent_completion_attested"] is True
    assert completion["database_schema"] == 62
    assert completion["scope"] == "agentos_mediated_agent_execution"
    assert completion["mcp_status_read_only"] is True
    assert completion["mcp_mutation_allowed"] is False

    poisoned = copy.deepcopy(policy)
    poisoned["completion_verification_policy"]["semantic_correctness_guaranteed"] = True
    with pytest.raises(RuntimeError, match="overclaim"):
        validate_policy(poisoned)


def test_v0284_policy_compatibility_is_preserved():
    from agentos.policy import load_policy, validate_policy

    historical = copy.deepcopy(load_policy(ROOT))
    historical["version"] = "0.28.4"
    historical.pop("completion_verification_policy", None)
    historical["web_control_plane_policy"]["database_schema"] = 61
    historical["privileged_control_plane_policy"]["database_schema"] = 61
    validate_policy(historical)


def test_completion_attestation_is_policy_activated():
    from agentos.enforcement_attestation import attest_enforcement

    report = attest_enforcement(ROOT)
    completion = report["completion_verification"]
    assert report["ok"], report["findings"]
    assert report["attestation_ready"] is True
    assert completion["structurally_attested"] is True
    assert completion["policy_declared_attested"] is True
    assert completion["policy_scope"] == "agentos_mediated_agent_execution"


def test_completion_release_integrity_gate_is_green():
    from agentos.release_integrity import check_release_integrity

    result = check_release_integrity(ROOT)
    codes = [
        str(item.get("code"))
        for item in result.get("findings", [])
        if "completion" in str(item.get("code", ""))
    ]
    assert codes == []
