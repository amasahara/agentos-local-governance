# AgentOS Local Governance

**Current release: v0.23.1 — Adaptive Token Budget & Model Profiles**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.23.1 extends the v0.23.0 Requirement-Preserving Context Compression pipeline with a deterministic, local-only **Model Profile Registry** and **Adaptive Token Budget**. The release keeps the v0.23.0 Control Plane fully lossless and changes only how the safe input budget is reserved and allocated.

Key guarantees:

- model profiles are data-only, hash-pinned, and never discovered from provider/network APIs; exact tokenizer assets are local-cache-only;
- adaptive calibration stores numeric token counts/hashes plus bounded identifiers only, never prompt/response content;
- calibration may increase output reserve or safety headroom, but cannot reduce Control Plane protection;
- AgentOS does not gain authority to switch provider/model; a profile is only a budget contract;
- fixed budgeting remains available for v0.23.0-compatible operator behavior;
- MCP adds read-only profile/budget/calibration inspection only;
- database schema: **45**.

## Upgrade

See [UPGRADE_FROM_0.23.0.md](UPGRADE_FROM_0.23.0.md).

## Node documentation

- [Adaptive Token Budget & Model Profiles](.agents/docs/ADAPTIVE_TOKEN_BUDGET_MODEL_PROFILES_V0231.md)
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)
- [Vietnamese developer guide](huong_dan.vi.md)
- [English developer guide](huong_dan.en.md)
