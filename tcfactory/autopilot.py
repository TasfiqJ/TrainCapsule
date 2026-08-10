from __future__ import annotations

import asyncio
import fcntl
import os
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO, cast

from rich.console import Console

from .auth import assert_max_oauth_only
from .checkpoints import CheckpointStore, new_checkpoint
from .completion import CompletionBlocked, audit_and_expand_or_complete
from .config import load_autonomy_config, load_factory_config
from .feature_ledger import FeatureItem, FeatureLedger, load_feature_ledger, save_feature_ledger
from .github_sync import (
    GitHubDivergenceError,
    GitHubSyncError,
    load_github_state,
    sync_github,
)
from .gitops import GitError, commit_all, current_sha, transplant_candidate_onto
from .models import (
    AutonomyConfig,
    AutonomyState,
    FactoryConfig,
    PipelineState,
    QueuePauseMetadata,
)
from .observability import append_event, write_heartbeat
from .pipeline import TURN_CEILING_MARKERS
from .planner import archive_failed_packet, create_and_promote_task_packet
from .queue import enqueue_task, process_one, promote_due_paused, queue_dirs, reconcile_running
from .quota import AuthenticationPause, QuotaLimitPause
from .self_repair import attempt_factory_self_repair, clear_hard_stuck, write_hard_stuck
from .util import read_json, utc_stamp, write_json

console = Console()

_VERIFIED_REPAIR_RETRY = Path("factory/state/VERIFIED_REPAIR_RETRY.json")
_VERIFIED_REPAIR_CONSUMED = Path("factory/state/VERIFIED_REPAIR_RETRY_CONSUMED.json")


class AutopilotError(RuntimeError):
    pass


def is_infrastructure_failure(error: str) -> bool:
    """Classify by the stage's own genuine signal, never by a wrapper's literal text.

    A wrapper message such as "no repair path remains" describes the pipeline's own
    control-flow decision for any role, not evidence that the stage hit an
    infrastructure fault. Matching that wrapper text directly would misclassify every
    truthful, non-infrastructure stage rejection that happens to lack a repair path as
    an infrastructure failure eligible for a free (non-revision-consuming) requeue.
    Only match on markers that pipeline.py's ``_terminal_failure_signal`` embeds from
    the actual stage result (its ``error``/``terminal_reason``), so genuine turn
    ceilings and infrastructure faults are still recognized after passing through a
    generic terminal ``PipelineFailure`` wrapper.
    """

    normalized = error.lower()
    infrastructure_markers = (
        "cannot resume",
        "main moved from",
        "service capacity",
        "infrastructure_error",
    )
    return any(
        marker in normalized for marker in infrastructure_markers + TURN_CEILING_MARKERS
    )


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


async def _repair_or_hard_stuck(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    autonomy: AutonomyConfig,
    state: AutonomyState,
    reason: str,
    blocker_id: str,
) -> bool:
    """Exhaust bounded, gated self-repair before publishing a durable hard stop."""
    last_artifact: str | None = state.last_repair_artifact
    while (
        autonomy.auto_repair_factory
        and state.repair_attempts < autonomy.max_self_repair_attempts
    ):
        state.repair_attempts += 1
        state.status = "repairing"
        state.next_wake_at = None
        state.repair_status = (
            f"attempt {state.repair_attempts}/{autonomy.max_self_repair_attempts}"
        )
        state.active_task_id = blocker_id
        state.current_action = "autonomous factory self-repair"
        state.blocker_reason = reason
        state.required_action = None
        state.last_event = f"Factory self-repair {state.repair_status}: {reason}"
        save_state(repo_root, factory, state)
        repair_reason = reason
        if last_artifact:
            repair_reason += (
                " Previous repair evidence must be inspected and salvaged when valid: "
                f"{last_artifact}"
            )
        try:
            outcome = await attempt_factory_self_repair(
                repo_root=repo_root,
                factory=factory,
                autonomy=autonomy,
                reason=repair_reason,
                attempt=state.repair_attempts,
            )
        except QuotaLimitPause as exc:
            state.status = "paused"
            state.repair_status = "waiting for included Claude allowance"
            state.next_wake_at = exc.record.resume_at
            state.last_event = str(exc)
            save_state(repo_root, factory, state)
            return False
        except AuthenticationPause as exc:
            state.status = "waiting_auth"
            state.repair_status = "waiting for Claude Max OAuth"
            state.next_wake_at = _now() + timedelta(
                seconds=factory.authentication_retry_seconds
            )
            state.last_event = exc.message
            save_state(repo_root, factory, state)
            return False
        last_artifact = outcome.artifact_path or last_artifact
        state.last_repair_artifact = last_artifact
        state.last_event = outcome.detail
        save_state(repo_root, factory, state)
        if outcome.applied:
            clear_hard_stuck(repo_root, autonomy)
            write_json(
                repo_root / _VERIFIED_REPAIR_RETRY,
                {
                    "artifact_path": outcome.artifact_path,
                    "blocker_id": blocker_id,
                    "repair_task_id": outcome.task_id,
                    "verified_at": _now().isoformat(),
                },
            )
            state.status = "restarting"
            state.repair_status = "verified repair merged"
            state.consecutive_failures = 0
            state.blocker_reason = None
            state.required_action = None
            state.last_event = (
                f"Verified autonomous repair {outcome.task_id} merged; restarting controller"
            )
            save_state(repo_root, factory, state)
            return True

    retry_at = _now() + timedelta(seconds=autonomy.hard_stuck_retry_seconds)
    required_action = (
        "Autonomous repair exhausted this safe, gated batch. The exact blocker and last repair "
        f"artifact are shown here; an independent batch will retry automatically at {retry_at}. "
        "Paid usage and gate weakening remain forbidden."
    )
    hard_stuck_path = write_hard_stuck(
        repo_root=repo_root,
        autonomy=autonomy,
        reason=reason,
        required_action=required_action,
        attempts=state.repair_attempts,
        artifact_path=last_artifact,
        auto_retry_at=retry_at,
    )
    state.status = "hard_stuck"
    state.repair_status = "exhausted"
    state.blocked_tasks = sorted(set([*state.blocked_tasks, blocker_id]))
    state.blocker_reason = reason
    state.required_action = required_action
    state.current_action = "hard stuck — safely paused"
    state.next_wake_at = retry_at
    state.last_event = f"Hard stuck record written: {hard_stuck_path}"
    save_state(repo_root, factory, state)
    _notify(autonomy, f"TrainCapsule factory is hard stuck: {reason}")
    return False


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
        if item.terminal_blocked:
            # Runtime queue residue cannot resurrect a task after its bounded
            # re-specification policy has deliberately made it terminal.
            continue
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
            # A queue-level PipelineBlocked result still receives bounded autonomous
            # re-specification. Only a ledger item marked terminal_blocked is final.
            item.status = "respec_required"
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


def terminal_root_blocker(ledger: FeatureLedger) -> FeatureItem | None:
    """Return the first automatable terminal cause, not every blocked descendant."""

    return next(
        (
            item
            for item in ledger.tasks
            if item.terminal_blocked and item.automatable and item.status != "passed"
        ),
        None,
    )


def visible_blocked_task_ids(ledger: FeatureLedger) -> list[str]:
    """Expose causal blockers in the UI while hiding dependency-only fallout."""

    return [
        item.task_id
        for item in ledger.tasks
        if item.status == "external_wait" or item.terminal_blocked
    ]


def terminal_blocker_reason(
    repo_root: Path, factory: FactoryConfig, item: FeatureItem
) -> str:
    """Report the current queue artifact instead of a potentially stale ledger note."""

    dirs = queue_dirs(repo_root, factory)
    error_path = dirs["failed"] / f"{item.task_id}.error.txt"
    if not error_path.is_file():
        error_path = dirs["blocked"] / f"{item.task_id}.error.txt"
    if error_path.is_file():
        try:
            relative = error_path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            relative = error_path
        error = error_path.read_text(encoding="utf-8", errors="replace").strip()
        return f"Durable queue artifact {relative}: {error or 'empty error artifact'}"
    return "Terminal automatable blocker has no durable queue error artifact."


def _verified_repair_intent(
    repo_root: Path, state: AutonomyState, ledger: FeatureLedger
) -> tuple[FeatureItem | None, str | None]:
    marker_path = repo_root / _VERIFIED_REPAIR_RETRY
    marker = (
        cast(dict[str, object], read_json(marker_path, {})) if marker_path.is_file() else {}
    )
    consumed = cast(
        dict[str, object], read_json(repo_root / _VERIFIED_REPAIR_CONSUMED, {})
    )
    artifact_path = str(marker.get("artifact_path") or "") or None
    blocker_id = str(marker.get("blocker_id") or "") or state.active_task_id
    has_signal = marker_path.is_file() or (
        state.repair_status == "verified repair merged"
        and not bool(consumed.get("repair_status_consumed"))
    )

    # Migration fallback for verified repairs produced before the durable retry marker existed.
    if not has_signal:
        result_paths = sorted((repo_root / "factory/state/self-repair").glob("*.result.json"))
        if result_paths:
            latest = result_paths[-1]
            result = read_json(latest, {})
            latest_artifact = str(latest)
            consumed_artifacts = {
                str(consumed.get("artifact_path") or ""),
                str(consumed.get("latest_self_repair_artifact") or ""),
            }
            predates_consumption = False
            recovered_at = str(consumed.get("recovered_at") or "")
            if recovered_at and bool(consumed.get("repair_status_consumed")):
                try:
                    consumed_at = datetime.fromisoformat(recovered_at.replace("Z", "+00:00"))
                    modified_at = datetime.fromtimestamp(latest.stat().st_mtime, UTC)
                    predates_consumption = modified_at <= consumed_at
                except (OSError, ValueError):
                    # The explicit artifact identities above remain authoritative when a
                    # legacy timestamp cannot be parsed or inspected.
                    predates_consumption = False
            if (
                bool(result.get("applied"))
                and latest_artifact not in consumed_artifacts
                and not predates_consumption
            ):
                artifact_path = latest_artifact
                has_signal = True
    if not has_signal:
        return None, None

    item = next(
        (candidate for candidate in ledger.tasks if candidate.task_id == blocker_id), None
    )
    if item is None:
        item = terminal_root_blocker(ledger)
    return item, artifact_path


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


@dataclass(frozen=True)
class RespecOutcome:
    """Result of one bounded automatic re-specification attempt.

    ``block_reason`` and ``evidence_path`` carry the *current* terminal-block cause so the
    self-repair role never has to infer it from ledger note ordering. Ledger notes are
    de-duplicated, so ``notes[-1]`` can be an unrelated older entry.
    """

    changed: bool
    block_reason: str | None = None
    evidence_path: str | None = None


def respec_block_reason(item: FeatureItem, outcome: RespecOutcome) -> str:
    """Compose the durable, non-stale blocker handed to autonomous self-repair."""

    return (
        f"Task {item.task_id} exhausted automatic re-specification. "
        f"Blocking reason: {outcome.block_reason or 'unrecorded'}. "
        "Durable failure evidence artifact: "
        f"{outcome.evidence_path or 'no queue error artifact recorded'} "
        f"(revisions {item.revisions}, value revisions {item.value_revisions})."
    )


def recover_task_after_verified_repair(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    state: AutonomyState,
    ledger: FeatureLedger,
) -> bool:
    """Atomically reopen the root task after a verified controller repair.

    The repair pipeline advances ``main``. Any partial product candidate therefore has to be
    transplanted onto that new revision before it can be resumed. The old checkpoint is archived,
    the candidate delta is preserved, and the same task is requeued without spending another
    specification revision.
    """

    item, repair_artifact = _verified_repair_intent(repo_root, state, ledger)
    if item is None or item.status == "passed":
        return False

    dirs = queue_dirs(repo_root, factory)
    task_path = repo_root / (item.packet_path or f"tasks/{item.task_id}.yaml")
    item.terminal_blocked = False
    item.infrastructure_recoveries = 0
    item.status = "queued" if task_path.is_file() else "ready"
    note = (
        "Verified controller repair merged; retrying the same task without consuming a "
        "specification revision and preserving its last valid candidate."
    )
    if note not in item.notes:
        item.notes.append(note)
    save_feature_ledger(factory.resolve(repo_root, factory.feature_ledger_path), ledger)
    new_base_sha = commit_all(
        repo_root, f"recover: resume {item.task_id.lower()} after verified controller repair"
    ) or current_sha(repo_root)

    checkpoint_store = CheckpointStore(factory.resolve(repo_root, factory.pipeline_state_dir))
    previous = checkpoint_store.load(item.task_id)
    candidate_sha = new_base_sha
    previous_findings: list[str] = []
    stage_index = 0
    if previous is not None:
        previous_findings = (previous.previous_findings or [])[-20:]
        stage_index = previous.stage_index
        if previous.candidate_sha != previous.starting_sha:
            candidate_sha = transplant_candidate_onto(
                repo_root,
                factory.resolve(repo_root, factory.worktree_dir),
                task_id=item.task_id,
                run_id=utc_stamp(),
                original_base_sha=previous.starting_sha,
                candidate_sha=previous.candidate_sha,
                new_base_sha=new_base_sha,
            )
        checkpoint_store.archive(
            previous,
            suffix=f"controller-repair-{_now().strftime('%Y%m%dT%H%M%SZ')}",
        )
    recovered = new_checkpoint(
        task_id=item.task_id,
        run_id=utc_stamp(),
        starting_sha=new_base_sha,
    )
    recovered.candidate_sha = candidate_sha
    recovered.stage_index = stage_index
    recovered.state = PipelineState.RUNNING
    recovered.previous_findings = [
        *previous_findings,
        "A verified controller repair was merged. The prior candidate was preserved on top of "
        "the repaired main revision; inspect it first and finish the unchanged task gates.",
    ]
    checkpoint_store.save(recovered)

    for queue_state in ("failed", "blocked", "paused", "running"):
        stale = dirs[queue_state] / f"{item.task_id}.yaml"
        stale.unlink(missing_ok=True)
        stale.with_suffix(".error.txt").unlink(missing_ok=True)
        stale.with_suffix(".pause.json").unlink(missing_ok=True)
    if task_path.is_file():
        enqueue_task(repo_root=repo_root, config=factory, source=task_path, replace=True)
    state.active_task_id = item.task_id
    state.status = "running"
    state.current_action = "resume task after verified controller repair"
    state.repair_attempts = 0
    state.repair_status = None
    state.blocker_reason = None
    state.required_action = None
    state.blocked_tasks = []
    state.next_wake_at = None
    state.last_event = f"Recovered and requeued {item.task_id} after verified controller repair"
    write_json(
        repo_root / _VERIFIED_REPAIR_CONSUMED,
        {
            "artifact_path": repair_artifact,
            "latest_self_repair_artifact": (
                str(latest_self_repair_results[-1])
                if (
                    latest_self_repair_results := sorted(
                        (repo_root / "factory/state/self-repair").glob("*.result.json")
                    )
                )
                else None
            ),
            "recovered_at": _now().isoformat(),
            "repair_status_consumed": True,
            "task_id": item.task_id,
        },
    )
    (repo_root / _VERIFIED_REPAIR_RETRY).unlink(missing_ok=True)
    return True


async def respec_failed_item(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    autonomy: AutonomyConfig,
    ledger: FeatureLedger,
    item: FeatureItem,
) -> RespecOutcome:
    if not autonomy.auto_respec_failed_tasks:
        return RespecOutcome(
            changed=False,
            block_reason="Automatic re-specification is disabled by autonomy configuration.",
        )
    dirs = queue_dirs(repo_root, factory)
    failed_error_path = dirs["failed"] / f"{item.task_id}.error.txt"
    if not failed_error_path.is_file():
        failed_error_path = dirs["blocked"] / f"{item.task_id}.error.txt"
    failed_error = (
        failed_error_path.read_text(encoding="utf-8", errors="replace")
        if failed_error_path.is_file()
        else ""
    )
    evidence_path: str | None = None
    if failed_error_path.is_file():
        try:
            evidence_path = str(failed_error_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            evidence_path = str(failed_error_path)
    task_path = repo_root / (item.packet_path or f"tasks/{item.task_id}.yaml")
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
    infrastructure_failure = is_infrastructure_failure(failed_error) and task_path.is_file()
    # The recovery budget is consecutive and applies at every revision level, not only at the
    # re-specification ceiling. Without that, a task below the ceiling never increments the
    # counter and can be requeued forever on infrastructure-classified failures.
    infrastructure_exhausted = infrastructure_failure and item.infrastructure_recoveries >= (
        autonomy.max_consecutive_infrastructure_recoveries
    )
    if infrastructure_failure and not infrastructure_exhausted:
        checkpoint_store = CheckpointStore(
            factory.resolve(repo_root, factory.pipeline_state_dir)
        )
        checkpoint = checkpoint_store.load(item.task_id)
        if checkpoint is not None:
            checkpoint_store.archive(
                checkpoint,
                suffix=f"infrastructure-{_now().strftime('%Y%m%dT%H%M%SZ')}",
            )
        for queue_state in ("failed", "blocked", "paused", "running"):
            stale_path = dirs[queue_state] / f"{item.task_id}.yaml"
            stale_path.unlink(missing_ok=True)
            stale_path.with_suffix(".error.txt").unlink(missing_ok=True)
            stale_path.with_suffix(".pause.json").unlink(missing_ok=True)
        item.status = "queued"
        item.terminal_blocked = False
        item.infrastructure_recoveries += 1
        reason = "Infrastructure-only failure recovered without consuming a specification revision."
        if reason not in item.notes:
            item.notes.append(reason)
        enqueue_task(
            repo_root=repo_root,
            config=factory,
            source=task_path,
            replace=True,
        )
        save_feature_ledger(factory.resolve(repo_root, factory.feature_ledger_path), ledger)
        commit_all(repo_root, f"recover infrastructure {item.task_id.lower()}")
        return RespecOutcome(changed=True)
    if current >= ceiling:
        item.status = "blocked"
        item.terminal_blocked = True
        if infrastructure_exhausted:
            reason = (
                "Infrastructure-recovery ceiling reached while the re-specification ceiling was "
                "already exhausted; repeated infrastructure-only failures are preventing forward "
                "progress and require operator intervention rather than another automatic "
                "recovery."
            )
        elif value_failure:
            reason = (
                "Material-value redesign ceiling reached; the feature remains technically "
                "possible but has not demonstrated a commercially material result."
            )
        else:
            reason = "Automatic re-specification ceiling reached."
        if reason not in item.notes:
            item.notes.append(reason)
        return RespecOutcome(changed=False, block_reason=reason, evidence_path=evidence_path)
    if task_path.exists():
        archive_failed_packet(repo_root, task_path, revision=item.revisions + 1)
    item.revisions += 1
    if infrastructure_exhausted:
        item.notes.append(
            f"Revision {item.revisions}: consecutive infrastructure recoveries reached "
            f"{autonomy.max_consecutive_infrastructure_recoveries} without a completed run, so "
            "the failure is treated as a specification defect (for example an under-sized turn "
            "or budget bound) and consumes a revision."
        )
    item.infrastructure_recoveries = 0
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
    for queue_state in ("failed", "blocked"):
        failed_path = dirs[queue_state] / f"{item.task_id}.yaml"
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
    return RespecOutcome(changed=True)


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
    hard_stuck_path = repo_root / autonomy.hard_stuck_path
    if hard_stuck_path.is_file():
        hard_stuck = read_json(hard_stuck_path, {})
        retry_raw = hard_stuck.get("auto_retry_at")
        retry_at = datetime.fromisoformat(retry_raw) if retry_raw else _now()
        if retry_at > _now():
            state.status = "hard_stuck"
            state.current_action = "hard stuck — safely paused"
            state.next_wake_at = retry_at
            state.last_event = f"automatic independent repair retry scheduled at {retry_at}"
            save_state(repo_root, factory, state)
            if once:
                return
            await asyncio.sleep(max(1.0, (retry_at - _now()).total_seconds()))
        clear_hard_stuck(repo_root, autonomy)
        state.repair_attempts = 0
        state.repair_status = None
        state.blocker_reason = None
        state.required_action = None
        state.blocked_tasks = []
        state.next_wake_at = None
        state.status = "restarting"
        state.current_action = "automatic independent repair retry"
        save_state(repo_root, factory, state)
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

        github_state_path = factory.resolve(repo_root, factory.github_state_path)
        if load_github_state(github_state_path).pending:
            try:
                pending_github_result = _sync_github_best_effort(
                    repo_root=repo_root,
                    factory=factory,
                    reason="resume pending origin/main sync before new work",
                    force=True,
                )
            except GitHubDivergenceError as exc:
                state.status = "blocked"
                state.last_event = f"GitHub divergence while resuming pending sync: {exc}"
                state.blocked_tasks = ["GITHUB_SYNC"]
                save_state(repo_root, factory, state)
                _notify(autonomy, state.last_event)
                return
            if pending_github_result.get("error"):
                state.consecutive_failures += 1
                state.status = "waiting_github"
                state.current_action = "resume pending origin/main sync and required CI"
                state.next_wake_at = _now() + timedelta(
                    seconds=autonomy.hard_stuck_retry_seconds
                )
                state.last_event = (
                    "Durable GitHub state is pending; no Claude task will start before "
                    f"retry at {state.next_wake_at.isoformat()}: "
                    f"{pending_github_result.get('error')}"
                )
                save_state(repo_root, factory, state)
                if (
                    state.consecutive_failures
                    >= autonomy.max_consecutive_factory_failures
                ):
                    await _repair_or_hard_stuck(
                        repo_root=repo_root,
                        factory=factory,
                        autonomy=autonomy,
                        state=state,
                        reason=state.last_event,
                        blocker_id="GITHUB_SYNC",
                    )
                    return
                if once:
                    return
                await asyncio.sleep(
                    max(1.0, (state.next_wake_at - _now()).total_seconds())
                )
                continue
            state.consecutive_failures = 0
            state.next_wake_at = None
            state.current_action = None
            state.last_event = "pending origin/main synchronization and required CI completed"
            save_state(repo_root, factory, state)
        if autonomy.auto_resume_quota:
            promote_due_paused(repo_root, factory)
        ledger_path = factory.resolve(repo_root, factory.feature_ledger_path)
        ledger = load_feature_ledger(ledger_path)
        if sync_ledger_from_queue(repo_root, factory, ledger):
            save_feature_ledger(ledger_path, ledger)
            commit_all(repo_root, "update roadmap")
        try:
            recovered_after_repair = recover_task_after_verified_repair(
                repo_root=repo_root,
                factory=factory,
                state=state,
                ledger=ledger,
            )
        except GitError as exc:
            state.last_event = f"candidate recovery after controller repair failed: {exc}"
            save_state(repo_root, factory, state)
            await _repair_or_hard_stuck(
                repo_root=repo_root,
                factory=factory,
                autonomy=autonomy,
                state=state,
                reason=state.last_event,
                blocker_id=state.active_task_id or "FACTORY_RECOVERY",
            )
            return
        if recovered_after_repair:
            save_state(repo_root, factory, state)
            try:
                _sync_github_best_effort(
                    repo_root=repo_root,
                    factory=factory,
                    reason="verified controller repair and recovered task",
                    force=True,
                )
            except GitHubDivergenceError as exc:
                state.status = "blocked"
                state.last_event = f"GitHub divergence after controller repair: {exc}"
                state.blocked_tasks = ["GITHUB_SYNC"]
                save_state(repo_root, factory, state)
                return
            if once:
                return
            continue

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
                respec_outcome = await respec_failed_item(
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
            if not respec_outcome.changed:
                save_feature_ledger(ledger_path, ledger)
                commit_all(repo_root, f"block {failed_item.task_id.lower()}")
                await _repair_or_hard_stuck(
                    repo_root=repo_root,
                    factory=factory,
                    autonomy=autonomy,
                    state=state,
                    reason=respec_block_reason(failed_item, respec_outcome),
                    blocker_id=failed_item.task_id,
                )
                return
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
            state.repair_attempts = 0
            state.repair_status = None
            state.blocker_reason = None
            state.required_action = None
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
            while github_result.get("status") == "deferred" and github_result.get("error"):
                state.consecutive_failures += 1
                state.status = "waiting_github"
                state.current_action = "retry origin/main synchronization and required CI"
                state.next_wake_at = _now() + timedelta(
                    seconds=autonomy.hard_stuck_retry_seconds
                )
                state.last_event = (
                    "origin/main synchronization or required CI failed; no new task will "
                    f"start before retry at {state.next_wake_at.isoformat()}: "
                    f"{github_result.get('error')}"
                )
                save_state(repo_root, factory, state)
                if (
                    state.consecutive_failures
                    >= autonomy.max_consecutive_factory_failures
                ):
                    await _repair_or_hard_stuck(
                        repo_root=repo_root,
                        factory=factory,
                        autonomy=autonomy,
                        state=state,
                        reason=state.last_event,
                        blocker_id="GITHUB_SYNC",
                    )
                    return
                if once:
                    return
                await asyncio.sleep(
                    max(1.0, (state.next_wake_at - _now()).total_seconds())
                )
                github_result = _sync_github_best_effort(
                    repo_root=repo_root,
                    factory=factory,
                    reason="retry verified task origin/main sync",
                    force=True,
                )
            state.consecutive_failures = 0
            state.next_wake_at = None
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
                    await _repair_or_hard_stuck(
                        repo_root=repo_root,
                        factory=factory,
                        autonomy=autonomy,
                        state=state,
                        reason=state.last_event,
                        blocker_id=next_item.task_id,
                    )
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

        terminal = terminal_root_blocker(ledger)
        if terminal is not None:
            state.active_task_id = terminal.task_id
            state.current_action = "autonomous repair of terminal root blocker"
            state.blocker_reason = terminal_blocker_reason(repo_root, factory, terminal)
            save_state(repo_root, factory, state)
            await _repair_or_hard_stuck(
                repo_root=repo_root,
                factory=factory,
                autonomy=autonomy,
                state=state,
                reason=(
                    f"Task {terminal.task_id} is the terminal root blocker preventing roadmap "
                    f"progress. Durable blocker: {state.blocker_reason}"
                ),
                blocker_id=terminal.task_id,
            )
            return

        blocked = visible_blocked_task_ids(ledger)
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
        await asyncio.sleep(autonomy.idle_poll_seconds)


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
        try:
            await _run_autopilot_inner(
                repo_root=resolved,
                factory_config_path=factory_config_path,
                autonomy_config_path=autonomy_config_path,
                once=once,
            )
        except (QuotaLimitPause, AuthenticationPause):
            raise
        except Exception as exc:  # noqa: BLE001
            autonomy_path = autonomy_config_path or Path(factory.autonomy_config_path)
            autonomy = load_autonomy_config(
                autonomy_path if autonomy_path.is_absolute() else resolved / autonomy_path
            )
            state = load_state(resolved, factory)
            await _repair_or_hard_stuck(
                repo_root=resolved,
                factory=factory,
                autonomy=autonomy,
                state=state,
                reason=f"Unhandled controller failure: {type(exc).__name__}: {exc}",
                blocker_id=state.active_task_id or "FACTORY_CONTROLLER",
            )
