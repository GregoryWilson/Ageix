#!/usr/bin/env bash
# Stops any running Ageix MCP server (legacy_mcp/server.py) and starts a fresh one
# in the background -- mirrors restart_ageix.sh, but for the separate MCP
# process that Claude.ai/Claude Code connect to. Restarting the main web
# daemon (restart_ageix.sh, or the ops.restart_daemon capability) does NOT
# restart this process; new tools added to legacy_mcp/server.py only become visible
# to MCP clients after this script (or an equivalent manual restart) runs.
#
# Usage: scripts/Ops/restart_ageix_mcp.sh [start|stop|restart]
#   (default: restart)
#
# Env vars:
#   MCP_TRANSPORT   "sse" or "stdio" (default: sse -- what claude.ai/remote
#                   clients use; stdio is for a locally-spawned Claude Code
#                   session and doesn't make sense to background)
#   MCP_PORT        bind port for sse transport (default: 8001, matching
#                   legacy_mcp/server.py's FastMCP(..., port=8001))
#   PYTHON_BIN      python interpreter to run legacy_mcp/server.py with
#                   (default: <repo_root>/venv/bin/python3)
#   LOG_FILE        where stdout/stderr are appended
#                   (default: /tmp/ageix_mcp.log)
#   PID_FILE        where the process's PID is recorded
#                   (default: /tmp/ageix_mcp.pid)
#   STARTUP_TIMEOUT seconds to wait and confirm the process is still alive
#                   after start (default: 5)
set -euo pipefail

ACTION="${1:-restart}"
case "$ACTION" in
  start|stop|restart) ;;
  *)
    echo "Usage: $0 [start|stop|restart]" >&2
    exit 2
    ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_TRANSPORT="${MCP_TRANSPORT:-sse}"
MCP_PORT="${MCP_PORT:-8001}"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  : # explicit override wins
elif [[ -x "${REPO_ROOT}/venv/bin/python3" ]]; then
  PYTHON_BIN="${REPO_ROOT}/venv/bin/python3"
else
  PYTHON_BIN="${REPO_ROOT}/venv/bin/python"
fi
LOG_FILE="${LOG_FILE:-/tmp/ageix_mcp.log}"
PID_FILE="${PID_FILE:-/tmp/ageix_mcp.pid}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-5}"
# Matches only the SSE instance (what claude.ai/this remote session connect
# to). legacy_mcp/server.py can also be spawned locally with --transport stdio (or
# no flag) by a Claude Code CLI session running directly on this box -- that
# process must never be touched by this script.
PROCESS_PATTERN="legacy_mcp/server.py.*--transport sse"

find_pids() {
  pgrep -f "$PROCESS_PATTERN" || true
}

stop_daemon() {
  local pids
  pids="$(find_pids)"
  if [[ -z "$pids" ]]; then
    echo "No running Ageix MCP server found (pattern: ${PROCESS_PATTERN})."
    rm -f "$PID_FILE"
    return 0
  fi

  echo "Stopping Ageix MCP server (pid(s): ${pids})..."
  # shellcheck disable=SC2086
  kill $pids

  for _ in $(seq 1 20); do
    if [[ -z "$(find_pids)" ]]; then
      rm -f "$PID_FILE"
      echo "Stopped."
      return 0
    fi
    sleep 0.5
  done

  echo "Process did not exit after SIGTERM; sending SIGKILL." >&2
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
  rm -f "$PID_FILE"
}

start_daemon() {
  if [[ -n "$(find_pids)" ]]; then
    echo "ERROR: Ageix MCP server is already running (pid(s): $(find_pids)). Use 'stop' or 'restart' first." >&2
    exit 1
  fi
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "ERROR: python not found or not executable at ${PYTHON_BIN}." >&2
    exit 2
  fi

  local transport_args=("--transport" "$MCP_TRANSPORT")
  echo "Starting Ageix MCP server (transport: ${MCP_TRANSPORT}), logging to ${LOG_FILE}..."
  AGEIX_BASE_URL="${AGEIX_BASE_URL:-http://127.0.0.1:8002}" PYTHONPATH="$REPO_ROOT" nohup "$PYTHON_BIN" \
    "${REPO_ROOT}/legacy_mcp/server.py" "${transport_args[@]}" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  disown
  echo "$pid" > "$PID_FILE"
  echo "Started (pid: ${pid})."

  sleep "$STARTUP_TIMEOUT"
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: process exited during startup. Check ${LOG_FILE}." >&2
    exit 1
  fi
  echo "Still running after ${STARTUP_TIMEOUT}s."
}

case "$ACTION" in
  stop)
    stop_daemon
    ;;
  start)
    start_daemon
    ;;
  restart)
    stop_daemon
    start_daemon
    ;;
esac
