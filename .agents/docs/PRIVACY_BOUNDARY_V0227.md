# Privacy Boundary v0.22.7

Local authority covers AgentOS SQLite-derived identity state, local staging artifacts, file-read cache, project memory/embeddings that reference the erased entity or staging paths, and local code-index rows if they unexpectedly reference those values. `.agents/cache` is privacy-first invalidated because it is rebuildable derived state.

External TARGET data is outside this authority. v0.22.7 records the requirement for external erasure but never synthesizes UPDATE/DELETE/UPSERT/MERGE. SOURCE remains SELECT-only.

Execution is blocked for related active/uncertain identity, extraction, insert, reconciliation, or recovery operations to avoid erasing evidence required to determine commit state.
