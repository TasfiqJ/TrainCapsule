#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/factory/logs/autopilot.log"
mkdir -p "$(dirname "$LOG")"
touch "$LOG"
printf 'Following %s. Press Ctrl+C to stop viewing; the factory keeps running.\n' "$LOG"
tail -n "${1:-100}" -f "$LOG"
