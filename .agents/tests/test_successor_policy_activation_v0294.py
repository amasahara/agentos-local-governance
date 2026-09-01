
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from agentos.policy import load_policy
from agentos.tool_runtime_profiles import (
    credential_reference_contract_from_policy,
    sandbox_configuration_from_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def test_v0294_successor_keeps_v0293_sandbox_configuration_contract_active():
    policy = load_policy(ROOT)

    assert policy["version"] == "0.29.4"

    configuration = sandbox_configuration_from_policy(
        policy
    )

    assert (
        configuration[
            "configuration_source"
        ]
        == "effective_policy"
    )
    assert len(
        configuration[
            "configuration_hash"
        ]
    ) == 64


def test_v0294_successor_keeps_v0293_credential_reference_contract_active():
    policy = load_policy(ROOT)

    contract = (
        credential_reference_contract_from_policy(
            policy
        )
    )

    assert (
        contract[
            "credential_reference_version"
        ]
        == 1
    )
    assert len(
        contract[
            "credential_reference_hash"
        ]
    ) == 64


def test_v0294_future_successor_versions_preserve_v0293_contracts():
    policy = copy.deepcopy(
        load_policy(ROOT)
    )
    policy["version"] = "0.29.5"

    configuration = (
        sandbox_configuration_from_policy(
            policy
        )
    )
    contract = (
        credential_reference_contract_from_policy(
            policy
        )
    )

    assert len(
        configuration[
            "configuration_hash"
        ]
    ) == 64
    assert len(
        contract[
            "credential_reference_hash"
        ]
    ) == 64


@pytest.mark.parametrize(
    "version",
    (
        "",
        "0.29.2",
        "not-a-version",
    ),
)
def test_v0294_pre_v0293_or_invalid_version_does_not_activate_successor_contract(
    version,
):
    policy = copy.deepcopy(
        load_policy(ROOT)
    )
    policy["version"] = version

    with pytest.raises(
        RuntimeError,
        match=(
            "sandbox_configuration_contract_invalid"
        ),
    ):
        sandbox_configuration_from_policy(
            policy
        )

    with pytest.raises(
        RuntimeError,
        match=(
            "credential_reference_contract_invalid"
        ),
    ):
        credential_reference_contract_from_policy(
            policy
        )
