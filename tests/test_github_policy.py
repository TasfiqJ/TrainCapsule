# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import tcfactory.github_sync as github_sync
from tcfactory.github_sync import (
    GitHubConfig,
    GitHubSyncError,
    MainOnlyPublisher,
    RequiredWorkflow,
    RequiredWorkflowStatus,
    push_main_with_retry,
)
from tcfactory.util import sha256_file, write_json
from tcfactory.v3.candidate_manifest import (
    CandidateManifest,
    ExecutorIdentity,
    GateBinding,
)
from tcfactory.v3.enums import ReleaseDecision

BASE = "a" * 40
CANDIDATE = "b" * 40
DIGEST = "sha256:" + "c" * 64


def _passed_status() -> RequiredWorkflowStatus:
    config = GitHubConfig(enabled=True)
    return RequiredWorkflowStatus(
        candidate_sha=CANDIDATE,
        status="pass",
        workflows=[
            RequiredWorkflow(name=name, status="completed", conclusion="success")
            for name in config.remote_ci.required_workflows
        ],
    )


def test_non_main_push_and_pr_surfaces_do_not_exist() -> None:
    assert not hasattr(github_sync, "push_release_branch_with_retry")
    assert not hasattr(github_sync, "prepare_release_pull_request")
    assert not hasattr(github_sync, "run_remote_ci")


def test_private_gate_uses_fixed_controller_owned_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", "/attacker/controlled")
    assert (
        Path.home()
        / ".local/share/traincapsule-factory/private-gates/run_private_gate.sh"
    ) == github_sync.CONTROLLER_PRIVATE_GATE
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


def test_main_only_publisher_binds_gates_and_publishes_exact_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    candidate_tree = tmp_path / "candidate"
    repo.mkdir()
    candidate_tree.mkdir()
    (repo / "config").mkdir()
    (repo / "factory/state").mkdir(parents=True)
    (repo / "config/owner_directives.yaml").write_text("version: 3\n", encoding="utf-8")
    gate = candidate_tree / "gate.sh"
    gate.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    gate.chmod(0o755)
    config = GitHubConfig(enabled=True, retry_attempts=1, retry_backoff_seconds=1)
    publisher = MainOnlyPublisher(
        repo_root=repo,
        config=config,
        receipt_root=repo / "factory/state/receipts",
        quarantine_root=repo / "factory/state/quarantine",
        local_gate_command=("bash", "gate.sh"),
    )
    monkeypatch.setattr(github_sync, "CONTROLLER_PRIVATE_GATE", tmp_path / "missing-private-gate")
    item = SimpleNamespace(work_item_id="V3-MIG-019")
    monkeypatch.setattr(github_sync, "current_branch", lambda _: "main")

    state = {"local": BASE, "remote": BASE}

    def fake_sha(path: Path, ref: str | None = None) -> str:
        if path.resolve() == candidate_tree.resolve() or ref not in {None, "main"}:
            return CANDIDATE
        return state["local"]

    monkeypatch.setattr(github_sync, "current_sha", fake_sha)
    monkeypatch.setattr(github_sync, "validate_github_ready", lambda *_: {})
    monkeypatch.setattr(github_sync, "_pre_push_checks", lambda *_: None)
    monkeypatch.setattr(github_sync, "_ensure_no_divergence", lambda *_: None)
    monkeypatch.setattr(
        github_sync,
        "fast_forward_main",
        lambda *_args, **_kwargs: state.update(local=CANDIDATE),
    )
    monkeypatch.setattr(
        github_sync, "_remote_branch_sha", lambda *_args, **_kwargs: state["remote"]
    )
    monkeypatch.setattr(github_sync, "required_workflow_status", lambda *_args: _passed_status())
    monkeypatch.setattr(
        github_sync,
        "wait_for_remote_ci",
        lambda *_args, **_kwargs: _passed_status().model_dump(mode="json", by_alias=True),
    )
    pushes: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "push"]:
            pushes.append(args)
            state["remote"] = args[-1].split(":", 1)[0]
        return subprocess.CompletedProcess(args, 0, "gate-output", "")

    monkeypatch.setattr(github_sync, "run_command", fake_run)
    gate_paths = publisher.prepare_candidate(
        item=item, candidate_sha=CANDIDATE, candidate_worktree=candidate_tree
    )
    gate_digests = {
        name: f"sha256:{sha256_file(path)}" for name, path in gate_paths.items()
    }
    manifest = CandidateManifest(
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        work_item_id=item.work_item_id,
        packet_digest=DIGEST,
        context_digest=DIGEST,
        executor=ExecutorIdentity(backend="fake", adapter="test"),
        stage_outputs=[],
        gates=[
            GateBinding(name=name, version="3", result="PASS", evidence_digest=digest)
            for name, digest in gate_digests.items()
        ],
        findings=[],
        external_evidence=[],
        checkpoint_digest=DIGEST,
        release_decision=ReleaseDecision.APPROVED_FOR_MAIN_PROMOTION,
        created_at=datetime.now(UTC),
    )
    manifest_path = repo / "manifest.json"
    write_json(manifest_path, manifest.model_dump(mode="json", by_alias=True))
    result = publisher.publish(
        item=item,
        candidate_ref="candidate-ref",
        candidate_sha=CANDIDATE,
        candidate_worktree=candidate_tree,
        candidate_manifest_path=manifest_path,
        packet_digest=DIGEST,
        source_digest=DIGEST,
        context_digest=DIGEST,
        checkpoint_digest=DIGEST,
        gate_digests=gate_digests,
    )
    assert result["status"] == "PUBLISHED_MAIN_VERIFIED"
    assert pushes == [["git", "push", "origin", f"{CANDIDATE}:refs/heads/main"]]
    assert all("refs/heads/main" in " ".join(command) for command in pushes)
