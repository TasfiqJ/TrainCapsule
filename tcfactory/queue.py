from __future__ import annotations

import asyncio
import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

from .checkpoints import CheckpointStore
from .config import load_roles, load_task
from .github_sync import (
    GitHubDivergenceError,
    GitHubSyncError,
    RemoteCIFailure,
    sync_github,
)
from .models import FactoryConfig, PauseKind, PipelineState, QueuePauseMetadata, QueueState
from .pipeline import PipelineBlocked, run_pipeline
from .quota import QuotaLimitPause
from .util import read_json, write_json

console = Console()


class QueueEmpty(RuntimeError):
    pass


def queue_dirs(repo_root: Path, config: FactoryConfig) -> dict[str, Path]:
    root = config.resolve(repo_root, config.queue_dir)
    result = {state.value: root / state.value for state in QueueState}
    for path in result.values():
        path.mkdir(parents=True, exist_ok=True)
    return result


def enqueue_task(
    *, repo_root: Path, config: FactoryConfig, source: Path, replace: bool = False
) -> Path:
    task = load_task(source)
    dirs = queue_dirs(repo_root, config)
    destination = dirs[QueueState.PENDING.value] / f"{task.task_id}.yaml"
    existing = [dirs[state.value] / destination.name for state in QueueState]
    if not replace and any(path.exists() for path in existing):
        raise FileExistsError(
            f"Task {task.task_id} already exists in the queue. Use --replace only after "
            "reviewing prior artifacts."
        )
    for path in existing:
        if path.exists():
            path.unlink()
        metadata = path.with_suffix(".pause.json")
        metadata.unlink(missing_ok=True)
        path.with_suffix(".error.txt").unlink(missing_ok=True)
    shutil.copy2(source, destination)
    return destination


def _done_task_ids(done_dir: Path) -> set[str]:
    return {path.stem for path in done_dir.glob("*.yaml")}


def promote_due_paused(
    repo_root: Path, config: FactoryConfig, *, now: datetime | None = None
) -> int:
    dirs = queue_dirs(repo_root, config)
    current = now or datetime.now(UTC)
    promoted = 0
    for paused in sorted(dirs[QueueState.PAUSED.value].glob("*.yaml")):
        metadata_path = paused.with_suffix(".pause.json")
        if not metadata_path.exists():
            resume_at = current
        else:
            metadata = QueuePauseMetadata.model_validate(read_json(metadata_path, {}))
            resume_at = metadata.resume_at
        if resume_at > current:
            continue
        pending = dirs[QueueState.PENDING.value] / paused.name
        os.replace(paused, pending)
        metadata_path.unlink(missing_ok=True)
        promoted += 1
        console.print(f"[cyan]Resuming quota-paused task[/cyan] {pending.stem}")
    return promoted


def reconcile_running(repo_root: Path, config: FactoryConfig) -> int:
    """Recover queue files left in running/ after process or WSL interruption."""
    dirs = queue_dirs(repo_root, config)
    checkpoint_store = CheckpointStore(config.resolve(repo_root, config.pipeline_state_dir))
    reconciled = 0
    for running in sorted(dirs[QueueState.RUNNING.value].glob("*.yaml")):
        checkpoint = checkpoint_store.load(running.stem)
        if checkpoint and checkpoint.state == PipelineState.PAUSED and checkpoint.pause:
            target = dirs[QueueState.PAUSED.value] / running.name
            os.replace(running, target)
            write_json(
                target.with_suffix(".pause.json"),
                QueuePauseMetadata(
                    task_id=running.stem,
                    kind=checkpoint.pause.kind,
                    resume_at=checkpoint.pause.resume_at,
                    message=checkpoint.pause.message,
                    run_id=checkpoint.run_id,
                ).model_dump(mode="json"),
            )
        elif checkpoint and checkpoint.state == PipelineState.BLOCKED:
            target = dirs[QueueState.BLOCKED.value] / running.name
            os.replace(running, target)
            target.with_suffix(".error.txt").write_text(
                checkpoint.error or "Pipeline blocked\n", encoding="utf-8"
            )
        else:
            target = dirs[QueueState.PAUSED.value] / running.name
            os.replace(running, target)
            resume_at = datetime.now(UTC) + timedelta(seconds=config.crash_resume_delay_seconds)
            write_json(
                target.with_suffix(".pause.json"),
                QueuePauseMetadata(
                    task_id=running.stem,
                    kind=PauseKind.SERVICE_CAPACITY,
                    resume_at=resume_at,
                    message="Recovered a task left running after process or WSL interruption.",
                    run_id=checkpoint.run_id if checkpoint else None,
                ).model_dump(mode="json"),
            )
        reconciled += 1
    return reconciled


def claim_next(repo_root: Path, config: FactoryConfig) -> Path:
    dirs = queue_dirs(repo_root, config)
    done = _done_task_ids(dirs[QueueState.DONE.value])
    for pending in sorted(
        dirs[QueueState.PENDING.value].glob("*.yaml"), key=lambda p: p.stat().st_mtime
    ):
        task = load_task(pending)
        if not set(task.depends_on).issubset(done):
            continue
        running = dirs[QueueState.RUNNING.value] / pending.name
        try:
            os.replace(pending, running)
            return running
        except FileNotFoundError:
            continue
    raise QueueEmpty("No dependency-ready pending task")


async def process_one(
    *,
    repo_root: Path,
    config: FactoryConfig,
    merge_override: bool | None = None,
) -> bool:
    dirs = queue_dirs(repo_root, config)
    promote_due_paused(repo_root, config)
    try:
        running = claim_next(repo_root, config)
    except QueueEmpty:
        return False
    task = load_task(running)
    roles = load_roles(config.resolve(repo_root, config.roles_path))
    console.rule(f"Queue worker claimed {task.task_id}")
    try:
        summary = await run_pipeline(
            repo_root=repo_root,
            config=config,
            task=task,
            role_configs=roles,
            merge_override=merge_override,
            resume=True,
        )
        if bool(summary.get("merged")) and task.github_push:
            state_path = config.resolve(repo_root, config.github_state_path)
            try:
                sync_github(
                    repo_root=repo_root,
                    config_path=config.resolve(repo_root, config.github_config_path),
                    state_path=state_path,
                    task=None,
                    reason=f"verified task {task.task_id}",
                    force=task.risk_tier.value in {"integration", "trust_core"},
                )
            except GitHubDivergenceError as exc:
                raise PipelineBlocked(str(exc)) from exc
            except RemoteCIFailure:
                raise
            except GitHubSyncError as exc:
                # Network/auth/transient push errors are durable and retried by the idle autopilot.
                console.print(f"[yellow]GitHub sync deferred:[/yellow] {exc}")
    except QuotaLimitPause as exc:
        try:
            sync_github(
                repo_root=repo_root,
                config_path=config.resolve(repo_root, config.github_config_path),
                state_path=config.resolve(repo_root, config.github_state_path),
                task=None,
                reason="before Claude quota pause",
                force=True,
            )
        except GitHubSyncError as sync_exc:
            console.print(f"[yellow]GitHub sync before quota pause deferred:[/yellow] {sync_exc}")
        paused = dirs[QueueState.PAUSED.value] / running.name
        os.replace(running, paused)
        write_json(
            paused.with_suffix(".pause.json"),
            QueuePauseMetadata(
                task_id=task.task_id,
                kind=exc.record.kind,
                resume_at=exc.record.resume_at,
                message=exc.record.message,
                run_id=None,
            ).model_dump(mode="json"),
        )
        console.print(
            f"[yellow]Task {task.task_id} paused for Claude limit until "
            f"{exc.record.resume_at.isoformat()}.[/yellow]"
        )
    except PipelineBlocked as exc:
        blocked = dirs[QueueState.BLOCKED.value] / running.name
        os.replace(running, blocked)
        blocked.with_suffix(".error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        console.print(f"[magenta]Task {task.task_id} blocked:[/magenta] {exc}")
    except Exception as exc:  # noqa: BLE001
        failed = dirs[QueueState.FAILED.value] / running.name
        os.replace(running, failed)
        failed.with_suffix(".error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        console.print(f"[red]Task {task.task_id} failed:[/red] {exc}")
    else:
        os.replace(running, dirs[QueueState.DONE.value] / running.name)
        console.print(f"[green]Task {task.task_id} completed.[/green]")
    return True


async def worker_loop(
    *,
    repo_root: Path,
    config: FactoryConfig,
    once: bool,
    poll_seconds: int | None = None,
    merge_override: bool | None = None,
) -> None:
    delay = poll_seconds or config.worker_poll_seconds
    reconcile_running(repo_root, config)
    while True:
        processed = await process_one(
            repo_root=repo_root,
            config=config,
            merge_override=merge_override,
        )
        if once:
            return
        if not processed:
            await asyncio.sleep(delay)
