#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v zip >/dev/null 2>&1; then
  echo "ERROR: zip command is required." >&2
  exit 1
fi

LABEL="${1:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo clean)}"
STAMP="$(date +"%Y%m%d_%H%M%S")"
ARTIFACT_DIR="$ROOT/artifacts"
OUTFILE="$ARTIFACT_DIR/ageix_repo_${LABEL}_${STAMP}.zip"

mkdir -p "$ARTIFACT_DIR"

echo "Building clean Ageix archive:"
echo "  $OUTFILE"

zip -rq "$OUTFILE" . \
  -x ".git/*" \
  -x "venv/*" \
  -x ".venv/*" \
  -x "env/*" \
  -x ".env" \
  -x ".env.*" \
  -x "*/.env" \
  -x "*/.env.*" \
  -x "__pycache__/*" \
  -x "*/__pycache__/*" \
  -x "*/*.pyc" \
  -x "*.pyc" \
  -x ".pytest_cache/*" \
  -x ".mypy_cache/*" \
  -x ".ruff_cache/*" \
  -x ".coverage" \
  -x "htmlcov/*" \
  -x ".ageix/runtime/*" \
  -x ".ageix/instance/*" \
  -x ".ageix/manifests/*" \
  -x ".ageix/config/auth.json" \
  -x ".ageix/verification/*" \
  -x "*/scratch/*" \
  -x "*/artifacts/*" \
  -x ".ageix/certs/*" \
  -x "certs/*" \
  -x "secrets/*" \
  -x "logs/*" \
  -x "logFiles/*" \
  -x "scratch/*" \
  -x "artifacts/*" \
  -x "*.log" \
  -x "*.tmp" \
  -x "*.patch" \
  -x "*.zip" \
  -x "*.pem" \
  -x "*.key" \
  -x "*.crt" \
  -x "*.csr" \
  -x "*.p12" \
  -x "*.pfx" \
  -x ".idea/*" \
  -x ".vscode/*"

"$ROOT/scripts/validate_clean_archive.sh" "$OUTFILE"

echo "Archive created:"
echo "  $OUTFILE"
