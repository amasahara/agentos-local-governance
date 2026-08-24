# AgentOS v0.28.2 User Guide

Current release: **v0.28.2 — Project Bootstrap & Repository Normalization**  
Database schema: **61**

AgentOS is a local-first governance layer between a user's repository and coding agents or LLMs. It does not replace the application's source layout: project code remains in the structure chosen by the project (`src/`, `app/`, `packages/`, or an existing layout), while the governance runtime lives under `.agents/`.

## Start a new project

From the AgentOS distribution, run:

```powershell
.\.agents\bin\agentos.cmd project-init --project-root D:\path\to\new-project
```

The command creates governed-project metadata and installs only the required project payload. Distribution README, VERSION, and AgentOS guides are not copied into the application root.

## Adopt an existing project

Generate a read-only adoption plan first:

```powershell
.\.agents\bin\agentos.cmd project-adopt --project-root D:\path\to\existing-project
```

Review the plan and resolve conflicts before applying it with explicit human confirmation:

```powershell
.\.agents\bin\agentos.cmd project-adopt --project-root D:\path\to\existing-project --apply --human-confirmed
```

AgentOS governs the existing source layout in place. The distribution does not need a representative root `src/` directory.

## Metadata and policy

- Distribution metadata: `.agents/distribution/metadata.json`
- Installed-project identity: `.agents/project/identity.json`
- Installed release metadata: `.agents/release/`
- Policy baseline and modules: `.agents/config/governance.json` with `.agents/config/policy/`
- Deterministic effective policy: `.agents/config/generated/governance.effective.json`

Do not edit the effective policy directly. Change the appropriate policy source and regenerate the artifact.

## Documentation by journey

- Quick start: `.agents/docs/QUICKSTART.md`
- New project: `.agents/docs/NEW_PROJECT.md`
- Existing project: `.agents/docs/EXISTING_PROJECT.md`
- Windows: `.agents/docs/WINDOWS.md`
- Reference: `.agents/docs/REFERENCE.md`

## Validate the distribution

```powershell
$env:PYTHONPATH = (Resolve-Path .\.agents).Path
python tools\build_manifest.py .
python tools\verify_manifest.py .
python -m pytest -q .agents\tests -rs
python tools\validate_release.py .
git diff --check
```

Run `tools/build_manifest.py` after any release-payload change. `tools/verify_manifest.py` must report `ok: true` before release.

## v0.28.2 scope

v0.28.2 normalizes bootstrap, repository layout, metadata, policy, and current documentation. It adds no new security feature. Historical changes belong in `CHANGELOG.md`; `README.en.md` remains the durable project overview.