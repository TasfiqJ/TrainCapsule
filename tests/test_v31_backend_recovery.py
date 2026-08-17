from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tcfactory.backends.base import AgentSession, SessionState
from tcfactory.checkpoints import CheckpointBudget, CheckpointStore, V3Checkpoint
from tcfactory.v3.backend_recovery import recover_repaired_claude_sandbox_blocks
from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.work_items import WorkItem, WorkItemCollection

SHA = "1" * 40
NEW_SHA = "2" * 40
DIGEST = "sha256:" + "a" * 64


def _item() -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": "V3-MIG-015",
            "title": "Migration",
            "lane": "FACTORY",
            "kind": "MIGRATION",
            "milestone": "M0_FACTORY_MIGRATED",
            "decisionContribution": "Migrate state.",
            "customerOutcome": "Preserve state.",
            "dependsOn": [],
            "softDependsOn": [],
            "blocksCommercialRelease": False,
            "priority": 85,
            "riskTier": "STANDARD",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NOT_EVALUATED",
            },
            "disposition": "KEEP",
            "status": "BLOCKED_TECHNICAL",
            "ownerType": "AI",
            "automatable": True,
            "packetPath": None,
            "evidenceRequired": ["migration report"],
            "externalReceiptRequired": False,
            "retryPolicy": {
                "maxPlanAttempts": 2,
                "maxCandidateRepairCycles": 3,
            },
        }
    )


def _checkpoint(artifact_root: Path) -> V3Checkpoint:
    now = datetime.now(UTC)
    return V3Checkpoint(
        generation=1,
        work_item_id="V3-MIG-015",
        lane=Lane.FACTORY,
        milestone="M0_FACTORY_MIGRATED",
        backend_session_ref="ASESS-CLAUDE-0006",
        backend_session=AgentSession(
            session_ref="ASESS-CLAUDE-0006",
            backend="claude",
            request_id="AREQ-TEST",
            state=SessionState.FAILED,
            started_at=now.isoformat(),
        ),
        budget=CheckpointBudget(
            max_turns=8,
            max_wall_time_seconds=120,
            plan_attempts_remaining=1,
            repair_cycles_remaining=1,
            restarts_remaining=1,
        ),
        context_digest=DIGEST,
        source_digest=DIGEST,
        candidate_sha=SHA,
        candidate_worktree=str(artifact_root.parent / "worktree"),
        artifact_root=str(artifact_root),
        active_role="factory_repair",
        circuit_breaker_reason="stage factory_repair finding abc repeated 2 time(s)",
        approval_state="MACHINE_POLICY_REQUIRED",
        active=False,
        created_at=now,
        updated_at=now,
    )


def test_fixed_sandbox_failure_is_archived_and_reopened_once(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    queue = V3Queue(runtime / "v3-queue")
    queue.initialize()
    item = _item()
    queue.put(item)
    checkpoints = CheckpointStore(runtime / "pipelines")
    artifact_root = runtime / "artifacts/v3/V3-MIG-015/run-1"
    result = artifact_root / "factory_repair/backend-result.json"
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps({"error": "bwrap: Can't mkdir /var/lib/.claude: Read-only file system"}),
        encoding="utf-8",
    )
    checkpoints.save_v3(_checkpoint(artifact_root))
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED", work_items=[item]
    )

    assert recover_repaired_claude_sandbox_blocks(
        collection=collection,
        queue=queue,
        checkpoints=checkpoints,
        runtime_root=runtime,
        current_main_sha=NEW_SHA,
        now=datetime.now(UTC),
    ) == ["V3-MIG-015"]
    assert queue.load("V3-MIG-015").status is WorkStatus.READY
    assert checkpoints.load_v3("V3-MIG-015") is None
    recovery = checkpoints.root / "recovery-archive" / (
        "222222222222-claude-native-credential-boundary-v3"
    )
    assert (recovery / "V3-MIG-015.json").is_file()
    journal = json.loads((recovery / "V3-MIG-015.journal.json").read_bytes())
    assert journal["phase"] == "COMMITTED"

    current = queue.load("V3-MIG-015")
    journal["phase"] = "ARCHIVED"
    (recovery / "V3-MIG-015.journal.json").write_text(
        json.dumps(journal), encoding="utf-8"
    )
    assert recover_repaired_claude_sandbox_blocks(
        collection=WorkItemCollection(
            active_milestone="M0_FACTORY_MIGRATED", work_items=[current]
        ),
        queue=queue,
        checkpoints=checkpoints,
        runtime_root=runtime,
        current_main_sha=NEW_SHA,
        now=datetime.now(UTC),
    ) == ["V3-MIG-015"]
    assert json.loads((recovery / "V3-MIG-015.journal.json").read_bytes())[
        "phase"
    ] == "COMMITTED"

    assert recover_repaired_claude_sandbox_blocks(
        collection=WorkItemCollection(
            active_milestone="M0_FACTORY_MIGRATED", work_items=[current]
        ),
        queue=queue,
        checkpoints=checkpoints,
        runtime_root=runtime,
        current_main_sha=NEW_SHA,
        now=datetime.now(UTC),
    ) == []


def test_unrelated_terminal_failure_remains_blocked(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    queue = V3Queue(runtime / "v3-queue")
    queue.initialize()
    item = _item()
    queue.put(item)
    checkpoints = CheckpointStore(runtime / "pipelines")
    artifact_root = runtime / "artifacts/v3/V3-MIG-015/run-1"
    result = artifact_root / "factory_repair/backend-result.json"
    result.parent.mkdir(parents=True)
    result.write_text('{"error":"ordinary test failure"}', encoding="utf-8")
    checkpoints.save_v3(_checkpoint(artifact_root))

    assert recover_repaired_claude_sandbox_blocks(
        collection=WorkItemCollection(
            active_milestone="M0_FACTORY_MIGRATED", work_items=[item]
        ),
        queue=queue,
        checkpoints=checkpoints,
        runtime_root=runtime,
        current_main_sha=NEW_SHA,
        now=datetime.now(UTC),
    ) == []
    assert queue.load("V3-MIG-015").status is WorkStatus.BLOCKED_TECHNICAL
    assert checkpoints.load_v3("V3-MIG-015") is not None
