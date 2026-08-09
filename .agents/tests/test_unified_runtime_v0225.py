"""
File: .agents/tests/test_unified_runtime_v0225.py

Purpose:
    Verify the v0.22.5 unified CLI/MCP and cross-platform runtime guarantees.

Responsibilities:
    - Prove command/tool registries are flat, unique, and importable.
    - Prove top-level POSIX/Windows wrappers use the same Python runtimes.
    - Prove MCP no longer relies on subprocess/version forwarding.
    - Prove fail-loud CLI and JSON-RPC error behavior.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

from agentos.cli_runtime import PRIVILEGED_COMMANDS, command_registry, main as cli_main
from agentos.mcp_runtime import ALL_TOOLS, CORE_TOOL_NAMES, FEATURE_TOOL_NAMES, serve
from agentos.policy import load_policy

ROOT = Path(__file__).resolve().parents[2]


def test_unified_cli_registry_imports_all_commands_without_duplicates() -> None:
    registry = command_registry()
    assert len(registry) == len(set(registry))
    assert len(registry) >= 190
    assert registry["start-task"] == "core"
    assert registry["project-identity-show"] == "project_identity_cli"
    assert registry["db-target-insert-execute"] == "controlled_target_insert_cli"
    assert registry["db-recovery-commit-decide"] == "reconciliation_recovery_cli"
    assert registry["runtime-health"] == "special"


def test_privileged_extension_commands_remain_context_bound(capsys) -> None:
    assert "db-target-insert-execute" in PRIVILEGED_COMMANDS
    code = cli_main(["--root", str(ROOT), "db-target-insert-execute", "--run-id", "1"])
    captured = capsys.readouterr()
    assert code == 2
    assert "requires --task-id and --session-id" in captured.err


def test_unknown_cli_command_fails_loud(capsys) -> None:
    code = cli_main(["--root", str(ROOT), "definitely-not-an-agentos-command"])
    captured = capsys.readouterr()
    assert code == 2
    assert "unknown command" in captured.err


def test_posix_and_windows_wrappers_share_same_runtimes() -> None:
    expected = {
        ".agents/bin/agentos": "agentos.cli_runtime",
        ".agents/bin/agentos.cmd": "agentos.cli_runtime",
        ".agents/bin/agentos-mcp": "agentos.mcp_runtime",
        ".agents/bin/agentos-mcp.cmd": "agentos.mcp_runtime",
    }
    for rel, runtime in expected.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert runtime in text
        assert "agentos.v0" not in text
        assert "agentos-mcp.v0" not in text
        assert "mcp_reconciliation_recovery_gateway" not in text


def test_legacy_version_launchers_are_not_top_level_execution_path() -> None:
    assert (ROOT / ".agents/bin/agentos.v0224").exists()
    assert (ROOT / ".agents/bin/agentos-mcp.v0221").exists()
    assert "agentos.v0224" not in (ROOT / ".agents/bin/agentos").read_text(encoding="utf-8")
    assert "agentos-mcp.v0221" not in (ROOT / ".agents/bin/agentos-mcp").read_text(encoding="utf-8")


def test_unified_mcp_catalog_is_unique_and_complete() -> None:
    names = [item["name"] for item in ALL_TOOLS]
    assert len(names) == len(set(names)) and len(names) >= 52
    assert len(CORE_TOOL_NAMES) == 14
    assert len(FEATURE_TOOL_NAMES) >= 37
    assert "agentos.mcp_health" in names
    assert "agentos.read_file" in names
    assert "agentos.db_reconciliation_get" in names


def test_extension_mutation_tools_are_not_exposed_over_mcp() -> None:
    names = {item["name"] for item in ALL_TOOLS}
    forbidden = {
        "agentos.db_target_insert_execute",
        "agentos.db_identity_candidate_decide",
        "agentos.db_recovery_commit_decide",
        "agentos.db_reconciliation_run",
        "agentos.db_connection_register",
    }
    assert not (names & forbidden)


def _serve_lines(monkeypatch, capsys, lines: list[dict]) -> list[dict]:
    payload = "".join(json.dumps(line) + "\n" for line in lines)
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    serve(ROOT)
    output = capsys.readouterr().out.strip().splitlines()
    return [json.loads(line) for line in output if line.strip()]


def test_mcp_initialize_health_and_unknown_method(monkeypatch, capsys) -> None:
    rows = _serve_lines(monkeypatch, capsys, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "agentos.mcp_health", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 3, "method": "missing/method"},
    ])
    assert rows[0]["result"]["serverInfo"]["version"] == (ROOT / "VERSION").read_text().strip()
    health = json.loads(rows[1]["result"]["content"][0]["text"])
    assert health["subprocess_forwarding"] is False
    assert health["tool_count"] >= 52
    assert rows[2]["error"]["code"] == -32601


def test_core_mcp_tool_requires_bound_context(monkeypatch, capsys) -> None:
    monkeypatch.delenv("AGENTOS_SESSION_TOKEN", raising=False)
    rows = _serve_lines(monkeypatch, capsys, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "agentos.read_file", "arguments": {"path": "README.md"}}}
    ])
    assert rows[0]["error"]["code"] == -32000
    assert "requires --task-id and --session-id" in rows[0]["error"]["message"]


def test_unified_runtime_modules_do_not_import_subprocess() -> None:
    for rel in (".agents/agentos/cli_runtime.py", ".agents/agentos/mcp_runtime.py"):
        assert "import subprocess" not in (ROOT / rel).read_text(encoding="utf-8")


def test_unified_runtime_policy_is_fail_closed() -> None:
    policy = load_policy(ROOT)
    runtime = policy["unified_runtime_policy"]
    assert runtime["single_python_cli_runtime_required"] is True
    assert runtime["single_python_mcp_runtime_required"] is True
    assert runtime["version_forwarding_runtime_allowed"] is False
    assert runtime["mcp_subprocess_forwarding_allowed"] is False
    assert runtime["extension_mutation_tools_exposed_over_mcp"] is False
