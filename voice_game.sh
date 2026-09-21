#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${ROOT}/.backend.pid"
PORT="$(sed -n 's/^PORT *= *//p' "${ROOT}/config/backend.conf" | head -1 | tr -d '"')"
backend_pid() { test -f "${PID_FILE}" && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; }
start() {
  if backend_pid; then echo "Backend already running (PID $(cat "${PID_FILE}"))"; return; fi
  mkdir -p "${ROOT}/logs"
  nohup uv run --with-requirements "${ROOT}/requirements.txt" uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" >"${ROOT}/logs/backend.log" 2>&1 &
  echo $! >"${PID_FILE}"
  echo "Backend started on port ${PORT} (PID $!)"
}
stop() { if backend_pid; then kill "$(cat "${PID_FILE}")" || true; fi; rm -f "${PID_FILE}"; }
status() { backend_pid && echo "Backend: running (PID $(cat "${PID_FILE}"))" || echo "Backend: stopped"; }
case "${1:-start}" in
  start) start;; stop) stop;; restart) stop; start;; status) status;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2;;
esac
