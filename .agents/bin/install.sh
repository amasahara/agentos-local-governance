#!/usr/bin/env sh
set -eu
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
TARGET_DIR=${1:-$(pwd)}
SOURCE_ROOT=${SOURCE_ROOT:-src}
mkdir -p "$TARGET_DIR/.agents"
cp -R "$SOURCE_DIR/.agents/." "$TARGET_DIR/.agents/"
for f in AGENTS.md README.md huong_dan.md VERSION; do
  if [ ! -e "$TARGET_DIR/$f" ]; then
    cp "$SOURCE_DIR/$f" "$TARGET_DIR/$f"
  else
    base=${f%.*}; ext=${f##*.}
    [ "$base" = "$f" ] && out="$TARGET_DIR/${f}.agentos" || out="$TARGET_DIR/${base}.agentos.${ext}"
    cp "$SOURCE_DIR/$f" "$out"
    printf '%s\n' "Preserved existing $f; AgentOS copy written to ${out#$TARGET_DIR/}."
  fi
done
chmod +x "$TARGET_DIR/.agents/bin/agentos" "$TARGET_DIR/.agents/bin/agentos-mcp" "$TARGET_DIR/.agents/bin/install-git-hooks.sh" 2>/dev/null || true
if [ "$SOURCE_ROOT" != "src" ]; then
  printf '{\n  "source_root": "%s"\n}\n' "$SOURCE_ROOT" > "$TARGET_DIR/.agents/config/governance.local.json"
fi
(cd "$TARGET_DIR" && \
  .agents/bin/agentos instruction-check && \
  .agents/bin/agentos docs-check && \
  .agents/bin/agentos db-status)
printf '%s\n' "Installation validated. Governance baseline is pending human review."
printf '%s\n' "Review governance files, then run: .agents/bin/agentos ack-baseline --identity YOUR_NAME"
