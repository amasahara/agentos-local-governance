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
**v0.29.3 — Sandbox Configuration & Credential Boundary** · schema **62**

v0.29.3 moves runtime profiles to governed effective-policy configuration and
binds deterministic configuration/reference hashes to AgentOS-mediated process
execution. Process credentials use `secret://alias` only and reuse the trusted
Secret Resolver with provider pin/capability approval.

Synchronous credentials resolve immediately before launch and exact projected
values are redacted from captured output. Async jobs persist only credential
hashes/count, verify the immutable `spec_hash` before resolution, and do not
persist stdout/stderr for credential-bearing jobs.

The release preserves v0.29.1 Windows Job Object containment and the v0.29.2
sandbox workspace/runtime-profile boundary. The claim remains limited to
`agentos_mediated_process_execution`.

`sandbox_configuration_attested = true` and `credential_boundary_attested = true`.
Credential isolation, Restricted Token, Low Integrity, host-filesystem isolation,
OS write confinement, and same-user host-bypass resistance remain unclaimed.
