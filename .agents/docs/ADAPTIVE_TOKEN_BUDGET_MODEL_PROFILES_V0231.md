# v0.23.1 — Adaptive Token Budget & Model Profiles

## Contract

v0.23.1 changes budget planning only. The v0.23.0 preservation contract remains authoritative: original user request, Requirement Ledger, AGENTS authority, approved scope, active plan and protected policy authority are lossless and cannot be token-pruned.

## Model profile

A profile is normalized data with a canonical SHA-256 hash. It defines context capacity, tokenizer policy, output-reserve bounds, system/tool overhead, safety-margin floor/ratio and minimum evidence target. No profile may load Python code, call a provider API, perform network discovery or auto-download a tokenizer. Optional `tiktoken` resolution is local-cache-only; a cache miss falls back to the multilingual heuristic unless exact-tokenizer policy explicitly requires failure.

The profile hash is stored in every v0.23.1 transport pack and in an immutable `context_model_profile_snapshots` record.

## Adaptive algorithm

`adaptive_budget_v1` derives a deterministic pressure score from protected Requirement Ledger categories and active-plan step count. Output reserve is bounded by the profile min/default/max. Input under-estimation p95 may add safety headroom; observed output p95 may increase output reserve. Calibration never reduces safety/output floors.

The decisive order is:

```text
1. resolve + hash-pin model profile
2. resolve tokenizer
3. count Control Plane
4. calculate output / overhead / safety reservations
5. input budget = capacity - reservations
6. fail closed if Control Plane does not fit
7. allocate remaining input budget to Evidence Plane
8. run v0.23.0 preservation/integrity gates
```

`minimum_evidence_tokens` is an observability target, not permission to cut the Control Plane. If the evidence floor is not met, the pack records that fact and relies on omission/expansion handles.

## Calibration

`context_token_observations` stores only numeric counts, hashes, profile identity, tokenizer identity and a bounded source enum. It has no prompt/response/raw-content columns. The allowed sources are `runtime_report`, `provider_usage`, `tokenizer_probe`, `operator_verified`, `benchmark`, and `local_runtime`. A transport pack may contribute at most one observation per source; an identical replay is idempotent and a conflicting replay fails closed.

Calibration is monotonic-safety: it can increase `safety_margin` or `reserved_output`; it cannot reduce Control Plane preservation, reduce configured safety floors, or authorize word-level deletion.

## Fixed compatibility mode

`fixed` mode preserves the v0.23.0 formula and explicit reservation overrides. This gives operators a deterministic compatibility path while adaptive mode becomes the v0.23.1 default.

## MCP authority

Read-only only:

- `agentos.context_model_profiles_get`
- `agentos.context_budget_history_get`
- `agentos.context_token_calibration_get`

Not exposed: token-observation recording, profile mutation, budget mutation, transport compilation/evaluation mutation, model/provider switching.

## Schema 45

Adds `context_model_profile_snapshots`, `context_budget_decisions`, `context_token_observations`, plus `model_profile_hash`, `budget_mode`, and `budget_decision_id` on `context_transport_packs`.
