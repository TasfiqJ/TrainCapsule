from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.work_items import WorkItem

NOW = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)


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
