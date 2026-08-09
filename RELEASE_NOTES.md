# AgentOS Local Governance v0.23.1 — Release Notes

## Adaptive Token Budget & Model Profiles

v0.23.1 builds directly on v0.23.0 Requirement-Preserving Context Compression. It does not loosen the preservation gate or evidence codec policy. It adds deterministic, auditable budget adaptation around them.

### Model profile registry

- Data-only profiles with canonical SHA-256 pinning.
- Context capacity, tokenizer policy, output bounds, overhead, safety floor/ratio and evidence floor.
- No provider API/network discovery.
- No dynamic module/function profile loading.
- No tokenizer auto-download.
- No AgentOS authority to switch provider/model.

### Adaptive budgeting

- New algorithm: `adaptive_budget_v1`.
- Requirement Ledger + active plan produce a deterministic complexity/pressure signal.
- Output reserve stays within profile bounds unless the operator supplies an explicit compatibility override.
- Safety margin is never below the profile floor and may grow using p95 local under-estimation evidence.
- Control Plane always receives budget before Evidence Plane.
- Protected overflow remains fail-closed.
- `fixed` mode keeps the v0.23.0 budgeting path available.

### Numeric calibration

- Runtime may record predicted/observed input token counts and optional observed output token counts.
- Calibration table stores numeric/hash metadata only.
- No prompt/response/evidence/raw source/credential content is persisted.
- Calibration may only increase future protective reservations; it cannot lower safety floors.

### Schema 45

Adds:

- `context_model_profile_snapshots`;
- `context_budget_decisions`;
- `context_token_observations`;
- model-profile/budget provenance columns on `context_transport_packs`.

Migration remains centralized through `agentos.db.connect()` and `foreign_keys=ON`.

### CLI/MCP

CLI adds profile inspection, budget history, calibration inspection and numeric observation recording. `context-transport-compile` adds `--budget-mode adaptive|fixed`.

MCP adds only three read-only tools: profile inspection, budget history and calibration statistics. Observation/profile/budget mutations and model switching are not exposed.

### Compatibility and safety

SOURCE remains SELECT-only. TARGET safety remains Controlled Target Insert only. v0.22.6 secret/lineage and v0.22.7 privacy boundaries remain unchanged. v0.23.0 request/instruction/scope/plan preservation remains 100% and fail-closed.

## Additional hardening

- Optional exact `tiktoken` tokenization is local-cache-only; AgentOS never fetches tokenizer assets over the network.
- Token-observation source metadata is an allowlisted enum, not arbitrary text. A transport/source pair is write-once; identical replay is idempotent and conflicting replay fails closed.
