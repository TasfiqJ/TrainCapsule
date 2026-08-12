from __future__ import annotations

import json
import multiprocessing
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.v3.controller_lock import ControllerLockError, controller_process_lock
from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.work_items import WorkItem

NOW = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)


def _claim_process(root: str, owner: str, start: object, results: object) -> None:
    start.wait()  # type: ignore[attr-defined]
    try:
        lease = V3Queue(Path(root)).claim(
            "V3-PROD-001", owner_id=owner, now=NOW, lease_seconds=30
        )
    except Exception as exc:  # noqa: BLE001 - child reports exact losing disposition
        results.put(("error", type(exc).__name__, str(exc)))  # type: ignore[attr-defined]
    else:
        results.put(("claimed", owner, lease.lease_id))  # type: ignore[attr-defined]


def _claim_and_crash(root: str) -> None:
    V3Queue(Path(root)).claim(
        "V3-PROD-001", owner_id="crashing-owner", now=NOW, lease_seconds=30
    )
    os._exit(23)


def _claim_and_wait(root: str, ready: object, release: object) -> None:
    V3Queue(Path(root)).claim(
        "V3-PROD-001", owner_id="live-owner", now=NOW, lease_seconds=300
    )
    ready.set()  # type: ignore[attr-defined]
    release.wait()  # type: ignore[attr-defined]


def _hold_controller_lock(path: str, ready: object, release: object) -> None:
    with controller_process_lock(Path(path)):
        ready.set()  # type: ignore[attr-defined]
        release.wait()  # type: ignore[attr-defined]


def _item() -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": "V3-PROD-001",
            "title": "Queue test",
            "lane": "PRODUCT",
            "kind": "CODE",
            "milestone": "M1_NATIVE_PREFLIGHT",
            "decisionContribution": "Exercise atomic queue behavior.",
            "customerOutcome": "No duplicate or implicit resume.",
            "dependsOn": [],
            "softDependsOn": [],
            "blocksCommercialRelease": False,
            "priority": 80,
            "riskTier": "STANDARD",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NATIVE_ADVANTAGE_UNPROVEN",
            },
            "disposition": "KEEP",
            "status": "READY",
            "ownerType": "AI",
            "automatable": True,
            "packetPath": None,
            "evidenceRequired": ["queue test"],
            "externalReceiptRequired": False,
            "retryPolicy": {
                "maxPlanAttempts": 2,
                "maxCandidateRepairCycles": 3,
            },
        }
    )


def test_queue_moves_atomically_and_recovery_never_auto_resumes(tmp_path: Path) -> None:
    queue = V3Queue(tmp_path / "v3-queue")
    ready = queue.put(_item())
    assert ready.parent.name == "ready"
    with pytest.raises(ValueError, match="duplicate queue work item"):
        queue.put(_item())

    queued = queue.transition("V3-PROD-001", WorkStatus.QUEUED, updated_at=NOW)
    running = queue.transition("V3-PROD-001", WorkStatus.RUNNING, updated_at=NOW)
    assert queued.exists() is False
    assert running.parent.name == "running"
    assert queue.by_lane()[Lane.PRODUCT][0].status is WorkStatus.RUNNING

    recovered = queue.recover_interrupted(updated_at=NOW)
    assert recovered == ["V3-PROD-001"]
    item = queue.load("V3-PROD-001")
    assert item.status is WorkStatus.BLOCKED_TECHNICAL
    assert queue.locate(item.work_item_id).parent.name == "blocked_technical"


def test_cross_process_claim_has_exactly_one_owner(tmp_path: Path) -> None:
    root = tmp_path / "v3-queue"
    queue = V3Queue(root)
    queue.put(_item())
    queue.transition("V3-PROD-001", WorkStatus.QUEUED, updated_at=NOW)
    context = multiprocessing.get_context("fork")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(target=_claim_process, args=(str(root), owner, start, results))
        for owner in ("owner-a", "owner-b")
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=5)
        assert process.exitcode == 0
    observed = [results.get(timeout=2), results.get(timeout=2)]
    assert sum(row[0] == "claimed" for row in observed) == 1
    lease = json.loads((root / ".leases/V3-PROD-001.json").read_text(encoding="utf-8"))
    assert lease["ownerId"] in {"owner-a", "owner-b"}
    assert queue.load("V3-PROD-001").status is WorkStatus.RUNNING


def test_claim_lock_is_released_on_process_crash_and_lease_recovers(tmp_path: Path) -> None:
    root = tmp_path / "v3-queue"
    queue = V3Queue(root)
    queue.put(_item())
    queue.transition("V3-PROD-001", WorkStatus.QUEUED, updated_at=NOW)
    process = multiprocessing.get_context("fork").Process(
        target=_claim_and_crash, args=(str(root),)
    )
    process.start()
    process.join(timeout=5)
    assert process.exitcode == 23
    assert queue.recover_interrupted(updated_at=NOW) == ["V3-PROD-001"]
    assert queue.load("V3-PROD-001").status is WorkStatus.BLOCKED_TECHNICAL


def test_live_process_lease_is_never_recovered_then_dead_owner_is(tmp_path: Path) -> None:
    root = tmp_path / "v3-queue"
    queue = V3Queue(root)
    queue.put(_item())
    queue.transition("V3-PROD-001", WorkStatus.QUEUED, updated_at=NOW)
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(target=_claim_and_wait, args=(str(root), ready, release))
    process.start()
    assert ready.wait(timeout=5)

    assert queue.recover_interrupted(updated_at=NOW) == []
    assert queue.load("V3-PROD-001").status is WorkStatus.RUNNING

    process.terminate()
    process.join(timeout=5)
    assert process.exitcode is not None
    assert queue.recover_interrupted(updated_at=NOW) == ["V3-PROD-001"]
    assert queue.load("V3-PROD-001").status is WorkStatus.BLOCKED_TECHNICAL


def test_controller_lock_rejects_live_second_process_and_releases_on_crash(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "runtime/controller.lock"
    context = multiprocessing.get_context("fork")
    ready = context.Event()
    release = context.Event()
    process = context.Process(target=_hold_controller_lock, args=(str(lock), ready, release))
    process.start()
    assert ready.wait(timeout=5)

    with (
        pytest.raises(ControllerLockError, match="already active"),
        controller_process_lock(lock),
    ):
        pass

    process.terminate()
    process.join(timeout=5)
    assert process.exitcode is not None
    with controller_process_lock(lock):
        pass


def test_legacy_archive_preserves_files_and_forbids_auto_resume(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    (source / "T002.yaml").write_text("task_id: T002\n", encoding="utf-8")
    queue = V3Queue(tmp_path / "v3-queue")
    queue.initialize()
    assert all(
        (queue.root / state.value.lower()).is_dir() for state in WorkStatus
    )
    archive = queue.archive_v2(source, archive_id="baseline", captured_at=NOW)
    assert (archive / "T002.yaml").read_text(encoding="utf-8") == "task_id: T002\n"
    manifest = json.loads((archive / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["autoResume"] is False
    assert manifest["capturedAt"] == NOW.isoformat()
    assert manifest["sourceDigest"].startswith("sha256:")
    assert manifest["files"][0]["path"] == "T002.yaml"
    assert source.is_dir()
    assert queue.archive_v2(source, archive_id="baseline", captured_at=NOW) == archive
    with pytest.raises(ValueError, match="unsafe characters"):
        queue.archive_v2(source, archive_id="../escape", captured_at=NOW)


def test_legacy_archive_rejects_symlinked_evidence(tmp_path: Path) -> None:
    source = tmp_path / "legacy"
    source.mkdir()
    external = tmp_path / "outside.yaml"
    external.write_text("secret: no\n", encoding="utf-8")
    (source / "T002.yaml").symlink_to(external)

    with pytest.raises(ValueError, match="contains symlinks"):
        V3Queue(tmp_path / "v3-queue").archive_v2(
            source,
            archive_id="baseline",
            captured_at=NOW,
        )
