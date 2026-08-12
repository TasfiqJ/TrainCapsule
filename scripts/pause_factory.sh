#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
export TCF_REQUIRE_MODEL_CREDENTIALS=0
source "$ROOT/scripts/load_factory_env.sh"
uv run tcfactory pause
printf 'Pause requested. The active bounded stage may finish before the controller becomes idle.\n'
uv run tcfactory status
