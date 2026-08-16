# Upgrade AgentOS v0.25.3 → v0.25.4

Use the `apply_v0254.py` asset from the v0.25.4 GitHub Release outside the project repository.

```powershell
python tools\apply_v0254.py D:\agentos-local-governance --dry-run
python tools\apply_v0254.py D:\agentos-local-governance
```

The updater is ownership-aware and fail-closed. It never overwrites project-owned source, `AGENTS.md`, local governance overrides, architecture working copies, skills, workflows, runtime/cache/state contents, or unknown project paths. Existing AgentOS-managed files must match the trusted v0.25.3 distribution baseline before replacement.

After upgrade:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests --basetemp=.agents\runtime\pytest-release-v0254 -rs
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd manifest-verify
.agents\bin\agentos.cmd architecture-compliance-status
```

No ACTIVE Architecture Contract is created by the updater. Architecture compliance becomes enforcing only for a baseline that a human has reviewed, approved, and activated through the existing architecture lifecycle.
