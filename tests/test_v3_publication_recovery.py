from __future__ import annotations

# pyright: reportPrivateUsage=false, reportUnknownLambdaType=false, reportUnknownArgumentType=false
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

import tcfactory.github_sync as github_sync
from tcfactory.github_sync import (
    GitHubConfig,
    MainOnlyMachineReceipt,
    MainOnlyPublisher,
    MainPublicationTransaction,
    PublicationPhase,
    RemoteCIFailure,
    RequiredWorkflow,
    RequiredWorkflowStatus,
)
from tcfactory.util import read_json, sha256_file, write_json

BASE = "a" * 40
CANDIDATE = "b" * 40
REVERT = "c" * 40
UNKNOWN = "d" * 40
DIGEST = "sha256:" + "e" * 64


def _workflow(
    status: Literal["pending", "pass", "fail"] = "pass",
) -> RequiredWorkflowStatus:
    return RequiredWorkflowStatus(
        candidate_sha=CANDIDATE,
        status=status,
        workflows=[
            RequiredWorkflow(
                name="TrainCapsule / Factory quality",
                status="completed" if status != "pending" else "in_progress",
                conclusion=(
                    "success" if status == "pass" else "failure" if status == "fail" else None
                ),
            )
        ],
    )


def _publisher(tmp_path: Path) -> MainOnlyPublisher:
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "docs/source-of-truth/v3-2026-08-11").mkdir(parents=True)
    (repo / "config/owner_directives.yaml").write_text("version: 3\n", encoding="utf-8")
    manifest = repo / "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json"
    manifest.write_text("{}\n", encoding="utf-8")
    state = repo / "factory/state"
    state.mkdir(parents=True)
    write_json(
        state / "MIGRATION_COMPLETE_V3.json",
        {
            "version": 3,
            "status": "COMPLETE",
            "completedSha": BASE,
            "sourceManifestSha256": sha256_file(manifest),
            "ownerDirectivesSha256": sha256_file(repo / "config/owner_directives.yaml"),
        },
    )
    return MainOnlyPublisher(
        repo_root=repo,
        config=GitHubConfig(enabled=True, retry_attempts=1, retry_backoff_seconds=1),
        receipt_root=state / "machine-policy-receipts",
        quarantine_root=state / "quarantine",
        local_gate_command=("true",),
    )


def _transaction(
    publisher: MainOnlyPublisher,
    phase: PublicationPhase,
    *,
    revert_sha: str | None = None,
) -> MainPublicationTransaction:
    now = datetime.now(UTC)
    receipt_path = publisher.receipt_root / "V3-MIG-019-bbbbbbbbbbbb.json"
    receipt = MainOnlyMachineReceipt(
        work_item_id="V3-MIG-019",
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        candidate_manifest_digest=DIGEST,
        packet_digest=DIGEST,
        source_digest=DIGEST,
        context_digest=DIGEST,
        checkpoint_digest=DIGEST,
        gate_digests={"deterministic-local": DIGEST},
        owner_directives_digest=DIGEST,
        local_gate_evidence={"candidateSha": CANDIDATE},
        private_gate_evidence={},
        created_at=now,
        retry_budget=1,
    )
    transaction = MainPublicationTransaction(
        transaction_id="MPUB-V3_MIG_019-BBBBBBBBBBBB",
        work_item_id="V3-MIG-019",
        base_sha=BASE,
        candidate_sha=CANDIDATE,
        phase=phase,
        receipt_path=str(receipt_path),
        machine_receipt=receipt,
        revert_sha=revert_sha,
        failure_reason="hosted checks failed" if phase.startswith("REVERT") else None,
        created_at=now,
        updated_at=now,
    )
    return publisher._save_transaction(transaction)


def _runtime(
    publisher: MainOnlyPublisher,
    monkeypatch: pytest.MonkeyPatch,
    *,
    local: str,
    remote: str,
    hosted: Literal["pending", "pass", "fail"] = "pass",
) -> tuple[dict[str, str], list[str]]:
    state = {"local": local, "remote": remote}
    effects: list[str] = []

    def current(_repo: Path, ref: str | None = None) -> str:
        if ref and ref.endswith("^{tree}"):
            return "f" * 40 if ref.startswith(CANDIDATE) else "0" * 40
        return state["local"]

    monkeypatch.setattr(github_sync, "current_sha", current)
    monkeypatch.setattr(
        github_sync, "_remote_branch_sha", lambda *_args, **_kwargs: state["remote"]
    )

    def promote(*_args: object, **_kwargs: object) -> None:
        effects.append("promote")
        state["local"] = CANDIDATE

    monkeypatch.setattr(github_sync, "fast_forward_main", promote)

    def push(sha: str) -> None:
        effects.append(f"push:{sha}")
        state["remote"] = sha

    monkeypatch.setattr(publisher, "_push_main", push)
    monkeypatch.setattr(
        github_sync,
        "required_workflow_status",
        lambda *_args, **_kwargs: _workflow("pending" if hosted == "pending" else hosted),
    )

    def wait(*_args: object, **_kwargs: object) -> dict[str, object]:
        effects.append("hosted-poll")
        if hosted == "fail":
            raise RemoteCIFailure("hosted checks failed")
        return _workflow("pass").model_dump(mode="json", by_alias=True)

    monkeypatch.setattr(github_sync, "wait_for_remote_ci", wait)
    return state, effects


@pytest.mark.parametrize(
    ("phase", "local", "remote", "expected_effects"),
    [
        ("PREPARED", BASE, BASE, ["promote", f"push:{CANDIDATE}", "hosted-poll"]),
        ("LOCAL_PROMOTED", CANDIDATE, BASE, [f"push:{CANDIDATE}", "hosted-poll"]),
        ("LOCAL_PROMOTED", CANDIDATE, CANDIDATE, ["hosted-poll"]),
        ("REMOTE_PUSHED", CANDIDATE, CANDIDATE, ["hosted-poll"]),
        ("HOSTED_PENDING", CANDIDATE, CANDIDATE, ["hosted-poll"]),
    ],
)
def test_recovery_resumes_every_candidate_publication_crash_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: PublicationPhase,
    local: str,
    remote: str,
    expected_effects: list[str],
) -> None:
    publisher = _publisher(tmp_path)
    transaction = _transaction(publisher, phase)
    state, effects = _runtime(publisher, monkeypatch, local=local, remote=remote, hosted="pass")
    completed = publisher.reconcile_transaction(transaction)
    assert completed.phase == "VERIFIED"
    assert state == {"local": CANDIDATE, "remote": CANDIDATE}
    assert effects == expected_effects
    metadata = read_json(publisher._metadata_path(), {})
    assert metadata["status"] == "PUBLISHED_MAIN_VERIFIED"
    marker = read_json(publisher.quarantine_root.parent / "MIGRATION_COMPLETE_V3.json", {})
    assert marker["completedSha"] == CANDIDATE


def test_recovery_resumes_failed_hosted_checks_and_revert_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = _publisher(tmp_path)
    transaction = _transaction(publisher, "HOSTED_PENDING")
    state, effects = _runtime(
        publisher,
        monkeypatch,
        local=CANDIDATE,
        remote=CANDIDATE,
        hosted="fail",
    )

    def create_revert(_transaction: MainPublicationTransaction) -> str:
        effects.append("local-revert")
        state["local"] = REVERT
        return REVERT

    monkeypatch.setattr(publisher, "_create_local_revert", create_revert)
    monkeypatch.setattr(publisher, "_assert_revert_tree", lambda *_args: None)
    completed = publisher.reconcile_transaction(transaction)
    assert completed.phase == "REVERTED"
    assert completed.revert_sha == REVERT
    assert state == {"local": REVERT, "remote": REVERT}
    assert effects == ["hosted-poll", "local-revert", f"push:{REVERT}"]
    assert read_json(publisher._metadata_path(), {})["status"] == "REVERTED_AND_QUARANTINED"
    marker = read_json(publisher.quarantine_root.parent / "MIGRATION_COMPLETE_V3.json", {})
    assert marker["completedSha"] == REVERT


def test_recovery_resumes_after_local_revert_before_remote_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = _publisher(tmp_path)
    transaction = _transaction(publisher, "REVERT_LOCAL", revert_sha=REVERT)
    state, effects = _runtime(publisher, monkeypatch, local=REVERT, remote=CANDIDATE, hosted="fail")
    monkeypatch.setattr(publisher, "_assert_revert_tree", lambda *_args: None)
    completed = publisher.reconcile_transaction(transaction)
    assert completed.phase == "REVERTED"
    assert state["remote"] == REVERT
    assert effects == [f"push:{REVERT}"]


def test_terminal_reconciliation_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = _publisher(tmp_path)
    _transaction(publisher, "VERIFIED")
    _, effects = _runtime(publisher, monkeypatch, local=CANDIDATE, remote=CANDIDATE, hosted="pass")
    first = publisher.reconcile_pending()
    second = publisher.reconcile_pending()
    assert first["status"] == second["status"] == "VERIFIED"
    assert effects == []


def test_ambiguous_recovery_fails_closed_and_persists_hard_stuck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = _publisher(tmp_path)
    transaction = _transaction(publisher, "PREPARED")
    _runtime(publisher, monkeypatch, local=UNKNOWN, remote=BASE)
    with pytest.raises(RemoteCIFailure, match="ambiguous PREPARED"):
        publisher.reconcile_transaction(transaction)
    saved = MainPublicationTransaction.model_validate(
        read_json(publisher._transaction_path(CANDIDATE), {})
    )
    assert saved.phase == "HARD_STUCK"
    state_root = publisher.quarantine_root.parent
    assert (state_root / "HARD_STUCK.json").is_file()
    assert (state_root / "STOP").is_file()
