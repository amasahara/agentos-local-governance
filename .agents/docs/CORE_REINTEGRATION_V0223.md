# Core Reintegration v0.22.3

Trust roots:

1. Historical core persistence/migrations 1–31 are restored from the v0.19.5 lineage preceding the v0.22.2 update.
2. Current GitHub v0.22.2 migrations 32–40 remain additive.
3. Core and extension governance policies are merged instead of replacing one another.
4. Historical and extension tests are both mandatory.

This node intentionally stops before v0.22.4, where database-domain mutations will be correlated to task/session capability operations and signed audit.
