from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.gitops import commit_all, current_sha
from tcfactory.models import PrivateGate, RiskTier, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.quality_policy import QualityPolicyError, enforce_candidate_quality
from tcfactory.util import run_command


def _repo(path: Path) -> str:
    run_command(["git", "init", "-b", "main"], cwd=path)
    run_command(["git", "config", "user.name", "Test User"], cwd=path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=path)
    (path / "app.py").write_text("x = 1\n")
    commit_all(path, "start")
    return current_sha(path)


def _task(**updates: object) -> TaskPacket:
    packet = TaskPacket(
        task_id="T900",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["app.py", "tests/**"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["app.py", "tests/**"])],
    )
    return packet.model_copy(update=updates)


def test_new_test_file_is_encouraged_not_blocked(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_new.py").write_text("def test_x():\n    assert 1 == 1\n")
    report = enforce_candidate_quality(
        worktree=tmp_path,
        base_sha=base,
        task=_task(),
        artifact_dir=tmp_path / "artifacts",
    )
    assert report["new_test_files"] == ["tests/test_new.py"]


def test_existing_test_change_needs_authority(tmp_path: Path) -> None:
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
            task=_task(allow_test_changes=False),
            artifact_dir=tmp_path / "artifacts",
        )


def test_high_risk_test_change_requires_private_gate(tmp_path: Path) -> None:
    base = _repo(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_new.py").write_text("def test_x():\n    assert 1 == 1\n")
    with pytest.raises(QualityPolicyError, match="private gate"):
        enforce_candidate_quality(
            worktree=tmp_path,
            base_sha=base,
            task=_task(risk_tier=RiskTier.TRUST_CORE, private_gate=PrivateGate(required=False)),
            artifact_dir=tmp_path / "artifacts",
        )
