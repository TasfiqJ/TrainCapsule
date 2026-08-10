#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
cd "$ROOT"
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 tasks/TNNN.yaml [--merge|--no-merge]" >&2
  exit 2
fi
TASK=$1
shift
uv run tcfactory validate-task "$TASK"
uv run tcfactory run "$TASK" "$@"
