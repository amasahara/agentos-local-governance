# Upgrade v0.24.1 → v0.24.2

Use the same one-command updater on Windows, Linux, and macOS:

```bash
python tools/apply_v0242.py .
```

The updater requires a coherent **v0.24.1 / schema 48** baseline and converges to **v0.24.2 / schema 49**.

It performs:

```text
verify v0.24.1/schema 48
→ backup
→ install reversible DB-aware schema/mapping/manifest codecs
→ schema 48 → 49
→ integrate codecs into Context Transport Evidence Plane
→ add hash/count-only projection telemetry
→ register read-only CLI/MCP inspection
→ update governance/docs/release integrity
→ compile
→ migrate
→ run v0.24.2 + context historical regression tests
→ run full repository regression
→ rebuild MANIFEST/checksums
→ release-integrity
→ validate v0.24.2
```

Dry run:

```bash
python tools/apply_v0242.py . --dry-run
```

The Control Plane remains lossless and is never passed through DB-aware codecs.

## Windows test-fixture isolation

Upgrade backups are runtime/recovery artifacts and are stored outside the repository
by default under `.agentos-upgrade-backups/<project-name>/` beside the project.
Set `AGENTOS_UPGRADE_BACKUP_HOME` to select another machine-local backup root.

Full-repository pytest fixtures that clone the project exclude `.agents/runtime`.
