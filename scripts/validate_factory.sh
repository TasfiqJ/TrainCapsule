#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
cd "$ROOT"
uv sync --extra dev
test -f uv.lock || { echo "uv sync did not create uv.lock" >&2; exit 1; }
uv run python scripts/verify_yaml_unique.py .
uv run tcfactory schema --output schemas/task.generated.json
uv run python scripts/gates/catalog_consistency.py
uv run python -m pytest
uv run ruff check .
uv run pyright
bash scripts/verify_claude_features.sh
uv run tcfactory doctor
