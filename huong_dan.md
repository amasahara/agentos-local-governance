# AgentOS Developer Guide

[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

Current version: **0.25.1**. Database schema: **49**.

For every release build, update authoritative current-release documents and
runtime metadata first, then run `python tools/build_manifest.py .`. The builder
synchronizes `PACKAGE_COMPLETENESS.json` before calculating package hashes.
Finally run `python tools/validate_release.py .`; `release_metadata_coherence`
must pass together with manifest, docs, instruction, migration and release
integrity checks.

Do not commit generated `VALIDATION_REPORT*.json` to clean `main`. v0.25.1 does
not change the v0.25.0 schema-46 bootstrap path, SOURCE/TARGET authority, privacy,
signed-audit, Context Control Plane, or MCP mutation boundary.
