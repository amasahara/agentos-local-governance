# DATA_SUBJECT_RIGHTS.md — v0.22.7

## Authority boundary
AgentOS can erase local derived identity state and local artifacts under its authority. It cannot assume authority over an external TARGET database. No TARGET UPDATE/DELETE/UPSERT/MERGE path is introduced.

## Lifecycle
1. Immutable request keyed by canonical `entity_uuid` and request hash.
2. Immutable plan containing affected counts and artifact-path hashes only.
3. Human review.
4. Human approval pinned to the exact `plan_hash`.
5. Local execution after active/in-doubt checks.
6. Canonical tombstone plus deletion of relinkable local bindings/candidates/lineage and related staging/cache/memory/index material.
7. Signed privacy-safe evidence.

## Retention
Retain only request/plan hashes, decisions, timestamps, counts, execution evidence hash, tombstone UUID/marker hash, and the external-erasure-required flag. Do not retain raw identifiers or old HMAC fingerprints merely for convenience. Existing append-only signed audit chains remain intact.

## External TARGET
If prior committed target lineage exists, local execution reports both `local_erasure_completed=true` and `external_target_erasure_required=true`. The external authority must perform and evidence any TARGET-side deletion through its own approved process; AgentOS does not mutate TARGET for privacy recovery.
