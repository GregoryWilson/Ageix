#!/usr/bin/env bash
set -euo pipefail

OUT="ageix_local_inventory_$(date +%Y%m%d_%H%M%S).txt"

{
  echo "=== repo ==="
  pwd
  git remote -v
  git branch --show-current
  git rev-parse HEAD

  echo
  echo "=== git status ==="
  git status --short --ignored

  echo
  echo "=== all files under .ageix ==="
  find .ageix -print | sort

  echo
  echo "=== tracked files under .ageix ==="
  git ls-files .ageix | sort

  echo
  echo "=== ignored files under .ageix ==="
  git ls-files --others --ignored --exclude-standard .ageix | sort

  echo
  echo "=== untracked but not ignored under .ageix ==="
  git ls-files --others --exclude-standard .ageix | sort

  echo
  echo "=== .gitignore ==="
  cat .gitignore
} > "$OUT"

echo "Wrote $OUT"
