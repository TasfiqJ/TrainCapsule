#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${TCF_RUNTIME_ROOT:-$ROOT/factory/state}"
LOG_DIR="$ROOT/factory/logs"
mkdir -p "$STATE_DIR" "$LOG_DIR"

# One launcher owns supervision. The controller retains its separate autopilot lock.
exec 9>"$STATE_DIR/supervisor.lock"
if ! flock -n 9; then
  printf 'Another V3 supervisor owns the single-instance lock; launcher exiting.\n' \
    >>"$LOG_DIR/autopilot.log"
  exit 0
fi

# A scheduled recovery heartbeat must respect durable operator controls without loading secrets.
if [[ -f "$STATE_DIR/STOP" || -f "$STATE_DIR/PAUSE" ]]; then
  printf 'Durable STOP/PAUSE is present; launcher remains stopped.\n' >>"$LOG_DIR/autopilot.log"
  exit 0
fi
if [[ -f "$STATE_DIR/HARD_STUCK.json" ]]; then
  printf 'HARD_STUCK is present; explicit recovery is required.\n' >>"$LOG_DIR/autopilot.log"
  exit 70
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
export TCF_LIGHTS_OUT=1
cd "$ROOT"
UV="$(command -v uv || true)"
if [[ -z "$UV" ]]; then
  printf 'uv was not found in PATH. Expected the configured factory runtime.\n' >&2
  exit 21
fi

# This checks V3 config, source integrity, credentials, the migration marker, and clean runtime
# state. Its output contains only backend-neutral credential state and commit/digest metadata.
"$UV" run python -m tcfactory.supervisor preflight --repo "$ROOT" \
  >>"$LOG_DIR/autopilot.log" 2>&1

while [[ ! -f "$STATE_DIR/STOP" && ! -f "$STATE_DIR/PAUSE" ]]; do
  "$UV" run python -m tcfactory.supervisor start --repo "$ROOT" \
    >>"$LOG_DIR/autopilot.log" 2>&1
  started_epoch="$(date +%s)"
  if "$UV" run tcfactory v3-controller --repo "$ROOT" \
    >>"$LOG_DIR/autopilot.log" 2>&1; then
    controller_exit=0
  else
    controller_exit=$?
  fi
  runtime_seconds="$(( $(date +%s) - started_epoch ))"

  if [[ -f "$STATE_DIR/STOP" || -f "$STATE_DIR/PAUSE" ]]; then
    printf 'Controller exited (%s) after durable STOP/PAUSE; no restart.\n' "$controller_exit" \
      >>"$LOG_DIR/autopilot.log"
    exit "$controller_exit"
  fi

  read -r decision delay < <(
    "$UV" run python -m tcfactory.supervisor record-exit \
      --repo "$ROOT" \
      --runtime-seconds "$runtime_seconds" \
      --exit-code "$controller_exit"
  )
  if [[ "$decision" == "HARD_STUCK" ]]; then
    printf 'Controller restart budget exhausted; HARD_STUCK written.\n' \
      >>"$LOG_DIR/autopilot.log"
    exit 70
  fi
  printf 'Controller exited (%s); bounded restart in %s seconds.\n' \
    "$controller_exit" "$delay" >>"$LOG_DIR/autopilot.log"
  sleep "$delay"
done

exit 0
