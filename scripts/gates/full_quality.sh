#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

bash scripts/gates/secret_scan.sh
uv run ruff check .
uv run pyright
uv run python -m pytest -q

run_root_script_if_present() {
  local script=$1
  if [[ -f package.json ]] && command -v pnpm >/dev/null 2>&1 \
    && jq -e --arg script "$script" '.scripts[$script] != null' package.json >/dev/null; then
    pnpm run "$script"
  fi
}

run_root_script_if_present lint
run_root_script_if_present test
run_root_script_if_present build
