from __future__ import annotations

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tcfactory.github_sync import (
    GitHubConfig,
    GitHubReleaseMetadata,
    GitHubSyncError,
    GitHubSyncState,
    RemoteCIConfig,
    RequiredWorkflow,
    RequiredWorkflowStatus,
    _create_or_update_draft_pull_request,
    prepare_release_pull_request,
    push_main_with_retry,
    push_release_branch_with_retry,
    record_verified_task,
    required_workflow_status,
    should_push,
)
from tcfactory.models import RiskTier


def test_periodic_release_threshold() -> None:
    config = GitHubConfig(enabled=True, push_after_verified_tasks=3)
    state = GitHubSyncState(tasks_since_push=3)
    assert should_push(
        config=config,
        state=state,
        task=None,
        force=False,
        now=datetime.now(UTC),
    )


def test_interval_release() -> None:
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
    [
        ("branch", "feature"),
        ("baseBranch", "develop"),
        ("remote", "upstream"),
        ("releaseMode", "direct"),
        ("directMainPush", True),
        ("autoMergeIntegration", True),
        ("autoMergeTrustCore", True),
    ],
)
def test_github_config_rejects_unsafe_release_policy(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        GitHubConfig.model_validate({field: value})


def test_direct_main_push_is_unconditionally_disabled(tmp_path: Path) -> None:
    with pytest.raises(GitHubSyncError, match="direct main push is disabled"):
        push_main_with_retry(
            tmp_path,
            GitHubConfig(),
            "refs/heads/main:refs/heads/main",
        )


def test_release_push_uses_exact_sha_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("tcfactory.github_sync.run_command", fake_run)
    sha = "a" * 40
    push_release_branch_with_retry(
        tmp_path,
        GitHubConfig(),
        candidate_sha=sha,
        release_branch="release/traincapsule/T900-a",
    )

    assert commands == [
        [
            "git",
            "push",
            "--porcelain",
            "origin",
            f"{sha}:refs/heads/release/traincapsule/T900-a",
        ]
    ]
    assert "--force" not in commands[0]
    assert "refs/heads/main" not in commands[0][-1]


def test_required_workflows_are_exact_sha_exact_branch_and_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "b" * 40
    config = GitHubConfig(
        remote_ci=RemoteCIConfig(required_workflows=["Factory", "Security"])
    )
    runs: list[dict[str, Any]] = [
        {
            "status": "completed",
            "conclusion": "failure",
            "workflowName": "Factory",
            "headSha": sha,
            "headBranch": "release/traincapsule/T900-b",
            "event": "pull_request",
            "createdAt": "2026-08-11T10:00:00Z",
        },
        {
            "status": "completed",
            "conclusion": "success",
            "workflowName": "Factory",
            "headSha": sha,
            "headBranch": "release/traincapsule/T900-b",
            "event": "pull_request",
            "createdAt": "2026-08-11T10:01:00Z",
        },
        {
            "status": "completed",
            "conclusion": "success",
            "workflowName": "Security",
            "headSha": sha,
            "headBranch": "release/traincapsule/T900-b",
            "event": "pull_request",
            "createdAt": "2026-08-11T10:02:00Z",
        },
        {
            "status": "completed",
            "conclusion": "success",
            "workflowName": "Security",
            "headSha": "c" * 40,
            "headBranch": "release/traincapsule/T900-b",
            "event": "pull_request",
            "createdAt": "2026-08-11T10:03:00Z",
        },
    ]
    monkeypatch.setattr("tcfactory.github_sync._workflow_runs", lambda *_: runs)

    status = required_workflow_status(
        tmp_path, config, sha, "release/traincapsule/T900-b"
    )

    assert status.status == "pass"
    assert [item.name for item in status.workflows] == ["Factory", "Security"]


def test_missing_or_failed_required_workflow_never_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "c" * 40
    config = GitHubConfig(
        remote_ci=RemoteCIConfig(required_workflows=["Factory", "Security"])
    )
    monkeypatch.setattr(
        "tcfactory.github_sync._workflow_runs",
        lambda *_: [
            {
                "status": "completed",
                "conclusion": "failure",
                "workflowName": "Factory",
                "headSha": sha,
                "headBranch": "release/traincapsule/T900-c",
                "event": "pull_request",
                "createdAt": "2026-08-11T10:00:00Z",
            }
        ],
    )

    status = required_workflow_status(
        tmp_path, config, sha, "release/traincapsule/T900-c"
    )

    assert status.status == "fail"
    assert status.workflows[1].status == "missing"


def test_draft_pr_create_redacts_body_and_never_requests_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "d" * 40
    observed = {
        "number": 41,
        "url": "https://github.test/pr/41",
        "isDraft": True,
        "headRefOid": sha,
    }
    lookups = iter([None, observed])
    monkeypatch.setattr(
        "tcfactory.github_sync._pull_request_for_branch", lambda *_: next(lookups)
    )
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="https://github.test/pr/41\n", stderr="")

    monkeypatch.setattr("tcfactory.github_sync.run_command", fake_run)
    pr = _create_or_update_draft_pull_request(
        tmp_path,
        GitHubConfig(),
        release_branch="release/traincapsule/T900-d",
        candidate_sha=sha,
        title="release token=ghp_supersecret",
        body="account_id=customer-42 bearer abcdefghijklmnopqrstuvwxyz",
    )

    flattened = " ".join(commands[0])
    assert pr["isDraft"] is True
    assert "--draft" in commands[0]
    assert "merge" not in commands[0]
    assert "ghp_supersecret" not in flattened
    assert "customer-42" not in flattened
    assert "abcdefghijklmnopqrstuvwxyz" not in flattened


def test_release_metadata_binds_exact_candidate_and_draft_pr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "e" * 40
    config = GitHubConfig(
        enabled=True, remote_ci=RemoteCIConfig(required_workflows=["Factory"])
    )
    monkeypatch.setattr("tcfactory.github_sync.current_sha", lambda *_: sha)
    monkeypatch.setattr("tcfactory.github_sync.validate_github_ready", lambda *_: {})
    monkeypatch.setattr("tcfactory.github_sync._pre_push_checks", lambda *_: None)
    monkeypatch.setattr("tcfactory.github_sync._ensure_no_divergence", lambda *_: None)
    monkeypatch.setattr(
        "tcfactory.github_sync._ensure_release_branch_fast_forward", lambda *_: None
    )
    monkeypatch.setattr("tcfactory.github_sync._remote_branch_sha", lambda *_: sha)
    monkeypatch.setattr(
        "tcfactory.github_sync._create_or_update_draft_pull_request",
        lambda *_args, **_kwargs: {
            "number": 42,
            "url": "https://github.test/pr/42",
            "isDraft": True,
            "headRefOid": sha,
        },
    )
    workflow = RequiredWorkflowStatus(
        candidate_sha=sha,
        release_branch="release/traincapsule/T900-e",
        status="pending",
        workflows=[RequiredWorkflow(name="Factory", status="missing")],
    )
    monkeypatch.setattr("tcfactory.github_sync.required_workflow_status", lambda *_: workflow)
    metadata_path = tmp_path / "release.json"

    metadata = prepare_release_pull_request(
        repo_root=tmp_path,
        config=config,
        candidate_ref="candidate/T900",
        candidate_sha=sha,
        release_branch="release/traincapsule/T900-e",
        title="T900 release",
        reason="verified",
        metadata_path=metadata_path,
    )

    assert isinstance(metadata, GitHubReleaseMetadata)
    assert metadata.candidate_sha == sha
    assert metadata.remote_release_sha == sha
    assert metadata.draft is True
    assert metadata.auto_merge is False
    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved["candidateSha"] == sha
    assert saved["pullRequestUrl"] == "https://github.test/pr/42"


def test_candidate_branch_sha_mismatch_fails_before_github_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tcfactory.github_sync.current_sha", lambda *_: "f" * 40)
    touched = False

    def mark_ready(*_: object) -> dict[str, str]:
        nonlocal touched
        touched = True
        return {}

    monkeypatch.setattr("tcfactory.github_sync.validate_github_ready", mark_ready)
    with pytest.raises(GitHubSyncError, match="candidate branch no longer resolves"):
        prepare_release_pull_request(
            repo_root=tmp_path,
            config=GitHubConfig(enabled=True),
            candidate_ref="candidate/T901",
            candidate_sha="0" * 40,
            release_branch="release/traincapsule/T901-0",
            title="T901 release",
            reason="verified",
            metadata_path=tmp_path / "release.json",
        )
    assert not touched
