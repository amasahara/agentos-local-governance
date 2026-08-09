# AgentOS Local Governance v0.23.0 — Requirement-Preserving Context Compression

[README landing](README.md) | [Tiếng Việt](README.vi.md)

## Goal

v0.23.0 adds a deterministic **LLM Transport Compiler** derived from the canonical Context Pack. It reduces evidence tokens while preserving user requirements, constraints, authority, safety rules, and approved scope without semantic rewriting.

The Control Plane is **LOSSLESS** and contains the verbatim original request + hash, stable Requirement Ledger, verbatim AGENTS authority, lossless approved scope, active plan + hash, protected policy authority and freshness/integrity hashes. Protected content is never translated, paraphrased, summarized, token-pruned, or word-pruned; budget overflow fails closed.

The Evidence Plane is compressed only by deterministic/extractive codecs: exact deduplication, metadata normalization, structural source projection, requirement-aware ranking, and hash-pinned omission handles. Python uses symbol/dependency windows, JSON uses policy-key projection, and repetitive logs may be aggregated structurally.

Token budget is `context capacity - reserved output - system/tool overhead - safety margin`, with Control Plane allocation first. Exact local tokenizers are preferred when available; `multilingual_heuristic_v1` is the offline fallback.

Read-only MCP tools are `agentos.context_transport_get`, `agentos.context_transport_explain`, `agentos.context_expand`, `agentos.context_requirement_get`, and `agentos.context_token_report`. Compile/evaluation mutation is not exposed over MCP.

Schema **44** adds transport packs, Requirement Ledger rows, expansion observability and evaluation metrics. The initial target is stable **2–4x compression**, not extreme compression.
