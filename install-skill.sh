#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/skills/groundgate/SKILL.md"

if [[ ! -f "$SKILL_SRC" ]]; then
  echo "Error: $SKILL_SRC not found." >&2
  exit 1
fi

TARGETS=(
  "${HOME}/.agents/skills/groundgate"
  "${HOME}/.gemini/antigravity-cli/skills/groundgate"
  "${HOME}/.claude/skills/groundgate"
)

installed=0
for dir in "${TARGETS[@]}"; do
  parent="$(dirname "$dir")"
  if [[ -d "$(dirname "$parent")" || "$dir" == "${HOME}/.agents/skills/groundgate" ]]; then
    mkdir -p "$dir"
    cp "$SKILL_SRC" "$dir/SKILL.md"
    echo "Installed groundgate skill -> $dir/SKILL.md"
    installed=$((installed + 1))
  fi
done

if [[ "$installed" -eq 0 ]]; then
  mkdir -p "${HOME}/.agents/skills/groundgate"
  cp "$SKILL_SRC" "${HOME}/.agents/skills/groundgate/SKILL.md"
  echo "Installed groundgate skill -> ${HOME}/.agents/skills/groundgate/SKILL.md"
fi
