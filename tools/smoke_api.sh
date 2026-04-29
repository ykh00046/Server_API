#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${SMOKE_VENV_DIR:-$ROOT_DIR/.smoke-venv}"
PYTHON_BIN=""

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "error: python3 or python is required" >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

SMOKE_PYTHON="$VENV_DIR/bin/python"

if [[ "${SMOKE_INSTALL:-0}" == "1" ]]; then
  "$SMOKE_PYTHON" -m pip install -r "$ROOT_DIR/requirements-smoke.txt"
fi

"$SMOKE_PYTHON" - <<'PY'
import importlib
import sys

required = [
    "pytest",
    "fastapi",
    "uvicorn",
    "orjson",
    "cachetools",
    "google.genai",
    "dotenv",
    "requests",
    "pydantic",
]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except ModuleNotFoundError:
        missing.append(name)
if missing:
    print("missing dependencies:", ", ".join(missing), file=sys.stderr)
    print("hint: run `SMOKE_INSTALL=1 tools/smoke_api.sh`", file=sys.stderr)
    sys.exit(1)
PY

cd "$ROOT_DIR"

echo "[1/3] pytest"
"$SMOKE_PYTHON" -m pytest tests -q

echo "[2/3] api.main import"
"$SMOKE_PYTHON" -c 'import api.main; print("api.main import ok")'

if [[ "${SMOKE_RUN_HEALTH:-0}" == "1" ]]; then
  PORT="${SMOKE_PORT:-18000}"
  echo "[3/3] /healthz"
  "$SMOKE_PYTHON" -m uvicorn api.main:app --host 127.0.0.1 --port "$PORT" >/tmp/server_api_smoke.log 2>&1 &
  UVICORN_PID=$!
  trap 'kill "$UVICORN_PID" >/dev/null 2>&1 || true' EXIT
  sleep 3
  curl -fsS "http://127.0.0.1:${PORT}/healthz"
  kill "$UVICORN_PID" >/dev/null 2>&1 || true
  trap - EXIT
fi

echo "smoke ok"
