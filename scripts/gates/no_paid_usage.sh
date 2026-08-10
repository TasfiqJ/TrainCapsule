#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
SHARED_PYTHON="$(dirname "$COMMON_GIT_DIR")/.venv/bin/python"
if [[ ! -x "$SHARED_PYTHON" ]]; then
  echo "INFRASTRUCTURE_ERROR: missing pinned Python at $SHARED_PYTHON" >&2
  exit 3
fi
exec "$SHARED_PYTHON" "$ROOT/scripts/gates/no_paid_usage.py"
