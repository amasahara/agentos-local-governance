# AgentOS Local Governance v0.23.1 — Adaptive Token Budget & Model Profiles

[README landing](README.md) | [Tiếng Việt](README.vi.md)

v0.23.1 extends v0.23.0 with a deterministic local **Model Profile Registry** and **Adaptive Token Budget** while keeping the lossless Control Plane unchanged.

A model profile is a data-only, SHA-256-pinned budget contract containing context capacity, tokenizer policy, output reservation bounds, system/tool overhead, safety floors, and a minimum evidence target. AgentOS performs no provider/network model discovery, dynamic profile code loading, or tokenizer auto-download, and it does not gain authority to switch providers or models.

Adaptive mode computes:

```text
input_budget = context_capacity
             - reserved_output
             - system_tool_overhead
             - safety_margin

evidence_budget = max(0, input_budget - control_tokens)
```

Requirement/plan complexity may increase the output reserve. Numeric runtime token observations may increase future output reserve or safety headroom. Calibration can never reduce the profile safety floor or weaken the lossless Control Plane. Fixed mode remains available for v0.23.0-compatible budgeting behavior.

Schema **45** adds immutable profile snapshots, budget decisions, numeric token observations, and profile/budget provenance columns on transport packs. No prompt, response, evidence, credential, or raw source content is stored in the calibration table.

New read-only MCP tools are `agentos.context_model_profiles_get`, `agentos.context_budget_history_get`, and `agentos.context_token_calibration_get`. Observation recording, profile mutation, budget mutation, compilation, evaluation mutation, and model switching are not exposed over MCP.

## Calibration/tokenizer hardening

Exact `tiktoken` assets are local-cache-only; cache misses never trigger downloads. Observation sources are allowlisted identifiers and one transport/source pair is write-once (identical replay is idempotent).
