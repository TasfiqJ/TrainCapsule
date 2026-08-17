from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast

import pytest

from tcfactory.github_sync import GitHubConfig, load_github_config
from tcfactory.util import read_json
from tcfactory.v3.candidate_freeze import CandidateFreezeError, FrozenCandidate
from tcfactory.v3.publication import (
    AuthorizedReceipt,
    AutomatedPRPublisher,
    CheckObservation,
    GhPublicationClient,
    PublicationCredentialUnavailable,
    PublicationError,
    PublicationPhase,
    PublicationTransaction,
    PublicCheckAuthorization,
    PullRequestObservation,
)

BASE = "a" * 40
CANDIDATE = "b" * 40
CANDIDATE_TREE = "c" * 40
MERGED = "d" * 40
MERGED_TREE = "e" * 40
DIGEST = "sha256:" + "f" * 64
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def test_gh_client_types_missing_noninteractive_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "tcfactory.v3.publication.run_command",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="To get started with GitHub CLI, please run: gh auth login",
        ),
    )
    client = GhPublicationClient(
        tmp_path,
        remote="origin",
        repository="TasfiqJ/TrainCapsule",
        branch_prefix="codex/",
    )

    with pytest.raises(
        PublicationCredentialUnavailable,
        match="non-interactive GitHub publication credential is unavailable",
    ):
        client._run(  # pyright: ignore[reportPrivateUsage]
            ["gh", "api", "repos/TasfiqJ/TrainCapsule"]
        )


def _config() -> GitHubConfig:
    root = Path(__file__).resolve().parents[1]
    payload = load_github_config(root / "config/github.yaml").model_dump(mode="json", by_alias=True)
    remote = payload["remoteCi"]
    assert isinstance(remote, dict)
    ids = cast(dict[str, object], remote["trustedCheckAppIds"])
    assert isinstance(ids, dict)
    remote["trustedCheckAppIds"] = {name: 15368 for name in ids}
    remote["postMergeRequiredWorkflows"] = [
        name for name in ids if name != "TrainCapsule / Machine policy"
    ]
    remote["pollSeconds"] = 5
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
        self.branches: dict[str, str] = {"main": BASE}
        self.anchor_main = BASE
        self.prs: dict[int, PullRequestObservation] = {}
        self.created_prs = 0
        self.pushes = 0
        self.ready_calls = 0
        self.merge_calls = 0
        self.closed: list[int] = []
        self.check_state = "success"
        self.post_merge_state = "success"
        self.fail_after_push_once = False
        self.fail_after_create_once = False
        self.trees = {
            BASE: "1" * 40,
            CANDIDATE: CANDIDATE_TREE,
            MERGED: MERGED_TREE,
        }

    def remote_branch_sha(self, branch: str) -> str | None:
        return self.branches.get(branch)

    def push_candidate_branch(self, *, sha: str, branch: str) -> None:
        assert branch != "main"
        self.pushes += 1
        self.branches[branch] = sha
        if self.fail_after_push_once:
            self.fail_after_push_once = False
            raise PublicationError("simulated crash after branch push")

    def find_pull_request(
        self, *, head_branch: str, base_branch: str, marker: str
    ) -> PullRequestObservation | None:
        del base_branch, marker
        return next((pr for pr in self.prs.values() if pr.head_branch == head_branch), None)

    def create_draft_pull_request(
        self, *, head_branch: str, base_branch: str, title: str, body: str
    ) -> PullRequestObservation:
        del title, body
        self.created_prs += 1
        number = len(self.prs) + 1
        pr = PullRequestObservation(
            number=number,
            url=f"https://github.com/TasfiqJ/TrainCapsule/pull/{number}",
            base_branch=cast(Literal["main"], base_branch),
            base_sha=self.branches[base_branch],
            head_branch=head_branch,
            head_sha=self.branches[head_branch],
            state="OPEN",
            is_draft=True,
        )
        self.prs[number] = pr
        if self.fail_after_create_once:
            self.fail_after_create_once = False
            raise PublicationError("simulated crash after PR creation")
        return pr

    def pull_request(self, number: int) -> PullRequestObservation:
        return self.prs[number]

    def checks(self, *, sha: str, pull_request_number: int | None) -> list[CheckObservation]:
        state = self.post_merge_state if pull_request_number is None else self.check_state
        event = "push" if pull_request_number is None else "pull_request"
        conclusion = None if state == "pending" else state
        status = "in_progress" if state == "pending" else "completed"
        return [
            CheckObservation(
                name=name,
                head_sha=sha,
                app_id=cast(int, app_id),
                event=event,
                status=status,
                conclusion=conclusion,
            )
            for name, app_id in self.config.remote_ci.trusted_check_app_ids.items()
        ]

    def mark_ready(self, *, number: int, expected_head_sha: str) -> None:
        pr = self.prs[number]
        assert pr.head_sha == expected_head_sha
        self.ready_calls += 1
        self.prs[number] = pr.model_copy(update={"is_draft": False})

    def enable_auto_merge(self, *, number: int, expected_head_sha: str) -> None:
        pr = self.prs[number]
        assert pr.head_sha == expected_head_sha
        self.merge_calls += 1
        self.prs[number] = pr.model_copy(update={"auto_merge_enabled": True})

    def close_pull_request(self, *, number: int, reason: str) -> None:
        del reason
        self.closed.append(number)
        self.prs[number] = self.prs[number].model_copy(update={"state": "CLOSED"})

    def commit_tree_sha(self, sha: str) -> str:
        return self.trees[sha]

    def create_revert_commit(self, *, merged_sha: str, base_sha: str, message: str) -> str:
        del merged_sha, base_sha, message
        revert = "9" * 40
        self.trees[revert] = self.trees[BASE]
        return revert

    def merge(self, number: int, sha: str = MERGED) -> None:
        self.trees.setdefault(sha, MERGED_TREE)
        self.prs[number] = self.prs[number].model_copy(
            update={"state": "MERGED", "merged_sha": sha, "is_draft": False}
        )
        self.branches["main"] = sha

    def advance_anchor(self, sha: str) -> None:
        self.anchor_main = sha


def _transaction() -> PublicationTransaction:
    return PublicationTransaction(
        transaction_id="PRPUB-V3_REL_001-BBBBBBBBBBBB",
        work_item_id="V3-REL-001",
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_tree_sha=CANDIDATE_TREE,
        candidate_worktree="/virtual/frozen-candidate",
        candidate_branch="factory/v3-rel-001/bbbbbbbbbbbb",
        candidate_manifest_digest=DIGEST,
        phase=PublicationPhase.PREPARED,
        created_at=NOW,
        updated_at=NOW,
    )


def _publisher(
    tmp_path: Path,
) -> tuple[AutomatedPRPublisher, MemoryGitHub, StubAuthorizer]:
    config = _config()
    client = MemoryGitHub(config)
    authorizer = StubAuthorizer()
    publisher = AutomatedPRPublisher(
        repo_root=tmp_path,
        config=config,
        transaction_root=tmp_path / "transactions",
        receipt_root=tmp_path / "external-receipts",
        quarantine_root=tmp_path / "quarantine",
        client=client,
        receipt_authorizer=authorizer,
        local_gate_command=("true",),
        clock=lambda: NOW,
        candidate_freezer=lambda _path, sha, tree: FrozenCandidate(
            candidate_sha=sha, candidate_tree_sha=tree
        ),
        anchor_main_observer=lambda: client.anchor_main,
    )
    return publisher, client, authorizer


def _advance_to_auto_merge(
    publisher: AutomatedPRPublisher, tx: PublicationTransaction
) -> PublicationTransaction:
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.AUTO_MERGE_REQUESTED
    return tx


def test_exact_candidate_pr_checks_receipt_merge_and_post_merge_invariants(
    tmp_path: Path,
) -> None:
    publisher, client, authorizer = _publisher(tmp_path)
    tx = _advance_to_auto_merge(publisher, _transaction())
    assert client.branches[tx.candidate_branch] == CANDIDATE
    assert client.created_prs == 1
    assert client.ready_calls == client.merge_calls == 1
    assert authorizer.calls == [CANDIDATE]
    assert tx.pull_request_number is not None
    client.merge(tx.pull_request_number)
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.MERGED
    client.advance_anchor(MERGED)
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.INVARIANTS_VERIFIED
    assert tx.merged_main_sha == MERGED
    assert client.branches["main"] == MERGED


def test_candidate_freeze_failure_prevents_branch_push_side_effect(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    observations = 0

    def fail_before_push(_path: Path, sha: str, tree: str) -> FrozenCandidate:
        nonlocal observations
        observations += 1
        if observations == 1:
            raise CandidateFreezeError("candidate became dirty")
        return FrozenCandidate(candidate_sha=sha, candidate_tree_sha=tree)

    publisher.candidate_freezer = fail_before_push

    with pytest.raises(PublicationError, match="HARD_STUCK"):
        publisher.reconcile_transaction(_transaction())

    assert CANDIDATE not in client.branches.values()
    assert client.created_prs == 0


def test_candidate_freeze_failure_prevents_merge_authorization(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    client.prs[1] = PullRequestObservation(
        number=1,
        url="https://github.com/TasfiqJ/TrainCapsule/pull/1",
        base_sha=BASE,
        head_branch="factory/v3-rel-001/bbbbbbbbbbbb",
        head_sha=CANDIDATE,
        state="OPEN",
        is_draft=True,
    )
    tx = _transaction().model_copy(
        update={
            "phase": PublicationPhase.READY_TO_MERGE,
            "pull_request_number": 1,
            "pull_request_url": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
        }
    )
    tx = PublicationTransaction.model_validate(tx.model_dump(mode="python"))
    def fail_before_merge(_path: Path, _sha: str, _tree: str) -> FrozenCandidate:
        raise CandidateFreezeError("candidate became dirty")

    publisher.candidate_freezer = fail_before_merge

    with pytest.raises(PublicationError, match="HARD_STUCK"):
        publisher.reconcile_transaction(tx)

    assert client.ready_calls == client.merge_calls == 0


def test_candidate_mutation_after_mark_ready_still_prevents_auto_merge(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    client.prs[1] = PullRequestObservation(
        number=1,
        url="https://github.com/TasfiqJ/TrainCapsule/pull/1",
        base_sha=BASE,
        head_branch="factory/v3-rel-001/bbbbbbbbbbbb",
        head_sha=CANDIDATE,
        state="OPEN",
        is_draft=True,
    )
    tx = PublicationTransaction.model_validate(
        _transaction()
        .model_copy(
            update={
                "phase": PublicationPhase.READY_TO_MERGE,
                "pull_request_number": 1,
                "pull_request_url": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
            }
        )
        .model_dump(mode="python")
    )
    observations = 0

    def fail_after_ready(_path: Path, sha: str, tree: str) -> FrozenCandidate:
        nonlocal observations
        observations += 1
        if observations == 2:
            raise CandidateFreezeError("candidate changed after ready transition")
        return FrozenCandidate(candidate_sha=sha, candidate_tree_sha=tree)

    publisher.candidate_freezer = fail_after_ready

    with pytest.raises(PublicationError, match="HARD_STUCK"):
        publisher.reconcile_transaction(tx)

    assert client.ready_calls == 1
    assert client.merge_calls == 0


def test_wrong_sha_stale_event_or_spoofed_app_never_satisfies_checks(
    tmp_path: Path,
) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = publisher.reconcile_transaction(_transaction())
    assert tx.phase is PublicationPhase.AUTO_MERGE_REQUESTED
    tx = tx.model_copy(update={"phase": PublicationPhase.CHECKS_PENDING})
    original = client.checks

    def hostile_checks(*, sha: str, pull_request_number: int | None) -> list[CheckObservation]:
        checks = original(sha=sha, pull_request_number=pull_request_number)
        return [
            check.model_copy(
                update={
                    "head_sha": BASE,
                    "event": "push",
                    "app_id": check.app_id + 1,
                }
            )
            for check in checks
        ]

    client.checks = hostile_checks  # type: ignore[method-assign]
    pending = publisher.reconcile_transaction(tx)
    assert pending.phase is PublicationPhase.CHECKS_PENDING
    assert client.merge_calls == 1


def test_failed_check_or_revoked_receipt_closes_pr_before_main(tmp_path: Path) -> None:
    publisher, client, authorizer = _publisher(tmp_path)
    client.check_state = "failure"
    failed = publisher.reconcile_transaction(_transaction())
    assert failed.phase is PublicationPhase.FAILED
    assert client.branches["main"] == BASE
    assert client.closed == [1]

    publisher, client, authorizer = _publisher(tmp_path / "revoked")
    authorizer.reject = True
    failed = publisher.reconcile_transaction(_transaction())
    assert failed.phase is PublicationPhase.FAILED
    assert "expired or revoked" in cast(str, failed.failure_reason)
    assert client.branches["main"] == BASE


def test_phase11_receipt_mismatch_is_rejected_before_publication_side_effects(
    tmp_path: Path,
) -> None:
    publisher, client, authorizer = _publisher(tmp_path)
    tx = _transaction().model_copy(
        update={
            "expected_machine_policy_receipt_id": "RECEIPT:VALUE:EXPECTED",
            "expected_machine_policy_receipt_digest": "sha256:" + "0" * 64,
        }
    )
    rejected = publisher.reconcile_transaction(tx)
    assert rejected.phase is PublicationPhase.FAILED
    assert "pre-authorized Phase 11" in cast(str, rejected.failure_reason)
    assert authorizer.calls == [CANDIDATE]
    assert client.pushes == 0
    assert client.created_prs == 0
    assert client.ready_calls == client.merge_calls == 0
    assert client.branches == {"main": BASE}


@pytest.mark.parametrize("crash_point", ["push", "pull-request"])
def test_crash_recovery_reconciles_side_effect_without_duplicate(
    tmp_path: Path, crash_point: str
) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = _transaction()
    if crash_point == "push":
        client.fail_after_push_once = True
    else:
        client.fail_after_create_once = True
    with pytest.raises(PublicationError, match="simulated crash"):
        publisher.reconcile_transaction(tx)
    transaction_path = tmp_path / "transactions" / f"{CANDIDATE}.json"
    persisted = read_json(transaction_path, {})
    if persisted:
        tx = PublicationTransaction.model_validate(persisted)
    recovered = publisher.reconcile_transaction(tx)
    assert recovered.phase is PublicationPhase.AUTO_MERGE_REQUESTED
    assert client.pushes == 1
    assert client.created_prs == 1


def test_branch_collision_and_merged_main_mismatch_are_hard_stuck(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = _transaction()
    client.branches[tx.candidate_branch] = BASE
    with pytest.raises(PublicationError, match="HARD_STUCK"):
        publisher.reconcile_transaction(tx)
    persisted = PublicationTransaction.model_validate(
        read_json(tmp_path / "transactions" / f"{CANDIDATE}.json", {})
    )
    assert persisted.phase is PublicationPhase.HARD_STUCK

    publisher, client, _ = _publisher(tmp_path / "merge-mismatch")
    tx = _advance_to_auto_merge(publisher, _transaction())
    assert tx.pull_request_number is not None
    client.merge(tx.pull_request_number)
    client.branches["main"] = BASE
    with pytest.raises(PublicationError, match="HARD_STUCK"):
        publisher.reconcile_transaction(tx)


def test_base_drift_closes_candidate_without_merge(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = _transaction()
    client.branches["main"] = "7" * 40
    failed = publisher.reconcile_transaction(tx)
    assert failed.phase is PublicationPhase.FAILED
    assert client.created_prs == 0
    assert client.merge_calls == 0


def test_post_merge_failure_uses_a_second_verified_pr_not_main_push(tmp_path: Path) -> None:
    publisher, client, _ = _publisher(tmp_path)
    tx = _advance_to_auto_merge(publisher, _transaction())
    assert tx.pull_request_number is not None
    client.merge(tx.pull_request_number)
    client.post_merge_state = "failure"
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.MERGED
    client.advance_anchor(MERGED)
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.REVERT_MERGE_REQUESTED
    assert tx.revert_pull_request_number is not None
    assert client.created_prs == 2
    assert all(branch != "main" for branch in client.branches if branch != "main")
    revert_pr = tx.revert_pull_request_number
    revert_merge = "8" * 40
    client.trees[revert_merge] = client.trees[BASE]
    client.merge(revert_pr, revert_merge)
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.REVERT_MERGE_REQUESTED
    client.advance_anchor(revert_merge)
    tx = publisher.reconcile_transaction(tx)
    assert tx.phase is PublicationPhase.REVERTED
    assert client.branches["main"] == revert_merge
