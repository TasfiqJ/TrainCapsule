#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
uv run python -m tcfactory.supervisor preflight --repo "$ROOT"
uv run tcfactory explain-blocker
uv run tcfactory status || true
