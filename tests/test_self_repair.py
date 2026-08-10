import json
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
    recovery = next(stage for stage in task.pipeline if stage.role == RoleName.RECOVERY)

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


def test_harder_self_repair_escalates_only_the_repair_review_model() -> None:
    task = build_self_repair_task(
        reason="hard controller failure",
        attempt=2,
        task_id="FACTORY_REPAIR_TEST_2",
    )

    assert task.pipeline[0].model == "opus"
    assert task.pipeline[1].model == "opus"
    assert task.pipeline[-1].model == "sonnet"


def test_hard_stuck_is_written_before_pause_and_can_be_cleared(tmp_path: Path) -> None:
    autonomy = AutonomyConfig()

    path = write_hard_stuck(
        repo_root=tmp_path,
        autonomy=autonomy,
        reason="controller failed",
        required_action="inspect evidence",
        attempts=3,
        artifact_path="factory/recovery/self-repair/result.json",
    )
    record = json.loads(path.read_text(encoding="utf-8"))

    assert record["status"] == "hard_stuck"
    assert record["reason"] == "controller failed"
    assert record["required_action"] == "inspect evidence"
    assert record["paid_usage_allowed"] is False

    clear_hard_stuck(tmp_path, autonomy)
    assert not path.exists()
