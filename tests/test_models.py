from pathlib import Path

from tcfactory.config import load_task
from tcfactory.models import RoleName


def test_demo_task_loads() -> None:
    task = load_task(Path("tasks/DEMO-001.yaml"))
    assert task.task_id == "DEMO-001"
    assert [stage.role for stage in task.pipeline] == [
        RoleName.SPECIFICATION,
        RoleName.BUILDER,
        RoleName.ADVERSARY,
        RoleName.AUDIT,
        RoleName.RELEASE,
    ]
    builder = next(stage for stage in task.pipeline if stage.role == RoleName.BUILDER)
    assert builder.tools is not None
    assert "Bash" in builder.tools
    expected_calibration_budgets = {
        RoleName.SPECIFICATION: 60_000,
        RoleName.BUILDER: 90_000,
        RoleName.ADVERSARY: 50_000,
        RoleName.AUDIT: 50_000,
        RoleName.RELEASE: 50_000,
    }
    assert {stage.role: stage.task_budget_tokens for stage in task.pipeline} == (
        expected_calibration_budgets
    )
    for stage in task.pipeline:
        if stage.machine_gates:
            assert stage.tools is not None
            assert "Bash" in stage.tools


def test_t001_has_no_builder() -> None:
    task = load_task(Path("tasks/T001.yaml"))
    assert RoleName.BUILDER not in {stage.role for stage in task.pipeline}
