#!/usr/bin/env bash
# Stops any running Ageix uvicorn daemon and starts a fresh one in the
# background, then polls /health until it responds -- replaces the manual
# "ps aux | grep uvicorn; kill <pid>; restart" sequence documented in
# docs/runbooks/ageix_service_operations.md with a single repeatable command.
#
# Usage: scripts/Ops/restart_ageix.sh [start|stop|restart]
#   (default: restart)
#
# Env vars:
#   AGEIX_HOST      bind host (default: 127.0.0.1)
#   AGEIX_PORT      bind port (default: 8002 -- matches the AGEIX_BASE_URL
#                   default already used by every other scripts/Ops/*.sh
#                   script; the runbook's old "8000" was stale)
#   VENV_PATH       path to the venv's uvicorn binary
#                   (default: <repo_root>/venv/bin/uvicorn)
#   LOG_FILE        where daemon stdout/stderr are appended
#                   (default: /tmp/ageix_uvicorn.log)
#   PID_FILE        where the daemon's PID is recorded
#                   (default: /tmp/ageix_uvicorn.pid)
#   HEALTH_TIMEOUT  seconds to wait for /health to respond after start
#                   (default: 30)
#   STOP_DELAY      seconds to sleep before sending the stop signal
#                   (default: 0). Set this when triggering a restart from
#                   inside the very server process being restarted (e.g. an
#                   MCP capability handler), so the HTTP response has time to
#                   flush back to the caller before the process is killed.
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
AGEIX_HOST="${AGEIX_HOST:-127.0.0.1}"
AGEIX_PORT="${AGEIX_PORT:-8002}"
VENV_PATH="${VENV_PATH:-${REPO_ROOT}/venv/bin/uvicorn}"
LOG_FILE="${LOG_FILE:-/tmp/ageix_uvicorn.log}"
PID_FILE="${PID_FILE:-/tmp/ageix_uvicorn.pid}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-30}"
STOP_DELAY="${STOP_DELAY:-0}"
PROCESS_PATTERN="web.app:create_app"

find_pids() {
  pgrep -f "$PROCESS_PATTERN" || true
}

stop_daemon() {
  local pids
  pids="$(find_pids)"
  if [[ -z "$pids" ]]; then
    echo "No running Ageix daemon found (pattern: ${PROCESS_PATTERN})."
    rm -f "$PID_FILE"
    return 0
  fi

  sleep "$STOP_DELAY"

  echo "Stopping Ageix daemon (pid(s): ${pids})..."
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

  echo "Daemon did not exit after SIGTERM; sending SIGKILL." >&2
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
  rm -f "$PID_FILE"
}

start_daemon() {
  if [[ -n "$(find_pids)" ]]; then
    echo "ERROR: Ageix daemon is already running (pid(s): $(find_pids)). Use 'stop' or 'restart' first." >&2
    exit 1
  fi
  if [[ ! -x "$VENV_PATH" ]]; then
    echo "ERROR: uvicorn not found or not executable at ${VENV_PATH}." >&2
    exit 2
  fi

  echo "Starting Ageix daemon on ${AGEIX_HOST}:${AGEIX_PORT}, logging to ${LOG_FILE}..."
  PYTHONPATH="$REPO_ROOT" nohup "$VENV_PATH" web.app:create_app --factory \
    --host "$AGEIX_HOST" --port "$AGEIX_PORT" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  disown
  echo "$pid" > "$PID_FILE"
  echo "Started (pid: ${pid})."

  echo "Waiting for /health to respond (timeout: ${HEALTH_TIMEOUT}s)..."
  local elapsed=0
  while (( elapsed < HEALTH_TIMEOUT )); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "ERROR: daemon process exited during startup. Check ${LOG_FILE}." >&2
      exit 1
    fi
    if curl -sS -o /dev/null --max-time 2 "http://${AGEIX_HOST}:${AGEIX_PORT}/health"; then
      echo "Healthy."
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo "ERROR: /health did not respond within ${HEALTH_TIMEOUT}s. Check ${LOG_FILE}." >&2
  exit 1
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
