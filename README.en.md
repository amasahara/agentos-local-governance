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
**v0.32.0 — Execution Identity & Model Provenance** · schema **65**

v0.32.0 adds durable, hash-bound and privacy-safe execution provenance linking task/session/execution references to provider/model/agent/runtime identity.

Schema 65 uses `execution_provenance` plus a separate task-outcome linkage table; it does not ALTER `task_outcomes`, preserving v0.31.x learning-signal source hashes.

`execution-provenance-register` is privileged control-plane-only; agents receive read-only `get/status`. `runtime_bound` is not remote-provider cryptographic attestation. Provider request IDs are SHA-256-only; credentials, endpoint URLs, raw prompts and raw responses are not persisted.

Learning effectiveness now requires provider/model matching for provenanced outcomes. Legacy outcomes remain valid but are excluded from strict v0.32 matched cohorts.

There is no automatic provider/model selection, no Context Authority change, no instruction authority, and MCP remains at 132 tools.

The release preserves v0.31.3 Learning Effectiveness & Drift, v0.31.2 Closed-Loop Skill & Policy Improvement, and **v0.29.5 — Native Physical Isolation Extensions**.
