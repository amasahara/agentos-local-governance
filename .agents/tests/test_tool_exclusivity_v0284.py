"""
File: .agents/tests/test_tool_exclusivity_v0284.py

Purpose:
    Protect v0.28.4 Tool Exclusivity & Enforcement Attestation.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import agentos.cli as cli_module
import agentos.gatewayd as gateway_module
import agentos.jobs as jobs_module
import agentos.proxy as proxy_module


ROOT = Path(__file__).resolve().parents[2]


def test_cli_job_submit_routes_through_proxy() -> None:
    source = inspect.getsource(cli_module)

    assert "proxy_submit_job(" in source
    assert (
        "result=submit_job(root,tid,session"
        not in source
    )


def test_gateway_async_execution_routes_through_proxy() -> None:
    source = inspect.getsource(gateway_module)

    assert "proxy_submit_job(" in source
    assert "return submit_job(" not in source


def test_async_job_runtime_requires_execution_token() -> None:
    signature = inspect.signature(jobs_module.submit_job)

    token = signature.parameters["execution_token"]

    assert token.kind is inspect.Parameter.KEYWORD_ONLY
    assert token.default is inspect.Parameter.empty


def test_proxy_exposes_canonical_async_submission() -> None:
    assert callable(proxy_module.proxy_submit_job)

    assert (
        proxy_module.CAPABILITIES[
            "agentos.run_command_async"
        ]
        == "process.exec"
    )


def test_async_job_cannot_start_without_guard_token(
    tmp_path: Path,
) -> None:
    root = tmp_path

    # The API contract itself must fail before any async
    # subprocess launch is possible.
    with pytest.raises(TypeError):
        jobs_module.submit_job(
            root,
            "T-V0284",
            "S-V0284",
            ["python", "-m", "pytest"],
        )


def test_start_job_requires_guarded_authority() -> None:
    signature = inspect.signature(
        jobs_module.start_job
    )

    token = signature.parameters[
        "execution_token"
    ]
    guarded = signature.parameters[
        "guarded_args"
    ]

    assert (
        token.kind
        is inspect.Parameter.KEYWORD_ONLY
    )
    assert (
        guarded.kind
        is inspect.Parameter.KEYWORD_ONLY
    )

    assert token.default is inspect.Parameter.empty
    assert guarded.default is inspect.Parameter.empty


def test_start_job_no_longer_accepts_clean_env() -> None:
    signature = inspect.signature(
        jobs_module.start_job
    )

    assert "clean_env" not in signature.parameters


def test_actual_async_side_effect_revalidates_token() -> None:
    source = inspect.getsource(
        jobs_module.start_job
    )

    assert "validate_execution_token(" in source
    assert "subprocess.Popen(" in source

    assert (
        source.index("validate_execution_token(")
        < source.index("subprocess.Popen(")
    )


def test_deferred_job_token_cannot_directly_launch() -> None:
    source = inspect.getsource(
        jobs_module.start_job
    )

    assert (
        'guarded_args.get("auto_start") is not True'
        in source
    )

    assert (
        "queued job requires a new guarded start operation"
        in source
    )


def test_async_launch_environment_is_guard_derived() -> None:
    source = inspect.getsource(
        jobs_module.start_job
    )
    signature = inspect.signature(
        jobs_module.start_job
    )

    assert "clean_env" not in signature.parameters

    assert (
        'guarded_args.get("env") or {}'
        in source
    )
    assert "_filtered_env(" in source
    assert "environment_hash" in source
    assert "env=launch_env" in source


def test_run_tests_routes_through_canonical_proxy() -> None:
    source = inspect.getsource(
        cli_module._run_tests
    )

    assert "proxy_execute(" in source
    assert '"agentos.run_command"' in source
    assert "subprocess.run(" not in source


def test_run_tests_default_excludes_agentos_internals() -> None:
    parser = cli_module.parser()
    parsed = parser.parse_args(
        ["run-tests"]
    )

    assert parsed.path == "tests"


def test_unified_runtime_has_no_raw_run_tests_override() -> None:
    import agentos.cli_runtime as runtime_module

    source = inspect.getsource(
        runtime_module
    )

    assert (
        "_run_tests_with_active_python"
        not in source
    )

    assert (
        "core_cli.subprocess.run("
        not in source
    )


def test_windows_python_executable_maps_to_test_profile() -> None:
    from agentos.policy import load_policy

    policy = load_policy(ROOT)

    profile = proxy_module._command_profile(
        [
            r"C:\\Python\\python.exe",
            "-m",
            "pytest",
            "tests",
            "-q",
        ],
        policy,
    )

    assert profile == "test"
