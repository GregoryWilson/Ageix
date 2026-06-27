#!/usr/bin/env bash
# Audits every local branch after a git history rewrite (e.g. the secret-scrub
# force-push to main/sprint-19.0/sprint-20.0/claude/local-repo-access-7mjf0h).
# For each local branch reports:
#   - in sync         local SHA matches its origin upstream
#   - ahead/behind     tracks origin but has diverged (stale pre-rewrite history)
#   - local-only       no upstream configured
# and, if a secret value is supplied, flags whether that string is still
# reachable anywhere in the branch's history (via pickaxe search).
#
# Usage: scripts/Ops/audit_local_branches.sh [secret-value-to-search-for]
#   e.g. scripts/Ops/audit_local_branches.sh "$OLD_DEV_TOKEN_VALUE"
#
# Run with no argument to skip the secret check and just see sync status.
set -euo pipefail

SECRET="${1:-}"

echo "Fetching origin..."
git fetch origin --quiet

printf "%-40s %-22s %-10s\n" "BRANCH" "STATUS" "SECRET?"
printf "%-40s %-22s %-10s\n" "------" "------" "-------"

while IFS= read -r branch; do
  upstream="$(git rev-parse --abbrev-ref --symbolic-full-name "${branch}@{upstream}" 2>/dev/null || true)"

  if [[ -n "$upstream" ]]; then
    local_sha="$(git rev-parse "$branch")"
    upstream_sha="$(git rev-parse "$upstream" 2>/dev/null || echo "")"
    if [[ "$local_sha" == "$upstream_sha" ]]; then
      status="in sync"
    else
      counts="$(git rev-list --left-right --count "${branch}...${upstream}" 2>/dev/null || echo "? ?")"
      ahead="$(awk '{print $1}' <<<"$counts")"
      behind="$(awk '{print $2}' <<<"$counts")"
      status="ahead ${ahead} behind ${behind}"
    fi
  else
    status="local-only"
  fi

  secret_flag="-"
  if [[ -n "$SECRET" ]]; then
    if git log --oneline -S"$SECRET" "$branch" 2>/dev/null | grep -q .; then
      secret_flag="FOUND"
    else
      secret_flag="clean"
    fi
  fi

  printf "%-40s %-22s %-10s\n" "$branch" "$status" "$secret_flag"
done < <(git branch --format='%(refname:short)')

echo
echo "ahead/behind on a branch that should be in sync with origin means it's still on"
echo "pre-rewrite history:"
echo "  git fetch origin && git reset --hard origin/<branch>"
echo
echo "SECRET=FOUND means the old value is still reachable in that branch's local history:"
echo "  - tracks origin:  git fetch origin && git reset --hard origin/<branch>"
echo "  - local-only, disposable:  git branch -D <branch>"
echo "  - local-only, has unique work you need: rebase its unique commits onto the"
echo "    cleaned origin branch, e.g. git rebase --onto origin/main <old-base> <branch>"
