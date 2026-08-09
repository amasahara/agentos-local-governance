# Upgrade v0.22.6 → v0.22.7

Use `python3 tools/apply_v0227.py /path/to/project --dry-run`, then apply without `--dry-run`. The upgrader requires exact `VERSION=0.22.6`, backs up changed files, merges privacy policy/capabilities, and preserves all prior governance nodes. Run `data-subject-rights-db-sync`, runtime/docs checks, and tests afterward.
