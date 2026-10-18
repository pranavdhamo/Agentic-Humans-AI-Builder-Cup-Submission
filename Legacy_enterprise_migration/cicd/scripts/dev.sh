#!/usr/bin/env bash
# One command local bootup: API on :8000, UI on :5173.   cicd/scripts/dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

[ -d "$ROOT/server/.venv" ] || { python3 -m venv "$ROOT/server/.venv"; "$ROOT/server/.venv/bin/pip" install -q -r "$ROOT/server/requirements.txt"; }
[ -d "$ROOT/client/node_modules" ] || (cd "$ROOT/client" && npm install --no-audit --no-fund)
[ -f "$ROOT/migrated/carddemo-batch/target/carddemo-batch-0.1.0.jar" ] || mvn -B -q -DskipTests -f "$ROOT/migrated/carddemo-batch/pom.xml" package

trap 'kill 0' EXIT
(cd "$ROOT/server" && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/client" && npm run dev) &
wait
