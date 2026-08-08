# Upgrade from v0.22.2 to v0.22.3

The upgrader targets the GitHub v0.22.2 layout and fails closed when the expected baseline signatures differ. It backs up modified files under `.agents/runtime/upgrade-backups/` before mutation.

```bash
python3 tools/apply_v0223.py /path/to/agentos-v0.22.2 --dry-run
python3 tools/apply_v0223.py /path/to/agentos-v0.22.2
```

Then run the gates documented in `USAGE_V0223.md`.
