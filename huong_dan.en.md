# AgentOS v0.25.0 Developer Guide — Schema Bootstrap Baseline

- Fresh DB: materialize schema 46, verify its fingerprint, then run 47→49.
- Existing DB: migrate incrementally from its recorded version.
- Fresh startup never invokes migration functions 1→46.
- Unversioned non-empty state fails closed.
- Current schema remains 49.
- SOURCE/TARGET authority, approvals, privacy, audit and MCP mutation are unchanged.

Release validation:

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```
