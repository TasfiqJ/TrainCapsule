from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tcfactory.github_sync import (
    GitHubConfig,
    GitHubSyncError,
    GitHubSyncState,
    push_main_with_retry,
    record_verified_task,
    should_push,
    wait_for_remote_ci,
)
from tcfactory.models import RiskTier


def test_periodic_push_threshold() -> None:
    config = GitHubConfig(enabled=True, push_after_verified_tasks=3)
    state = GitHubSyncState(tasks_since_push=3)
    assert should_push(
        config=config,
        state=state,
        task=None,
        force=False,
        now=datetime.now(UTC),
    )


def test_interval_push() -> None:
    config = GitHubConfig(enabled=True, push_interval_seconds=60)
    state = GitHubSyncState(
        tasks_since_push=1,
        pending=True,
        last_push_at=datetime.now(UTC) - timedelta(seconds=61),
    )
    assert should_push(
        config=config,
        state=state,
        task=None,
        force=False,
        now=datetime.now(UTC),
    )


def test_record_verified_task_persists_risk(tmp_path: Path) -> None:
    from tcfactory.models import RoleName, SecurityPolicy, Stage, TaskPacket

    task = TaskPacket(
        task_id="T900",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["x"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["x"])],
        risk_tier=RiskTier.INTEGRATION,
    )
    state = record_verified_task(tmp_path / "state.json", task=task)
    assert state.tasks_since_push == 1
    assert state.last_task_risk == RiskTier.INTEGRATION
    assert state.pending


@pytest.mark.parametrize(
    ("field", "value"),
    [("branch", "feature"), ("remote", "upstream")],
)
def test_github_config_rejects_any_non_main_push_target(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        GitHubConfig.model_validate({field: value})


def test_push_helper_rejects_non_main_refspec_before_running_git(tmp_path: Path) -> None:
    with pytest.raises(GitHubSyncError, match="restricted to origin"):
        push_main_with_retry(tmp_path, GitHubConfig(), "feature:feature")


def test_push_helper_executes_only_the_full_main_refspec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("tcfactory.github_sync.run_command", fake_run)

    push_main_with_retry(
        tmp_path,
        GitHubConfig(),
        "refs/heads/main:refs/heads/main",
    )

    assert commands == [
        [
            "git",
            "push",
            "--porcelain",
            "origin",
            "refs/heads/main:refs/heads/main",
        ]
    ]


def test_remote_ci_uses_only_newest_main_push_for_exact_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    runs: list[dict[str, Any]] = [
        {
            "databaseId": 10,
            "status": "completed",
            "conclusion": "failure",
            "workflowName": "AI factory quality",
            "headSha": sha,
            "headBranch": "main",
            "event": "push",
            "createdAt": "2026-08-11T10:00:00Z",
            "url": "https://example.test/old",
        },
        {
            "databaseId": 11,
            "status": "completed",
            "conclusion": "success",
            "workflowName": "AI factory quality",
            "headSha": sha,
            "headBranch": "main",
            "event": "push",
            "createdAt": "2026-08-11T10:01:00Z",
            "url": "https://example.test/new",
        },
        {
            "databaseId": 12,
            "status": "completed",
            "conclusion": "success",
            "workflowName": "AI factory quality",
            "headSha": sha,
            "headBranch": "feature",
            "event": "pull_request",
            "createdAt": "2026-08-11T10:02:00Z",
            "url": "https://example.test/pr",
        },
    ]
    def fake_runs(_repo_root: Path, _sha: str) -> list[dict[str, Any]]:
        return runs

    monkeypatch.setattr("tcfactory.github_sync._workflow_runs", fake_runs)

    result = wait_for_remote_ci(
        tmp_path,
        GitHubConfig(enabled=True),
        sha,
        not_before=datetime(2026, 8, 11, 10, 0, 30, tzinfo=UTC),
    )

    assert result["status"] == "pass"
    assert [run["databaseId"] for run in result["runs"]] == [11]


def test_remote_ci_rejects_latest_failed_push_even_if_old_run_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "b" * 40
    runs: list[dict[str, Any]] = [
        {
            "databaseId": 20,
            "status": "completed",
            "conclusion": "success",
            "workflowName": "AI factory quality",
            "headSha": sha,
            "headBranch": "main",
            "event": "push",
            "createdAt": "2026-08-11T10:00:00Z",
        },
        {
            "databaseId": 21,
            "status": "completed",
            "conclusion": "failure",
            "workflowName": "AI factory quality",
            "headSha": sha,
            "headBranch": "main",
            "event": "push",
            "createdAt": "2026-08-11T10:01:00Z",
        },
    ]
    def fake_runs(_repo_root: Path, _sha: str) -> list[dict[str, Any]]:
        return runs

    monkeypatch.setattr("tcfactory.github_sync._workflow_runs", fake_runs)

    with pytest.raises(GitHubSyncError, match="failed"):
        wait_for_remote_ci(tmp_path, GitHubConfig(enabled=True), sha)
