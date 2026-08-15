# Upgrade AgentOS v0.25.1 → v0.25.2

v0.25.2 introduces the **27-Section Architecture Contract & Human Clarification Gates**
and upgrades the AgentOS state schema **49 → 50**. The schema-46 bootstrap artifact
is preserved; fresh databases continue from bootstrap 46 through migrations
47, 48, 49 and 50.

The clean-main repository intentionally does **not** carry versioned updater
scripts. Obtain `apply_v0252.py` and its published SHA-256 from GitHub Release
`v0.25.2`, and keep the updater outside the repository.

## 1. Obtain and verify the release updater

Example PowerShell location:

```text
D:\agentos-updaters\apply_v0252.py
```

Verify the downloaded file against the SHA-256 published with GitHub Release
`v0.25.2` before execution.

```powershell
Get-FileHash D:\agentos-updaters\apply_v0252.py -Algorithm SHA256
```

## 2. Dry-run against a clean v0.25.1 checkout

```powershell
python D:\agentos-updaters\apply_v0252.py D:\agentos-local-governance --dry-run
```

The updater must report baseline **0.25.1 / schema 49** and target
**0.25.2 / schema 50**.

## 3. Apply the upgrade

```powershell
python D:\agentos-updaters\apply_v0252.py D:\agentos-local-governance
```

The updater creates a machine-local backup before replacing governed files.

## 4. Initialize the Architecture Contract working copy

```powershell
.\.agents\bin\agentos.cmd architecture-init --created-by HUMAN
```

Initialization creates unresolved working-copy templates only. It does not infer,
approve, or activate architecture.

## 5. Validate the materialized release

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python tools\build_manifest.py .
python tools\verify_manifest.py .
python tools\validate_release.py .
python -m pytest -q .agents\tests -rs
```

Existing approved tasks must receive a v0.25.2 structured clarity assessment
before further mutation. This is intentional fail-closed behavior, not a
backward-compatibility bypass.

Architecture approval/activation and human-decision resolution remain human
authority. MCP may inspect architecture and may open a monotonic blocker, but it
cannot approve architecture or resolve/waive human decisions.
