#!/usr/bin/env python3
"""Validate AgentOS Local Governance v0.22.2 full release."""
from __future__ import annotations
import json
from pathlib import Path
import py_compile
import sqlite3
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
required = [
    "VERSION", "AGENTS.md", "README.md", "README.vi.md", "README.en.md", "huong_dan.md", "huong_dan.vi.md", "huong_dan.en.md",
    ".agents/agentos/reconciliation_recovery.py", ".agents/agentos/reconciliation_recovery_cli.py", ".agents/agentos/mcp_reconciliation_recovery_gateway.py",
    ".agents/config/reconciliation_recovery_policy.v0222.json", ".agents/docs/RECONCILIATION_AND_RECOVERY.md", ".agents/docs/USAGE_V0222.md",
    ".agents/tests/test_reconciliation_recovery_v0222.py", "tools/apply_v0222.py",
]
missing = [p for p in required if not (root / p).exists()]
version = (root / "VERSION").read_text().strip() if (root / "VERSION").exists() else None
governance = json.loads((root / ".agents/config/governance.json").read_text()) if (root / ".agents/config/governance.json").exists() else {}
policy = governance.get("reconciliation_recovery_policy") or {}
controlled = governance.get("controlled_target_insert_policy") or {}

compile_errors = []
for path in (root / ".agents/agentos").glob("*.py"):
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        compile_errors.append(f"{path.name}:{exc}")

expected_tables = {"db_reconciliation_runs", "db_reconciliation_findings", "db_recovery_cases", "db_recovery_checkpoints", "db_recovery_events"}
with sqlite3.connect(root / ".agents/state/agentos.db") as conn:
    sys.path.insert(0, str(root / ".agents"))
    from agentos.reconciliation_recovery import migration_40
    migration_40(conn)
    schema_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] in expected_tables}

docs = subprocess.run([str(root / ".agents/bin/agentos"), "docs-check"], capture_output=True, text=True)
try:
    docs_json = json.loads(docs.stdout)
except Exception:
    docs_json = {"ok": False, "raw": docs.stdout, "stderr": docs.stderr}

request = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
mcp = subprocess.run([str(root / ".agents/bin/agentos-mcp")], input=request, capture_output=True, text=True)
lines = [json.loads(x) for x in mcp.stdout.splitlines() if x.strip()]
mcp_version = None
mcp_tools = []
for item in lines:
    if item.get("id") == 1:
        mcp_version = ((item.get("result") or {}).get("serverInfo") or {}).get("version")
    if item.get("id") == 2:
        mcp_tools = (item.get("result") or {}).get("tools") or []
names = {x.get("name", "") for x in mcp_tools}
mutation_words = ("execute", "approve", "decide", "finalize", "credential", "raw_value")
mutation_names = sorted(n for n in names if any(word in n for word in mutation_words))
required_tools = {
    "agentos.db_reconciliation_get", "agentos.db_reconciliation_summary_get", "agentos.db_reconciliation_spec_get",
    "agentos.db_recovery_cases_get", "agentos.db_recovery_readiness_get", "agentos.db_recovery_checkpoints_get",
}

ok = (
    not missing and not compile_errors and version == "0.22.2"
    and governance.get("version", governance.get("governance_version")) == "0.22.2"
    and policy.get("database_schema") == 40
    and policy.get("target_reconciliation_is_read_only") is True
    and policy.get("in_doubt_auto_retry_allowed") is False
    and policy.get("partial_target_auto_repair_allowed") is False
    and policy.get("source_write_allowed") is False
    and policy.get("raw_values_in_reconciliation_state_allowed") is False
    and controlled.get("raw_target_insert_allowed") is False
    and controlled.get("source_write_allowed") is False
    and controlled.get("reconciled_not_committed_automatic_retry_allowed") is False
    and schema_tables == expected_tables
    and docs.returncode == 0 and docs_json.get("ok") is True
    and mcp.returncode == 0 and mcp_version == "0.22.2" and len(mcp_tools) == 37
    and required_tools <= names and not mutation_names
)
result = {
    "ok": ok,
    "version": version,
    "governance_version": governance.get("version", governance.get("governance_version")),
    "database_schema": 40,
    "schema_tables": sorted(schema_tables),
    "missing": missing,
    "compile_errors": compile_errors,
    "docs_check": docs_json,
    "mcp_server_version": mcp_version,
    "mcp_tool_count": len(mcp_tools),
    "mcp_mutation_names": mutation_names,
    "target_reconciliation_is_read_only": policy.get("target_reconciliation_is_read_only"),
    "in_doubt_auto_retry_allowed": policy.get("in_doubt_auto_retry_allowed"),
    "partial_target_auto_repair_allowed": policy.get("partial_target_auto_repair_allowed"),
    "raw_values_in_reconciliation_state_allowed": policy.get("raw_values_in_reconciliation_state_allowed"),
}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if ok else 1)
