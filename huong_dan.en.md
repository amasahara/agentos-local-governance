# AgentOS v0.25.2 Developer Guide

1. Run `architecture-init` to create exactly 27 templates; it performs no source discovery or architecture inference.
2. Complete Markdown and JSON contracts. An `applicable` section needs a non-empty payload and may not retain the default UNRESOLVED marker.
3. Run `architecture-validate`, create a baseline, then have a human review → approve → activate the exact baseline hash.
4. Before `approve-task`, run `clarity-assess`. If assumptions/ambiguities/decisions remain, use `grill-me` and wait for human resolution.
5. During coding, raise `decision-request` for material behavior/architecture/data/API/security/scope choices instead of guessing.
6. While a blocking decision is open, continue only bounded read-only investigation; dependent mutation must stop.
7. A human resolves with `decision-resolve --human-confirmed`. Non-`none` impact revokes task approval and supersedes submitted/active plans.
8. Rebuild the manifest and run release/docs/instruction/regression validation after upgrade.

Database schema: **56**; bootstrap baseline remains **46**.
