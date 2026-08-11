from __future__ import annotations

from pathlib import Path

from tcfactory.config import load_task
from tcfactory.models import RoleName
from tcfactory.pipeline import (
    controller_owned_finding_paths,
    find_mutating_stage_for_findings,
    repository_finding_paths,
)

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> Path:
    for relative in (
        "docs/research/T002_name_trademark_check.md",
        "docs/evidence/T002/manifest.json",
        "scripts/gates/output_and_integration_gate.py",
        "tasks/T002.yaml",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    return tmp_path


def test_reviewer_paths_outside_every_mutator_force_respecification(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_task(ROOT / "tasks/T002.yaml")
    findings = [
        "BLOCKING: scripts/gates/output_and_integration_gate.py:66 accepts false clear.",
        "Controller must update tasks/T002.yaml before retrying research.",
    ]

    stage, gaps = find_mutating_stage_for_findings(
        repo_root=repo,
        task=task,
        findings=findings,
    )

    assert stage.role == RoleName.RESEARCH
    assert gaps == ["scripts/gates/output_and_integration_gate.py", "tasks/T002.yaml"]
    assert repository_finding_paths(repo, findings) == gaps


def test_repair_routes_to_a_writable_stage_covering_reviewer_paths(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_task(ROOT / "tasks/T002.yaml")
    research = task.pipeline[0]
    builder = research.model_copy(
        update={
            "role": RoleName.BUILDER,
            "allowed_paths": ["scripts/gates/**", "tasks/**"],
            "forbidden_paths": [],
            "read_only": False,
        }
    )
    routed_task = task.model_copy(update={"pipeline": [builder, *task.pipeline]})

    stage, gaps = find_mutating_stage_for_findings(
        repo_root=repo,
        task=routed_task,
        findings=["Fix scripts/gates/output_and_integration_gate.py and tasks/T002.yaml."],
    )

    assert stage.role == RoleName.BUILDER
    assert gaps == []


def test_repair_requires_one_stage_to_cover_every_reviewer_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_task(ROOT / "tasks/T002.yaml")
    research = task.pipeline[0]
    builder = research.model_copy(
        update={
            "role": RoleName.BUILDER,
            "allowed_paths": ["scripts/gates/**"],
            "forbidden_paths": [],
            "read_only": False,
        }
    )
    routed_task = task.model_copy(update={"pipeline": [builder, *task.pipeline]})

    stage, gaps = find_mutating_stage_for_findings(
        repo_root=repo,
        task=routed_task,
        findings=[
            "Fix scripts/gates/output_and_integration_gate.py and "
            "docs/research/T002_name_trademark_check.md."
        ],
    )

    assert stage.role == RoleName.BUILDER
    assert gaps == ["docs/research/T002_name_trademark_check.md"]


def test_repair_routing_respects_forbidden_paths(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_task(ROOT / "tasks/T002.yaml")
    research = task.pipeline[0]
    builder = research.model_copy(
        update={
            "role": RoleName.BUILDER,
            "allowed_paths": ["scripts/gates/**", "tasks/**"],
            "forbidden_paths": ["scripts/gates/output_and_integration_gate.py"],
            "read_only": False,
        }
    )
    routed_task = task.model_copy(update={"pipeline": [builder, *task.pipeline]})

    stage, gaps = find_mutating_stage_for_findings(
        repo_root=repo,
        task=routed_task,
        findings=["Fix scripts/gates/output_and_integration_gate.py and tasks/T002.yaml."],
    )

    assert stage.role == RoleName.BUILDER
    assert gaps == ["scripts/gates/output_and_integration_gate.py"]


def test_recursive_allowed_path_covers_a_cited_directory_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    task = load_task(ROOT / "tasks/T002.yaml")

    stage, gaps = find_mutating_stage_for_findings(
        repo_root=repo,
        task=task,
        findings=["Repair the evidence bundle at docs/evidence/T002 before review."],
    )

    assert stage.role == RoleName.RESEARCH
    assert gaps == []


def test_controller_owned_gaps_are_separated_from_respecifiable_paths() -> None:
    paths = [
        "scripts/gates",
        "tcfactory/research_policy.py",
        "specs/tasks/T002.md",
    ]

    assert controller_owned_finding_paths(paths) == [
        "scripts/gates",
        "tcfactory/research_policy.py",
    ]
