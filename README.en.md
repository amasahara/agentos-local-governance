# AgentOS Local Governance

**A local-first governance layer between your project and AI coding agents.**

[Tiếng Việt](README.vi.md) · [Quickstart](.agents/docs/QUICKSTART.md) · [Changelog](CHANGELOG.md) · [Release notes](RELEASE_NOTES.md)

## What is AgentOS?

AgentOS Local Governance is not an application framework and does not replace a coding agent. It is a repository-local control layer that lets AI work on your code under explicit scope, policy, architecture, approval, and evidence boundaries.

```text
Human / request
      ↓
AI coding agent or LLM
      ↓
AgentOS: scope · policy · workflow · evidence · approval
      ↓
The user's existing source tree and project structure
```

Its purpose is to keep decision authority with humans while allowing agents to read context, plan work, use tools, modify code, and coordinate execution in a verifiable way.

## What problem does it solve?

AgentOS provides project-level primitives to preserve approved requirements and scope, gate writes and tool calls, manage plans and human decisions, protect concurrent work with leases and expected hashes, attach evidence to material claims, and validate documentation, drift, release identity, and payload.

AgentOS fails closed when workflow, scope, decisions, drift, or approval are not valid.

## Boundary with user source

The distribution intentionally **does not create a representative root `src/` directory**. AgentOS does not own the application's source layout.

Your project may use `src/`, `app/`, `apps/`, `packages/`, `services/`, or another structure. AgentOS governs that layout in place; AgentOS itself is implemented under `.agents/agentos/`.

```text
<project-root>/
├── .agents/              AgentOS managed payload and local governance state
├── src/ or app/...       Source owned by the user's project
├── README.md             Application documentation owned by the user
└── VERSION               Application version owned by the user, when present
```

Installation does not copy AgentOS README, VERSION, or guides into the application root.

## How it works

A governed task preserves the original request, detects the environment, builds bounded context, resolves material ambiguity through human decisions, obtains scope and plan approval, checks authorization before execution, records evidence and audit, and runs documentation, test, structural, and synchronization checks before completion.

## Get started

New project:

```powershell
.\.agents\bin\agentos-admin.cmd project-init --target D:\path\to\project
```

Existing project, generate a read-only adoption plan first:

```powershell
.\.agents\bin\agentos.cmd project-adopt --target D:\path\to\project
```

After human review:

```powershell
.\.agents\bin\agentos-admin.cmd project-adopt --target D:\path\to\project --apply --human-confirmed
```

Follow the guide for your journey:

- [NEW PROJECT](.agents/docs/NEW_PROJECT.md)
- [EXISTING PROJECT](.agents/docs/EXISTING_PROJECT.md)
- [WINDOWS](.agents/docs/WINDOWS.md)
- [REFERENCE](.agents/docs/REFERENCE.md)

## Distribution repository layout

- `.agents/agentos/`: current runtime implementation;
- `.agents/config/policy/`: modular policy sources;
- `.agents/config/generated/governance.effective.json`: deterministically generated effective policy;
- `.agents/distribution/metadata.json`: authoritative distribution metadata;
- `.agents/docs/`: operational and reference documentation;
- `.agents/tests/`: distribution regression tests, excluded from installed application payload;
- `tools/`: distribution build and validation tools, not installed into application projects.

Version history belongs in [CHANGELOG.md](CHANGELOG.md), Git history, tags, and release artifacts—not in the current onboarding path.

## Contributing

State the problem and acceptance criteria, place changes by responsibility and lifecycle, update relevant tests and documentation, run release validation and manifest verification, and do not commit runtime caches or reproducible test output.

Governance changes must keep `AGENTS.md`, structured policy, runtime enforcement, tests, documentation, changelog, and release identity coherent.
## Current release
**v0.30.1 — Release & Schema Metadata Coherence** · schema **63**

This release is a coherence-only prerequisite for v0.31.0. It does not add a
new database migration or learning feature. It aligns current release identity,
schema-bootstrap metadata, and generated policy with runtime schema 63, and it
adds a fail-closed contiguous migration check for bootstrap schema 46 → 63.

Historical subsystem fields such as `database_schema = 55` remain descriptive
metadata for the release in which those subsystems were introduced; they are
not rewritten merely to match the current schema.

### Inherited predecessor contracts

v0.30.1 preserves **v0.30.0 — Context Authority & Untrusted Provenance**.
Evidence-derived or untrusted context still cannot promote itself into AgentOS
instruction authority in the governed Context Transport path. This predecessor
contract does not claim that prompt injection is eliminated or that human review
is replaced.

v0.30.1 also preserves **v0.29.5 — Native Physical Isolation Extensions** and
its bounded v0.29.4 Restricted Token predecessor. Those Windows execution claims
remain scoped to AgentOS-mediated process execution and do not imply general
host isolation or same-user host-bypass resistance.
