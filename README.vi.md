# AgentOS Local Governance v0.23.0 — Requirement-Preserving Context Compression

[README landing](README.md) | [English](README.en.md)

## Mục tiêu

v0.23.0 bổ sung **LLM Transport Compiler** dẫn xuất từ canonical Context Pack để giảm token truyền cho LLM nhưng tuyệt đối không làm mất hoặc đổi nghĩa yêu cầu, constraint, authority, safety rule và approved scope.

Pipeline:

```text
Canonical Context Pack
        ↓
Requirement Ledger + protected authority lock
        ↓
Control Plane — LOSSLESS
        +
Evidence Plane — deterministic/extractive COMPRESSIBLE
        ↓
Requirement Preservation Gate
        ↓
READY Transport Pack
        ↓
LLM
```

## Control Plane

Control Plane giữ nguyên 100%:

- original user request **verbatim** + SHA-256;
- Requirement Ledger ID ổn định cho objective/constraint/prohibition/deliverable/acceptance criterion;
- `AGENTS.md` verbatim + hash;
- approved scope lossless + hash;
- active plan JSON + `plan_hash`;
- deterministic policy authority projection + source/projection hash;
- source freshness và canonical context revision.

Không dịch, paraphrase, summarize, token-prune hoặc word-level delete protected content. Nếu Control Plane lớn hơn model input budget thì compiler **fail-closed** thay vì cắt.

## Evidence Plane

Compression ladder cố định:

1. exact deduplication;
2. metadata normalization;
3. structural projection;
4. requirement-aware ranking;
5. omission handles;
6. fail-closed.

Codec cấu trúc gồm Python symbol/dependency windows, JSON policy-key projection, log repeat aggregation và exact excerpt fallback. Evidence bị bỏ khỏi transport luôn có expansion handle hash-pinned.

## Token budget

```text
input_budget = model_context_capacity
             - reserved_output
             - system_tool_overhead
             - safety_margin
```

Control Plane được cấp ngân sách trước Evidence Plane. Tokenizer abstraction ưu tiên tokenizer chính xác cục bộ nếu có; nếu không có thì dùng `multilingual_heuristic_v1`.

## MCP read-only

```text
agentos.context_transport_get
agentos.context_transport_explain
agentos.context_expand
agentos.context_requirement_get
agentos.context_token_report
```

Không expose compile/evaluate/mutation authority cho LLM.

## Schema 44

Bổ sung `context_transport_packs`, `context_requirement_ledger`, `context_expansion_events`, `context_transport_evaluations`. Migration vẫn đi qua `agentos.db.connect()` và `PRAGMA foreign_keys=ON`.

## Evaluation

Metrics: `raw_tokens`, `transport_tokens`, `compression_ratio`, `protected_requirement_count`, `preserved_requirement_count`, `requirement_preservation_rate`, `context_miss_count`, `expansion_request_count`, `task_success_rate`, `test_pass_rate`, `rework_count`, `tool_call_count`. Mục tiêu ban đầu ưu tiên **2–4x compression ổn định** hơn compression cực đoan.
