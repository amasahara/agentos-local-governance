# AgentOS v0.25.1 Developer Guide — Release Metadata Coherence

1. Treat `VERSION` as the single release-version source of truth.
2. Synchronize current-release docs, `agentos.__version__`, MCP runtime, and governance version.
3. Run `python tools/build_manifest.py .`; the builder synchronizes `PACKAGE_COMPLETENESS.json` before hashing.
4. Run `python tools/verify_manifest.py .`.
5. Run `python tools/validate_release.py .` and require `release_metadata_coherence` to pass.
6. Run documentation, instruction, and regression tests before release.

Database schema remains **49** and v0.25.1 has no migration. Do not commit
`VALIDATION_REPORT*.json` to clean `main`. The v0.25.0 bootstrap path and all
SOURCE/TARGET, privacy, signed-audit, context, and MCP authority boundaries remain unchanged.
