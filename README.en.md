# AgentOS Local Governance v0.24.2 — DB-Aware Context Projection

[README landing](README.md) | [Tiếng Việt](README.vi.md)

**Current release: v0.24.2 — DB-Aware Context Projection**  
Database schema: **49**.

## v0.24.2 — DB-Aware Context Projection

v0.24.2 adds deterministic reversible structural codecs for DB schema,
field-mapping, and manifest evidence. A projection is selected only when its
serialized representation is smaller, and decoding must reproduce the same
canonical JSON structure.

The Context Control Plane remains fully lossless: original request, Requirement
Ledger, `AGENTS.md` authority, approved scope, active plan, and governance
authority are never projected.

Schema 49 stores only hashes, codec metadata, and byte/token counters for
DB-aware projection telemetry; raw projected DB content is not persisted.

## v0.24.1 — Risk-Tiered Batch Review

LOW mappings may be reviewed in a signed exact-plan-hash bundle. MEDIUM/HIGH
remain individual human review, BLOCKED mappings cannot be reviewed, and the
existing whole-plan approval gate remains mandatory.

## Strict read-only MCP state access

`agentos.context_db_projection_get` reads projection telemetry through SQLite
`mode=ro`; it cannot create the AgentOS state database or run schema migrations.

## Release validation

```bash
python tools/build_manifest.py .
python tools/verify_manifest.py .
python tools/validate_release.py .
PYTHONPATH=.agents python -m pytest -q .agents/tests -rs
```

## Upgrade

See [Upgrade v0.24.1 → v0.24.2](UPGRADE_FROM_0.24.1.md). Versioned updaters are
GitHub Release assets and are intentionally absent from clean `main`.

## Documentation

- [DB-Aware Context Projection](.agents/docs/DB_AWARE_CONTEXT_PROJECTION_V0242.md)
- [Risk-Tiered Batch Review](.agents/docs/RISK_TIERED_BATCH_REVIEW_V0241.md)
- [Repository Release Policy](.agents/docs/REPOSITORY_RELEASE_POLICY.md)
