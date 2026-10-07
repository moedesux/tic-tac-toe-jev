#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${ROOT}/.backend.pid"
PORT="$(sed -n 's/^PORT *= *//p' "${ROOT}/config/backend.conf" | head -1 | tr -d '"')"
backend_pid() {
  test -f "${PID_FILE}" && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null &&
    [[ "$(ps -o stat= -p "$(cat "${PID_FILE}")")" != Z* ]]
}
port_in_use() { (echo >"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; }
start() {
  if backend_pid; then echo "Backend already running (PID $(cat "${PID_FILE}"))"; return; fi
  rm -f "${PID_FILE}"
  if port_in_use; then
    echo "Port ${PORT} is already in use. Stop its server before starting this backend." >&2
    return 1
  fi
  mkdir -p "${ROOT}/logs"
  nohup uv run --with-requirements "${ROOT}/requirements.txt" uvicorn backend.main:app --host 0.0.0.0 --port "${PORT}" >"${ROOT}/logs/backend.log" 2>&1 &
  echo $! >"${PID_FILE}"
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    if ! backend_pid; then
      rm -f "${PID_FILE}"
      echo "Backend failed to start. See ${ROOT}/logs/backend.log." >&2
      return 1
    fi
    if curl --noproxy '*' --silent --fail --max-time 1 "http://127.0.0.1:${PORT}/api/health" >/dev/null && backend_pid; then
      echo "Backend started on port ${PORT} (PID $(cat "${PID_FILE}"))"
      return
    fi
    sleep 0.1
  done
  echo "Backend failed to start within 30 seconds. See ${ROOT}/logs/backend.log." >&2
  stop
  return 1
}
stop() {
  if backend_pid; then
    kill "$(cat "${PID_FILE}")" || true
    local deadline=$((SECONDS + 30))
    while (( SECONDS < deadline )); do
      if ! backend_pid && ! port_in_use; then rm -f "${PID_FILE}"; return; fi
      sleep 0.1
    done
    echo "Backend did not stop within 30 seconds. Check ${ROOT}/logs/backend.log and port ${PORT}." >&2
    return 1
  fi
  rm -f "${PID_FILE}"
}
status() { backend_pid && echo "Backend: running (PID $(cat "${PID_FILE}"))" || echo "Backend: stopped"; }
case "${1:-start}" in
  start) start;; stop) stop;; restart) stop; start;; status) status;;
  *) echo "Usage: $0 {start|stop|restart|status}" >&2; exit 2;;
esac
