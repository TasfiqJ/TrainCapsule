from __future__ import annotations

from pathlib import Path


def test_windows_task_runs_foreground_autopilot() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "register_windows_autostart.ps1").read_text(encoding="utf-8")
    entry = (root / "scripts" / "windows_task_entrypoint.sh").read_text(encoding="utf-8")
    assert "windows_task_entrypoint.sh" in script
    assert "MultipleInstances IgnoreNew" in script
    assert "-Force" not in script
    assert "RepetitionInterval (New-TimeSpan -Minutes 15)" in script
    assert "$Triggers = @($LogonTrigger, $RecoveryTrigger)" in script
    assert "-Trigger $Triggers" in script
    assert "RestartCount 999" not in script
    assert "$RepoPath = $env:TCF_REPO_PATH" in script
    assert "$WslDistribution = $env:TCF_WSL_DISTRIBUTION" in script
    assert '$FactoryRuntimePath = "scripts/windows_task_entrypoint.sh"' in script
    assert "/home/jasim" not in script
    assert "Ubuntu-22.04" not in script
    assert "EncodedCommand" in script
    assert "Start-Process" in script
    assert "-WindowStyle Hidden" in script
    assert "tcfactory v3-controller" in entry
    assert "tcfactory autopilot" not in entry
    assert "load_factory_env.sh" in entry
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in entry
    assert "HARD_STUCK.json" in entry
    assert 'flock -n 9' in entry
    assert "single-instance lock" in entry
    assert "while true" not in entry
    assert "while [[ ! -f" in entry
    assert "tcfactory.supervisor preflight" in entry
    assert "tcfactory.supervisor record-exit" in entry
    assert "source integrity" in entry
    assert "migration marker" in entry


def test_private_github_runner_has_limited_recovery_task() -> None:
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "register_windows_github_runner.ps1").read_text(encoding="utf-8")
    assert "run-traincapsule-runner-foreground.sh" in script
    assert "RunLevel Limited" in script
    assert "MultipleInstances IgnoreNew" in script
    assert "RepetitionInterval (New-TimeSpan -Minutes 15)" in script
    assert "-Force" not in script


def test_legacy_max_token_configuration_is_disabled_and_loader_stays_read_only() -> None:
    root = Path(__file__).resolve().parents[1]
    configure = (root / "scripts" / "configure_max5_token.sh").read_text(encoding="utf-8")
    loader = (root / "scripts" / "load_factory_env.sh").read_text(encoding="utf-8")
    assert "permanently disabled" in configure
    assert "exit 64" in configure
    assert "setup-token" not in configure
    assert "export CLAUDE_CODE_OAUTH_TOKEN=%q" not in configure
    assert "TCF_CLAUDE_OAUTH_TOKEN_FILE" in loader
    assert "export CLAUDE_CODE_OAUTH_TOKEN" in loader


def test_legacy_max_token_setup_cannot_self_assert_usage_credit_state() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "configure_max5_token.sh").read_text(encoding="utf-8")
    assert "permanently disabled" in text
    assert "usage-credits-disabled.ack" not in text
    assert "TCF_USAGE_CREDITS_DISABLED_ACK" not in text
