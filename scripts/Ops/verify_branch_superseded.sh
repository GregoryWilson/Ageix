#!/usr/bin/env bash
# Checks whether a local branch's commits are already captured in origin/main,
# robust to a history rewrite (e.g. git filter-repo) that gave every commit a
# new hash. Hash-based checks (merge-base --is-ancestor, tree equality) both
# break after a rewrite -- ancestor checks fail for everything past the
# rewrite point even when content is unchanged, and tree-equality is too
# strict since main keeps moving forward. This compares commits by patch
# content (git patch-id), which survives the rehash as long as the diff text
# itself didn't change.
#
# Usage: scripts/Ops/verify_branch_superseded.sh <branch> [<branch> ...]
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 <branch> [<branch> ...]" >&2
  exit 2
fi

echo "Fetching origin..." >&2
git fetch origin --quiet

MAIN_IDS="$(mktemp)"
trap 'rm -f "$MAIN_IDS"' EXIT
git log origin/main -p | git patch-id --stable | awk '{print $1}' | sort -u > "$MAIN_IDS"

for b in "$@"; do
  total=0
  missing=0
  missing_commits=()
  while read -r pid commit_hash; do
    [[ -z "$pid" ]] && continue
    total=$((total + 1))
    if ! grep -qx "$pid" "$MAIN_IDS"; then
      missing=$((missing + 1))
      missing_commits+=("$commit_hash")
    fi
  done < <(git log "$b" -p | git patch-id --stable)

  echo "== $b: $missing/$total commits not found by content in origin/main =="
  if [[ $missing -gt 0 ]]; then
    for c in "${missing_commits[@]}"; do
      printf "    %s  %s\n" "$c" "$(git log -1 --format='%s' "$c" 2>/dev/null || echo '?')"
    done
  fi
done
