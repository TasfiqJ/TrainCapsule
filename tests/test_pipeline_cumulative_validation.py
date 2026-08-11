from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.config import load_factory_config, load_task
from tcfactory.gates import PathPolicyError
from tcfactory.gitops import Worktree
from tcfactory.models import Gate, RiskTier, RoleName, Stage, TaskPacket
from tcfactory.pipeline import (
    cumulative_scope_gaps,
    validate_cumulative_candidate,
    validate_release_candidate,
)
from tcfactory.quality_policy import QualityPolicyError

ROOT = Path(__file__).resolve().parents[1]


def test_cumulative_validation_scans_from_original_task_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_task(ROOT / "tasks/T002.yaml")
    starting_sha = "a" * 40
    scanned: list[str] = []

    def changed(_worktree: Path, base_sha: str) -> list[str]:
        scanned.append(base_sha)
        return []

    monkeypatch.setattr("tcfactory.pipeline.changed_files", changed)

    def reject_hidden_partial(**kwargs: object) -> dict[str, object]:
        assert kwargs["base_sha"] == starting_sha
        raise QualityPolicyError("preserved partial candidate weakened an existing test")

    monkeypatch.setattr("tcfactory.pipeline.enforce_candidate_quality", reject_hidden_partial)

    with pytest.raises(QualityPolicyError, match="preserved partial candidate"):
        validate_cumulative_candidate(
            worktree=tmp_path,
            starting_sha=starting_sha,
            task=task,
            artifact_dir=tmp_path / "artifacts",
        )

    assert scanned == [starting_sha]


def test_cumulative_scope_rejects_a_path_outside_every_mutating_stage() -> None:
    task = load_task(ROOT / "tasks/T002.yaml")

    assert cumulative_scope_gaps(
        task,
        [
            "docs/research/T002_name_trademark_check.md",
            "scripts/gates/output_and_integration_gate.py",
        ],
    ) == ["scripts/gates/output_and_integration_gate.py"]


def test_cumulative_scope_accepts_authorized_factory_repair_changes() -> None:
    task = TaskPacket(
        task_id="FACTORY_REPAIR_1",
        title="Repair the controller",
        phase="Factory repair",
        goal="Restore the loop",
        source_of_truth=["README.md"],
        acceptance_criteria=["Repair is verified"],
        outputs=["tcfactory/**"],
        stop_conditions=["Repair is unsafe"],
        gates=[Gate(name="quality", command="bash scripts/gates/fast_quality.sh")],
        pipeline=[
            Stage(
                role=RoleName.FACTORY_REPAIR,
                allowed_paths=["tcfactory/**"],
                forbidden_paths=["tcfactory/billing.py"],
                require_changes=True,
            )
        ],
        risk_tier=RiskTier.TRUST_CORE,
    )
    assert cumulative_scope_gaps(task, ["tcfactory/pipeline.py"]) == []


def test_cumulative_scope_failure_runs_before_quality_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_task(ROOT / "tasks/T002.yaml")
    def changed(_worktree: Path, _base_sha: str) -> list[str]:
        return ["scripts/gates/output_and_integration_gate.py"]

    monkeypatch.setattr("tcfactory.pipeline.changed_files", changed)
    quality_called = False

    def quality(**_kwargs: object) -> dict[str, object]:
        nonlocal quality_called
        quality_called = True
        return {}

    monkeypatch.setattr("tcfactory.pipeline.enforce_candidate_quality", quality)

    with pytest.raises(PathPolicyError, match="outside every writable task stage"):
        validate_cumulative_candidate(
            worktree=tmp_path,
            starting_sha="a" * 40,
            task=task,
            artifact_dir=tmp_path / "artifacts",
        )

    assert quality_called is False


def test_pre_release_validation_reuses_original_starting_sha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    task = load_task(ROOT / "tasks/T002.yaml")
    config = load_factory_config(ROOT / "config/factory.yaml")
    starting_sha = "a" * 40
    candidate_sha = "b" * 40
    worktree = Worktree(path=tmp_path / "candidate", branch="candidate", base_sha=candidate_sha)
    worktree.path.mkdir()
    observed: list[tuple[str, str]] = []

    def create(*_args: object, **_kwargs: object) -> Worktree:
        return worktree

    def cleanup(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("tcfactory.pipeline.create_worktree", create)
    monkeypatch.setattr("tcfactory.pipeline.cleanup_worktree", cleanup)

    def validate(**kwargs: object) -> list[str]:
        observed.append((str(kwargs["starting_sha"]), str(kwargs["worktree"])))
        return []

    monkeypatch.setattr("tcfactory.pipeline.validate_cumulative_candidate", validate)

    validate_release_candidate(
        repo_root=tmp_path,
        config=config,
        task=task,
        starting_sha=starting_sha,
        candidate_sha=candidate_sha,
        run_id="20260811T010000Z",
    )

    assert observed == [(starting_sha, str(worktree.path))]
