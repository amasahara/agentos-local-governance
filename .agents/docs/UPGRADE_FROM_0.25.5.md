# Upgrade AgentOS v0.25.5 → v0.26.0

Use the `apply_v0260.py` asset from the v0.26.0 GitHub Release outside the project repository.

```powershell
python tools\apply_v0260.py D:\agentos-local-governance --dry-run
python tools\apply_v0260.py D:\agentos-local-governance
```

The updater is distribution-lock hash-gated and fail-closed. It does not overwrite project-owned source, `AGENTS.md`, local governance overrides, `.agents/architecture/**`, skills, workflows, runtime/cache/state data, or unknown project paths. It snapshots the SQLite state database before migration and restores both distribution files and the database on failed post-validation.

After upgrade:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests\test_architecture_planning_v0260.py
python -m pytest -q .agents\tests --basetemp=.agents\runtime\pytest-release-v0260 -rs
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd manifest-verify
```

No Architecture Baseline is created or activated by this updater. With no ACTIVE baseline, historical plans remain non-blocking `not_evaluable`. Once a human activates a baseline, new plans must carry the complete architecture-aware planning envelope and are pinned by AgentOS to the exact ACTIVE baseline hash.
