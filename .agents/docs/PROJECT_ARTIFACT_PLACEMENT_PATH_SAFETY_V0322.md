# AgentOS Local Governance v0.32.2 — Project Artifact Placement & Path Safety

Database schema: **65**

## Purpose

This patch corrects CREATE placement when the caller supplies an explicit,
valid project-relative path.

## Placement contract

An explicit project-relative target is preserved.

A basename-only target continues to use the configured `source_root`.

Placement resolution does not grant write authority. The resolved target must
still satisfy the existing approved-scope and write authorization gates.

Absolute paths, drive-qualified paths and parent traversal remain rejected.

## Regression coverage

The release tests cover:

- explicit project-owned targets outside `src/`;
- explicit `src/` targets;
- targets outside approved scope;
- traversal and Windows absolute paths;
- protected AgentOS paths;
- approved directory scope;
- configurable `source_root`;
- the exact hospital Baseline review-artifact destination.

## Compatibility

Schema remains **65**.

No database migration is introduced.

The separate authority model for AgentOS internal state, runtime, cache and
index writes is unchanged.
