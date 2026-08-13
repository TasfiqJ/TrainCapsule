from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .models import CommitType, TaskPacket
from .util import run_command, slugify

_RUNTIME_ONLY_GIT_PATHS = (
    ":(exclude,top).mcp.json",
    ":(exclude,top)factory/.mcp.json",
    ":(exclude,top)factory/.claude/**",
)


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str
    base_sha: str


class GitError(RuntimeError):
    pass


_CLAUDE_SANDBOX_SENTINELS = frozenset(
    {
        ".gitmodules",
        ".npmrc",
        ".yarnrc",
        ".yarnrc.yml",
        "bunfig.toml",
        "package-lock.json",
        "package.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)


def ensure_git_repo(repo_root: Path) -> None:
    try:
        run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo_root)
    except Exception as exc:  # noqa: BLE001
        raise GitError(f"Not a git repository: {repo_root}") from exc


def current_sha(repo_root: Path, ref: str = "HEAD") -> str:
    return run_command(["git", "rev-parse", ref], cwd=repo_root).stdout.strip()


def current_branch(repo_root: Path) -> str:
    return run_command(["git", "branch", "--show-current"], cwd=repo_root).stdout.strip()


def is_clean(repo_root: Path) -> bool:
    return not run_command(["git", "status", "--porcelain"], cwd=repo_root).stdout.strip()


def git_identity(repo_root: Path) -> tuple[str, str]:
    name = run_command(["git", "config", "user.name"], cwd=repo_root, check=False).stdout.strip()
    email = run_command(["git", "config", "user.email"], cwd=repo_root, check=False).stdout.strip()
    if not name or not email:
        raise GitError(
            "Git user.name and user.email must be configured during one-time setup. "
            "The factory never invents a fake author identity."
        )
    return name, email


def create_worktree(
    repo_root: Path,
    worktree_root: Path,
    *,
    task_id: str,
    run_id: str,
    role: str,
    attempt: int,
    base_sha: str,
) -> Worktree:
    branch = slugify(f"factory/{task_id}-{run_id}-{role}-a{attempt}")
    path = worktree_root / slugify(f"{task_id}-{run_id}-{role}-a{attempt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.rmtree(path)
    run_command(
        ["git", "worktree", "add", "-b", branch, str(path), base_sha],
        cwd=repo_root,
    )
    return Worktree(path=path, branch=branch, base_sha=base_sha)


def changed_files(worktree: Path, base_sha: str) -> list[str]:
    committed = run_command(
        ["git", "diff", "--name-only", f"{base_sha}...HEAD"], cwd=worktree
    ).stdout.splitlines()
    uncommitted = run_command(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree
    ).stdout.splitlines()
    paths = set(committed)
    for line in uncommitted:
        if len(line) >= 4:
            paths.add(line[3:].strip())

    def is_empty_untracked_sandbox_sentinel(path: str) -> bool:
        if path not in _CLAUDE_SANDBOX_SENTINELS:
            return False
        candidate = worktree / path
        if not candidate.is_file() or candidate.stat().st_size != 0:
            return False
        tracked = run_command(
            ["git", "cat-file", "-e", f"{base_sha}:{path}"],
            cwd=worktree,
            check=False,
        )
        if tracked.returncode == 0:
            return False
        candidate.unlink()
        return True

    return sorted(path for path in paths if path and not is_empty_untracked_sandbox_sentinel(path))


def commit_all(worktree: Path, message: str) -> str | None:
    pathspecs = [".", *_RUNTIME_ONLY_GIT_PATHS]
    status = run_command(
        ["git", "status", "--porcelain", "--", *pathspecs], cwd=worktree
    ).stdout.strip()
    if not status:
        return current_sha(worktree)
    git_identity(worktree)
    run_command(["git", "add", "-A", "--", *pathspecs], cwd=worktree)
    run_command(["git", "commit", "-m", message], cwd=worktree)
    return current_sha(worktree)


def cleanup_worktree(repo_root: Path, worktree: Worktree, *, delete_branch: bool = False) -> None:
    if worktree.path.exists():
        run_command(
            ["git", "worktree", "remove", "--force", str(worktree.path)],
            cwd=repo_root,
            check=False,
        )
    run_command(["git", "worktree", "prune"], cwd=repo_root, check=False)
    if delete_branch:
        run_command(["git", "branch", "-D", worktree.branch], cwd=repo_root, check=False)


def transplant_candidate_onto(
    repo_root: Path,
    worktree_root: Path,
    *,
    task_id: str,
    run_id: str,
    original_base_sha: str,
    candidate_sha: str,
    new_base_sha: str,
) -> str:
    """Replay only a task candidate's delta onto a repaired controller revision.

    Reusing the old candidate tree would erase the controller repair, while starting over would
    discard valid product work. Applying the exact old-base-to-candidate delta onto repaired main
    preserves both and fails closed when the changes genuinely conflict.
    """

    if candidate_sha == original_base_sha:
        return new_base_sha
    patch = run_command(
        [
            "git",
            "diff",
            "--binary",
            "--full-index",
            original_base_sha,
            candidate_sha,
            "--",
        ],
        cwd=repo_root,
    ).stdout
    if not patch.strip():
        return new_base_sha
    worktree = create_worktree(
        repo_root,
        worktree_root,
        task_id=task_id,
        run_id=run_id,
        role="controller-recovery",
        attempt=1,
        base_sha=new_base_sha,
    )
    try:
        applied = run_command(
            ["git", "apply", "--3way", "--index", "-"],
            cwd=worktree.path,
            check=False,
            input_text=patch,
        )
        if applied.returncode != 0:
            detail = (applied.stderr or applied.stdout).strip()
            raise GitError(
                "Could not transplant the preserved candidate onto repaired main without a "
                f"conflict: {detail or 'git apply failed'}"
            )
        recovered_sha = commit_all(
            worktree.path,
            f"recover: preserve {task_id.lower()} candidate after controller repair",
        )
        if not recovered_sha:
            raise GitError("Candidate transplant produced no recoverable commit")
        return recovered_sha
    finally:
        cleanup_worktree(repo_root, worktree, delete_branch=False)


def _clean_words(value: str) -> str:
    text = re.sub(r"[`*_#:\[\](){}]", " ", value)
    text = re.sub(
        r"\b(TrainCapsule|Matrix|task|feature|implement|implementation)\b", " ", text, flags=re.I
    )
    text = re.sub(r"[^A-Za-z0-9._/-]+", " ", text)
    return " ".join(text.split()).strip().lower()


def short_commit_subject(task: TaskPacket, *, max_chars: int = 50) -> str:
    if task.commit_subject:
        subject = _clean_words(task.commit_subject)
    else:
        verb = {
            CommitType.FEAT: "add",
            CommitType.FIX: "fix",
            CommitType.TEST: "test",
            CommitType.DOCS: "update",
            CommitType.CHORE: "update",
            CommitType.REFACTOR: "refactor",
            CommitType.PERF: "speed up",
            CommitType.BUILD: "update",
            CommitType.CI: "update ci",
            CommitType.SPEC: "define",
        }[task.commit_type]
        body = _clean_words(task.title)
        subject = body if body.startswith(verb + " ") else f"{verb} {body}".strip()
    subject = subject.rstrip(". ") or f"update {task.task_id.lower()}"
    if len(subject) <= max_chars:
        return subject
    clipped = subject[: max_chars + 1].rsplit(" ", 1)[0].rstrip("-_/ ")
    return clipped or subject[:max_chars]


def task_commit_message(task: TaskPacket, *, run_id: str) -> str:
    del run_id  # Detailed provenance is stored locally, not in the public commit subject.
    return short_commit_subject(task, max_chars=50)


def squash_candidate(
    repo_root: Path,
    *,
    task: TaskPacket,
    run_id: str,
    starting_sha: str,
    candidate_sha: str,
) -> str:
    """Create one direct-child release commit with the candidate tree.

    Internal role commits remain disposable evidence. Main receives one short, human-readable
    task commit authored with the operator's configured Git identity.
    """

    if candidate_sha == starting_sha:
        return candidate_sha
    git_identity(repo_root)
    tree = current_sha(repo_root, f"{candidate_sha}^{{tree}}")
    message = task_commit_message(task, run_id=run_id)
    result = run_command(
        ["git", "commit-tree", tree, "-p", starting_sha],
        cwd=repo_root,
        input_text=message,
    )
    release_sha = result.stdout.strip()
    if not release_sha:
        raise GitError("git commit-tree did not return a release commit")
    release_tree = current_sha(repo_root, f"{release_sha}^{{tree}}")
    if release_tree != tree:
        raise GitError("Squashed release commit does not preserve the verified candidate tree")
    return release_sha


def cleanup_task_branches(repo_root: Path, *, task_id: str, run_id: str) -> None:
    prefix = slugify(f"factory/{task_id}-{run_id}")
    branches = run_command(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/factory"],
        cwd=repo_root,
        check=False,
    ).stdout.splitlines()
    for branch in branches:
        if branch.startswith(prefix):
            run_command(["git", "branch", "-D", branch], cwd=repo_root, check=False)
    run_command(["git", "worktree", "prune"], cwd=repo_root, check=False)


def remote_exists(repo_root: Path, name: str = "origin") -> bool:
    result = run_command(["git", "remote", "get-url", name], cwd=repo_root, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def configured_identity(repo_root: Path) -> tuple[str, str]:
    name = run_command(["git", "config", "user.name"], cwd=repo_root, check=False).stdout.strip()
    email = run_command(["git", "config", "user.email"], cwd=repo_root, check=False).stdout.strip()
    if not name or not email:
        raise GitError("Git identity is incomplete. Configure user.name and user.email.")
    return name, email
