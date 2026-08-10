from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rich.console import Console

from .checkpoints import CheckpointStore, checkpoint_result_payload, new_checkpoint
from .claude_features import (
    load_claude_features,
    make_session_name,
    should_launch_scout,
)
from .claude_runner import run_agent_stage
from .commit_messages import stage_commit_message
from .gates import (
    PathPolicyError,
    PrivateGateError,
    run_gate,
    run_private_gate,
    select_gates,
    validate_changed_paths,
)
from .github_sync import GithubSyncError, record_verified_task, run_remote_ci
from .gitops import (
    Worktree,
    changed_files,
    cleanup_task_branches,
    cleanup_worktree,
    commit_all,
    create_worktree,
    current_sha,
    ensure_git_repo,
    fast_forward_main,
    is_clean,
    squash_candidate,
)
from .handoffs import write_handoff
from .ledger import Ledger
from .models import (
    FactoryConfig,
    GateResult,
    PauseKind,
    PipelineCheckpoint,
    PipelineState,
    QuotaPauseRecord,
    RoleConfig,
    RoleName,
    Stage,
    StageResult,
    TaskPacket,
    ValueStatus,
    Verdict,
)
from .provenance import append_provenance
from .quality_policy import QualityPolicyError, enforce_candidate_quality
from .quota import AuthenticationPause, QuotaLimitPause
from .util import run_command, utc_stamp, write_json
from .value import ValueGateError, evaluate_value_contract

console = Console()


class PipelineFailure(RuntimeError):
    pass


class PipelineBlocked(RuntimeError):
    pass


MAX_STAGE_TURNS = 200
TURN_ESCALATION_FACTOR = 2
_TURN_CEILING_MARKERS = (
    "reached maximum number of turns",
    "error_max_turns",
    "terminal_reason=max_turns",
)


def stage_hit_turn_ceiling(result: StageResult) -> bool:
    """A turn ceiling truncates the work phase; it is not a truthful product rejection.

    The report-continuation path can still rescue a structured report from a truncated
    session, so ``terminal_reason`` may read ``completed`` while the durable error text
    still records the ceiling. Both signals are checked.
    """

    if (result.terminal_reason or "").strip().lower() == "max_turns":
        return True
    error = (result.error or "").lower()
    return any(marker in error for marker in _TURN_CEILING_MARKERS)


def escalated_turn_budget(current: int) -> int | None:
    """Bounded one-step turn increase so a retry is not truncated identically.

    Token and dollar budgets still bound the retry; only the turn ceiling moves.
    Returns ``None`` when the stage already sits at the schema ceiling.
    """

    if current >= MAX_STAGE_TURNS:
        return None
    return min(current * TURN_ESCALATION_FACTOR, MAX_STAGE_TURNS)


def retry_stage_update(
    stage: Stage,
    result: StageResult,
    role_config: RoleConfig,
    model: str,
) -> dict[str, object]:
    """Rotate the retry model, and raise the turn ceiling only when it caused truncation.

    Without the turn increase a stage that exhausted its turns is retried with the exact
    same resource ceiling, so it truncates again and burns the whole bounded retry budget
    on one deterministic infrastructure limit. A truthful product rejection keeps its
    original turn budget.
    """

    update: dict[str, object] = {"model": model}
    if not stage_hit_turn_ceiling(result):
        return update
    escalated = escalated_turn_budget(stage.max_turns or role_config.max_turns)
    if escalated is not None:
        update["max_turns"] = escalated
    return update


def _role_requires_changes(role: RoleName) -> bool:
    return role in {
        RoleName.PLANNER,
        RoleName.SPECIFICATION,
        RoleName.BUILDER,
        RoleName.RESEARCH,
        RoleName.RECOVERY,
    }


def _find_mutating_stage(task: TaskPacket) -> Stage:
    preferred = task.repair.mutating_role
    if preferred is not None:
        for stage in task.pipeline:
            if stage.role == preferred:
                return stage
    for role in (
        RoleName.BUILDER,
        RoleName.PLANNER,
        RoleName.SPECIFICATION,
        RoleName.RESEARCH,
        RoleName.RECOVERY,
    ):
        for stage in task.pipeline:
            if stage.role == role:
                return stage
    raise PipelineFailure("Repair requested but task pipeline has no writable stage")


def _find_stage_index(task: TaskPacket, role: RoleName) -> int:
    for index, stage in enumerate(task.pipeline):
        if stage.role == role:
            return index
    return 0


def _findings_from_result(result: StageResult) -> list[str]:
    findings: list[str] = []
    if result.report:
        findings.extend(result.report.findings)
        findings.extend(result.report.limitations)
    if result.error:
        findings.append(result.error)
    for gate in result.gate_results:
        if not gate.passed:
            findings.append(
                f"Machine gate {gate.name!r} failed with exit code {gate.return_code}; "
                f"see {gate.stderr_path} and {gate.stdout_path}."
            )
    if not findings:
        findings.append(f"Stage {result.role.value} returned verdict {result.verdict.value}.")
    return findings


def apply_scout_verdict(
    primary: StageResult,
    scout: StageResult,
    *,
    blocking_on_concrete_failure: bool,
    blocking_on_non_pass: bool,
) -> None:
    if primary.verdict != Verdict.PASS or scout.verdict == Verdict.PASS:
        return
    findings = _findings_from_result(scout)
    if blocking_on_concrete_failure and scout.verdict == Verdict.FAIL:
        primary.verdict = Verdict.FAIL
        primary.error = (
            "Integration scout found a concrete blocking contradiction: "
            + " | ".join(findings[:4])
        )
    elif blocking_on_non_pass:
        primary.verdict = scout.verdict
        primary.error = (
            f"Integration scout returned {scout.verdict.value}; independent peer evidence "
            "is required: "
            + " | ".join(findings[:4])
        )


def _clear_active(checkpoint: PipelineCheckpoint) -> None:
    checkpoint.active_role = None
    checkpoint.active_attempt = None
    checkpoint.active_base_sha = None
    checkpoint.active_worktree = None


def _checkpoint_partial_work(
    *,
    repo_root: Path,
    task: TaskPacket,
    stage: Stage,
    role_config: RoleConfig,
    worktree: Worktree,
    checkpoint: PipelineCheckpoint,
    reason: str,
) -> str:
    read_only = role_config.read_only if stage.read_only is None else stage.read_only
    changed = changed_files(worktree.path, worktree.base_sha)
    validate_changed_paths(
        changed,
        allowed=stage.allowed_paths,
        forbidden=stage.forbidden_paths,
        read_only=read_only,
    )
    candidate_sha = worktree.base_sha
    if not read_only and changed:
        committed = commit_all(
            worktree.path,
            stage_commit_message(task, stage.role, checkpoint=True),
        )
        if committed:
            candidate_sha = committed
    checkpoint.candidate_sha = candidate_sha
    checkpoint.previous_findings = [
        reason,
        "Resume in a fresh Claude session. Inspect the current candidate first, preserve valid "
        "partial work, and complete the unchanged acceptance criteria without weakening tests.",
    ]
    cleanup_worktree(repo_root, worktree, delete_branch=False)
    _clear_active(checkpoint)
    return candidate_sha


def _recover_interrupted_stage(
    *,
    repo_root: Path,
    task: TaskPacket,
    role_configs: dict[RoleName, RoleConfig],
    checkpoint: PipelineCheckpoint,
    store: CheckpointStore,
) -> None:
    if checkpoint.active_role is None or checkpoint.active_worktree is None:
        _clear_active(checkpoint)
        checkpoint.state = PipelineState.RUNNING
        checkpoint.previous_findings = [
            "The factory process stopped during the prior stage. Start a fresh session from the "
            "last durable candidate SHA and re-run the stage."
        ]
        store.save(checkpoint)
        return

    path = Path(checkpoint.active_worktree)
    role = checkpoint.active_role
    stage = task.pipeline[checkpoint.stage_index]
    if stage.role != role:
        raise PipelineBlocked(
            f"Checkpoint role mismatch: checkpoint={role.value}, task stage={stage.role.value}"
        )
    if path.exists():
        branch = run_command(["git", "branch", "--show-current"], cwd=path).stdout.strip()
        worktree = Worktree(
            path=path,
            branch=branch,
            base_sha=checkpoint.active_base_sha or checkpoint.candidate_sha,
        )
        try:
            _checkpoint_partial_work(
                repo_root=repo_root,
                task=task,
                stage=stage,
                role_config=role_configs[role],
                worktree=worktree,
                checkpoint=checkpoint,
                reason="Recovered partial work after an interrupted factory process.",
            )
        except PathPolicyError as exc:
            checkpoint.state = PipelineState.BLOCKED
            checkpoint.error = f"Interrupted worktree violated path policy: {exc}"
            store.save(checkpoint)
            raise PipelineBlocked(checkpoint.error) from exc
    else:
        _clear_active(checkpoint)
        checkpoint.previous_findings = [
            "The prior process stopped and its active worktree no longer exists. Re-run this "
            "stage from the last durable candidate SHA in a fresh session."
        ]
    checkpoint.state = PipelineState.RUNNING
    checkpoint.pause = None
    store.save(checkpoint)


async def _execute_stage(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    role_configs: dict[RoleName, RoleConfig],
    stage: Stage,
    base_sha: str,
    run_id: str,
    attempt: int,
    ledger: Ledger,
    previous_findings: list[str] | None,
    checkpoint: PipelineCheckpoint,
    checkpoint_store: CheckpointStore,
) -> tuple[StageResult, str, Worktree]:
    role_config = role_configs[stage.role]
    features = load_claude_features(config.resolve(repo_root, config.claude_features_path))
    launch_scout = should_launch_scout(features, task, stage)
    scout_config = role_configs.get(RoleName.INTEGRATION_SCOUT) if launch_scout else None
    model_budget = stage.max_budget_usd or role_config.max_budget_usd
    scout_budget = scout_config.max_budget_usd if scout_config is not None else 0.0
    requested_budget = model_budget + scout_budget
    task_spend = ledger.task_cost(task.task_id, run_id)
    if task_spend + requested_budget > task.task_budget_usd:
        raise PipelineFailure(
            f"Task budget exceeded before {stage.role.value}: ${task_spend:.2f} spent, "
            f"${requested_budget:.2f} requested, ${task.task_budget_usd:.2f} task cap."
        )
    ledger.assert_budget(requested_budget)

    worktree_root = config.resolve(repo_root, config.worktree_dir)
    worktree = create_worktree(
        repo_root,
        worktree_root,
        task_id=task.task_id,
        run_id=run_id,
        role=stage.role.value,
        attempt=attempt,
        base_sha=base_sha,
    )
    artifact_dir = (
        config.resolve(repo_root, config.artifact_dir)
        / task.task_id
        / run_id
        / f"{stage.role.value}-a{attempt}"
    )

    checkpoint.state = PipelineState.RUNNING
    checkpoint.active_role = stage.role
    checkpoint.active_attempt = attempt
    checkpoint.active_base_sha = base_sha
    checkpoint.active_worktree = str(worktree.path)
    checkpoint_store.save(checkpoint)

    scout_future: asyncio.Task[StageResult] | None = None
    scout_name: str | None = None
    primary_name: str | None = None
    if launch_scout and scout_config is not None:
        primary_name = make_session_name(task.task_id, stage.role, run_id, attempt)
        scout_name = make_session_name(task.task_id, RoleName.INTEGRATION_SCOUT, run_id, attempt)
        scout_acceptance = [
            "Find concrete integration assumptions that could invalidate the builder.",
            "Message the builder at most twice with falsifiable same-task findings.",
            "Return UNKNOWN rather than guessing and write no files.",
        ]
        if task.task_id == "DEMO-001":
            scout_acceptance.extend(
                [
                    "Complete the required RPMSG/1 same-machine calibration handshake with "
                    "the builder.",
                    "Record the builder session name and received message summary in "
                    "structured evidence.",
                    "Return BLOCKED if the peer is not discoverable or delivery cannot be "
                    "evidenced.",
                ]
            )
        scout_stage = Stage(
            role=RoleName.INTEGRATION_SCOUT,
            read_only=True,
            require_changes=False,
            forbidden_paths=["**"],
            allowed_paths=[],
            acceptance_criteria=scout_acceptance,
            peer_messaging=True,
        )
        scout_future = asyncio.create_task(
            run_agent_stage(
                repo_root=repo_root,
                worktree=worktree.path,
                config=config,
                task=task,
                stage=scout_stage,
                role_config=scout_config,
                global_prompt_path=config.global_prompt,
                run_id=run_id,
                attempt=attempt,
                artifact_dir=artifact_dir / "integration-scout",
                previous_findings=previous_findings,
                base_sha=base_sha,
                handoff_path=checkpoint.handoff_path,
                session_name_override=scout_name,
                peer_names=[primary_name],
                peer_messaging_override=True,
            )
        )
        await asyncio.sleep(features.integration_scout.startup_delay_seconds)

    try:
        result = await run_agent_stage(
            repo_root=repo_root,
            worktree=worktree.path,
            config=config,
            task=task,
            stage=stage,
            role_config=role_config,
            global_prompt_path=config.global_prompt,
            run_id=run_id,
            attempt=attempt,
            artifact_dir=artifact_dir,
            previous_findings=previous_findings,
            base_sha=base_sha,
            handoff_path=checkpoint.handoff_path,
            session_name_override=primary_name,
            peer_names=[scout_name] if scout_name else None,
            peer_messaging_override=True if scout_name else None,
        )
        if scout_future is not None:
            try:
                scout_result = await asyncio.wait_for(
                    scout_future, timeout=features.integration_scout.timeout_seconds
                )
                result.total_cost_usd += scout_result.total_cost_usd
                result.peer_sessions.append(
                    {
                        "role": scout_result.role.value,
                        "model": scout_result.model,
                        "session_id": scout_result.session_id,
                        "session_name": scout_result.session_name,
                        "verdict": scout_result.verdict.value,
                        "cost_usd": scout_result.total_cost_usd,
                        "artifact_dir": scout_result.artifact_dir,
                    }
                )
                apply_scout_verdict(
                    result,
                    scout_result,
                    blocking_on_concrete_failure=(
                        features.integration_scout.blocking_on_concrete_failure
                    ),
                    blocking_on_non_pass=features.integration_scout.blocking_on_non_pass,
                )
            except (TimeoutError, QuotaLimitPause, AuthenticationPause) as exc:
                result.peer_sessions.append(
                    {
                        "role": RoleName.INTEGRATION_SCOUT.value,
                        "session_name": scout_name,
                        "verdict": "unavailable",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if (
                    features.integration_scout.blocking_on_non_pass
                    and result.verdict == Verdict.PASS
                ):
                    result.verdict = Verdict.UNKNOWN
                    result.error = (
                        "Integration scout was unavailable; independent peer evidence is "
                        f"required: {type(exc).__name__}: {exc}"
                    )
            except Exception as exc:  # noqa: BLE001
                result.peer_sessions.append(
                    {
                        "role": RoleName.INTEGRATION_SCOUT.value,
                        "session_name": scout_name,
                        "verdict": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                if (
                    features.integration_scout.blocking_on_non_pass
                    and result.verdict == Verdict.PASS
                ):
                    result.verdict = Verdict.UNKNOWN
                    result.error = (
                        "Integration scout errored; independent peer evidence is required: "
                        f"{type(exc).__name__}: {exc}"
                    )
    except QuotaLimitPause as exc:
        if scout_future is not None and not scout_future.done():
            scout_future.cancel()
        if exc.stage_result is not None:
            exc.stage_result.base_sha = base_sha
            exc.stage_result.changed_files = changed_files(worktree.path, base_sha)
            ledger.append(exc.stage_result)
            checkpoint.results.append(checkpoint_result_payload(exc.stage_result))
            write_json(
                artifact_dir / "stage-result-paused.json",
                exc.stage_result.model_dump(mode="json"),
            )
        _checkpoint_partial_work(
            repo_root=repo_root,
            task=task,
            stage=stage,
            role_config=role_config,
            worktree=worktree,
            checkpoint=checkpoint,
            reason=(
                f"Claude limit interrupted {stage.role.value}; wait until "
                f"{exc.record.resume_at.isoformat()} and continue."
            ),
        )
        checkpoint.state = PipelineState.PAUSED
        checkpoint.pause = exc.record
        checkpoint.quota_resumptions[stage.role.value] = (
            checkpoint.quota_resumptions.get(stage.role.value, 0) + 1
        )
        checkpoint_store.save(checkpoint)
        raise
    except AuthenticationPause as exc:
        if scout_future is not None and not scout_future.done():
            scout_future.cancel()
        detected_at = datetime.now(UTC)
        record = QuotaPauseRecord(
            kind=PauseKind.AUTHENTICATION,
            detected_at=detected_at,
            resume_at=detected_at + timedelta(seconds=config.authentication_retry_seconds),
            message=exc.message,
            source="authentication",
        )
        _checkpoint_partial_work(
            repo_root=repo_root,
            task=task,
            stage=stage,
            role_config=role_config,
            worktree=worktree,
            checkpoint=checkpoint,
            reason=(
                "Claude subscription authentication is unavailable. Preserve permitted partial "
                "work and retry this same stage in a fresh session after authentication is "
                "restored."
            ),
        )
        checkpoint.state = PipelineState.PAUSED
        checkpoint.pause = record
        checkpoint.quota_resumptions[stage.role.value] = (
            checkpoint.quota_resumptions.get(stage.role.value, 0) + 1
        )
        checkpoint_store.save(checkpoint)
        raise QuotaLimitPause(record) from exc
    except BaseException:
        if scout_future is not None and not scout_future.done():
            scout_future.cancel()
        # The checkpoint intentionally retains active_worktree so the service can recover
        # partial edits after restart or power loss.
        checkpoint_store.save(checkpoint)
        raise

    result.base_sha = base_sha
    read_only = role_config.read_only if stage.read_only is None else stage.read_only
    require_changes = (
        _role_requires_changes(stage.role)
        if stage.require_changes is None
        else stage.require_changes
    )
    changed = changed_files(worktree.path, base_sha)
    result.changed_files = changed
    path_policy_valid = True
    try:
        validate_changed_paths(
            changed,
            allowed=stage.allowed_paths,
            forbidden=stage.forbidden_paths,
            read_only=read_only,
        )
        if require_changes and result.verdict == Verdict.PASS and not changed:
            raise PathPolicyError(
                f"Stage {stage.role.value} declared PASS but produced no repository change."
            )
    except PathPolicyError as exc:
        path_policy_valid = False
        result.verdict = Verdict.FAIL
        result.error = f"{result.error}; {exc}" if result.error else str(exc)

    if result.verdict == Verdict.PASS and not read_only:
        try:
            enforce_candidate_quality(
                worktree=worktree.path,
                base_sha=base_sha,
                task=task,
                artifact_dir=artifact_dir,
            )
        except QualityPolicyError as exc:
            result.verdict = Verdict.FAIL
            result.error = f"{result.error}; {exc}" if result.error else str(exc)

    if result.verdict == Verdict.PASS:
        gate_results: list[GateResult] = []
        for gate in select_gates(task.gates, stage.role, stage.machine_gates):
            gate_result = run_gate(gate, cwd=worktree.path, artifact_dir=artifact_dir)
            gate_results.append(gate_result)
            if gate.required and not gate_result.passed:
                result.verdict = Verdict.FAIL
        result.gate_results = gate_results

    next_sha = base_sha
    if result.verdict == Verdict.PASS and not read_only:
        commit = commit_all(
            worktree.path,
            stage_commit_message(task, stage.role),
        )
        if commit:
            next_sha = commit
            result.commit_sha = commit
    elif result.verdict == Verdict.PASS:
        result.commit_sha = base_sha
    elif not read_only and changed and path_policy_valid:
        # Preserve in-scope partial work on the isolated candidate branch. A fresh
        # Sonnet/Opus session can finish it; final gates still control promotion.
        commit = commit_all(
            worktree.path,
            stage_commit_message(task, stage.role, checkpoint=True),
        )
        if commit:
            next_sha = commit
            result.commit_sha = commit

    handoff = write_handoff(
        artifact_dir=artifact_dir,
        task=task,
        result=result,
        base_sha=base_sha,
        candidate_sha=next_sha,
        next_action=(
            "advance to the next independent role"
            if result.verdict == Verdict.PASS
            else "start a fresh bounded repair or re-specification session"
        ),
        findings=_findings_from_result(result) if result.verdict != Verdict.PASS else [],
    )
    checkpoint.handoff_path = str(handoff)
    append_provenance(
        config.resolve(repo_root, config.provenance_path),
        {
            "task_id": task.task_id,
            "run_id": run_id,
            "role": stage.role.value,
            "attempt": attempt,
            "risk_tier": task.risk_tier.value,
            "model": result.model,
            "session_id": result.session_id,
            "verdict": result.verdict.value,
            "base_sha": base_sha,
            "candidate_sha": next_sha,
            "commit_sha": result.commit_sha,
        },
    )
    write_json(artifact_dir / "stage-result-final.json", result.model_dump(mode="json"))
    ledger.append(result)
    cleanup_worktree(repo_root, worktree, delete_branch=False)
    _clear_active(checkpoint)
    checkpoint_store.save(checkpoint)
    return result, next_sha, worktree


def _run_value_release_gate(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    candidate_sha: str,
    run_id: str,
) -> dict[str, object]:
    worktree = create_worktree(
        repo_root,
        config.resolve(repo_root, config.worktree_dir),
        task_id=task.task_id,
        run_id=run_id,
        role="value-gate",
        attempt=1,
        base_sha=candidate_sha,
    )
    artifact_dir = (
        config.resolve(repo_root, config.artifact_dir) / task.task_id / run_id / "value-gate"
    )
    try:
        result = evaluate_value_contract(
            repo_root=worktree.path, task=task, artifact_dir=artifact_dir
        )
    except ValueGateError as exc:
        raise PipelineFailure(f"Value evidence gate failed: {exc}") from exc
    finally:
        cleanup_worktree(repo_root, worktree, delete_branch=False)

    assessment = result.assessment
    payload = assessment.model_dump(mode="json")
    if assessment.status in {ValueStatus.FAIL, ValueStatus.REDESIGN, ValueStatus.UNKNOWN}:
        raise PipelineFailure(
            f"Material-value gate returned {assessment.status.value}: {assessment.summary}"
        )
    if assessment.status == ValueStatus.EXTERNAL_EVIDENCE_REQUIRED:
        raise PipelineBlocked(
            "External value evidence is required and cannot be manufactured by the autonomous "
            f"builder: {assessment.summary}"
        )
    return payload


def _run_private_release_gate(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    candidate_sha: str,
    run_id: str,
) -> tuple[dict[str, object], Worktree | None]:
    private = task.private_gate
    if not private.suite:
        return {"configured": False, "required": private.required, "status": "not-requested"}, None

    runner_value = os.getenv(config.private_gate_runner_env)
    if not runner_value:
        if private.required:
            raise PipelineFailure(
                f"Required private gate is configured but {
                    config.private_gate_runner_env
                } is unset."
            )
        return {
            "configured": False,
            "required": False,
            "suite": private.suite,
            "status": "runner-unavailable",
        }, None

    worktree = create_worktree(
        repo_root,
        config.resolve(repo_root, config.worktree_dir),
        task_id=task.task_id,
        run_id=run_id,
        role="private-gate",
        attempt=1,
        base_sha=candidate_sha,
    )
    artifact_dir = (
        config.resolve(repo_root, config.artifact_dir) / task.task_id / run_id / "private-gate"
    )
    try:
        result = run_private_gate(
            runner=Path(runner_value),
            suite=private.suite,
            cwd=worktree.path,
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            timeout_seconds=private.timeout_seconds,
            task_id=task.task_id,
            run_id=run_id,
            candidate_sha=candidate_sha,
        )
    except PrivateGateError as exc:
        raise PipelineFailure(str(exc)) from exc

    payload: dict[str, object] = {
        "configured": True,
        "required": private.required,
        "suite": private.suite,
        "status": "pass" if result.passed else "fail",
        "result": result.model_dump(mode="json"),
    }
    write_json(artifact_dir / "private-gate-result.json", payload)
    if private.required and not result.passed:
        raise PipelineFailure(
            "Required external private gate failed. Hidden implementation details are "
            "intentionally "
            f"not passed to the builder; inspect {artifact_dir}."
        )
    return payload, worktree


def _load_checkpoint(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    starting_sha: str,
    resume: bool,
) -> tuple[CheckpointStore, PipelineCheckpoint]:
    store = CheckpointStore(config.resolve(repo_root, config.pipeline_state_dir))
    existing = store.load(task.task_id) if resume else None
    if existing and existing.state in {
        PipelineState.RUNNING,
        PipelineState.PAUSED,
        PipelineState.BLOCKED,
    }:
        if existing.starting_sha != starting_sha:
            raise PipelineBlocked(
                f"Cannot resume {task.task_id}: main moved from {existing.starting_sha} to "
                f"{starting_sha}. Reconcile the previous candidate explicitly."
            )
        return store, existing
    if existing:
        store.archive(existing)
    checkpoint = new_checkpoint(
        task_id=task.task_id,
        run_id=utc_stamp(),
        starting_sha=starting_sha,
    )
    store.save(checkpoint)
    return store, checkpoint


async def run_pipeline(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    role_configs: dict[RoleName, RoleConfig],
    merge_override: bool | None = None,
    resume: bool = True,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    ensure_git_repo(repo_root)
    if config.require_clean_main and not is_clean(repo_root):
        raise PipelineFailure(
            "Main repository is not clean. Commit or stash changes before running."
        )

    starting_sha = current_sha(repo_root, task.base_branch)
    checkpoint_store, checkpoint = _load_checkpoint(
        repo_root=repo_root,
        config=config,
        task=task,
        starting_sha=starting_sha,
        resume=resume,
    )
    if checkpoint.state == PipelineState.BLOCKED:
        raise PipelineBlocked(checkpoint.error or "Pipeline is blocked")
    if checkpoint.state == PipelineState.PAUSED and checkpoint.pause is not None:
        now = datetime.now(UTC)
        if checkpoint.pause.resume_at > now:
            raise QuotaLimitPause(checkpoint.pause)
        checkpoint.state = PipelineState.RUNNING
        checkpoint.pause = None
        checkpoint_store.save(checkpoint)
    if checkpoint.state == PipelineState.RUNNING and checkpoint.active_role is not None:
        _recover_interrupted_stage(
            repo_root=repo_root,
            task=task,
            role_configs=role_configs,
            checkpoint=checkpoint,
            store=checkpoint_store,
        )

    run_id = checkpoint.run_id
    candidate_sha = checkpoint.candidate_sha
    ledger = Ledger(config.resolve(repo_root, config.ledger_path), config.monthly_budget_usd)
    all_results = [StageResult.model_validate(item) for item in checkpoint.results]

    console.rule(f"TrainCapsule AI Factory — {task.task_id} — {run_id}")
    try:
        while checkpoint.stage_index < len(task.pipeline):
            stage = task.pipeline[checkpoint.stage_index]
            key = stage.role.value
            checkpoint.stage_attempts[key] = checkpoint.stage_attempts.get(key, 0) + 1
            attempt = checkpoint.stage_attempts[key]
            checkpoint_store.save(checkpoint)
            console.print(
                f"[bold]{stage.role.value}[/bold] fresh session {attempt} from "
                f"{candidate_sha[:12]} using {stage.model or role_configs[stage.role].model}"
            )
            result, next_sha, _worktree = await _execute_stage(
                repo_root=repo_root,
                config=config,
                task=task,
                role_configs=role_configs,
                stage=stage,
                base_sha=candidate_sha,
                run_id=run_id,
                attempt=attempt,
                ledger=ledger,
                previous_findings=checkpoint.previous_findings,
                checkpoint=checkpoint,
                checkpoint_store=checkpoint_store,
            )
            all_results.append(result)
            checkpoint.results.append(checkpoint_result_payload(result))

            if result.verdict == Verdict.PASS:
                candidate_sha = next_sha
                checkpoint.candidate_sha = candidate_sha
                checkpoint.previous_findings = None
                checkpoint.stage_index += 1
                checkpoint.state = PipelineState.RUNNING
                checkpoint_store.save(checkpoint)
                continue

            checkpoint.stage_failures[key] = checkpoint.stage_failures.get(key, 0) + 1
            findings = _findings_from_result(result)
            console.print(f"[red]Stage failed:[/red] {findings}")

            is_configured_mutator = (
                task.repair.enabled
                and task.repair.mutating_role is not None
                and stage.role == task.repair.mutating_role
            )
            if stage.role == RoleName.BUILDER or is_configured_mutator:
                failure_count = checkpoint.stage_failures[key]
                if next_sha != candidate_sha:
                    candidate_sha = next_sha
                    checkpoint.candidate_sha = candidate_sha
                if is_configured_mutator and stage.role != RoleName.BUILDER:
                    retry_models = (
                        task.repair.mutating_retry_models
                        or task.repair.builder_models
                    )
                    retry_index = failure_count - 1
                else:
                    retry_models = task.repair.builder_models
                    retry_index = failure_count
                if retry_index < len(retry_models):
                    update = retry_stage_update(
                        stage,
                        result,
                        role_configs[stage.role],
                        retry_models[retry_index],
                    )
                    if "max_turns" in update:
                        console.print(
                            f"[yellow]Turn ceiling hit:[/yellow] retrying "
                            f"{stage.role.value} with {update['max_turns']} turns "
                            f"(was {stage.max_turns or role_configs[stage.role].max_turns})"
                        )
                    replacement = stage.model_copy(update=update)
                    task.pipeline[checkpoint.stage_index] = replacement
                    checkpoint.previous_findings = findings
                    checkpoint_store.save(checkpoint)
                    continue
                raise PipelineFailure(
                    f"Mutating stage {stage.role.value} failed after "
                    f"{failure_count} bounded failures. "
                    "Re-specification is required."
                )

            review_roles = {
                RoleName.ADVERSARY,
                RoleName.AUDIT,
                RoleName.SECURITY,
                RoleName.PERFORMANCE,
                RoleName.VALUE_VALIDATOR,
                RoleName.VALUE_ADVERSARY,
                RoleName.RELEASE,
            }
            if (
                stage.role in review_roles
                and task.repair.enabled
                and checkpoint.repair_cycles < task.repair.max_cycles
            ):
                mutating = _find_mutating_stage(task)
                repair_findings = list(findings)
                repaired = False
                while checkpoint.repair_cycles < task.repair.max_cycles:
                    checkpoint.repair_cycles += 1
                    models = task.repair.builder_models
                    model = models[
                        min(checkpoint.repair_cycles - 1, len(models) - 1)
                    ]
                    repair_stage = mutating.model_copy(
                        update={
                            "model": model,
                            "acceptance_criteria": mutating.acceptance_criteria
                            + [
                                "Resolve every previous reviewer finding without "
                                "weakening evidence."
                            ],
                        }
                    )
                    repair_key = repair_stage.role.value
                    checkpoint.stage_attempts[repair_key] = (
                        checkpoint.stage_attempts.get(repair_key, 0) + 1
                    )
                    repair_attempt = checkpoint.stage_attempts[repair_key]
                    console.print(
                        f"[yellow]Repair cycle "
                        f"{checkpoint.repair_cycles}/{task.repair.max_cycles}"
                        f"[/yellow] with {repair_stage.role.value} model {model}"
                    )
                    repair_result, repair_sha, _repair_worktree = await _execute_stage(
                        repo_root=repo_root,
                        config=config,
                        task=task,
                        role_configs=role_configs,
                        stage=repair_stage,
                        base_sha=candidate_sha,
                        run_id=run_id,
                        attempt=repair_attempt,
                        ledger=ledger,
                        previous_findings=repair_findings,
                        checkpoint=checkpoint,
                        checkpoint_store=checkpoint_store,
                    )
                    all_results.append(repair_result)
                    checkpoint.results.append(checkpoint_result_payload(repair_result))
                    if repair_result.verdict == Verdict.PASS:
                        candidate_sha = repair_sha
                        checkpoint.candidate_sha = candidate_sha
                        checkpoint.previous_findings = None
                        checkpoint.stage_index = _find_stage_index(
                            task, task.repair.restart_review_from
                        )
                        checkpoint_store.save(checkpoint)
                        repaired = True
                        break
                    repair_findings.extend(_findings_from_result(repair_result))
                    checkpoint.previous_findings = repair_findings
                    checkpoint_store.save(checkpoint)
                if not repaired:
                    raise PipelineFailure(
                        "Every bounded Sonnet/Opus repair cycle failed; "
                        "automatic re-specification is required."
                    )
                continue

            raise PipelineFailure(f"Stage {stage.role.value} failed and no repair path remains.")

        value_gate_summary = _run_value_release_gate(
            repo_root=repo_root,
            config=config,
            task=task,
            candidate_sha=candidate_sha,
            run_id=run_id,
        )
        checkpoint.value_gate = value_gate_summary
        checkpoint_store.save(checkpoint)

        private_gate_summary, private_worktree = _run_private_release_gate(
            repo_root=repo_root,
            config=config,
            task=task,
            candidate_sha=candidate_sha,
            run_id=run_id,
        )
        if private_worktree:
            cleanup_worktree(repo_root, private_worktree, delete_branch=False)
        checkpoint.private_gate = private_gate_summary
        checkpoint_store.save(checkpoint)

        # Create the exact one-commit release candidate before remote CI. GitHub Actions
        # therefore validates the same SHA that may later fast-forward main, not merely an
        # internal role commit with an equivalent tree.
        release_sha = squash_candidate(
            repo_root,
            task=task,
            run_id=run_id,
            starting_sha=starting_sha,
            candidate_sha=candidate_sha,
        )
        checkpoint.candidate_sha = release_sha
        checkpoint_store.save(checkpoint)

        remote_ci_summary: dict[str, object] = {
            "required": task.remote_ci_required,
            "status": "not-requested",
            "release_sha": release_sha,
        }
        if task.remote_ci_required and release_sha != starting_sha:
            try:
                remote_ci_summary = run_remote_ci(
                    repo_root=repo_root,
                    factory=config,
                    task=task,
                    candidate_sha=release_sha,
                    run_id=run_id,
                    artifact_dir=(
                        config.resolve(repo_root, config.artifact_dir)
                        / task.task_id
                        / run_id
                        / "remote-ci"
                    ),
                )
            except GithubSyncError as exc:
                raise PipelineBlocked(f"Required GitHub remote CI did not pass: {exc}") from exc
        elif task.remote_ci_required:
            remote_ci_summary["status"] = "no-change"
        checkpoint.remote_ci = remote_ci_summary
        checkpoint_store.save(checkpoint)

        should_merge = task.auto_merge if merge_override is None else merge_override
        if should_merge and release_sha != starting_sha:
            fast_forward_main(
                repo_root,
                task.base_branch,
                expected_base_sha=starting_sha,
                final_sha=release_sha,
            )
            cleanup_task_branches(repo_root, task_id=task.task_id, run_id=run_id)
            if task.github_push:
                record_verified_task(config.resolve(repo_root, config.github_state_path), task=task)

        checkpoint.state = PipelineState.PASSED
        checkpoint.completed_at = datetime.now(UTC)
        checkpoint.error = None
        checkpoint_store.save(checkpoint)
        summary: dict[str, object] = {
            "task_id": task.task_id,
            "run_id": run_id,
            "starting_sha": starting_sha,
            "verified_candidate_sha": candidate_sha,
            "final_sha": release_sha,
            "merged": bool(should_merge and release_sha != starting_sha),
            "repair_cycles": checkpoint.repair_cycles,
            "quota_resumptions": checkpoint.quota_resumptions,
            "cost_usd": sum(result.total_cost_usd for result in all_results),
            "value_gate": value_gate_summary,
            "private_gate": private_gate_summary,
            "remote_ci": remote_ci_summary,
            "risk_tier": task.risk_tier.value,
            "results": [result.model_dump(mode="json") for result in all_results],
        }
        summary_path = (
            config.resolve(repo_root, config.artifact_dir)
            / task.task_id
            / run_id
            / "pipeline-summary.json"
        )
        write_json(summary_path, summary)
        console.print(f"[green]Pipeline passed.[/green] Summary: {summary_path}")
        return summary
    except QuotaLimitPause:
        raise
    except PipelineBlocked:
        checkpoint.state = PipelineState.BLOCKED
        checkpoint.completed_at = None
        checkpoint_store.save(checkpoint)
        raise
    except Exception as exc:
        checkpoint.state = PipelineState.FAILED
        checkpoint.error = f"{type(exc).__name__}: {exc}"
        checkpoint.completed_at = datetime.now(UTC)
        checkpoint_store.save(checkpoint)
        failure_path = (
            config.resolve(repo_root, config.artifact_dir)
            / task.task_id
            / run_id
            / "pipeline-failure.json"
        )
        write_json(
            failure_path,
            {
                "task_id": task.task_id,
                "run_id": run_id,
                "starting_sha": starting_sha,
                "candidate_sha": checkpoint.candidate_sha,
                "stage_index": checkpoint.stage_index,
                "error": checkpoint.error,
                "results": checkpoint.results,
            },
        )
        raise
