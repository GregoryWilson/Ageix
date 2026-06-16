#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/apply_patch_and_commit.sh [patch-file] [commit-message]

If either argument is omitted, the script prompts for it.
The script stops on the first error.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

patch_file="${1:-}"
commit_message="${2:-}"

if [[ -z "$patch_file" ]]; then
  read -r -p "Patch file: " patch_file
fi

if [[ -z "$commit_message" ]]; then
  read -r -p "Commit message: " commit_message
fi

if [[ -z "$patch_file" ]]; then
  echo "ERROR: Patch file is required." >&2
  exit 1
fi

if [[ -z "$commit_message" ]]; then
  echo "ERROR: Commit message is required." >&2
  exit 1
fi

if [[ ! -f "$patch_file" ]]; then
  echo "ERROR: Patch file not found: $patch_file" >&2
  exit 1
fi

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ERROR: This script must be run inside a Git repository." >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

UNTRACKED=$(git status --porcelain | grep '^??' || true)

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "ERROR: Modified tracked files detected."
    git status --short
    exit 1
fi

if [ -n "$UNTRACKED" ]; then
    echo "WARNING: Untracked files present:"
    echo "$UNTRACKED"
fi

echo "Checking patch..."
git apply --check "$patch_file"

echo "Applying patch..."
git apply "$patch_file"

echo "Running tests..."
PYTHONPATH=. python -m pytest

echo "Staging changes..."
git add -A

echo "Committing changes..."
git commit -m "$commit_message"

git status
PYTHONPATH=. python -m pytest
rm -rf ../ageix_repo.zip
git archive --format=zip --prefix=ageix/ --output ../ageix_repo.zip HEAD

echo "Done."
git status --short

