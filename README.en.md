# AgentOS Local Governance

**A local-first governance runtime for AI coding agents.**

[Tiếng Việt](README.md) · [Quickstart](.agents/docs/QUICKSTART.md) · [New project](.agents/docs/NEW_PROJECT.md) · [Existing project](.agents/docs/EXISTING_PROJECT.md) · [Windows](.agents/docs/WINDOWS.md) · [Reference](.agents/docs/REFERENCE.md)

## Current release: v0.28.2

v0.28.2 is **Project Bootstrap & Repository Normalization**. It adds no new security feature. This release:

- normalizes release identity to version 0.28.2 and schema 61;
- separates distribution metadata from installed-project metadata;
- replaces the legacy installer flow with `project-init` and `project-adopt`;
- removes representative project identity and Hospital Core purpose from the distribution;
- keeps AgentOS README, VERSION, guides, tests, historical launchers, and historical tools out of the installed application payload;
- compiles modular policy sources into deterministic effective policy;
- validates repositories by role: `agentos_distribution` or `governed_project`.

## Start a project

For a new project:

```powershell
.\.agents\bin\agentos.cmd project-init --project-root D:\path\to\project
```

For an existing project, first generate a read-only adoption plan:

```powershell
.\.agents\bin\agentos.cmd project-adopt --project-root D:\path\to\project
```

Review the plan before applying it with the required human confirmation. See [NEW_PROJECT.md](.agents/docs/NEW_PROJECT.md) and [EXISTING_PROJECT.md](.agents/docs/EXISTING_PROJECT.md).

## Metadata ownership

- Distribution identity: `.agents/distribution/metadata.json`
- Installed-project identity: `.agents/project/identity.json`
- Installed release metadata: `.agents/release/`
- Modular policy source: `.agents/config/policy/`
- Generated effective policy: `.agents/config/generated/governance.effective.json`

The distribution does not contain a representative `project.id` or application purpose. Every governed project receives its own UUID and begins with purpose `UNCONFIRMED`.

## Documentation

Current operational documentation is organized by user journey:

- [QUICKSTART.md](.agents/docs/QUICKSTART.md)
- [NEW_PROJECT.md](.agents/docs/NEW_PROJECT.md)
- [EXISTING_PROJECT.md](.agents/docs/EXISTING_PROJECT.md)
- [WINDOWS.md](.agents/docs/WINDOWS.md)
- [REFERENCE.md](.agents/docs/REFERENCE.md)

Historical details belong in [CHANGELOG.md](CHANGELOG.md), release notes, tags, and archived release artifacts rather than current operational documentation.

## Human authority

Human approval remains mandatory for architecture decisions, task approval, sensitive local overrides, and governance-baseline acknowledgement. AgentOS does not turn an assumption into human authority.
