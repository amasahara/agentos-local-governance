# Upgrade v0.24.1 → v0.24.2

v0.24.2 upgrades schema **48 → 49** and adds DB-Aware Context Projection.

The clean-main repository intentionally does **not** contain
`tools/apply_v0242.py`. The versioned updater is distributed with the GitHub
Release `v0.24.2`.

## 1. Obtain release assets

From GitHub Release `v0.24.2`, obtain:

```text
apply_v0242.py
apply_v0242.py.sha256   (or SHA256SUMS.txt)
```

Keep the updater outside the repository, for example:

```text
D:\agentos-updaters\apply_v0242.py
```

## 2. Verify checksum

PowerShell example:

```powershell
Get-FileHash D:\agentos-updaters\apply_v0242.py -Algorithm SHA256
```

Compare the result with the SHA-256 published in the GitHub Release asset.

## 3. Run the updater against the repository

```powershell
python D:\agentos-updaters\apply_v0242.py D:\agentos-local-governance
```

Linux/macOS example:

```bash
python ~/agentos-updaters/apply_v0242.py ~/agentos-local-governance
```

The updater requires a coherent **v0.24.1 / schema 48** baseline and converges
to **v0.24.2 / schema 49**.

## 4. Validate the materialized release

```powershell
cd D:\agentos-local-governance
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests -rs
```

The Control Plane remains lossless. SOURCE/TARGET mutation authority, approval,
privacy, signed-audit, and risk-tier review boundaries are unchanged.

## Windows backup location

Upgrade/recovery backups are machine-local release artifacts outside clean
`main`. `AGENTOS_UPGRADE_BACKUP_HOME` may be used to choose their location.
