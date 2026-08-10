from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.gitops import (
    GitError,
    changed_files,
    commit_all,
    current_sha,
    squash_candidate,
    task_commit_message,
    transplant_candidate_onto,
)
from tcfactory.models import CommitType, RoleName, SecurityPolicy, Stage, TaskPacket
from tcfactory.util import run_command


def _init_repo(path: Path) -> str:
    run_command(["git", "init", "-b", "main"], cwd=path)
    run_command(["git", "config", "user.name", "Test User"], cwd=path)
    run_command(["git", "config", "user.email", "test@example.com"], cwd=path)
    (path / "a.txt").write_text("base\n")
    commit_all(path, "start")
    return current_sha(path)


def _task() -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="Implement an unnecessarily verbose evidence exchange endpoint",
        phase="test",
        goal="test",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["a.txt"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["a.txt"])],
        commit_type=CommitType.FEAT,
    )


def test_commit_all_uses_operator_identity(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "b.txt").write_text("value\n")
    sha = commit_all(tmp_path, "add file")
    assert sha
    author = run_command(
        ["git", "show", "-s", "--format=%an <%ae>", sha], cwd=tmp_path
    ).stdout.strip()
    assert author == "Test User <test@example.com>"


def test_changed_files_expands_directories_and_filters_only_empty_sentinels(
    tmp_path: Path,
) -> None:
    base = _init_repo(tmp_path)
    spec = tmp_path / "specs" / "tasks" / "DEMO-001.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("specification\n", encoding="utf-8")
    (tmp_path / ".npmrc").write_text("", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("real change\n", encoding="utf-8")

    assert changed_files(tmp_path, base) == ["package-lock.json", "specs/tasks/DEMO-001.md"]
    assert not (tmp_path / ".npmrc").exists()


def test_squash_candidate_creates_one_direct_child_with_same_tree(tmp_path: Path) -> None:
    base = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("candidate\n")
    candidate = commit_all(tmp_path, "internal builder commit")
    assert candidate
    release = squash_candidate(
        tmp_path,
        task=_task(),
        run_id="20260807T000000Z",
        starting_sha=base,
        candidate_sha=candidate,
    )
    parent = current_sha(tmp_path, f"{release}^")
    assert parent == base
    assert current_sha(tmp_path, f"{release}^{{tree}}") == current_sha(
        tmp_path, f"{candidate}^{{tree}}"
    )
    subject = run_command(
        ["git", "show", "-s", "--format=%s", release], cwd=tmp_path
    ).stdout.strip()
    assert len(subject) <= 50
    assert ":" not in subject
    assert subject == task_commit_message(_task(), run_id="20260807T000000Z")
    author = run_command(
        ["git", "show", "-s", "--format=%an <%ae>", release], cwd=tmp_path
    ).stdout.strip()
    assert author == "Test User <test@example.com>"


def test_transplant_candidate_preserves_product_work_and_repaired_main(tmp_path: Path) -> None:
    base = _init_repo(tmp_path)
    (tmp_path / "product.txt").write_text("candidate\n", encoding="utf-8")
    candidate = commit_all(tmp_path, "partial product candidate")
    assert candidate
    run_command(["git", "reset", "--hard", base], cwd=tmp_path)
    (tmp_path / "controller.txt").write_text("repair\n", encoding="utf-8")
    repaired_main = commit_all(tmp_path, "repair controller")
    assert repaired_main

    recovered = transplant_candidate_onto(
        tmp_path,
        tmp_path / "worktrees",
        task_id="T001",
        run_id="20260810T000000Z",
        original_base_sha=base,
        candidate_sha=candidate,
        new_base_sha=repaired_main,
    )

    assert current_sha(tmp_path, f"{recovered}^") == repaired_main
    assert run_command(["git", "show", f"{recovered}:product.txt"], cwd=tmp_path).stdout == (
        "candidate\n"
    )
    assert run_command(["git", "show", f"{recovered}:controller.txt"], cwd=tmp_path).stdout == (
        "repair\n"
    )


def test_transplant_candidate_fails_closed_on_real_conflict(tmp_path: Path) -> None:
    base = _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("candidate\n", encoding="utf-8")
    candidate = commit_all(tmp_path, "partial product candidate")
    assert candidate
    run_command(["git", "reset", "--hard", base], cwd=tmp_path)
    (tmp_path / "a.txt").write_text("controller repair\n", encoding="utf-8")
    repaired_main = commit_all(tmp_path, "repair controller")
    assert repaired_main

    with pytest.raises(GitError, match="without a conflict"):
        transplant_candidate_onto(
            tmp_path,
            tmp_path / "worktrees",
            task_id="T001",
            run_id="20260810T000001Z",
            original_base_sha=base,
            candidate_sha=candidate,
            new_base_sha=repaired_main,
        )
