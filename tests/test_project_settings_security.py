from __future__ import annotations

import json
from pathlib import Path


def test_project_settings_protect_controller_credentials() -> None:
    settings = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["forceLoginMethod"] == "claudeai"
    sandbox = settings["sandbox"]
    assert sandbox["enabled"] is True
    assert sandbox["allowUnsandboxedCommands"] is False

    denied_reads = set(sandbox["filesystem"]["denyRead"])
    assert "~/.config/traincapsule" in denied_reads
    assert "~/.local/share/traincapsule-factory/private-gates" in denied_reads
    assert "/mnt/c" in denied_reads

    denied_env = {
        item["name"] for item in sandbox["credentials"]["envVars"] if item.get("mode") == "deny"
    }
    assert "CLAUDE_CODE_OAUTH_TOKEN" in denied_env
    assert "TCF_CLAUDE_OAUTH_TOKEN_FILE" in denied_env
    assert "TCF_PRIVATE_GATE_RUNNER" in denied_env

    matchers = {item["matcher"] for item in settings["hooks"]["PreToolUse"]}
    assert "Read|Grep|Glob|Write|Edit|Bash|WebFetch|WebSearch" in matchers
