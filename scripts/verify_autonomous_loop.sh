#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
uv run tcfactory config validate
uv run tcfactory product doctor
uv run tcfactory verify
printf 'V3 AUTONOMOUS LOOP PREFLIGHT VERIFIED\n'
