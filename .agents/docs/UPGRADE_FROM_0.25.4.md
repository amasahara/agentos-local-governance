# Upgrade v0.25.4 → v0.25.5

Use the updater distributed with the GitHub Release asset, not a copy placed inside the governed repository.

```powershell
python tools\apply_v0255.py D:\agentos-local-governance --dry-run
```

Proceed only when preflight returns `"ok": true` and `"findings": []`.

```powershell
python tools\apply_v0255.py D:\agentos-local-governance
```

The updater:

- validates v0.25.4 distribution-lock hashes before mutation;
- never overwrites project-owned source, `AGENTS.md`, local governance, architecture working copies, skills, workflows, runtime or state artifacts;
- creates a consistent SQLite backup before schema migration;
- migrates schema 52 → 53 additively;
- checks prior table row counts for loss;
- rebuilds package metadata, distribution lock, manifest and checksums in stable order;
- runs docs, runtime and manifest release gates;
- restores AgentOS-managed files and SQLite state if the upgrade fails.

After upgrade:

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python -m pytest -q .agents\tests\test_architecture_change_v0255.py
python -m pytest -q .agents\tests --basetemp=.agents\runtime\pytest-release-v0255 -rs
.agents\bin\agentos.cmd docs-check
.agents\bin\agentos.cmd runtime-health
.agents\bin\agentos.cmd manifest-verify
.agents\bin\agentos.cmd architecture-change-status
```

`architecture-change-status` does not activate or mutate Architecture Authority.

## Regression-contract maintenance

The updater also patches `.agents/tests/test_architecture_compliance_v0254.py` under the v0.25.4 distribution-lock hash. The test still guarantees schema-52 coverage, but accepts later current schemas such as schema 53.
