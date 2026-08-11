#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_factory_env.sh"
printf '\n== V3 runtime status ==\n'
uv run tcfactory status
printf '\n== TrainCapsule factory health ==\n'
uv run tcfactory verify || true
printf '\n== Roadmap ==\n'
uv run tcfactory roadmap
printf '\n== Queue ==\n'
uv run tcfactory queue-status
printf '\n== GitHub ==\n'
uv run tcfactory github-status || true
printf '\n== Claude-native peers ==\n'
uv run tcfactory peer-status
printf '\n== Recent controller events ==\n'
uv run tcfactory logs --limit "${1:-40}"
