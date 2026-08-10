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

# The foreground wsl.exe process keeps WSL alive. Restarting after a bounded controller exit
# immediately loads a verified self-repair instead of waiting for the next scheduled heartbeat.
while true; do
  if "$UV" run tcfactory autopilot --repo "$ROOT" \
    >>"$LOG_DIR/autopilot.log" 2>&1; then
    controller_exit=0
  else
    controller_exit=$?
  fi
  if [[ -f "$ROOT/factory/state/STOP" || -f "$ROOT/factory/state/HARD_STUCK.json" ]]; then
    exit "$controller_exit"
  fi
  printf 'Controller exited (%s); restarting in 15 seconds.\n' "$controller_exit" \
    >>"$LOG_DIR/autopilot.log"
  sleep 15
done
