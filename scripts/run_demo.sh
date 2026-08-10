#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
cd "$ROOT"
uv run tcfactory validate-task tasks/DEMO-001.yaml
uv run tcfactory run tasks/DEMO-001.yaml --no-merge
uv run tcfactory costs
