# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.25.2**. Database schema: **50**.

Before approving work, create a structured clarity assessment. Any material
assumption or unresolved decision must be surfaced through `grill-me` and resolved
by a human. Architecture files are working-copy material only; use the explicit
baseline review/approve/activate lifecycle to establish authority.

After upgrade, rebuild the manifest, run release validation, and run the full test
suite. Fresh state continues to bootstrap schema 46 and apply migrations 47→50.
