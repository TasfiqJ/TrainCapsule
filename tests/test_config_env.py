from pathlib import Path

import pytest

from tcfactory.config import load_factory_config


def _write_config(path: Path) -> None:
    path.write_text(
        """version: 1
repo_root: .
task_dir: tasks
artifact_dir: factory/artifacts
worktree_dir: factory/worktrees
ledger_path: factory/state/ledger.json
queue_dir: factory/queue
worker_poll_seconds: 30
roles_path: config/roles.yaml
global_prompt: prompts/global.md
monthly_budget_usd: 500.0
require_clean_main: true
sandbox_enabled: true
project_settings_only: true
strict_mcp: true
max_parallel: 1
private_gate_runner_env: TCF_PRIVATE_GATE_RUNNER
""",
        encoding="utf-8",
    )


def test_monthly_estimate_cap_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "factory.yaml"
    _write_config(config_path)
    monkeypatch.setenv("TCF_MONTHLY_ESTIMATED_USD_CAP", "123.45")
    config = load_factory_config(config_path)
    assert config.monthly_budget_usd == 123.45


def test_legacy_monthly_budget_alias_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "factory.yaml"
    _write_config(config_path)
    monkeypatch.setenv("TCF_MONTHLY_BUDGET_USD", "98.76")
    config = load_factory_config(config_path)
    assert config.monthly_budget_usd == 98.76


def test_invalid_monthly_budget_env_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "factory.yaml"
    _write_config(config_path)
    monkeypatch.setenv("TCF_MONTHLY_ESTIMATED_USD_CAP", "not-a-number")
    with pytest.raises(ValueError, match="positive number"):
        load_factory_config(config_path)


def test_parallel_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "factory.yaml"
    _write_config(config_path)
    monkeypatch.setenv("TCF_MAX_PARALLEL", "2")
    config = load_factory_config(config_path)
    assert config.max_parallel == 2
