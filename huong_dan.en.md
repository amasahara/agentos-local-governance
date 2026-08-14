# AgentOS v0.24.2 Developer Guide — DB-Aware Context Projection

## v0.24.2 — DB-Aware Context Projection

1. Project only strongly-signalled schema/mapping/manifest Evidence Plane data.
2. Require deterministic, reversible, source-hash-pinned codecs.
3. Select a projection only when it is smaller than its source representation.
4. Never persist raw schema/mapping/manifest content or projected text.
5. Preserve the original request, Requirement Ledger, `AGENTS.md`, approved scope,
   active plan, and governance authority losslessly.
6. `agentos.context_db_projection_get` opens state through SQLite `mode=ro`; it
   cannot create the database or run migrations.

## v0.24.1 — Risk-Tiered Batch Review

Batch only deterministic LOW mappings into a signed bundle, review MEDIUM/HIGH
individually, resolve BLOCKED mappings, and retain whole-plan approval.

## Release validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

Versioned updater/recovery files are GitHub Release assets rather than clean-main files.
