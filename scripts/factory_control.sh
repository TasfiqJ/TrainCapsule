#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
ACTION="${1:-overview}"
shift || true

case "$ACTION" in
  overview|status)
    bash scripts/factory_status.sh "${1:-40}"
    ;;
  start)
    mkdir -p factory/logs factory/state
    if [[ -f factory/state/autopilot.pid ]] && kill -0 "$(cat factory/state/autopilot.pid)" 2>/dev/null; then
      echo "Autopilot is already running with PID $(cat factory/state/autopilot.pid)."
      exit 0
    fi
    if [[ -f factory/state/STOP || -f factory/state/HARD_STUCK.json ]]; then
      echo "Startup refused: use explicit recovery and resume before start." >&2
      exit 2
    fi
    uv run python -m tcfactory.supervisor preflight --repo "$ROOT"
    nohup bash scripts/windows_task_entrypoint.sh >> factory/logs/autopilot.log 2>&1 &
    echo $! > factory/state/autopilot.pid
    sleep 2
    if ! kill -0 "$!" 2>/dev/null; then
      rm -f factory/state/autopilot.pid
      echo "V3 controller failed during startup; inspect the bounded log." >&2
      exit 70
    fi
    echo "V3 controller started and remained healthy through startup observation."
    ;;
  pause)
    bash scripts/pause_factory.sh
    ;;
  resume)
    bash scripts/resume_factory.sh
    ;;
  stop)
    bash scripts/stop_factory.sh
    ;;
  verify)
    bash scripts/verify_autonomous_loop.sh
    ;;
  recover)
    bash scripts/recover_factory.sh
    ;;
  logs)
    bash scripts/tail_factory_logs.sh "${1:-100}"
    ;;
  queue)
    uv run tcfactory queue-status "$@"
    ;;
  costs)
    uv run tcfactory costs "$@"
    ;;
  roadmap)
    uv run tcfactory roadmap "$@"
    ;;
  schedule-dry-run|schedule)
    uv run tcfactory v3-schedule --dry-run --explain "$@"
    ;;
  milestone-status|milestones)
    uv run tcfactory milestones "$@"
    ;;
  lanes)
    uv run tcfactory lanes "$@"
    ;;
  commercial)
    uv run tcfactory commercial-state "$@"
    ;;
  competitors)
    uv run tcfactory competitors status "$@"
    ;;
  pilot)
    uv run tcfactory pilot status "$@"
    ;;
  approvals)
    uv run tcfactory approvals list "$@"
    ;;
  kill-gates)
    uv run tcfactory kill-gates "$@"
    ;;
  doctor)
    uv run tcfactory product doctor "$@"
    ;;
  migration)
    uv run tcfactory migrate --dry-run "$@"
    ;;
  candidate-salvage)
    uv run tcfactory candidate-salvage "$@"
    ;;
  value)
    [[ $# -ge 1 ]] || { echo "usage: $0 value tasks/TASK.yaml" >&2; exit 2; }
    uv run tcfactory value-status "$@"
    ;;
  peers)
    uv run tcfactory peer-status "$@"
    ;;
  blocker)
    uv run tcfactory explain-blocker "$@"
    ;;
  features)
    uv run tcfactory features "$@"
    ;;
  github)
    uv run tcfactory github-status "$@"
    ;;
  sync)
    uv run tcfactory github-sync "$@"
    ;;
  *)
    cat >&2 <<'USAGE'
usage: scripts/factory_control.sh <action> [args]
actions: overview start pause resume stop verify recover logs queue costs roadmap schedule-dry-run milestone-status lanes commercial competitors pilot approvals kill-gates doctor migration candidate-salvage value peers blocker features github sync
USAGE
    exit 2
    ;;
esac
