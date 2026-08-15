from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from tcfactory import auth


def _claude_path(_name: str) -> str:
    return "/usr/bin/claude"


def _missing_path(_name: str) -> None:
    return None


def _prepare_subscription_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Production shells may already have the durable lights-out OAuth route loaded.
    # Clear it so subscription-login tests exercise only the state they arrange.
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(tmp_path / "missing-claude-oauth-token"))
    monkeypatch.delenv("TCF_USAGE_CREDITS_DISABLED_ACK", raising=False)
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (config_dir / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(auth.shutil, "which", _claude_path)


def _status_result(payload: dict[str, object], returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def _status_runner(payload: dict[str, object]) -> Callable[..., SimpleNamespace]:
    def run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return _status_result(payload)

    return run


def test_max_oauth_subscription_login_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_subscription_login(tmp_path, monkeypatch)
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        _status_runner({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}),
    )
    assert auth.assert_max_oauth_only() == "subscription_login"


def test_oauth_environment_token_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setattr(auth.shutil, "which", _claude_path)
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        _status_runner(
            {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
        ),
    )
    assert auth.assert_max_oauth_only() == "oauth_env"


@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
    ],
)
def test_non_subscription_routes_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _prepare_subscription_login(tmp_path, monkeypatch)
    monkeypatch.setenv(name, "configured")
    with pytest.raises(RuntimeError, match="non-subscription routing variables"):
        auth.assert_max_oauth_only()


def test_console_auth_method_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_subscription_login(tmp_path, monkeypatch)
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        _status_runner({"loggedIn": True, "authMethod": "console", "apiProvider": "firstParty"}),
    )
    with pytest.raises(RuntimeError, match="authMethod"):
        auth.assert_max_oauth_only()


def test_api_key_helper_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (config_dir / ".credentials.json").write_text("{}", encoding="utf-8")
    (config_dir / "settings.json").write_text(
        json.dumps({"apiKeyHelper": "/tmp/key-helper"}), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    with pytest.raises(RuntimeError, match="apiKeyHelper"):
        auth.assert_max_oauth_only()


def test_missing_claude_executable_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_subscription_login(tmp_path, monkeypatch)
    monkeypatch.setattr(auth.shutil, "which", _missing_path)
    with pytest.raises(RuntimeError, match="cannot be verified"):
        auth.assert_max_oauth_only()


def test_lights_out_requires_setup_token_not_interactive_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare_subscription_login(tmp_path, monkeypatch)
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        _status_runner({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}),
    )
    with pytest.raises(RuntimeError, match="setup-token"):
        auth.assert_max_oauth_only(require_long_lived_token=True)


def test_lights_out_accepts_long_lived_subscription_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("not-a-real-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("TCF_USAGE_CREDITS_DISABLED_ACK", "1")
    monkeypatch.setattr(auth.shutil, "which", _claude_path)
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        _status_runner(
            {"loggedIn": True, "authMethod": "oauth_token", "apiProvider": "firstParty"}
        ),
    )
    assert auth.assert_max_oauth_only(require_long_lived_token=True) == "oauth_env"


def test_token_file_is_reloaded_without_process_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("first-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    assert auth.refresh_subscription_oauth_token() is True
    assert auth.active_subscription_auth_source() == "oauth_env"
    assert auth.os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "first-token"

    token_file.write_text("renewed-token\n", encoding="utf-8")
    assert auth.refresh_subscription_oauth_token() is True
    assert auth.os.environ["CLAUDE_CODE_OAUTH_TOKEN"] == "renewed-token"


def test_sanitized_agent_environment_loads_token_file_and_removes_api_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("subscription-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", "/private/runner")
    monkeypatch.setenv("TCF_ENV_FILE", "/private/env")
    environment = auth.sanitized_agent_environment()
    assert environment["CLAUDE_CODE_OAUTH_TOKEN"] == "subscription-token"
    assert "ANTHROPIC_API_KEY" not in environment
    assert "TCF_PRIVATE_GATE_RUNNER" not in environment
    assert "TCF_CLAUDE_OAUTH_TOKEN_FILE" not in environment
    assert "TCF_ENV_FILE" not in environment


def test_sanitized_agent_environment_keeps_explicit_claude_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("subscription-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    config_dir = tmp_path / "controller-home" / ".claude"
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))

    environment = auth.sanitized_agent_environment(
        {"CLAUDE_CONFIG_DIR": str(config_dir.resolve())}
    )

    assert environment["CLAUDE_CONFIG_DIR"] == str(config_dir.resolve())


def test_lights_out_rejects_world_readable_token_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("not-a-real-token\n", encoding="utf-8")
    token_file.chmod(0o644)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.setattr(auth.shutil, "which", _claude_path)
    with pytest.raises(RuntimeError, match="unsafe permissions"):
        auth.assert_max_oauth_only(require_long_lived_token=True)


def test_lights_out_requires_usage_credit_acknowledgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("not-a-real-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "not-a-real-token")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    monkeypatch.delenv("TCF_USAGE_CREDITS_DISABLED_ACK", raising=False)
    with pytest.raises(RuntimeError, match="usage credits"):
        auth.assert_max_oauth_only(require_long_lived_token=True)


def test_sanitized_agent_environment_strips_controller_ack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "claude-oauth-token"
    token_file.write_text("subscription-token\n", encoding="utf-8")
    token_file.chmod(0o600)
    monkeypatch.setenv("TCF_CLAUDE_OAUTH_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("TCF_USAGE_CREDITS_DISABLED_ACK", "1")
    environment = auth.sanitized_agent_environment()
    assert "TCF_USAGE_CREDITS_DISABLED_ACK" not in environment
