#!/usr/bin/env bash
set -euo pipefail

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }

uv sync --extra dev
uv run python -c 'import claude_agent_sdk; print("claude-agent-sdk import passed")'
uv run tcfactory schema --output schemas/task.generated.json
uv run python -m pytest
uv run ruff check .
uv run pyright
uv run tcfactory doctor

echo "Bootstrap checks passed. Commit the generated uv.lock and clean repository before running agents."
