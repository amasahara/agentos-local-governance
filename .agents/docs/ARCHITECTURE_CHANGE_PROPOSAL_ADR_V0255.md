# AgentOS v0.25.5 — Architecture Change Proposal & ADR Lifecycle

**Release:** 0.25.5 — Architecture Change Proposal & ADR Lifecycle

## Mục tiêu

v0.25.5 xử lý trường hợp v0.25.4 phát hiện một architecture compliance finding nhưng implementation thực sự cần một thay đổi kiến trúc hợp lệ.

Luồng authority:

```text
ACTIVE human Architecture Baseline
            |
            v
Architecture Compliance PASS/WARN/BLOCK
            |
            v
Architecture Change Proposal (proposal-only)
            |
            v
ADR draft
            |
            v
Human review + exact proposal hash
            |
            v
Human approval / rejection
            |
            v
(optional) bind approved proposal -> candidate baseline
            |
            v
Existing Architecture Baseline lifecycle
create -> review -> approve -> activate
```

## Invariant authority

- AI/system actors may create and submit a proposal-only record.
- Proposal creation/submission is not Architecture Authority.
- Human review, approval, rejection, and target-baseline binding require explicit confirmation plus exact proposal hash.
- An approved proposal does not modify `.agents/architecture/**`.
- An approved proposal does not create or activate an Architecture Baseline.
- Once an ACTIVE baseline already exists, a successor baseline cannot activate unless it is bound to an approved proposal whose linked ADR is accepted.
- A new baseline still uses the existing human Architecture Contract lifecycle.
- MCP remains read-only for proposal/ADR state.

## Schema 53

Adds:

- `architecture_change_proposals`
- `architecture_change_proposal_findings`
- `architecture_adrs`
- `architecture_change_events`

Proposal state:

```text
draft -> submitted -> reviewed -> approved
                         \-> rejected
```

ADR state:

```text
proposed -> accepted
         \-> rejected
```

The ADR is accepted only when a human approves the exact linked proposal.

## Compliance binding

A proposal may bind to an Architecture Compliance run and selected findings. When bound:

- source compliance run must be `block` or `warn`;
- run baseline id/hash must match the current ACTIVE baseline;
- selected findings must belong to the selected run;
- proposal identity includes source run hash and finding hashes.

Human review/approval fails closed if the source Architecture Baseline has changed since proposal creation.

## Proposal content

A proposal stores deterministic machine-readable fields:

- title
- summary
- rationale
- affected architecture sections
- proposed changes
- impact analysis
- validation plan
- rollback plan
- source baseline id/hash
- optional compliance run/findings
- immutable proposal hash

## ADR model

Each proposal creates one linked ADR draft containing:

- context
- proposed decision
- consequences
- alternatives
- immutable ADR hash

ADR content can be rendered read-only as Markdown; no automatic ADR file is written into project-owned architecture directories.

## CLI

Proposal-only operations:

- `architecture-proposal-create`
- `architecture-proposal-submit`
- `architecture-proposal-show`
- `architecture-proposals`
- `architecture-adr-show`
- `architecture-change-status`

Human-gated operations:

- `architecture-proposal-review`
- `architecture-proposal-approve`
- `architecture-proposal-reject`
- `architecture-proposal-bind-baseline`

Human-gated operations require task/session governance context on a production AgentOS project plus `--human-confirmed` and exact proposal hash.

## MCP

Read-only tools:

- `agentos.architecture_change_proposal_get`
- `agentos.architecture_change_proposals_list`
- `agentos.architecture_adr_get`
- `agentos.architecture_change_status_get`

MCP does not expose:

- create
- submit
- review
- approve
- reject
- bind
- activate
- waive

## Baseline binding

After a human approves a proposal, the human may separately update the Architecture Contract working copy and create a candidate baseline using the existing v0.25.2 lifecycle. `architecture-proposal-bind-baseline` records traceability between the approved proposal/ADR and that candidate baseline but does not change baseline status. A later `architecture-baseline-activate` call verifies that approved proposal + accepted ADR binding before superseding the current ACTIVE baseline.

## Update preservation

The v0.25.5 updater preserves project-owned source and architecture working artifacts. It only updates AgentOS distribution-managed files whose current SHA-256 matches the v0.25.4 distribution lock.

The updater also fixes metadata-finalization ordering so `PACKAGE_COMPLETENESS.json` is finalized before the new distribution lock and manifest are generated, preventing stale lock hashes caused by self-metadata ordering.

## Historical regression compatibility

The v0.25.4 compliance regression continues to verify migration/schema-52 coverage, but it no longer requires the current AgentOS schema to remain exactly 52. v0.25.5 raises the current schema to 53 while retaining the v0.25.4 contract as a monotonic historical floor.
