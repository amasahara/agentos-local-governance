# v0.23.0 — Requirement-Preserving Context Compression

## Authority model

The canonical Context Pack remains the source of evidence truth. v0.23.0 creates a derived transport representation; it does not replace canonical context. Generative LLM summarization is forbidden as transport authority.

## Control Plane — LOSSLESS

Protected fields are original request, Requirement Ledger, AGENTS authority, approved scope, active plan, protected policy authority, and their hashes. The Requirement Preservation Gate verifies exact request hash, protected exact spans, scope hash, active plan hash, AGENTS/policy hashes, canonical source freshness, and transport integrity. Preservation rate must equal `1.0`.

## Evidence Plane — COMPRESSIBLE

Evidence uses only deterministic/extractive transformations. The ordered ladder is exact dedup → metadata normalization → structural projection → requirement-aware ranking → omission handles → fail-closed. No word-level deletion is permitted.

Python projection preserves exact symbol/dependency windows. JSON projection preserves selected structural keys/values. Repetitive logs may be aggregated with counts. Omitted material is represented by a hash-pinned expansion handle.

## Budget contract

`input_budget = context_capacity - reserved_output - system_tool_overhead - safety_margin`. Control Plane consumes budget first. Exact tokenizer implementations are preferred; an offline multilingual heuristic is a conservative fallback.

## Transport integrity

Each pack records transport version, task/context revisions, original request/hash, requirement ledger, authority hashes, scope/plan hashes, source freshness hash, token budget, raw/transport/saved token counts, compression ratio, included source handles/excerpts/source hashes/codecs, omission/expansion index, and SHA-256 transport integrity hash.

## MCP boundary

Only five read-only operations are exposed: get, explain, expand, requirement_get, and token_report. Compilation, shadow/evaluation persistence, policy changes, task/scope changes, and any other mutation remain outside MCP. MCP expansion is strictly read-only and does not record an expansion event.

## Evaluation/shadow framework

Metrics: raw/transport tokens, compression ratio, protected/preserved requirement counts, preservation rate, context misses, expansion requests, task success rate, test pass rate, rework count, and tool call count. The initial optimization target is stable 2–4x compression with zero protected-requirement loss.
