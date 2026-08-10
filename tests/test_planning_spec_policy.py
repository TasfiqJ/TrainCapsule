"""Regression tests for planner task-specification path classification.

`tcfactory.risk.planning_pipeline` mandates `specs/tasks/<TASK_ID>.md` as a
writable planner output, but the quality policy classified every path under
`specs/` as a test. Re-planning an existing task therefore failed with
"Task is not authorized to modify existing tests" and, on integration/trust-core
tiers, "Integration/trust-core test changes require an external private gate",
which no planner attempt could satisfy. These tests pin the narrow exemption and
its negative controls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import PrivateGate, RiskTier, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.quality_policy import QualityPolicyError, enforce_candidate_quality, scan_candidate
from tcfactory.util import run_command


def _repo(path: Path) -> str:
    run_command(["git", "init", "-b", "main"], cwd=path)
    run_command(["git", "config", "user.name", "Test User"], cwd=path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=path)
    (path / "app.py").write_text("x = 1\n")
    commit_all(path, "start")
    return current_sha(path)


def _planner_task(**updates: object) -> TaskPacket:
    packet = TaskPacket(
        task_id="T002",
        title="plan",
        phase="planning",
        goal="plan",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["specs/tasks/T002.md"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        allow_test_changes=False,
        private_gate=PrivateGate(required=False),
        pipeline=[
            Stage(
                role=RoleName.PLANNER,
                allowed_paths=["factory/proposals/T002.yaml", "specs/tasks/T002.md"],
            )
        ],
    )
    return packet.model_copy(update=updates)


def _write_spec(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)


def test_replanning_existing_task_spec_is_not_a_test_change(tmp_path: Path) -> None:
    """The exact PLAN_T002_R1 failure: rewriting an already-committed task spec."""
    _repo(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002.md", "# T002\n\nFirst plan.\n")
    commit_all(tmp_path, "plan T002")
    base = current_sha(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002.md", "# T002\n\nRevised plan.\n")
    (tmp_path / "factory/proposals").mkdir(parents=True)
    (tmp_path / "factory/proposals/T002.yaml").write_text("task_id: T002\n")

    report = enforce_candidate_quality(
        worktree=tmp_path,
        base_sha=base,
        task=_planner_task(risk_tier=RiskTier.TRUST_CORE),
        artifact_dir=tmp_path / "artifacts",
    )

    assert "specs/tasks/T002.md" in report["changed_files"]
    assert report["test_changes"] == []
    assert report["existing_test_changes"] == []
    assert report["new_test_files"] == []
    assert report["passed"] is True


def test_new_task_spec_does_not_require_a_private_gate(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002.md", "# T002\n\nFirst plan.\n")

    report = enforce_candidate_quality(
        worktree=tmp_path,
        base_sha=base,
        task=_planner_task(risk_tier=RiskTier.INTEGRATION),
        artifact_dir=tmp_path / "artifacts",
    )

    assert report["test_changes"] == []
    assert report["passed"] is True


def test_executable_spec_under_specs_tasks_is_still_a_guarded_test(tmp_path: Path) -> None:
    """Negative control: the exemption is limited to markdown planning documents."""
    _repo(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002_spec.py", "def test_x():\n    assert 1 == 1\n")
    commit_all(tmp_path, "add spec test")
    base = current_sha(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002_spec.py", "def test_x():\n    assert 2 == 2\n")

    with pytest.raises(QualityPolicyError, match="existing tests"):
        enforce_candidate_quality(
            worktree=tmp_path,
            base_sha=base,
            task=_planner_task(),
            artifact_dir=tmp_path / "artifacts",
        )


def test_markdown_elsewhere_under_specs_is_still_a_guarded_test(tmp_path: Path) -> None:
    """Negative control: only the controller-owned `specs/tasks/*.md` slot is exempt."""
    base = _repo(tmp_path)
    _write_spec(tmp_path / "specs/oracle/expected.md", "expected output\n")

    report = scan_candidate(
        worktree=tmp_path,
        base_sha=base,
        task=_planner_task(risk_tier=RiskTier.TRUST_CORE),
        artifact_dir=tmp_path / "artifacts",
    )

    assert report["test_changes"] == ["specs/oracle/expected.md"]
    assert any("private gate" in violation for violation in report["violations"])


def test_nested_task_spec_directory_is_still_a_guarded_test(tmp_path: Path) -> None:
    """Negative control: the exemption does not recurse below `specs/tasks/`."""
    base = _repo(tmp_path)
    _write_spec(tmp_path / "specs/tasks/T002/cases.md", "case\n")

    report = scan_candidate(
        worktree=tmp_path,
        base_sha=base,
        task=_planner_task(risk_tier=RiskTier.TRUST_CORE),
        artifact_dir=tmp_path / "artifacts",
    )

    assert report["test_changes"] == ["specs/tasks/T002/cases.md"]
    assert any("private gate" in violation for violation in report["violations"])


def test_ordinary_test_paths_remain_guarded(tmp_path: Path) -> None:
    """Negative control: the ordinary test-authority gate is unchanged."""
    _repo(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_old.py").write_text("def test_x():\n    assert 1 == 1\n")
    commit_all(tmp_path, "add test")
    base = current_sha(tmp_path)
    (tmp_path / "tests/test_old.py").write_text("def test_x():\n    assert 2 == 2\n")

    with pytest.raises(QualityPolicyError, match="existing tests"):
        enforce_candidate_quality(
            worktree=tmp_path,
            base_sha=base,
            task=_planner_task(),
            artifact_dir=tmp_path / "artifacts",
        )
