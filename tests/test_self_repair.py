import json
from datetime import UTC, datetime
from pathlib import Path

from tcfactory.models import AutonomyConfig, RoleName
from tcfactory.self_repair import (
    build_self_repair_task,
    clear_hard_stuck,
    write_hard_stuck,
)


def test_self_repair_can_change_loop_but_not_billing_or_gates() -> None:
    task = build_self_repair_task(
        reason="RuntimeError: controller failed",
        attempt=1,
        task_id="FACTORY_REPAIR_TEST_1",
    )
    recovery = next(stage for stage in task.pipeline if stage.role == RoleName.FACTORY_REPAIR)

    assert "tcfactory/**" in recovery.allowed_paths
    assert "scripts/windows_task_entrypoint.sh" in recovery.allowed_paths
    assert "tcfactory/auth.py" in recovery.forbidden_paths
    assert "scripts/gates/**" in recovery.forbidden_paths
    assert "config/**" in recovery.forbidden_paths
    assert {gate.name for gate in task.gates} == {
        "no-paid-usage",
        "secret-scan",
        "fast-quality",
        "self-repair-scope",
    }
    assert task.auto_merge is True
    assert task.github_push is False


def test_critical_self_repair_starts_with_opus_and_mixes_repair_models() -> None:
    task = build_self_repair_task(
        reason="hard controller failure",
        attempt=2,
        task_id="FACTORY_REPAIR_TEST_2",
    )

    assert task.pipeline[0].model == "opus"
    assert task.pipeline[0].role == RoleName.FACTORY_REPAIR
    assert task.pipeline[1].model == "opus"
    assert task.pipeline[-1].model == "sonnet"
    assert task.repair.mutating_role == RoleName.FACTORY_REPAIR
    assert task.repair.builder_models == ["sonnet", "opus", "sonnet", "opus"]
    assert task.repair.mutating_retry_models == ["sonnet", "opus", "sonnet"]
    assert task.repair.max_cycles == 4


def test_hard_stuck_is_written_before_pause_and_can_be_cleared(tmp_path: Path) -> None:
    autonomy = AutonomyConfig()

    path = write_hard_stuck(
        repo_root=tmp_path,
        autonomy=autonomy,
        reason="controller failed",
        required_action="inspect evidence",
        attempts=3,
        artifact_path="factory/recovery/self-repair/result.json",
        auto_retry_at=datetime(2026, 8, 10, 16, 0, tzinfo=UTC),
    )
    record = json.loads(path.read_text(encoding="utf-8"))

    assert record["status"] == "hard_stuck"
    assert record["reason"] == "controller failed"
    assert record["required_action"] == "inspect evidence"
    assert record["paid_usage_allowed"] is False
    assert record["auto_retry_at"] == "2026-08-10T16:00:00+00:00"

    clear_hard_stuck(tmp_path, autonomy)
    assert not path.exists()
