# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import tcfactory.github_sync as github_sync
from tcfactory.github_sync import (
    GitHubConfig,
    GitHubSyncError,
    MainOnlyPublisher,
    push_main_with_retry,
)

BASE = "a" * 40
CANDIDATE = "b" * 40


def test_non_main_push_and_pr_surfaces_do_not_exist() -> None:
    assert not hasattr(github_sync, "push_release_branch_with_retry")
    assert not hasattr(github_sync, "prepare_release_pull_request")
    assert not hasattr(github_sync, "run_remote_ci")


def test_private_gate_uses_fixed_controller_owned_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", "/attacker/controlled")
    assert Path("/var/lib/traincapsule-factory/private-gates/run_private_gate.sh") == (
        github_sync.CONTROLLER_PRIVATE_GATE
    )
    assert "TCF_PRIVATE_GATE_RUNNER" not in github_sync.CONTROLLER_PRIVATE_GATE.as_posix()


def test_push_helper_accepts_only_exact_sha_to_main(monkeypatch: pytest.MonkeyPatch) -> None:
    config = GitHubConfig(enabled=True, retry_attempts=1, retry_backoff_seconds=1)
    for refspec in ("candidate:refs/heads/main", f"{CANDIDATE}:refs/heads/dev"):
        with pytest.raises(GitHubSyncError, match="exact-SHA main"):
            push_main_with_retry(Path("."), config, refspec)
    observed: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed.append(args)
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(github_sync, "run_command", fake_run)
    push_main_with_retry(Path("."), config, f"{CANDIDATE}:refs/heads/main")
    assert observed == [
        ["git", "push", "--porcelain", "origin", f"{CANDIDATE}:refs/heads/main"]
    ]


def test_historical_v3_publisher_is_unreachable_under_v31(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(RuntimeError, match="disabled.*pending Phase 4"):
        MainOnlyPublisher(
            repo_root=repo,
            config=GitHubConfig(enabled=True),
            receipt_root=tmp_path / "receipts",
            quarantine_root=tmp_path / "quarantine",
            local_gate_command=("true",),
        )


def test_disabled_historical_publisher_creates_no_receipt_or_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    receipt_root = tmp_path / "receipts"
    with pytest.raises(RuntimeError):
        MainOnlyPublisher(
            repo_root=repo,
            config=GitHubConfig(enabled=True),
            receipt_root=receipt_root,
            quarantine_root=tmp_path / "quarantine",
        )
    assert not receipt_root.exists()
