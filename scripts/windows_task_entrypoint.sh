#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/factory/logs"
mkdir -p "$LOG_DIR"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
export TCF_LIGHTS_OUT=1
cd "$ROOT"
UV="$(command -v uv || true)"
if [[ -z "$UV" ]]; then
  printf 'uv was not found in PATH. Expected ~/.local/bin/uv.\n' >&2
  exit 21
fi

# The foreground wsl.exe process keeps WSL alive. The controller owns the single-instance
# lock, durable checkpoints, quota sleeps, fresh Claude sessions, and crash recovery.
exec "$UV" run tcfactory autopilot --repo "$ROOT" \
  >>"$LOG_DIR/autopilot.log" 2>&1
