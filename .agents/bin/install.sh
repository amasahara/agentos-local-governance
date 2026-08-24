#!/usr/bin/env sh
# File: .agents/bin/install.sh
# Purpose: Compatibility entry point for explicit AgentOS project bootstrap modes.
# Responsibilities:
# - Dispatch project-init and project-adopt to the current AgentOS runtime.
# - Require an explicit target project and preserve its existing root files.
# - Avoid recursive distribution copying and legacy installer semantics.

set -eu

usage() {
    printf '%s\n' 'Usage:'
    printf '%s\n' '  install.sh project-init <project-root> [additional options]'
    printf '%s\n' '  install.sh project-adopt <project-root> [--apply --human-confirmed]'
}

if [ "$#" -lt 2 ]; then
    usage >&2
    exit 2
fi

mode=$1
project_root=$2
shift 2

case "$mode" in
    project-init|project-adopt)
        ;;
    *)
        printf 'Unsupported mode: %s\n' "$mode" >&2
        usage >&2
        exit 2
        ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
distribution_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)

exec "$script_dir/agentos" \
    --root "$distribution_root" \
    "$mode" \
    --distribution-root "$distribution_root" \
    --project-root "$project_root" \
    "$@"