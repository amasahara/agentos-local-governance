# AgentOS Local Governance v0.20.1 — Release Notes

## Primary Project Selection & Domain Compatibility

This release adds the decision layer required before governed project consolidation.

### Added

- Read-only candidate project snapshots using v0.20.0 identity/purpose metadata.
- Compatibility states: `compatible`, `conditionally_compatible`, `incompatible`.
- Non-overridable business-domain mismatch gate.
- Human confirmation for same-domain/different-purpose pairs.
- Advisory primary-project ranking based on business role/capability breadth.
- Human-only primary selection, committed only from the selected primary root.
- Schema 33 selection/provenance tables.
- Read-only MCP selection intelligence.
- Split Vietnamese/English GitHub documentation retained.

### Security and governance properties

- External candidate scans do not initialize identity, update registries, or write candidate databases.
- Technical similarity cannot override a business-domain mismatch.
- MCP cannot confirm compatibility or select a Primary Project.
- Physical code consolidation remains disabled until v0.20.2.

### Database migration

`32 → 33`, additive only.

### Tests

The release test suite covers exact compatibility, domain mismatch, conditional purpose confirmation, candidate source immutability, duplicate project UUID rejection, advisory-only recommendations, active-root Primary enforcement, selection persistence, migration tables, and MCP mutation absence.
