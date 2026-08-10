#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
./scripts/verify_max_subscription.sh
./scripts/verify_claude_features.sh
uv run tcfactory schema --output schemas/task.generated.json
uv run python -m pytest
uv run ruff check .
uv run pyright
uv run python scripts/verify_yaml_unique.py .
uv run tcfactory doctor
uv run tcfactory verify
printf 'AUTONOMOUS LOOP VERIFIED\n'
