#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
uv run tcfactory recover
uv run tcfactory resume
printf 'Resume requested. The registered Windows task/systemd service will continue the queue.\n'
uv run tcfactory autonomy-status
