from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from tcfactory.github_sync import GitHubConfig, load_github_config
from tcfactory.v3.candidate_freeze import FrozenCandidate
from tcfactory.v3.publication import (
    AuthorizedReceipt,
    CheckObservation,
    DirectMainPublisher,
    GhPublicationClient,
    PublicationClient,
    PublicationCredentialUnavailable,
    PublicationError,
    PublicationPhase,
    PublicationTransaction,
    PublicCheckAuthorization,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
CANDIDATE_TREE = "c" * 40
DIGEST = "sha256:" + "f" * 64
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _config() -> GitHubConfig:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(
        mode="json", by_alias=True
    )
    remote = cast(dict[str, object], payload["remoteCi"])
    ids = cast(dict[str, object], remote["trustedCheckAppIds"])
    remote["trustedCheckAppIds"] = {name: 15368 for name in ids}
    remote["postMergeRequiredWorkflows"] = [
        name for name in ids if name != "TrainCapsule / Machine policy"
    ]
    return GitHubConfig.model_validate(payload)


class StubAuthorizer:
    def __init__(self) -> None:
        self.reject = False
        self.calls: list[str] = []

    def authorize(
        self,
        receipt_path: Path,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
    ) -> AuthorizedReceipt:
        del receipt_path, candidate_tree_sha, base_sha, work_item_id, candidate_manifest_digest
        self.calls.append(candidate_sha)
        if self.reject:
            raise PublicationError("receipt is expired or revoked")
        authorization = PublicCheckAuthorization(
            check_name="TrainCapsule / Machine policy",
            candidate_sha=candidate_sha,
            conclusion="success",
            receipt_id="RECEIPT:POLICY:001",
            receipt_digest=DIGEST,
        )
        return cast(AuthorizedReceipt, SimpleNamespace(authorization=authorization))


class MemoryGitHub:
    def __init__(self, config: GitHubConfig) -> None:
        self.config = config
        self.main = BASE
        self.anchor_main = BASE
        self.pushes: list[tuple[str, str]] = []
        self.post_push_state = "success"
        self.fail_after_push_once = False
        self.trees = {BASE: "1" * 40, CANDIDATE: CANDIDATE_TREE}

    def remote_branch_sha(self, branch: str) -> str | None:
        return self.main if branch == "main" else None

    def push_main(self, *, sha: str, expected_base_sha: str) -> None:
        if self.main != expected_base_sha:
            raise PublicationError("main moved before direct publication")
        self.pushes.append((expected_base_sha, sha))
        self.main = sha
        if self.fail_after_push_once:
            self.fail_after_push_once = False
            raise PublicationError("simulated crash after direct push")

    def checks(self, *, sha: str, pull_request_number: int | None) -> list[CheckObservation]:
        assert pull_request_number is None
        pending = self.post_push_state == "pending"
        return [
            CheckObservation(
                name=name,
                head_sha=sha,
                app_id=cast(int, app_id),
                event="push",
                status="in_progress" if pending else "completed",
                conclusion=None if pending else self.post_push_state,
            )
            for name, app_id in self.config.remote_ci.trusted_check_app_ids.items()
            if name != "TrainCapsule / Machine policy"
        ]

    def commit_tree_sha(self, sha: str) -> str:
        return self.trees[sha]

    def create_revert_commit(self, *, merged_sha: str, base_sha: str, message: str) -> str:
        del merged_sha, base_sha, message
        revert = "9" * 40
        self.trees[revert] = self.trees[BASE]
        return revert


def _transaction() -> PublicationTransaction:
    return PublicationTransaction(
        transaction_id="MAINPUB-V3_REL_001-BBBBBBBBBBBB",
        work_item_id="V3-REL-001",
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_tree_sha=CANDIDATE_TREE,
        candidate_worktree="/virtual/frozen-candidate",
        candidate_branch="main",
        candidate_manifest_digest=DIGEST,
        phase=PublicationPhase.PREPARED,
        created_at=NOW,
        updated_at=NOW,
    )


def _publisher(tmp_path: Path) -> tuple[DirectMainPublisher, MemoryGitHub, StubAuthorizer]:
    config = _config()
    client = MemoryGitHub(config)
    authorizer = StubAuthorizer()
    publisher = DirectMainPublisher(
        repo_root=tmp_path,
        config=config,
        transaction_root=tmp_path / "transactions",
        receipt_root=tmp_path / "external-receipts",
        quarantine_root=tmp_path / "quarantine",
        client=cast(PublicationClient, client),
        receipt_authorizer=authorizer,
        local_gate_command=("true",),
        clock=lambda: NOW,
        candidate_freezer=lambda _path, sha, tree: FrozenCandidate(
            candidate_sha=sha, candidate_tree_sha=tree
        ),
        anchor_main_observer=lambda: client.anchor_main,
    )
    return publisher, client, authorizer


def test_gh_client_types_missing_noninteractive_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed_command(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="To get started with GitHub CLI, please run: gh auth login",
        )

    monkeypatch.setattr(
        "tcfactory.v3.publication.run_command",
        failed_command,
    )
    client = GhPublicationClient(
        tmp_path, remote="origin", repository="TasfiqJ/TrainCapsule"
    )
    with pytest.raises(PublicationCredentialUnavailable):
        client._run(  # pyright: ignore[reportPrivateUsage]
            ["gh", "api", "repos/TasfiqJ/TrainCapsule"]
        )


def test_direct_main_waits_for_receipt_then_verifies_post_push_checks(tmp_path: Path) -> None:
    publisher, client, authorizer = _publisher(tmp_path)
    tx = publisher.reconcile_transaction(_transaction())
    assert tx.phase is PublicationPhase.MERGED
    assert client.pushes == [(BASE, CANDIDATE)]
    assert authorizer.calls == [CANDIDATE]
    client.anchor_main = CANDIDATE
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.INVARIANTS_VERIFIED
    assert tx.merged_main_sha == CANDIDATE


def test_direct_main_rejects_base_race_before_push(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    client.main = "d" * 40
    tx = publisher.reconcile_transaction(_transaction())
    assert tx.phase is PublicationPhase.FAILED
    assert client.pushes == []


def test_crash_after_push_reconciles_without_duplicate_push(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    client.fail_after_push_once = True
    with pytest.raises(PublicationError, match="simulated crash"):
        publisher.reconcile_transaction(_transaction())
    tx = publisher.reconcile_transaction(_transaction())
    assert tx.phase is PublicationPhase.MERGED
    assert client.pushes == [(BASE, CANDIDATE)]


def test_failed_post_push_checks_trigger_exact_direct_revert(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = publisher.reconcile_transaction(_transaction())
    client.anchor_main = CANDIDATE
    client.post_push_state = "failure"
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.REVERTED
    assert len(client.pushes) == 2
    assert client.pushes[1][0] == CANDIDATE
    assert client.commit_tree_sha(client.pushes[1][1]) == client.commit_tree_sha(BASE)
