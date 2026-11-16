#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
URL="http://localhost:8000"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf 'Python 3.11+ is required (missing: %s).\n' "$PYTHON" >&2
  exit 2
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  printf 'Python 3.11 or newer is required.\n' >&2
  exit 2
fi

open_browser() {
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
}

VENV="$ROOT/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"
cd "$ROOT"

"$VENV/bin/uvicorn" server.app:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  wait "$SERVER_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

ready=0
for ((attempt = 0; attempt < 30; attempt++)); do
  if curl --fail --silent "$URL/health" >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID"
    exit 1
  fi
  sleep 1
done

if [[ "$ready" != 1 ]]; then
  printf 'Server did not become ready at %s.\n' "$URL" >&2
  exit 1
fi

open_browser
printf 'Dashboard: %s\n' "$URL"
wait "$SERVER_PID"