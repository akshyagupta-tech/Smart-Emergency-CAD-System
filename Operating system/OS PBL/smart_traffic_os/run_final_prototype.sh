#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VENV="$ROOT/.venv"
URL="http://localhost:8000"
SERVER_PID=""

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf 'Python 3 is required (missing: %s).\n' "$PYTHON" >&2
  exit 2
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  printf 'Python 3.10 or newer is required.\n' >&2
  exit 2
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  "$PYTHON" -m venv "$VENV"
fi

MISSING_PACKAGES="$("$VENV/bin/python" -c 'import importlib.util; modules = {"fastapi": "fastapi", "uvicorn": "uvicorn", "websockets": "websockets", "numpy": "numpy"}; print(" ".join(package for package, module in modules.items() if importlib.util.find_spec(module) is None))')"
if [[ -n "$MISSING_PACKAGES" ]]; then
  read -r -a MISSING_ARRAY <<< "$MISSING_PACKAGES"
  printf 'Installing missing dependencies: %s\n' "$MISSING_PACKAGES"
  "$VENV/bin/python" -m pip install --disable-pip-version-check "${MISSING_ARRAY[@]}"
else
  printf 'Dependencies already available: fastapi uvicorn websockets numpy\n'
fi

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill -INT "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}

handle_signal() {
  printf '\nStopping Smart Traffic OS gateway...\n'
  trap - INT TERM
  cleanup
  exit 0
}

cd "$ROOT"
"$VENV/bin/python" -m uvicorn server.gateway:app --host 0.0.0.0 --port 8000 &
SERVER_PID=$!
trap cleanup EXIT
trap handle_signal INT TERM

ready=0
for ((attempt = 0; attempt < 30; attempt++)); do
  if curl --fail --silent "$URL/api/health" >/dev/null; then
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
  printf 'Unified gateway did not become ready at %s.\n' "$URL" >&2
  exit 1
fi

if command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || printf 'Could not open browser automatically.\n' >&2
else
  printf 'macOS open command unavailable; visit %s manually.\n' "$URL" >&2
fi

printf 'Smart Traffic OS is running at %s. Press Ctrl+C to stop.\n' "$URL"
wait "$SERVER_PID"