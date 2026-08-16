# Upgrade AgentOS v0.25.2 → v0.25.3

This is an **AgentOS-internal release document**. Project-owned root documentation is not rewritten during an AgentOS update.

## Obtain the updater

Download `apply_v0253.py` from the **GitHub Release** asset for v0.25.3 and keep it outside the project-owned source tree, or in a temporary operator directory.

PowerShell:

```powershell
python .\apply_v0253.py D:\agentos-local-governance --dry-run
python .\apply_v0253.py D:\agentos-local-governance
```

POSIX:

```bash
python3 ./apply_v0253.py /path/to/agentos-local-governance --dry-run
python3 ./apply_v0253.py /path/to/agentos-local-governance
```

If preflight reports `managed_file_modified_or_missing`, stop. Do not force overwrite. Move project-specific policy changes to `.agents/config/governance.local.json` and restore the canonical distribution file before retrying.

## Preservation guarantees

The v0.25.3 updater does not overwrite project-owned source/rules/workflow state, including `AGENTS.md`, `.agents/config/governance.local.json`, `.agents/architecture/**`, `.agents/skills/**`, `.agents/workflows/**`, `.agents/state/**`, `.agents/runtime/**`, and unknown project paths.

## Validation

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests\test_architecture_discovery_v0253.py
python -m pytest -q .agents\tests --basetemp=.agents\runtime\pytest-release-v0253 -rs
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd manifest-verify
```
