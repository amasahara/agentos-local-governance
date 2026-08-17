# Upgrade AgentOS v0.26.1 → v0.26.2

## Distribution model

The v0.26.2 updater is distributed as a **GitHub Release asset**. Extract the release
asset outside the target repository, then run `apply_v0262.py` from that extracted
asset against the repository you want to upgrade.

PowerShell example:

```powershell
python D:\agentos-updaters\agentos-v0262\tools\apply_v0262.py D:\agentos-local-governance --dry-run
python D:\agentos-updaters\agentos-v0262\tools\apply_v0262.py D:\agentos-local-governance
```

After the upgrade, run from the target repository:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
```

Expected release identity:

- Version: **0.26.2**
- Database schema: **56**
- Release: **Runtime/Data/API & Business Boundary Enforcement**

The updater verifies the functional v0.26.1 baseline before changing managed files.
It does not grant architecture approval, waiver, or activation authority to an LLM.
