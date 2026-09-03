# Context Authority & Untrusted Provenance — v0.30.0

## Purpose

AgentOS v0.30.0 introduces an explicit authority boundary for the context assembly path.

```text
UNTRUSTED OR EVIDENCE-DERIVED CONTENT != INSTRUCTION AUTHORITY
```

AgentOS classifies context by **source origin**, not by whether the text looks imperative or instruction-like.

## Authority classes

```text
none
governance
human_request
approved_task
human_decision
```

## Provenance / trust classes

```text
governance_authority
human_authority
approved_task_authority
project_evidence
tool_evidence
external_untrusted
generated_evidence
unknown_untrusted
```

Verified provenance is not equivalent to instruction authority.

## No authority promotion

Derived content does not gain authority through retrieval, projection, compression, summarization, copying from evidence, or instruction-like wording.

Exact copies may preserve authority only when the parent already has explicit authority, the child uses the same explicit authority origin, and the transform is an allowed exact-preserving transform.

## Context Transport binding

Context Transport v0.30.0 binds `provenance_manifest_hash` and `context_authority_hash` in addition to the existing request/authority/scope/plan/freshness/transport pins. The read path re-evaluates stored hash-only provenance and rejects pin mismatch.

## Persistence boundary

Schema 63 adds:

```text
context_provenance_records
context_authority_evaluations
context_authority_findings
```

The v0.30.0 provenance tables persist hashes, labels, producer/transform metadata, and parent provenance IDs rather than duplicating raw request, source, tool, external-document, or generated-summary content.

## Read-only inspection

CLI:

```text
context-authority-status
context-provenance-show
context-authority-explain
context-authority-findings
```

MCP:

```text
agentos.context_authority_status_get
agentos.context_provenance_get
agentos.context_authority_explain
agentos.context_authority_findings_get
```

There is no MCP context-authority grant, trust-promotion, provenance-override, approval, or finding-waiver surface.

## Attestation scope and non-claims

Structural attestation covers origin classification, no-promotion, hash-only persistence, transport pinning, read-only surfaces, and bounded non-claims.

v0.30.0 does not claim prompt-injection elimination, semantic correctness, prevention of every model-manipulation path, replacement of human review, same-user host bypass resistance, or general host isolation.
