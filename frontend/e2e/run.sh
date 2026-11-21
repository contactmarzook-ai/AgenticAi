#!/usr/bin/env bash
# Browser tests: starts the mock LLM, the API (fresh SQLite per spec) and the Vite dev server,
# runs every *.cjs spec in order, and stops everything afterwards.
#   bash frontend/e2e/run.sh            # all specs
#   bash frontend/e2e/run.sh 03         # specs whose name starts with 03
# Requires: backend deps installed (pip), frontend deps installed (npm ci), Playwright Chromium.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${E2E_OUT:-$HERE/results}"
WORK="$(mktemp -d)"
mkdir -p "$OUT"
PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done; rm -rf "$WORK"; }
trap cleanup EXIT

wait_for() { for _ in $(seq 1 60); do curl -fs -o /dev/null "$1" && return 0; sleep 1; done; echo "timeout waiting for $1"; return 1; }

cd "$ROOT/backend"
python -m uvicorn dev.mock_llm:app --port 9999 > "$OUT/mock.log" 2>&1 & PIDS+=($!)
cd "$ROOT/frontend"
npx vite --port 5173 --strictPort > "$OUT/vite.log" 2>&1 & PIDS+=($!)
wait_for http://localhost:9999/v1/models || exit 1
wait_for http://localhost:5173/ || exit 1

start_api() {
  cd "$ROOT/backend"
  DATABASE_URL="sqlite:///$WORK/e2e-$1.db" BOOTSTRAP_ADMIN_EMAIL=admin@example.com BOOTSTRAP_ADMIN_PASSWORD='Admin#Passw0rd!' \
  LLM_BASE_URL=http://localhost:9999/v1 LLM_DEFAULT_MODEL=mock-model CREDENTIALS_KEY=e2e-test-key-0123456789abcdef0123456789 \
  USER_RUNS_PER_MINUTE=500 python -m uvicorn app.main:app --port 8000 > "$OUT/api-$1.log" 2>&1 &
  API_PID=$!
  wait_for http://localhost:8000/healthz
}

FAILED=0
for spec in "$HERE"/${1:-}*.cjs; do
  name="$(basename "$spec" .cjs)"
  start_api "$name" || { FAILED=1; break; }
  echo "== $name"
  if ! (cd "$HERE" && node "$spec" "$OUT"); then FAILED=1; echo "FAILED: $name"; fi
  kill "$API_PID" 2>/dev/null; wait "$API_PID" 2>/dev/null
done
exit $FAILED
