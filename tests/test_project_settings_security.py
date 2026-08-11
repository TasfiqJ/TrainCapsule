from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


def test_project_settings_protect_controller_credentials() -> None:
    settings = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["forceLoginMethod"] == "claudeai"
    sandbox = settings["sandbox"]
    # Mutating roles retain the whole authorized repository while the OS boundary keeps
    # private gates, credentials, Windows, and unrelated host paths unreachable.
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


@pytest.mark.parametrize("name", ["session_audit.py", "stop_failure_checkpoint.py"])
def test_hooks_run_with_wsl_system_python(tmp_path: Path, name: str) -> None:
    output = tmp_path / f"{name}.jsonl"
    environment = {
        **os.environ,
        "TCF_SESSION_AUDIT_PATH": str(output),
        "TCF_STOP_FAILURE_PATH": str(output),
    }

    completed = subprocess.run(
        ["/usr/bin/python3", f".claude/hooks/{name}"],
        input=json.dumps({"hook_event_name": "compatibility-test"}),
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["event"] == "compatibility-test"
