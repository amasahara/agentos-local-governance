# AgentOS Local Governance

**Current release: v0.24.3 — MCP Feature Runtime Refactor**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

Database schema: **49**.

v0.24.3 separates active MCP feature execution from historical
`mcp_*_gateway.py` compatibility modules. The active runtime is now split into:

```text
mcp_runtime
├─ mcp_core_runtime
│  └─ trusted gateway_client → gatewayd enforcement
└─ mcp_feature_runtime
   ├─ mcp_feature_handlers
   └─ modern read-only feature modules
```

The public MCP tool surface is preserved: **14 core + 63 feature + health = 78 tools**.

## Governance invariants

- No DB schema migration in v0.24.3; schema remains 49.
- Legacy MCP gateway modules are not active handler owners.
- Active MCP runtime does not subprocess/version-forward.
- Governed core tools still use the trusted gatewayd enforcement boundary.
- Extension mutation tools remain outside MCP.
- SOURCE/TARGET DB boundaries, human approval, privacy, signed audit and context-preservation rules are unchanged.

## Validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

## Upgrade

See [Upgrade v0.24.2 → v0.24.3](UPGRADE_FROM_0.24.2.md). The versioned updater
is a GitHub Release asset and is intentionally absent from clean `main`.

## Current node documentation

- [MCP Feature Runtime Refactor](.agents/docs/MCP_FEATURE_RUNTIME_REFACTOR_V0243.md)
- [DB-Aware Context Projection](.agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md)
- [Risk-Tiered Batch Review](.agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)
