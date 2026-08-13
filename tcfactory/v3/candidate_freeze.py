"""Fail-closed observation of an immutable Git candidate worktree."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from tcfactory.util import run_command
from tcfactory.v3.base import SHA_PATTERN


class CandidateFreezeError(RuntimeError):
    """The candidate worktree no longer represents its reviewed commit and tree."""


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    candidate_sha: str
    candidate_tree_sha: str


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise CandidateFreezeError("candidate worktree is unavailable") from exc
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise CandidateFreezeError("candidate worktree must be a non-symlink directory")
    return observed.st_dev, observed.st_ino


def _git_value(worktree: Path, arguments: list[str], *, label: str) -> str:
    observed = run_command(["git", *arguments], cwd=worktree, check=False)
    value = observed.stdout.strip()
    if observed.returncode != 0:
        raise CandidateFreezeError(f"candidate {label} is unavailable")
    return value


def assert_frozen_candidate(
    worktree: Path,
    *,
    expected_candidate_sha: str,
    expected_candidate_tree_sha: str | None = None,
) -> FrozenCandidate:
    """Observe a clean exact-HEAD candidate twice across a stable directory identity.

    The second status and directory-identity observations close mutations that race
    the first status/identity read. Callers must invoke this immediately before each
    publication side effect as well as after every evidence-producing action.
    """

    if SHA_PATTERN.fullmatch(expected_candidate_sha) is None:
        raise CandidateFreezeError("expected candidate SHA is invalid")
    if (
        expected_candidate_tree_sha is not None
        and SHA_PATTERN.fullmatch(expected_candidate_tree_sha) is None
    ):
        raise CandidateFreezeError("expected candidate tree SHA is invalid")
    candidate = worktree.absolute()
    before_identity = _directory_identity(candidate)
    dirty_before = _git_value(
        candidate,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        label="status",
    )
    head = _git_value(candidate, ["rev-parse", "HEAD"], label="HEAD")
    tree = _git_value(candidate, ["rev-parse", "HEAD^{tree}"], label="tree")
    dirty_after = _git_value(
        candidate,
        ["status", "--porcelain=v1", "--untracked-files=all"],
        label="status",
    )
    after_identity = _directory_identity(candidate)
    if before_identity != after_identity:
        raise CandidateFreezeError(
            "candidate worktree directory identity changed during freeze check"
        )
    if dirty_before or dirty_after:
        raise CandidateFreezeError("candidate worktree is not clean and fully committed")
    if head != expected_candidate_sha:
        raise CandidateFreezeError("candidate HEAD differs from the reviewed candidate SHA")
    if expected_candidate_tree_sha is not None and tree != expected_candidate_tree_sha:
        raise CandidateFreezeError("candidate tree differs from the reviewed candidate tree")
    if SHA_PATTERN.fullmatch(tree) is None:
        raise CandidateFreezeError("candidate tree identity is invalid")
    return FrozenCandidate(candidate_sha=head, candidate_tree_sha=tree)


def quarantine_tainted_evidence(
    evidence: dict[str, Path], *, quarantine_root: Path, reason: str
) -> None:
    """Move controller-owned evidence out of the admissible evidence namespace."""

    quarantine_root.mkdir(parents=True, exist_ok=True)
    for index, (name, path) in enumerate(sorted(evidence.items()), start=1):
        if not path.is_file() or path.is_symlink():
            continue
        safe_name = "".join(character if character.isalnum() else "-" for character in name)
        target = quarantine_root / f"{index:02d}-{safe_name}.tainted"
        try:
            os.replace(path, target)
        except OSError:
            # Evidence outside the controller artifact root is never trusted again;
            # preserve a bounded diagnostic copy when ownership prevents a move.
            target.write_bytes(path.read_bytes())
    (quarantine_root / "REASON.txt").write_text(reason + "\n", encoding="utf-8")
