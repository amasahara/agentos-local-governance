# Upgrade v0.24.2 → v0.24.3

v0.24.3 introduces **MCP Feature Runtime Refactor** and keeps database schema **49**.

The clean-main repository does not contain versioned updater scripts. Obtain
`apply_v0243.py` and its SHA-256 from GitHub Release `v0.24.3`, keep it outside
the repository, then run it against the v0.24.2 checkout.

PowerShell:

```powershell
Get-FileHash D:\agentos-updaters\apply_v0243.py -Algorithm SHA256
python D:\agentos-updaters\apply_v0243.py D:\agentos-local-governance
```

Linux/macOS:

```bash
python ~/agentos-updaters/apply_v0243.py ~/agentos-local-governance
```

The updater requires:

```text
VERSION 0.24.2
schema 49
clean-main v0.24.2 runtime
```

and converges to:

```text
VERSION 0.24.3
schema 49
active MCP feature runtime detached from legacy gateways
```

After upgrade:

```powershell
cd D:\agentos-local-governance
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

No MCP mutation permission is added by this node.
