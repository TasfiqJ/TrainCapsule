#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
WEB_DIR="apps/web"
PACKAGE="$WEB_DIR/package.json"

if [[ ! -f "$PACKAGE" ]]; then
  echo 'apps/web/package.json is missing; UI E2E cannot be claimed.' >&2
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo 'pnpm is required for UI E2E.' >&2
  exit 1
fi

run_required() {
  local script=$1
  if ! jq -e --arg script "$script" '.scripts[$script] != null' "$PACKAGE" >/dev/null; then
    echo "apps/web must define a $script script before UI completion can pass." >&2
    exit 1
  fi
  pnpm --dir "$WEB_DIR" run "$script"
}

run_optional() {
  local script=$1
  if jq -e --arg script "$script" '.scripts[$script] != null' "$PACKAGE" >/dev/null; then
    pnpm --dir "$WEB_DIR" run "$script"
  fi
}

run_optional lint
run_optional test
run_required build
run_required test:e2e
