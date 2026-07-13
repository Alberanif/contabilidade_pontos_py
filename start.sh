#!/usr/bin/env bash
# Starts backend (FastAPI/uvicorn) and frontend (Vite) together.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cleanup() {
  echo "Stopping backend and frontend..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

(
  cd "$ROOT_DIR/backend"
  source "$ROOT_DIR/venv/Scripts/activate"
  python main.py
) &
BACKEND_PID=$!

(
  cd "$ROOT_DIR/frontend"
  npm run dev
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
