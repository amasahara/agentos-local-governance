# Upgrade AgentOS v0.26.2 → v0.26.3

## Distribution model

The v0.26.3 updater is distributed as a **GitHub Release asset**. Extract the release
asset outside the target repository, then run `apply_v0263.py` against the repository.

PowerShell example:

```powershell
python D:\agentos-updaters\agentos-v0263\tools\apply_v0263.py D:\agentos-local-governance --dry-run
python D:\agentos-updaters\agentos-v0263\tools\apply_v0263.py D:\agentos-local-governance
```

Then rebuild release metadata and validate:

```powershell
cd D:\agentos-local-governance
$env:PYTHONPATH = (Resolve-Path .\.agents).Path

python tools\build_manifest.py .
python tools\verify_manifest.py .
python -m pytest -q .agents\tests -rs
python tools\validate_release.py .
git diff --check
git diff --cached --check
```

Expected identity after a successful upgrade:

- Version: **0.26.3**
- Database schema: **57**
- Release: **Quality/Operational Enforcement**
- Expected CLI surface: **302 commands**
- Expected MCP surface: **107 tools**

The updater requires a finalized v0.26.2 functional baseline (schema 56 and the v0.26.2
MCP/release-integrity reconciliation). It does not grant Architecture Authority to an LLM.
