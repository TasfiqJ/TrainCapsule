#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
required="2.1.224"
command -v claude >/dev/null 2>&1 || { echo 'Claude Code is not installed.' >&2; exit 1; }
current="$(claude --version 2>&1 | head -1)"
python3 - "$current" "$required" <<'PY'
import re, sys

def parse(raw: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not match:
        raise SystemExit(f"Cannot parse Claude Code version from: {raw}")
    return tuple(map(int, match.groups()))

current, required = parse(sys.argv[1]), parse(sys.argv[2])
if current < required:
    raise SystemExit(f"Claude Code {sys.argv[1]} is too old; require >= {sys.argv[2]}")
print(f"Claude Code feature floor passed: {current} >= {required}")
PY
python3 - <<'PY'
import json
from pathlib import Path
import yaml

features = yaml.safe_load(Path('config/claude_features.yaml').read_text())
settings = json.loads(Path('.claude/settings.json').read_text())
assert features['cross_session_messaging']['enabled'] is True
assert features['cross_session_messaging']['same_machine_only'] is True
assert features['cross_session_messaging']['isolate_peer_machines'] is True
assert features['goal']['enabled'] is True
assert features['advisor']['enabled'] is True
assert features['agent_teams']['enabled'] is True
assert features['memory']['auto_memory_enabled'] is True
assert features['dynamic_workflows']['enabled'] is False
assert settings['sandbox']['enabled'] is False
assert settings['sandbox']['allowUnsandboxedCommands'] is True
assert settings['isolatePeerMachines'] is True
assert settings['autoMemoryEnabled'] is True
assert settings['forceLoginMethod'] == 'claudeai'
print('Claude-native policy passed: renewable production agents, memory, messaging, hooks, and isolation configured.')
PY
printf 'A live cross-session handshake is verified later by scripts/run_one_time_calibration.sh.\n'
