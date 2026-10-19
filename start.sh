#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PROJECTS="${1:-}"
PORT="${PORT:-8741}"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  python3 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  (cd "$ROOT/frontend" && npm install && npm run build)
fi

if [[ -n "$PROJECTS" ]]; then
  export BRAIN_ROOT="$(cd "$PROJECTS" && pwd)"
else
  export BRAIN_ROOT="$ROOT/demo-projects"
fi

port_busy() {
  "$ROOT/.venv/bin/python" -c 'import socket,sys
s=socket.socket(); s.settimeout(0.3)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()' "$1"
}

if port_busy "$PORT"; then
  echo "Port $PORT is in use. Looking for the next free port."
  start="$PORT"
  PORT=""
  for ((p=start+1; p<start+20; p++)); do
    if ! port_busy "$p"; then
      PORT="$p"
      break
    fi
  done
  if [[ -z "$PORT" ]]; then
    echo "No free port near $start." >&2
    exit 1
  fi
fi

echo ""
echo "AI Brain is mapping $BRAIN_ROOT"
echo "Open http://127.0.0.1:$PORT"
echo "The page comes up while the folder is still being read."
echo ""

exec "$ROOT/.venv/bin/python" -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT"
