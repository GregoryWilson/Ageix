#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" ]]; then
  echo "Usage: scripts/validate_clean_archive.sh <archive.zip>" >&2
  exit 2
fi
if [[ ! -f "$ARCHIVE" ]]; then
  echo "ERROR: archive not found: $ARCHIVE" >&2
  exit 2
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo "ERROR: unzip command is required." >&2
  exit 1
fi

LISTING="$(mktemp)"
trap 'rm -f "$LISTING"' EXIT
unzip -Z1 "$ARCHIVE" > "$LISTING"

fail_if_matches() {
  local pattern="$1"
  local label="$2"
  if grep -Eq "$pattern" "$LISTING"; then
    echo "ERROR: clean archive contains $label:" >&2
    grep -E "$pattern" "$LISTING" >&2
    exit 1
  fi
}

fail_if_matches '(^|/)\.git(/|$)' '.git content'
fail_if_matches '(^|/)(venv|\.venv|env)(/|$)' 'virtual environment content'
fail_if_matches '(^|/)__pycache__(/|$)|\.pyc$' 'Python cache content'
fail_if_matches '(^|/)\.pytest_cache(/|$)|(^|/)\.mypy_cache(/|$)|(^|/)\.ruff_cache(/|$)' 'tool cache content'
fail_if_matches '(^|/)\.env($|\.)' '.env files'
fail_if_matches '(^|/)\.ageix/(runtime|instance|manifests|certs)(/|$)' 'Ageix runtime state'
fail_if_matches '(^|/)\.ageix/config/auth\.json$' 'local auth config'
fail_if_matches '(^|/)(logs|logFiles|scratch|artifacts)(/|$)' 'runtime/log/scratch/artifact directories'
fail_if_matches '\.(log|tmp|patch|zip|pem|key|crt|csr|p12|pfx)$' 'generated, archive, or secret-like files'
fail_if_matches '(^|/)\.idea(/|$)|(^|/)\.vscode(/|$)' 'IDE files'

echo "Clean archive validation PASS: $ARCHIVE"
