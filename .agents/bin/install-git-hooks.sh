#!/usr/bin/env sh
set -eu
ROOT=${1:-$(pwd)}
[ -d "$ROOT/.git" ] || { echo "No .git directory found." >&2; exit 2; }
mkdir -p "$ROOT/.git/hooks"
cp "$ROOT/.agents/bin/hooks/pre-commit" "$ROOT/.git/hooks/pre-commit"
chmod +x "$ROOT/.git/hooks/pre-commit"
echo "AgentOS pre-commit hook installed."
