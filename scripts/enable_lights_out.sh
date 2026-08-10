#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISTRIBUTION="${TCF_WSL_DISTRIBUTION:-Ubuntu}"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
cd "$ROOT"

if [[ ! -f factory/state/CALIBRATION_PASSED ]]; then
  echo 'Refused: factory/state/CALIBRATION_PASSED is missing.' >&2
  echo 'Complete the harmless and deliberate-negative calibration before lights-out mode.' >&2
  exit 2
fi
if [[ -z "${TCF_PRIVATE_GATE_RUNNER:-}" || ! -x "$TCF_PRIVATE_GATE_RUNNER" ]]; then
  echo 'Refused: the external private gate is not configured and executable.' >&2
  exit 2
fi

uv run tcfactory doctor
uv run tcfactory autonomy-enable --acknowledge

PS_SCRIPT="$(wslpath -w "$ROOT/scripts/register_windows_autostart.ps1")"
powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File "$PS_SCRIPT" \
  -Distribution "$DISTRIBUTION" \
  -LinuxRepoPath "$ROOT" \
  -StartNow

echo 'Lights-out TrainCapsule product construction has started.'
echo "Status: cd '$ROOT' && source scripts/load_factory_env.sh && uv run tcfactory autonomy-status"
echo "Logs:   tail -f '$ROOT/factory/logs/autopilot.log'"
