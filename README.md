# AgentOS Local Governance

**Current release: v0.23.0 — Requirement-Preserving Context Compression**

[🇻🇳 Tiếng Việt](README.vi.md) | [🇬🇧 English](README.en.md)

v0.23.0 adds a deterministic **LLM Transport Compiler** on top of the canonical Context Pack. The **Control Plane is LOSSLESS**: original user request, Requirement Ledger, AGENTS authority, approved scope, active plan, and protected policy authority are preserved and hash-gated. Only the **Evidence Plane is COMPRESSIBLE**, using deterministic/extractive codecs and read-only expansion handles. Database schema: **44**.

The release does **not** use generative LLM summarization as authority, does not gzip/base64/minify semantic context, does not word-prune protected content, and does not expose transport compilation/mutation over MCP.

## Upgrade
See [UPGRADE_FROM_0.22.7.md](UPGRADE_FROM_0.22.7.md).

## Node documentation
- [Requirement-Preserving Context Compression](.agents/docs/REQUIREMENT_PRESERVING_CONTEXT_COMPRESSION_V0230.md)
- [Vietnamese developer guide](huong_dan.vi.md)
- [English developer guide](huong_dan.en.md)
