# v0.22.1 — Identity Resolution, Deduplication & Lineage

## Boundary

Identity resolution runs locally over validated v0.21.2 staging. It does not query SOURCE with write access and does not expose record values through MCP. Controlled TARGET INSERT remains the only database write path.

## Decision model

1. Human-approved TARGET business key → keyed exact fingerprint.
2. Existing exact fingerprint → same canonical entity.
3. No exact match + strong fields → keyed strong fingerprint.
4. Strong fingerprint hit → privacy-safe candidate, mandatory human decision.
5. No candidate / rejected candidate → new canonical entity.

An LLM may explain or rank evidence outside the mutation boundary, but `llm_may_decide_identity=false` is enforced by not exposing candidate mutation through MCP.

## Privacy

Identity values remain in local staging only. AgentOS state stores HMAC-SHA256 pseudonymous tokens and hashes. The HMAC key is local-only and Git-ignored.

## Dedup semantics

- Intra-batch: only one record per canonical entity enters deduplicated staging.
- Cross-batch: if an entity already has committed TARGET lineage, no new INSERT row is produced.
- Provenance is preserved for every SOURCE binding, including duplicates that do not trigger a new INSERT.

## Lineage chain

`source_record_token → canonical_entity_uuid → target_record_token → insert_run/receipt`

Each lineage row also pins SOURCE snapshot, SOURCE locator hash, mapping-set hash, TARGET contract hash, and commit receipt hash.
