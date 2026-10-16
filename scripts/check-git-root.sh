#!/bin/sh
# Exit 0 only when the current directory's git root is this project.
set -e
script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
workspace=$(CDPATH= cd -- "$script_dir/.." && pwd)
root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ "$root" != "$workspace" ]; then
  echo "Git root is '${root:-unknown}'." >&2
  echo "Run git commands from $workspace." >&2
  exit 1
fi
