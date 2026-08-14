# Upgrade v0.24.3 → v0.25.0

v0.25.0 introduces **Schema Bootstrap Baseline** and keeps database schema **49**.

The clean-main repository intentionally does not contain versioned updater
scripts. Obtain `apply_v0250.py` and its SHA-256 from GitHub Release `v0.25.0`
and keep the updater outside the repository.

PowerShell:

```powershell
Get-FileHash D:\agentos-updaters\apply_v0250.py -Algorithm SHA256
python D:\agentos-updaters\apply_v0250.py D:\agentos-local-governance
```

The updater requires a coherent v0.24.3/schema-49 checkout and generates the
release-pinned schema-46 bootstrap artifact from that migration chain before
changing runtime initialization.

After upgrade:

```powershell
cd D:\agentos-local-governance
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

Existing databases retain incremental migration semantics. Only a truly fresh,
empty state database takes the bootstrap path.
