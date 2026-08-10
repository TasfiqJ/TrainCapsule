#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
SHARED_VENV="$(dirname "$COMMON_GIT_DIR")/.venv"
for executable in ruff pyright python; do
  if [[ ! -x "$SHARED_VENV/bin/$executable" ]]; then
    echo "INFRASTRUCTURE_ERROR: missing pinned $SHARED_VENV/bin/$executable" >&2
    exit 3
  fi
done

UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" && -x "$HOME/.local/bin/uv" ]]; then
  UV_BIN="$HOME/.local/bin/uv"
fi
if [[ -z "$UV_BIN" ]]; then
  echo "INFRASTRUCTURE_ERROR: uv executable is unavailable" >&2
  exit 3
fi

export VIRTUAL_ENV="$SHARED_VENV"
export UV_OFFLINE=1
"$UV_BIN" run --active --no-sync ruff check .
"$UV_BIN" run --active --no-sync pyright
"$UV_BIN" run --active --no-sync python -m pytest -q

run_root_script_if_present() {
  local script=$1
  if [[ -f package.json ]] && command -v pnpm >/dev/null 2>&1 \
    && jq -e --arg script "$script" '.scripts[$script] != null' package.json >/dev/null; then
    pnpm run "$script"
  fi
}

run_root_script_if_present lint
run_root_script_if_present test
