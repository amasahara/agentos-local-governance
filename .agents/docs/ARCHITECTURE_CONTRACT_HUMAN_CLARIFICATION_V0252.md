# v0.25.2 — 27-Section Architecture Contract & Human Clarification Gates

## Purpose

v0.25.2 establishes two linked governance boundaries: a human-owned Architecture
Authority and a fail-closed Human Clarification/Decision Gate. The release does
not discover architecture from source and does not yet enforce source-code
architecture drift.

## Architecture registry

The registry is fixed: ARCH-01 Project Overview, ARCH-02 Tech Stack, ARCH-03 Folder
Structure, ARCH-04 System Architecture, ARCH-05 Module Breakdown, ARCH-06 Request
Flow, ARCH-07 Authentication, ARCH-08 Authorization, ARCH-09 Database, ARCH-10 API
Architecture, ARCH-11 Business Flow, ARCH-12 Dependency Graph, ARCH-13 External
Services, ARCH-14 Configuration, ARCH-15 Logging, ARCH-16 Error Handling, ARCH-17
Security, ARCH-18 Performance, ARCH-19 Scalability, ARCH-20 Deployment, ARCH-21
Testing, ARCH-22 Coding Convention, ARCH-23 Design Pattern, ARCH-24 Strengths,
ARCH-25 Technical Debt, ARCH-26 Improvement Proposal, ARCH-27 Appendix.

ARCH-26 is always `proposal_only`. Runtime code must not interpret proposal text as
current architecture authority.

## Working copy and baseline

`architecture-init` creates `.agents/architecture/sections/*.md` and
`.agents/architecture/contracts/*.json`. It does not inspect dependencies, imports,
routes, databases, CI, deployment or other source evidence. Those are v0.25.3.

Working-copy files cannot contain top-level approval/activation authority. A
baseline snapshot stores immutable section content and hashes in SQLite. The
baseline hash is deterministic over ordered section hashes. Review, approval and
activation each require explicit human confirmation and the exact expected hash.
Activation supersedes a previous active baseline atomically; editing the working
copy later never mutates the active snapshot.

## Grill Me / No Silent Assumption

A task cannot be approved without a latest `clear` structured clarity assessment.
Any material assumption is itself blocking. Incomplete requirement dimensions
must be paired with explicit questions. Structured questions are persisted as
human-decision requests.

AI may open a decision and may attach options/recommendation/rationale. It may not
resolve or waive the decision. The MCP request tool is deliberately monotonic: it
can only add a blocker. Read-only tools remain available while waiting; write,
process/network execution, precommit readiness and privileged governed mutations
fail closed.

Human resolutions are stored locally with exact answer text and SHA-256. Signed
external audit contains only hashes and bounded metadata. A resolution classified
as requirement/scope/architecture change revokes task approval and supersedes
submitted/active plans.

## Schema 50

- `architecture_baselines`
- `architecture_section_revisions`
- `architecture_contract_artifacts`
- `architecture_baseline_sections`
- `architecture_events`
- `task_clarity_assessments`
- `human_decision_requests`
- `human_decision_resolutions`
- `human_decision_events`

The bootstrap baseline stays at schema 46. Fresh DB: 46 → 47 → 48 → 49 → 50.
Existing v0.25.1 DB: 49 → 50.

## MCP boundary

Read-only: `agentos.architecture_get`, `agentos.architecture_section_get`,
`agentos.architecture_status_get`, `agentos.human_decision_status`,
`agentos.human_decision_get`.

Monotonic blocker only: `agentos.human_decision_request`.

Not exposed: architecture init/create/review/approve/activate/reject, clarity
persistence, decision resolve/waive, plan/task approval mutation.

## Deferred nodes

- v0.25.3: Architecture Discovery & Evidence Binding
- v0.25.4: Architecture Drift & Compliance Engine
- v0.25.5: Architecture Change Proposal & ADR Lifecycle
- v0.26.0: Architecture-Aware Task Planning
