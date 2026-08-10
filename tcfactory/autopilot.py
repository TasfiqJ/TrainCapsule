from __future__ import annotations

import asyncio
import fcntl
import os
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

from rich.console import Console

from .auth import assert_max_oauth_only
from .completion import CompletionBlocked, audit_and_expand_or_complete
from .config import load_autonomy_config, load_factory_config
from .feature_ledger import FeatureItem, FeatureLedger, load_feature_ledger, save_feature_ledger
from .github_sync import GitHubDivergenceError, GitHubSyncError, sync_github
from .gitops import commit_all
from .models import AutonomyConfig, AutonomyState, FactoryConfig, QueuePauseMetadata
from .observability import append_event, write_heartbeat
from .planner import archive_failed_packet, create_and_promote_task_packet
from .queue import enqueue_task, process_one, promote_due_paused, queue_dirs, reconcile_running
from .quota import AuthenticationPause, QuotaLimitPause
from .util import read_json, write_json

console = Console()


class AutopilotError(RuntimeError):
    pass


@contextmanager
def exclusive_autopilot_lock(
    repo_root: Path, config: FactoryConfig
) -> Generator[TextIO, None, None]:
    """Prevent duplicate Windows Task Scheduler/systemd/manual autopilots.

    The file remains on disk for observability; the kernel advisory lock is the authority.
    This package runs the controller inside Linux/WSL where ``fcntl`` is available.
    """

    path = config.resolve(repo_root, config.autopilot_lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AutopilotError(
                f"Another TrainCapsule autopilot already holds {path}. "
                "Do not run a manual worker beside the Windows scheduled task."
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started_at={_now().isoformat()}\n")
        handle.flush()
        yield handle
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _now() -> datetime:
    return datetime.now(UTC)


def _state_path(repo_root: Path, config: FactoryConfig) -> Path:
    return config.resolve(repo_root, config.autonomy_state_path)


def load_state(repo_root: Path, config: FactoryConfig) -> AutonomyState:
    path = _state_path(repo_root, config)
    if not path.exists():
        return AutonomyState(updated_at=_now())
    return AutonomyState.model_validate(read_json(path, {}))


def save_state(repo_root: Path, config: FactoryConfig, state: AutonomyState) -> None:
    state.updated_at = _now()
    write_json(_state_path(repo_root, config), state.model_dump(mode="json"))
    write_heartbeat(
        config.resolve(repo_root, config.heartbeat_path),
        component="autopilot",
        status=state.status,
        task_id=state.active_task_id,
        detail=state.current_action or state.last_event,
        next_wake_at=state.next_wake_at,
    )


def _notify(autonomy: AutonomyConfig, message: str) -> None:
    if not autonomy.notification_command:
        return
    env = os.environ.copy()
    env["TCF_NOTIFICATION"] = message
    subprocess.run(
        ["bash", "-lc", autonomy.notification_command],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=env,
    )


def _queue_task_ids(repo_root: Path, config: FactoryConfig) -> dict[str, set[str]]:
    dirs = queue_dirs(repo_root, config)
    return {
        state: {path.stem for path in directory.glob("*.yaml")} for state, directory in dirs.items()
    }


def sync_ledger_from_queue(
    repo_root: Path,
    config: FactoryConfig,
    ledger: FeatureLedger,
) -> bool:
    queue = _queue_task_ids(repo_root, config)
    changed = False
    for item in ledger.tasks:
        old = item.status
        if item.task_id in queue["done"]:
            item.status = "passed"
            summaries = sorted(
                config.resolve(repo_root, config.artifact_dir).glob(
                    f"{item.task_id}/*/pipeline-summary.json"
                )
            )
            if summaries:
                relative = str(summaries[-1].relative_to(repo_root))
                if relative not in item.evidence:
                    item.evidence.append(relative)
        elif item.task_id in queue["running"]:
            item.status = "running"
        elif item.task_id in queue["paused"]:
            item.status = "paused"
        elif item.task_id in queue["failed"]:
            item.status = "respec_required"
        elif item.task_id in queue["blocked"]:
            item.status = "blocked"
        elif item.task_id in queue["pending"]:
            item.status = "queued"
        elif item.packet_path and item.status not in {"passed", "external_wait", "deferred"}:
            item.status = "packet_approved"
        if item.status != old:
            changed = True
    before = [(item.task_id, item.status) for item in ledger.tasks]
    ledger.refresh_readiness()
    after = [(item.task_id, item.status) for item in ledger.tasks]
    return changed or before != after


def _nearest_pause(repo_root: Path, config: FactoryConfig) -> datetime | None:
    dirs = queue_dirs(repo_root, config)
    times: list[datetime] = []
    for path in dirs["paused"].glob("*.pause.json"):
        try:
            metadata = QueuePauseMetadata.model_validate(read_json(path, {}))
        except Exception:  # noqa: BLE001
            continue
        times.append(metadata.resume_at)
    return min(times) if times else None


def _sync_github_best_effort(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    reason: str,
    force: bool,
) -> dict[str, object]:
    try:
        return sync_github(
            repo_root=repo_root,
            config_path=factory.resolve(repo_root, factory.github_config_path),
            state_path=factory.resolve(repo_root, factory.github_state_path),
            task=None,
            reason=reason,
            force=force,
        )
    except GitHubDivergenceError:
        raise
    except GitHubSyncError as exc:
        return {"status": "deferred", "error": f"{type(exc).__name__}: {exc}"}


def _calibration_ready(repo_root: Path, autonomy: AutonomyConfig) -> bool:
    if not autonomy.require_calibration:
        return True
    return (repo_root / autonomy.calibration_marker).exists()


def _completion_reached(ledger: FeatureLedger, autonomy: AutonomyConfig) -> bool:
    if autonomy.completion_target == "all_automatable":
        return ledger.all_automatable_complete()
    return ledger.build_complete()


def _write_completion(repo_root: Path, config: FactoryConfig, ledger: FeatureLedger) -> Path:
    path = repo_root / "factory" / "state" / "PRODUCT_BUILD_COMPLETE.json"
    audit_roots = sorted(config.resolve(repo_root, config.completion_dir).glob("*"))
    latest_audit = str(audit_roots[-1]) if audit_roots else None
    write_json(
        path,
        {
            "completion_audit_root": latest_audit,
            "completed_at": _now().isoformat(),
            "target": "product_build",
            "passed_tasks": [item.task_id for item in ledger.tasks if item.status == "passed"],
            "external_wait": [
                item.task_id for item in ledger.tasks if item.status == "external_wait"
            ],
            "deferred": [item.task_id for item in ledger.tasks if item.status == "deferred"],
            "statement": (
                "All automatable product-build tasks in the machine-readable roadmap passed. "
                "External maintainer acceptance, customer payment, and acquisition interest are "
                "not machine-creatable completion criteria."
            ),
        },
    )
    return path


async def _respec_failed_item(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    autonomy: AutonomyConfig,
    ledger: FeatureLedger,
    item: FeatureItem,
) -> bool:
    if not autonomy.auto_respec_failed_tasks:
        return False
    failed_error_path = queue_dirs(repo_root, factory)["failed"] / f"{item.task_id}.error.txt"
    failed_error = (
        failed_error_path.read_text(encoding="utf-8", errors="replace")
        if failed_error_path.is_file()
        else ""
    )
    value_failure = any(
        marker in failed_error.lower()
        for marker in (
            "material-value gate",
            "value evidence gate",
            "predeclared materiality threshold",
        )
    )
    ceiling = (
        autonomy.value_redesign_limit if value_failure else autonomy.max_respecifications_per_task
    )
    current = item.value_revisions if value_failure else item.revisions
    if current >= ceiling:
        item.status = "blocked"
        item.terminal_blocked = True
        reason = (
            "Material-value redesign ceiling reached; the feature remains technically possible "
            "but has not demonstrated a commercially material result."
            if value_failure
            else "Automatic re-specification ceiling reached."
        )
        item.notes.append(reason)
        return False
    task_path = repo_root / (item.packet_path or f"tasks/{item.task_id}.yaml")
    if task_path.exists():
        archive_failed_packet(repo_root, task_path, revision=item.revisions + 1)
    item.revisions += 1
    if value_failure:
        item.value_revisions += 1
    item.packet_path = None
    item.status = "ready"
    item.terminal_blocked = False
    if value_failure:
        item.notes.append(
            f"Value redesign {item.value_revisions}/{autonomy.value_redesign_limit}: preserve the "
            "predeclared customer outcome and threshold; change the mechanism rather than lowering "
            "the bar after observing the result."
        )
    else:
        item.notes.append(
            f"Revision {item.revisions} requested after bounded pipeline failure; preserve the "
            "original outcome and strengthen specification/gates."
        )
    failed_path = queue_dirs(repo_root, factory)["failed"] / f"{item.task_id}.yaml"
    failed_path.unlink(missing_ok=True)
    failed_path.with_suffix(".error.txt").unlink(missing_ok=True)
    save_feature_ledger(factory.resolve(repo_root, factory.feature_ledger_path), ledger)
    commit_all(repo_root, f"retry {item.task_id.lower()}")
    await create_and_promote_task_packet(
        repo_root=repo_root,
        factory_config=factory,
        autonomy_config=autonomy,
        ledger=ledger,
        item=item,
    )
    return True


async def _run_autopilot_inner(
    *,
    repo_root: Path,
    factory_config_path: Path,
    autonomy_config_path: Path | None = None,
    once: bool = False,
) -> None:
    repo_root = repo_root.resolve()
    factory = load_factory_config(repo_root / factory_config_path)
    autonomy_path = autonomy_config_path or Path(factory.autonomy_config_path)
    autonomy = load_autonomy_config(
        autonomy_path if autonomy_path.is_absolute() else repo_root / autonomy_path
    )
    if not autonomy.enabled:
        raise AutopilotError(
            "Lights-out autonomy is disabled. Complete calibration, then run "
            "`tcfactory autonomy-enable --acknowledge` or set enabled: true."
        )
    if not _calibration_ready(repo_root, autonomy):
        raise AutopilotError(
            f"Calibration marker is missing: {autonomy.calibration_marker}. The factory must "
            "prove harmless passes and deliberate rejections before automatic merging."
        )
    if factory.max_parallel != 1:
        raise AutopilotError("Lights-out v2 requires TCF_MAX_PARALLEL=1 for serial main promotion.")

    state = load_state(repo_root, factory)
    existing_completion = repo_root / "factory" / "state" / "PRODUCT_BUILD_COMPLETE.json"
    if existing_completion.exists():
        state.status = "complete"
        state.active_task_id = None
        state.current_action = None
        state.last_event = f"existing product completion marker: {existing_completion}"
        save_state(repo_root, factory, state)
        return
    state.status = "running"
    state.last_event = "autopilot started"
    save_state(repo_root, factory, state)
    append_event(
        factory.resolve(repo_root, factory.event_log_path),
        event="autopilot_started",
        component="autopilot",
        detail=f"once={once}",
    )
    reconcile_running(repo_root, factory)

    while True:
        stop_path = repo_root / autonomy.stop_file
        pause_path = repo_root / autonomy.pause_file
        if stop_path.exists():
            state.status = "stopped"
            state.last_event = f"stop file detected: {stop_path}"
            save_state(repo_root, factory, state)
            return
        if pause_path.exists():
            state.status = "paused"
            state.last_event = f"operator pause file detected: {pause_path}"
            save_state(repo_root, factory, state)
            if once:
                return
            await asyncio.sleep(autonomy.idle_poll_seconds)
            continue

        try:
            assert_max_oauth_only(
                require_long_lived_token=factory.require_long_lived_oauth_for_autopilot
            )
        except RuntimeError as exc:
            state.status = "waiting_auth"
            state.next_wake_at = _now() + timedelta(seconds=factory.authentication_retry_seconds)
            state.last_event = (
                f"Claude Max OAuth unavailable; retrying automatically at "
                f"{state.next_wake_at.isoformat()}: {exc}"
            )
            save_state(repo_root, factory, state)
            _notify(autonomy, state.last_event)
            if once:
                return
            await asyncio.sleep(max(1.0, (state.next_wake_at - _now()).total_seconds()))
            continue
        if autonomy.auto_resume_quota:
            promote_due_paused(repo_root, factory)
        ledger_path = factory.resolve(repo_root, factory.feature_ledger_path)
        ledger = load_feature_ledger(ledger_path)
        if sync_ledger_from_queue(repo_root, factory, ledger):
            save_feature_ledger(ledger_path, ledger)
            commit_all(repo_root, "update roadmap")

        if _completion_reached(ledger, autonomy):
            state.status = "auditing"
            state.current_action = "independent product completion audit"
            state.active_task_id = "PRODUCT_COMPLETION"
            save_state(repo_root, factory, state)
            try:
                if factory.completion_audit_enabled:
                    outcome, completion_evidence = await audit_and_expand_or_complete(
                        repo_root=repo_root,
                        config=factory,
                        ledger=ledger,
                        audits_required=autonomy.completion_audits_required,
                    )
                else:
                    outcome, completion_evidence = "complete", []
            except QuotaLimitPause as exc:
                state.status = "paused"
                state.next_wake_at = exc.record.resume_at + timedelta(
                    seconds=autonomy.quota_reset_buffer_seconds
                )
                state.last_event = str(exc)
                save_state(repo_root, factory, state)
                if once:
                    return
                await asyncio.sleep(max(1.0, (state.next_wake_at - _now()).total_seconds()))
                state.status = "running"
                continue
            except AuthenticationPause as exc:
                state.status = "waiting_auth"
                state.next_wake_at = _now() + timedelta(
                    seconds=factory.authentication_retry_seconds
                )
                state.last_event = (
                    f"Completion audit paused for Claude Max OAuth; retrying at "
                    f"{state.next_wake_at.isoformat()}: {exc.message}"
                )
                save_state(repo_root, factory, state)
                _notify(autonomy, state.last_event)
                if once:
                    return
                await asyncio.sleep(max(1.0, (state.next_wake_at - _now()).total_seconds()))
                state.status = "running"
                continue
            except CompletionBlocked as exc:
                state.status = "blocked"
                state.last_event = f"completion audit blocked: {exc}"
                state.blocked_tasks = ["PRODUCT_COMPLETION"]
                save_state(repo_root, factory, state)
                _notify(autonomy, state.last_event)
                return

            if outcome == "expanded":
                expansion_count = len(
                    list(
                        factory.resolve(repo_root, factory.completion_dir).glob(
                            "*/ROADMAP_EXPANDED.json"
                        )
                    )
                )
                if (
                    not autonomy.auto_expand_roadmap
                    or expansion_count > autonomy.max_completion_expansions
                ):
                    state.status = "blocked"
                    state.blocked_tasks = ["PRODUCT_COMPLETION"]
                    state.last_event = (
                        "Completion audit found additional work, but automatic roadmap "
                        f"expansion is disabled or exceeded its ceiling ({expansion_count}/"
                        f"{autonomy.max_completion_expansions})."
                    )
                    save_state(repo_root, factory, state)
                    _notify(autonomy, state.last_event)
                    return
                state.status = "running"
                state.active_task_id = None
                state.current_action = None
                state.last_event = (
                    "Independent completion audit expanded the roadmap: "
                    + ", ".join(completion_evidence)
                )
                save_state(repo_root, factory, state)
                if once:
                    return
                continue

            complete_path = _write_completion(repo_root, factory, ledger)
            try:
                github_result = _sync_github_best_effort(
                    repo_root=repo_root,
                    factory=factory,
                    reason="product build completion",
                    force=autonomy.push_at_completion,
                )
            except GitHubDivergenceError as exc:
                state.status = "blocked"
                state.last_event = f"GitHub divergence at completion: {exc}"
                state.blocked_tasks = ["GITHUB_SYNC"]
                save_state(repo_root, factory, state)
                _notify(autonomy, state.last_event)
                return
            state.status = "complete"
            state.active_task_id = None
            state.current_action = None
            state.last_event = (
                f"product build complete: {complete_path}; GitHub: {github_result.get('status')}"
            )
            state.completed_tasks = [
                item.task_id for item in ledger.tasks if item.status == "passed"
            ]
            save_state(repo_root, factory, state)
            _notify(autonomy, state.last_event)
            return

        failed_item = next(
            (item for item in ledger.tasks if item.status == "respec_required"), None
        )
        if failed_item is not None:
            state.active_task_id = failed_item.task_id
            state.current_action = "automatic re-specification"
            save_state(repo_root, factory, state)
            try:
                changed = await _respec_failed_item(
                    repo_root=repo_root,
                    factory=factory,
                    autonomy=autonomy,
                    ledger=ledger,
                    item=failed_item,
                )
            except QuotaLimitPause as exc:
                state.status = "paused"
                state.next_wake_at = exc.record.resume_at + timedelta(
                    seconds=autonomy.quota_reset_buffer_seconds
                )
                state.last_event = str(exc)
                save_state(repo_root, factory, state)
                if once:
                    return
                delay = max(1.0, (state.next_wake_at - _now()).total_seconds())
                await asyncio.sleep(delay)
                state.status = "running"
                continue
            if not changed:
                save_feature_ledger(ledger_path, ledger)
                commit_all(repo_root, f"block {failed_item.task_id.lower()}")
            if once:
                return
            continue

        processed = await process_one(
            repo_root=repo_root,
            config=factory,
            merge_override=autonomy.auto_merge,
        )
        if processed:
            state.status = "running"
            state.consecutive_failures = 0
            try:
                github_result = _sync_github_best_effort(
                    repo_root=repo_root,
                    factory=factory,
                    reason="verified task batch",
                    force=False,
                )
            except GitHubDivergenceError as exc:
                state.status = "blocked"
                state.last_event = f"GitHub divergence after verified task: {exc}"
                state.blocked_tasks = ["GITHUB_SYNC"]
                save_state(repo_root, factory, state)
                _notify(autonomy, state.last_event)
                return
            state.last_event = (
                "queue task processed; GitHub synchronization "
                f"{github_result.get('status', 'unknown')}"
            )
            save_state(repo_root, factory, state)
            if once:
                return
            continue

        next_item = ledger.next_ready()
        if next_item is not None:
            state.active_task_id = next_item.task_id
            state.current_action = (
                "create task packet" if not next_item.packet_path else "enqueue task"
            )
            save_state(repo_root, factory, state)
            try:
                if not next_item.packet_path:
                    await create_and_promote_task_packet(
                        repo_root=repo_root,
                        factory_config=factory,
                        autonomy_config=autonomy,
                        ledger=ledger,
                        item=next_item,
                    )
                packet_path = repo_root / str(next_item.packet_path)
                enqueue_task(
                    repo_root=repo_root,
                    config=factory,
                    source=packet_path,
                    replace=False,
                )
                next_item.status = "queued"
                save_feature_ledger(ledger_path, ledger)
                commit_all(repo_root, f"queue {next_item.task_id.lower()}")
            except QuotaLimitPause as exc:
                state.status = "paused"
                state.next_wake_at = exc.record.resume_at + timedelta(
                    seconds=autonomy.quota_reset_buffer_seconds
                )
                state.last_event = str(exc)
                save_state(repo_root, factory, state)
                if once:
                    return
                delay = max(1.0, (state.next_wake_at - _now()).total_seconds())
                await asyncio.sleep(delay)
                state.status = "running"
            except Exception as exc:  # noqa: BLE001
                state.consecutive_failures += 1
                state.last_event = f"planning/enqueue failure: {type(exc).__name__}: {exc}"
                save_state(repo_root, factory, state)
                if state.consecutive_failures >= autonomy.max_consecutive_factory_failures:
                    state.status = "blocked"
                    save_state(repo_root, factory, state)
                    _notify(autonomy, state.last_event)
                    return
                await asyncio.sleep(autonomy.idle_poll_seconds)
            if once:
                return
            continue

        nearest = _nearest_pause(repo_root, factory)
        if nearest:
            if autonomy.push_before_quota_pause:
                try:
                    _sync_github_best_effort(
                        repo_root=repo_root,
                        factory=factory,
                        reason="before quota wait",
                        force=True,
                    )
                except GitHubDivergenceError as exc:
                    state.status = "blocked"
                    state.last_event = f"GitHub divergence before quota wait: {exc}"
                    state.blocked_tasks = ["GITHUB_SYNC"]
                    save_state(repo_root, factory, state)
                    return
            wake = nearest + timedelta(seconds=autonomy.quota_reset_buffer_seconds)
            state.status = "paused"
            state.next_wake_at = wake
            state.last_event = f"waiting for Claude limit reset at {wake.isoformat()}"
            save_state(repo_root, factory, state)
            if once:
                return
            await asyncio.sleep(max(1.0, (wake - _now()).total_seconds()))
            state.status = "running"
            continue

        try:
            _sync_github_best_effort(
                repo_root=repo_root,
                factory=factory,
                reason="periodic idle synchronization",
                force=False,
            )
        except GitHubDivergenceError as exc:
            state.status = "blocked"
            state.last_event = f"GitHub divergence: {exc}"
            state.blocked_tasks = ["GITHUB_SYNC"]
            save_state(repo_root, factory, state)
            _notify(autonomy, state.last_event)
            return

        blocked = [
            item.task_id for item in ledger.tasks if item.status in {"blocked", "external_wait"}
        ]
        state.status = "blocked" if blocked else "idle"
        state.blocked_tasks = blocked
        state.active_task_id = None
        state.current_action = None
        state.last_event = (
            f"No dependency-ready automatable task. Blocked: {', '.join(blocked)}"
            if blocked
            else "No queued or ready task; waiting for roadmap state change."
        )
        save_state(repo_root, factory, state)
        if once:
            return
        await asyncio.sleep(
            autonomy.external_blocker_sleep_seconds if blocked else autonomy.idle_poll_seconds
        )


async def run_autopilot(
    *,
    repo_root: Path,
    factory_config_path: Path,
    autonomy_config_path: Path | None = None,
    once: bool = False,
) -> None:
    """Run exactly one lights-out controller instance for this repository."""

    resolved = repo_root.resolve()
    factory = load_factory_config(resolved / factory_config_path)
    with exclusive_autopilot_lock(resolved, factory):
        await _run_autopilot_inner(
            repo_root=resolved,
            factory_config_path=factory_config_path,
            autonomy_config_path=autonomy_config_path,
            once=once,
        )
