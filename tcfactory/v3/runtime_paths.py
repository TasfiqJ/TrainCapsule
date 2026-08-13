"""Single source of truth for all mutable V3 runtime paths."""

from __future__ import annotations

import fcntl
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from .base import V3Model
from .configuration import FactoryV3Config, load_factory_v3


class V3RuntimePaths(V3Model):
    state_root: Path
    queue: Path
    checkpoints: Path
    controller_state: Path
    scheduler_decisions: Path
    milestone_state: Path
    milestone_evidence: Path
    milestone_decisions: Path
    machine_policy_receipts: Path
    source_proposals: Path
    value_redesign_proposals: Path
    quarantine: Path
    canary_results: Path
    activation_transactions: Path
    control_archive: Path
    migration_marker: Path
    supervisor_state: Path
    supervisor_lock: Path
    controller_lock: Path
    hard_stuck: Path
    stop: Path
    pause: Path
    git_root: Path
    worktree_root: Path
    artifact_root: Path


def resolve_v3_runtime_paths(
    repo_root: Path, config: FactoryV3Config | None = None
) -> V3RuntimePaths:
    """Resolve the configured V3 state root once for every runtime consumer."""

    root = repo_root.resolve()
    factory = config or load_factory_v3(root / "config" / "factory.yaml")
    raw_root = os.getenv(factory.runtime.local_state_root_environment_variable)
    if raw_root:
        state_root = Path(raw_root).expanduser()
        if not state_root.is_absolute():
            raise ValueError("configured runtime state root must be absolute")
        state_root = state_root.resolve()
    else:
        state_root = (root / "factory" / "state").resolve()
    return V3RuntimePaths(
        state_root=state_root,
        queue=state_root / "v3-queue",
        checkpoints=state_root / "pipelines",
        controller_state=state_root / "v3-controller.json",
        scheduler_decisions=state_root / "scheduler-decisions",
        milestone_state=state_root / "milestone-state.json",
        milestone_evidence=state_root / "milestone-evidence",
        milestone_decisions=state_root / "milestone-decisions",
        machine_policy_receipts=state_root / "machine-policy-receipts",
        source_proposals=state_root / "source-proposals",
        value_redesign_proposals=state_root / "value-redesign-proposals",
        quarantine=state_root / "quarantine",
        canary_results=state_root / "canary-results",
        activation_transactions=state_root / "activation-transactions",
        control_archive=state_root / "control-archive",
        migration_marker=state_root / factory.runtime.migration_complete_marker,
        supervisor_state=state_root / factory.runtime.supervisor_state_file,
        supervisor_lock=state_root / factory.runtime.supervisor_lock_file,
        controller_lock=state_root / "controller.lock",
        hard_stuck=state_root / factory.runtime.hard_stuck_file,
        stop=state_root / factory.runtime.stop_file,
        pause=state_root / "PAUSE",
        git_root=state_root / "git",
        worktree_root=state_root / "worktrees",
        artifact_root=state_root / "artifacts" / "v3",
    )


def _private_runtime_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != 0o700
    ):
        raise RuntimeError(f"mutable runtime directory is not private and owner-bound: {path}")


@contextmanager
def _anchor_lock(state_root: Path) -> Generator[None, None, None]:
    lock_path = state_root / "git-anchor.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        observed = os.fstat(descriptor)
        if observed.st_uid != os.geteuid() or stat.S_IMODE(observed.st_mode) != 0o600:
            raise RuntimeError("mutable Git anchor lock is not owner-bound")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )
    if result.returncode != 0:
        raise RuntimeError("mutable Git anchor validation failed")
    return result.stdout.strip()


def ensure_v3_mutable_runtime(
    repo_root: Path,
    paths: V3RuntimePaths,
    *,
    require_snapshot_alignment: bool = True,
) -> None:
    """Create an isolated controller-owned Git anchor and bounded mutable roots."""

    immutable = repo_root.resolve(strict=True)
    _private_runtime_directory(paths.state_root)
    _private_runtime_directory(paths.worktree_root)
    _private_runtime_directory(paths.artifact_root.parent)
    _private_runtime_directory(paths.artifact_root)
    if immutable == Path("/var/lib/traincapsule-verifier/repository-boundary"):
        for mutable in (paths.git_root, paths.worktree_root, paths.artifact_root):
            if mutable.resolve().is_relative_to(immutable):
                raise RuntimeError("installed mutable runtime escaped into the authority snapshot")
    with _anchor_lock(paths.state_root):
        if paths.git_root.exists():
            empty_entries = list(paths.git_root.iterdir()) if paths.git_root.is_dir() else []
            if empty_entries == []:
                observed_empty = paths.git_root.lstat()
                if (
                    paths.git_root.is_symlink()
                    or not stat.S_ISDIR(observed_empty.st_mode)
                    or observed_empty.st_uid != os.geteuid()
                    or stat.S_IMODE(observed_empty.st_mode) != 0o700
                ):
                    raise RuntimeError("empty mutable Git anchor is not private and owner-bound")
                paths.git_root.rmdir()
        if not paths.git_root.exists():
            with tempfile.TemporaryDirectory(
                prefix="git-anchor-stage-", dir=paths.state_root
            ) as raw_stage:
                stage = Path(raw_stage) / "anchor.git"
                clone = subprocess.run(
                    [
                        "/usr/bin/git",
                        "clone",
                        "--bare",
                        "--no-hardlinks",
                        "--no-local",
                        str(immutable),
                        str(stage),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    env={
                        "PATH": "/usr/bin:/bin",
                        "GIT_CONFIG_NOSYSTEM": "1",
                        "GIT_CONFIG_GLOBAL": "/dev/null",
                        "GIT_CONFIG_SYSTEM": "/dev/null",
                    },
                )
                if clone.returncode != 0:
                    raise RuntimeError("could not materialize isolated mutable Git anchor")
                _git(stage, "remote", "remove", "origin")
                for key in ("user.name", "user.email"):
                    identity = _git(immutable, "config", key)
                    if not identity:
                        raise RuntimeError("installed repository has no bound Git author identity")
                    _git(stage, "config", key, identity)
                shutil.rmtree(stage / "hooks")
                os.replace(stage, paths.git_root)
        observed = paths.git_root.lstat()
        if (
            paths.git_root.is_symlink()
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.geteuid()
        ):
            raise RuntimeError("mutable Git anchor is not owner-bound")
        os.chmod(paths.git_root, 0o700)
        if (paths.git_root / "hooks").exists() or (
            paths.git_root / "objects/info/alternates"
        ).exists():
            raise RuntimeError("mutable Git anchor has forbidden external behavior")
        if _git(paths.git_root, "remote"):
            raise RuntimeError("controller mutable Git anchor must not contain a remote")
        immutable_sha = _git(immutable, "rev-parse", "refs/heads/main")
        immutable_tree = _git(immutable, "rev-parse", f"{immutable_sha}^{{tree}}")
        anchor_main = _git(paths.git_root, "rev-parse", "refs/heads/main")
        anchor_tree = _git(paths.git_root, "rev-parse", f"{anchor_main}^{{tree}}")
        if require_snapshot_alignment and (
            anchor_main != immutable_sha
            or anchor_tree != immutable_tree
        ):
            raise RuntimeError(
                "mutable Git main is not the exact installed authority snapshot; "
                "independent anchor advancement is required"
            )
