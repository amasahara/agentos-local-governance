# v0.23.2 — Context Expansion & Compression Evaluation

## 1. Invariants inherited unchanged

1. Canonical Context Pack is authoritative; Transport Pack is derived.
2. Original user request, Requirement Ledger, AGENTS authority, approved scope and active plan are lossless protected content.
3. Protected-content preservation rate is exactly 1.0 or compilation/evaluation fails closed.
4. Only Evidence Plane data may be compressed or expanded.
5. Expansion is read-only and hash-pinned; no source/transport/authority mutation is allowed.
6. Generative LLM summarization is not compression authority.
7. MCP does not gain compile/evaluate-persist/authority mutation.

## 2. Expansion contract v2

An expansion request is bound to:

- transport hash and revision;
- omission handle and canonical revision;
- source hash;
- bounded line window;
- bounded token ceiling;
- allowlisted reason code;
- optional stable Requirement Ledger IDs.

Allowed reasons: `inspection`, `requirement_gap`, `tool_execution`, `test_failure`, `context_miss_probe`, `operator_review`.

Persistent telemetry stores metadata only. Excerpts/raw source text are never stored in `context_expansion_sessions` or `context_expansion_events`.

Batch defaults are policy-bounded by maximum handles, per-handle lines/tokens, and aggregate tokens. Source drift blocks expansion.

## 3. Compression Evaluation v2

Every canonical candidate must be accounted for by either an included evidence item or a valid hash-pinned expansion handle. Evaluation computes:

- canonical/included/expandable/accounted/unaccounted candidate counts;
- handle integrity rate;
- raw/transport tokens and compression ratio;
- exact protected requirement preservation;
- context miss count;
- expansion request/success/failure counts;
- task/test/rework/tool-call metrics when available;
- budget utilization.

Hard failures: preservation below 100%, unaccounted candidate, handle integrity below 100%, input-budget overflow, transport-integrity failure, or stale/unverified source.

The initial 2–4x compression band is advisory. A ratio outside the band creates a warning, not permission to remove protected content.

## 4. Shadow comparison

Historical `SUPERSEDED` transport revisions may be read only when explicitly requested by evaluation. Comparison is deterministic and reports regressions rather than automatically selecting or activating a transport revision.

## 5. Privacy and audit

Expansion/evaluation state contains hashes, IDs, counts, ranges, status and numeric metrics only. It must not contain prompts, responses, credentials, expanded source excerpts, raw identity values, or secret material.

## 6. MCP boundary

MCP additions are read-only: expansion explain, batch expansion without telemetry persistence, expansion-history metadata, compression-evaluation read, and shadow comparison. Evaluation persistence and comparison persistence are CLI/operator operations only.
