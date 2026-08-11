from __future__ import annotations

import asyncio
import os
import re
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
    file_sha256,
    run_gate,
    run_private_gate,
    select_gates,
    validate_changed_paths,
)
from .github_sync import record_verified_task
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
from .model_routing import may_downgrade_for_limit, routed_stage, stage_model_chain
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
from .observability import append_event
from .provenance import append_provenance
from .quality_policy import QualityPolicyError, enforce_candidate_quality
from .quota import AuthenticationPause, QuotaLimitPause
from .risk import with_working_token_reserve
from .stage_policy import (
    PRODUCT_PROTECTED_PATHS,
    apply_objective_stage_contracts,
    objective_pipeline_errors,
)
from .util import path_matches, run_command, utc_stamp, write_json
from .value import ValueGateError, evaluate_value_contract

console = Console()


class PipelineFailure(RuntimeError):
    pass


class PipelineBlocked(RuntimeError):
    pass


MAX_STAGE_TURNS = 200
TURN_ESCALATION_FACTOR = 2
MAX_REVIEW_TURN_MULTIPLIER = 4
TURN_CEILING_MARKERS = (
    "reached maximum number of turns",
    "error_max_turns",
    "terminal_reason=max_turns",
)
REVIEW_BUDGET_EXHAUSTION_MARKERS = (
    "budget exhaustion",
    "context exhaustion",
    "context/budget exhaustion",
    "insufficient budget",
    "maximum number of turns",
    "turn ceiling",
)
REVIEW_INCOMPLETE_MARKERS = (
    "not executed",
    "were not run",
    "did not run",
    "could not run",
    "before they could run",
    "review is incomplete",
    "check is incomplete",
)
MAX_REVIEW_INFRA_RETRIES = 2
STRUCTURED_OUTPUT_FAULT_MARKERS = (
    # Both forms are emitted verbatim by claude_runner: the canonical
    # ``terminal_reason=<value>`` text and the SDK result subtype.
    "terminal_reason=structured_output_retry_exhausted",
    "subtype=error_max_structured_output_retries",
)
FACTORY_REPAIR_SCOPE_MARKER = "factory_repair_required"
FINDING_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])((?:[A-Za-z0-9_.()\-]+/)+[A-Za-z0-9_.()\-]+)"
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
    return any(marker in error for marker in TURN_CEILING_MARKERS)


def review_report_hit_budget_ceiling(result: StageResult) -> bool:
    """Recognize a truthful UNKNOWN caused by an incomplete bounded review.

    Claude can sometimes use its final turn to serialize a valid UNKNOWN report after
    exhausting the session before it runs the required checks.  The SDK then reports a
    normal completion, so ``stage_hit_turn_ceiling`` cannot see the infrastructure
    cause.  Require both an explicit resource-exhaustion statement and an explicit
    incomplete-execution statement.  That keeps product/evidence UNKNOWN verdicts on
    the normal fail-closed path.
    """

    if result.verdict != Verdict.UNKNOWN or result.report is None:
        return False
    report_text = "\n".join(
        [
            result.report.summary,
            *result.report.findings,
            *result.report.limitations,
            *result.report.next_actions,
        ]
    ).lower()
    return any(marker in report_text for marker in REVIEW_BUDGET_EXHAUSTION_MARKERS) and any(
        marker in report_text for marker in REVIEW_INCOMPLETE_MARKERS
    )


def stage_hit_structured_output_fault(result: StageResult) -> bool:
    """A structured-output retry exhaustion is a tooling fault, not a review verdict.

    The Claude Agent SDK gives up after repeated attempts to coerce a response into a
    schema-valid ``AgentReport`` and returns no report at all. The review role never
    evaluated the candidate, so there are no reviewer findings for a mutating repair
    cycle to resolve; routing this straight into ``repair.max_cycles`` burns a bounded
    repair cycle on an SDK hiccup instead of retrying the same read-only review.
    """

    if (result.terminal_reason or "").strip().lower() == "structured_output_retry_exhausted":
        return True
    error = (result.error or "").lower()
    return any(marker in error for marker in STRUCTURED_OUTPUT_FAULT_MARKERS)


def terminal_failure_signal(result: StageResult) -> str:
    """The durable, classifiable text for a terminal stage failure.

    Terminal ``PipelineFailure`` messages are generic wrappers (e.g. "no repair path
    remains") that describe the pipeline's own control-flow decision, not the stage's
    actual error. Wrapping that generic text loses the one signal a recovery
    classifier needs: whether the stage itself hit a turn ceiling, an infrastructure
    fault, or a genuine product rejection. Embedding the raw ``result.error``/
    ``terminal_reason`` keeps that signal in the durable failure artifact instead of
    forcing classifiers to hardcode the wrapper text of one past incident.

    ``unknown`` is returned when the stage carried neither signal. It is deliberately
    not classifiable as infrastructure: an unattributable failure must stay a truthful
    failure rather than earn a free requeue.

    A bare ``terminal_reason`` (e.g. ``"max_turns"``) is embedded in the canonical
    ``terminal_reason=<value>`` form, matching the marker ``is_infrastructure_failure``
    matches on. Returning the bare reason made a genuine turn ceiling with no populated
    ``.error`` unclassifiable as infrastructure, consuming a re-specification revision
    identically to a truthful product rejection.
    """

    if result.error:
        return result.error
    if result.terminal_reason:
        return f"terminal_reason={result.terminal_reason}"
    return "unknown"


def terminal_failure_message(summary: str, result: StageResult) -> str:
    """Build a terminal failure message that preserves the stage's own signal.

    Every terminal ``PipelineFailure`` goes through here so the durable ``.error.txt``
    artifact and the recovery classifier always see the same text. Tests exercise this
    function directly instead of re-declaring the format string.
    """

    return f"{summary} Last stage error: {terminal_failure_signal(result)}"


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

    effort_order = ["low", "medium", "high", "xhigh", "max"]
    current_effort = stage.effort or role_config.effort
    effort_index = effort_order.index(current_effort)
    update: dict[str, object] = {
        "model": model,
        "effort": effort_order[min(effort_index + 1, len(effort_order) - 1)],
    }
    if not stage_hit_turn_ceiling(result):
        return update
    escalated = escalated_turn_budget(stage.max_turns or role_config.max_turns)
    if escalated is not None:
        update["max_turns"] = escalated
    return update


def review_turn_retry_update(
    stage: Stage,
    result: StageResult,
    role_config: RoleConfig,
) -> dict[str, object] | None:
    """Give a truncated independent review enough room without bypassing its verdict.

    Review roles must not be routed to a mutating repair merely because the reviewer
    used every turn before emitting its structured report. Retry the same independent
    role with a larger ceiling first. The increase is bounded to four times the role's
    declared budget (and the global schema ceiling), so a wedged reviewer still reaches
    the normal truthful repair/failure path.
    """

    if not (stage_hit_turn_ceiling(result) or review_report_hit_budget_ceiling(result)):
        return None
    # A truncated reviewer that already returned concrete, actionable findings has done
    # enough to start repair.  Re-running it against byte-identical input wastes a full
    # Claude session and makes the read-only role appear to be a failed repair attempt.
    if result.report and result.report.next_actions:
        return None
    base_turns = role_config.max_turns
    current_turns = stage.max_turns or base_turns
    review_ceiling = min(base_turns * MAX_REVIEW_TURN_MULTIPLIER, MAX_STAGE_TURNS)
    if current_turns >= review_ceiling:
        return None
    return {
        "max_turns": min(
            current_turns * TURN_ESCALATION_FACTOR,
            review_ceiling,
        )
    }


def review_infra_retry_update(
    result: StageResult,
    failure_count: int,
) -> dict[str, object] | None:
    """Retry an independent review whose report was lost to an SDK serialization fault.

    ``review_turn_retry_update`` only rescues a reviewer that ran out of turns. When the
    SDK instead exhausts its structured-output attempts there is no report at all, so the
    reviewer expressed no finding -- yet the review branch falls through to a mutating
    repair cycle. That spends a bounded ``repair.max_cycles`` slot, and seeds the repair
    with SDK error text as if it were review feedback, on a candidate no reviewer judged.
    Re-run the identical read-only review instead, at most ``MAX_REVIEW_INFRA_RETRIES``
    times per stage, so a persistently wedged reviewer still reaches the normal truthful
    repair/failure path and no verdict is ever assumed on its behalf.

    Returns an empty mapping when the stage must be retried unchanged: the fault is in
    report serialization, not in the review budget or the model, and the turn ceiling is
    already handled by ``review_turn_retry_update`` ahead of this check. ``None`` means
    "not a structured-output fault, or the bounded retries are spent".
    """

    if not stage_hit_structured_output_fault(result):
        return None
    if failure_count > MAX_REVIEW_INFRA_RETRIES:
        return None
    return {}


def preserve_mutating_candidate(
    checkpoint: PipelineCheckpoint,
    current_sha: str,
    attempted_sha: str,
) -> str:
    """Carry valid in-scope partial work into the next bounded repair attempt.

    ``_execute_stage`` commits path-policy-valid partial edits even when a mutating
    agent truthfully returns FAIL.  Losing that commit here makes the next repair
    restart from the older defect and leaves the durable checkpoint pointing
    backwards.  Final gates and independent reviewers still control promotion.
    """

    if attempted_sha != current_sha:
        checkpoint.candidate_sha = attempted_sha
        return attempted_sha
    return current_sha


def _role_requires_changes(role: RoleName) -> bool:
    return role in {
        RoleName.PLANNER,
        RoleName.SPECIFICATION,
        RoleName.BUILDER,
        RoleName.RESEARCH,
        RoleName.RECOVERY,
        RoleName.FACTORY_REPAIR,
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


def repository_finding_paths(repo_root: Path, findings: list[str]) -> list[str]:
    """Extract credible repository paths from reviewer findings.

    URLs and prose fragments are ignored unless the referenced path (or its parent for a
    proposed new file) exists inside the repository.
    """

    paths: set[str] = set()
    for finding in findings:
        for raw in FINDING_PATH_RE.findall(finding):
            normalized = raw.replace("\\", "/").rstrip(".,;:!?)]}")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            relative = Path(normalized)
            if ".." in relative.parts:
                continue
            candidate = repo_root / relative
            if candidate.exists() or candidate.parent.exists():
                paths.add(relative.as_posix())
    return sorted(paths)


def _policy_path_matches(path: str, patterns: list[str] | frozenset[str]) -> bool:
    """Match a path policy, including a cited recursive-directory root.

    Reviewers often cite ``docs/evidence/T002`` or ``scripts/gates`` as a repair
    surface.  ``path_matches`` correctly matches files below ``/**`` but the directory
    root itself is not a child, so recognize that equivalent citation explicitly.
    """

    if path_matches(path, list(patterns)):
        return True
    normalized = path.replace("\\", "/").rstrip("/")
    return any(
        pattern.replace("\\", "/").endswith("/**")
        and normalized == pattern.replace("\\", "/")[:-3].rstrip("/")
        for pattern in patterns
    )


def controller_owned_finding_paths(paths: list[str]) -> list[str]:
    """Return findings that product-task re-specification can never authorize."""

    return sorted(
        path for path in paths if _policy_path_matches(path, PRODUCT_PROTECTED_PATHS)
    )


def find_mutating_stage_for_findings(
    *, repo_root: Path, task: TaskPacket, findings: list[str]
) -> tuple[Stage, list[str]]:
    """Route repair to a stage that can edit the files named by an independent review.

    When every credible path is outside every writable stage, returning those paths forces
    task re-specification instead of an impossible same-role retry loop.
    """

    fallback = _find_mutating_stage(task)
    paths = repository_finding_paths(repo_root, findings)
    if not paths:
        return fallback, []
    candidates = [
        stage
        for stage in task.pipeline
        if _role_requires_changes(stage.role) and stage.read_only is not True
    ]
    candidates = candidates or [fallback]
    coverage = [
        (
            stage,
            {
                path
                for path in paths
                if _policy_path_matches(path, stage.allowed_paths)
                and not _policy_path_matches(path, stage.forbidden_paths)
            },
        )
        for stage in candidates
    ]
    best_stage, covered = max(coverage, key=lambda item: len(item[1]))
    gaps = sorted(set(paths) - covered)
    return best_stage, gaps


def cumulative_scope_gaps(task: TaskPacket, changed: list[str]) -> list[str]:
    """Return candidate paths that no writable task stage is authorized to change."""

    writable = [
        stage
        for stage in task.pipeline
        if _role_requires_changes(stage.role) and stage.read_only is not True
    ]
    return sorted(
        path
        for path in changed
        if not any(
            path_matches(path, stage.allowed_paths)
            and not path_matches(path, stage.forbidden_paths)
            for stage in writable
        )
    )


def validate_cumulative_candidate(
    *,
    worktree: Path,
    starting_sha: str,
    task: TaskPacket,
    artifact_dir: Path,
) -> list[str]:
    """Validate the complete task delta so a failed partial commit cannot hide defects."""

    cumulative_changed = changed_files(worktree, starting_sha)
    gaps = cumulative_scope_gaps(task, cumulative_changed)
    if gaps:
        raise PathPolicyError(
            "Cumulative candidate contains paths outside every writable task stage: "
            + ", ".join(gaps)
        )
    enforce_candidate_quality(
        worktree=worktree,
        base_sha=starting_sha,
        task=task,
        artifact_dir=artifact_dir,
    )
    return cumulative_changed


def _find_stage_index(task: TaskPacket, role: RoleName) -> int:
    for index, stage in enumerate(task.pipeline):
        if stage.role == role:
            return index
    return 0


def findings_from_result(result: StageResult) -> list[str]:
    findings: list[str] = []
    if result.report:
        findings.extend(result.report.findings)
        findings.extend(
            f"Reviewer-directed repair: {action}" for action in result.report.next_actions
        )
        findings.extend(f"Known limitation: {item}" for item in result.report.limitations)
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
    findings = findings_from_result(scout)
    if blocking_on_concrete_failure and scout.verdict == Verdict.FAIL:
        primary.verdict = Verdict.FAIL
        primary.error = "Integration scout found a concrete blocking contradiction: " + " | ".join(
            findings[:4]
        )
    elif blocking_on_non_pass:
        primary.verdict = scout.verdict
        primary.error = (
            f"Integration scout returned {scout.verdict.value}; independent peer evidence "
            "is required: " + " | ".join(findings[:4])
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
    stage = interrupted_stage(task, checkpoint)
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


def interrupted_stage(task: TaskPacket, checkpoint: PipelineCheckpoint) -> Stage:
    """Resolve a durable active stage, including reviewer-triggered repair work.

    During a repair cycle the pipeline index intentionally remains on the rejecting
    reviewer while the declared mutating role works from that review's candidate.  A
    process restart in that window is therefore not a checkpoint-role mismatch.  Only
    accept the task's declared mutating stage as the alternate; every other mismatch
    remains fail-closed.
    """

    scheduled = task.pipeline[checkpoint.stage_index]
    role = checkpoint.active_role
    if role is None or scheduled.role == role:
        return scheduled
    if task.repair.enabled:
        mutating = _find_mutating_stage(task)
        if mutating.role == role:
            return mutating
    raise PipelineBlocked(
        f"Checkpoint role mismatch: checkpoint={role.value}, task stage={scheduled.role.value}"
    )


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
    subscription_unbounded = (
        config.work_until_done
        and config.auth_mode == "max_oauth_only"
        and config.disable_max_oauth_budget_caps
    )
    if not subscription_unbounded:
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
        model_chain = stage_model_chain(stage, role_config)
        routed_failures: list[dict[str, object]] = []
        routed_cost = 0.0
        routed_findings = list(previous_findings or [])
        result: StageResult | None = None
        for route_index, selected_model in enumerate(model_chain):
            selected_stage = routed_stage(stage, model_chain, route_index)
            selected_artifact_dir = (
                artifact_dir
                if route_index == 0
                else artifact_dir / f"model-fallback-{route_index}-{selected_model}"
            )
            try:
                result = await run_agent_stage(
                    repo_root=repo_root,
                    worktree=worktree.path,
                    config=config,
                    task=task,
                    stage=selected_stage,
                    role_config=role_config,
                    global_prompt_path=config.global_prompt,
                    run_id=run_id,
                    attempt=attempt,
                    artifact_dir=selected_artifact_dir,
                    previous_findings=routed_findings or None,
                    base_sha=base_sha,
                    handoff_path=checkpoint.handoff_path,
                    session_name_override=primary_name,
                    peer_names=[scout_name] if scout_name else None,
                    peer_messaging_override=True if scout_name else None,
                )
                break
            except QuotaLimitPause as exc:
                if not may_downgrade_for_limit(exc.record.kind, model_chain, route_index):
                    raise
                next_model = model_chain[route_index + 1]
                partial_cost = (
                    exc.stage_result.total_cost_usd if exc.stage_result is not None else 0.0
                )
                routed_cost += partial_cost
                routed_failure: dict[str, object] = {
                    "model": selected_model,
                    "next_model": next_model,
                    "pause_kind": exc.record.kind.value,
                    "message": exc.record.message,
                    "partial_work_preserved": bool(changed_files(worktree.path, base_sha)),
                    "cost_usd": partial_cost,
                }
                routed_failures.append(routed_failure)
                write_json(
                    artifact_dir / f"model-fallback-{route_index + 1}.json",
                    routed_failure,
                )
                append_event(
                    config.resolve(repo_root, config.event_log_path),
                    event="agent_model_fallback",
                    component="pipeline",
                    task_id=task.task_id,
                    run_id=run_id,
                    role=stage.role.value,
                    detail=f"{selected_model} -> {next_model}",
                    data={"reason": exc.record.kind.value},
                )
                routed_findings.append(
                    f"The {selected_model} subscription allowance became unavailable. "
                    f"Continue the same bounded task with {next_model}; inspect and verify any "
                    "permitted partial work already present in the worktree."
                )
        if result is None:
            raise PipelineFailure("Model routing exhausted without a stage result")
        if routed_failures:
            result.total_cost_usd += routed_cost
            result.peer_sessions.extend(
                {"role": stage.role.value, "verdict": "model_fallback", **item}
                for item in routed_failures
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
            validate_cumulative_candidate(
                worktree=worktree.path,
                starting_sha=checkpoint.starting_sha,
                task=task,
                artifact_dir=artifact_dir / "cumulative-quality",
            )
        except (PathPolicyError, QualityPolicyError) as exc:
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
        findings=findings_from_result(result) if result.verdict != Verdict.PASS else [],
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


def validate_release_candidate(
    *,
    repo_root: Path,
    config: FactoryConfig,
    task: TaskPacket,
    starting_sha: str,
    candidate_sha: str,
    run_id: str,
) -> None:
    """Recheck the entire candidate delta immediately before release gates."""

    worktree = create_worktree(
        repo_root,
        config.resolve(repo_root, config.worktree_dir),
        task_id=task.task_id,
        run_id=run_id,
        role="cumulative-validation",
        attempt=1,
        base_sha=candidate_sha,
    )
    artifact_dir = (
        config.resolve(repo_root, config.artifact_dir)
        / task.task_id
        / run_id
        / "cumulative-validation"
    )
    try:
        validate_cumulative_candidate(
            worktree=worktree.path,
            starting_sha=starting_sha,
            task=task,
            artifact_dir=artifact_dir,
        )
    except (PathPolicyError, QualityPolicyError) as exc:
        raise PipelineFailure(f"Cumulative candidate validation failed: {exc}") from exc
    finally:
        cleanup_worktree(repo_root, worktree, delete_branch=False)


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

    runner = Path(runner_value).expanduser().resolve()
    try:
        runner_sha256 = file_sha256(runner)
    except PrivateGateError as exc:
        raise PipelineFailure(str(exc)) from exc

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
        observed_head_before = current_sha(worktree.path)
        if observed_head_before != candidate_sha:
            raise PipelineFailure(
                "Private-gate worktree was not created at the requested candidate SHA: "
                f"{observed_head_before} != {candidate_sha}."
            )
        result = run_private_gate(
            runner=runner,
            suite=private.suite,
            cwd=worktree.path,
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            timeout_seconds=private.timeout_seconds,
            task_id=task.task_id,
            run_id=run_id,
            candidate_sha=candidate_sha,
        )
        observed_head_after = current_sha(worktree.path)
        mutations = changed_files(worktree.path, candidate_sha)
        runner_sha256_after = file_sha256(runner)
    except PrivateGateError as exc:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise PipelineFailure(str(exc)) from exc
    except BaseException:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise

    payload: dict[str, object] = {
        "configured": True,
        "required": private.required,
        "suite": private.suite,
        "candidate_sha": candidate_sha,
        "observed_head_before": observed_head_before,
        "observed_head_after": observed_head_after,
        "runner_sha256": runner_sha256,
        "runner_sha256_after": runner_sha256_after,
        "candidate_mutations": mutations,
        "status": (
            "pass"
            if (
                result.passed
                and not mutations
                and observed_head_after == candidate_sha
                and runner_sha256_after == runner_sha256
            )
            else "fail"
        ),
        "result": result.model_dump(mode="json"),
    }
    write_json(artifact_dir / "private-gate-result.json", payload)
    if runner_sha256_after != runner_sha256:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise PipelineFailure(
            "External private gate runner changed while the suite was executing; "
            f"inspect {artifact_dir}."
        )
    if observed_head_after != candidate_sha:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise PipelineFailure(
            "External private gate changed the candidate worktree HEAD and cannot certify "
            f"it: {observed_head_after} != {candidate_sha}. Inspect {artifact_dir}."
        )
    if mutations:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise PipelineFailure(
            "External private gate modified the candidate worktree and cannot certify it: "
            f"{mutations}. Inspect {artifact_dir}."
        )
    if private.required and not result.passed:
        cleanup_worktree(repo_root, worktree, delete_branch=False)
        raise PipelineFailure(
            "Required external private gate failed. Hidden implementation details are "
            "intentionally "
            f"not passed to the builder; inspect {artifact_dir}."
        )
    return payload, worktree


def _empty_paused_checkpoint_can_rebase(checkpoint: PipelineCheckpoint) -> bool:
    """Return whether a stale paused checkpoint contains no work to preserve.

    A controller repair may advance ``main`` while a planner is quota-paused.  Restarting
    is lossless only when the session produced no candidate commit, result, or active
    worktree.  Any real partial work keeps the fail-closed reconciliation requirement.
    """

    return (
        checkpoint.state == PipelineState.PAUSED
        and checkpoint.candidate_sha == checkpoint.starting_sha
        and not checkpoint.results
        and checkpoint.active_role is None
        and checkpoint.active_worktree is None
    )


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
            if _empty_paused_checkpoint_can_rebase(existing):
                store.archive(existing, suffix=f"stale-base-{utc_stamp()}")
                existing = None
            else:
                raise PipelineBlocked(
                    f"Cannot resume {task.task_id}: main moved from {existing.starting_sha} to "
                    f"{starting_sha}. Reconcile the previous candidate explicitly."
                )
        if existing is not None:
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
    task = apply_objective_stage_contracts(task)
    contract_errors = objective_pipeline_errors(task)
    if contract_errors:
        raise PipelineFailure(
            "Objective pipeline contract rejected: " + "; ".join(contract_errors)
        )
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
            stage = with_working_token_reserve(
                task.pipeline[checkpoint.stage_index],
                work_until_done=config.work_until_done,
                mutating_turn_floor=config.mutating_session_turn_floor,
                review_turn_floor=config.review_session_turn_floor,
            )
            task.pipeline[checkpoint.stage_index] = stage
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
            findings = findings_from_result(result)
            console.print(f"[red]Stage failed:[/red] {findings}")

            if result.verdict == Verdict.BLOCKED:
                raise PipelineBlocked(
                    terminal_failure_message(
                        f"Stage {stage.role.value} reached a truthful external blocker.",
                        result,
                    )
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
            if stage.role in review_roles:
                review_update = review_turn_retry_update(
                    stage,
                    result,
                    role_configs[stage.role],
                )
                if review_update is not None:
                    console.print(
                        f"[yellow]Review turn ceiling hit:[/yellow] retrying "
                        f"{stage.role.value} independently with "
                        f"{review_update['max_turns']} turns "
                        f"(was {stage.max_turns or role_configs[stage.role].max_turns})"
                    )
                    task.pipeline[checkpoint.stage_index] = stage.model_copy(update=review_update)
                    checkpoint.previous_findings = findings
                    checkpoint_store.save(checkpoint)
                    continue
                infra_update = review_infra_retry_update(
                    result,
                    checkpoint.stage_failures[key],
                )
                if infra_update is not None:
                    console.print(
                        f"[yellow]Review report lost to a structured-output fault:"
                        f"[/yellow] re-running {stage.role.value} independently "
                        f"(attempt {checkpoint.stage_failures[key]} of "
                        f"{MAX_REVIEW_INFRA_RETRIES})"
                    )
                    append_event(
                        config.resolve(repo_root, config.event_log_path),
                        event="review_infrastructure_retry",
                        component="pipeline",
                        task_id=task.task_id,
                        run_id=run_id,
                        role=stage.role.value,
                        detail=terminal_failure_signal(result)[:200],
                    )
                    if infra_update:
                        task.pipeline[checkpoint.stage_index] = stage.model_copy(
                            update=infra_update
                        )
                    # previous_findings is deliberately left as-is: the SDK never
                    # produced a report, so there is no reviewer finding to carry and
                    # injecting the transport error would fake review feedback.
                    checkpoint_store.save(checkpoint)
                    continue

            is_configured_mutator = (
                task.repair.enabled
                and task.repair.mutating_role is not None
                and stage.role == task.repair.mutating_role
            )
            renewable_mutator = config.work_until_done and _role_requires_changes(stage.role)
            if stage.role == RoleName.BUILDER or is_configured_mutator or renewable_mutator:
                failure_count = checkpoint.stage_failures[key]
                candidate_sha = preserve_mutating_candidate(checkpoint, candidate_sha, next_sha)
                if is_configured_mutator and stage.role != RoleName.BUILDER:
                    retry_models = task.repair.mutating_retry_models or task.repair.builder_models
                    retry_index = failure_count - 1
                else:
                    retry_models = task.repair.builder_models
                    retry_index = failure_count
                retry_models = retry_models or [stage.model or role_configs[stage.role].model]
                if config.work_until_done:
                    retry_index %= len(retry_models)
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
                    terminal_failure_message(
                        f"Mutating stage {stage.role.value} failed after "
                        f"{failure_count} bounded failures. "
                        "Re-specification is required.",
                        result,
                    )
                )

            if (
                stage.role in review_roles
                and task.repair.enabled
                and (
                    config.work_until_done
                    or checkpoint.repair_cycles < task.repair.max_cycles
                )
            ):
                mutating, scope_gaps = find_mutating_stage_for_findings(
                    repo_root=repo_root,
                    task=task,
                    findings=findings,
                )
                if scope_gaps:
                    controller_gaps = controller_owned_finding_paths(scope_gaps)
                    if controller_gaps:
                        detail = (
                            f"{FACTORY_REPAIR_SCOPE_MARKER}: Reviewer {stage.role.value} "
                            "identified protected controller-owned repair targets: "
                            f"{', '.join(controller_gaps)}. Preserve the product candidate and "
                            "route this failure to verified factory self-repair without consuming "
                            "another task specification revision. Repair controller "
                            "classification/routing; do not authorize the product task to edit "
                            "these protected paths."
                        )
                        append_event(
                            config.resolve(repo_root, config.event_log_path),
                            event="factory_repair_scope_gap",
                            component="pipeline",
                            task_id=task.task_id,
                            run_id=run_id,
                            role=stage.role.value,
                            detail=detail,
                        )
                        raise PipelineFailure(detail)
                    detail = (
                        f"Reviewer {stage.role.value} identified repair targets outside every "
                        f"writable stage: {', '.join(scope_gaps)}. Automatic task "
                        "re-specification is required before another repair attempt."
                    )
                    append_event(
                        config.resolve(repo_root, config.event_log_path),
                        event="repair_scope_gap",
                        component="pipeline",
                        task_id=task.task_id,
                        run_id=run_id,
                        role=stage.role.value,
                        detail=detail,
                    )
                    raise PipelineFailure(detail)
                repair_findings = list(findings)
                repaired = False
                # Stays None if no repair cycle ran, so the terminal message falls back
                # to the original failing stage's signal instead of raising NameError
                # and replacing a truthful PipelineFailure with a controller crash.
                repair_result: StageResult | None = None
                while (
                    config.work_until_done
                    or checkpoint.repair_cycles < task.repair.max_cycles
                ):
                    checkpoint.repair_cycles += 1
                    models = task.repair.builder_models or [
                        mutating.model or role_configs[mutating.role].model
                    ]
                    if config.work_until_done:
                        model = models[(checkpoint.repair_cycles - 1) % len(models)]
                    else:
                        model = models[min(checkpoint.repair_cycles - 1, len(models) - 1)]
                    base_effort = mutating.effort or role_configs[mutating.role].effort
                    repair_effort = "max" if checkpoint.repair_cycles > 1 else base_effort
                    repair_stage = mutating.model_copy(
                        update={
                            "model": model,
                            "effort": repair_effort,
                            "max_turns": max(
                                mutating.max_turns or 0,
                                config.mutating_session_turn_floor,
                            ),
                            "max_budget_usd": (
                                None if config.work_until_done else mutating.max_budget_usd
                            ),
                            "task_budget_tokens": (
                                None if config.work_until_done else mutating.task_budget_tokens
                            ),
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
                        f"{checkpoint.repair_cycles}/"
                        f"{'renewable' if config.work_until_done else task.repair.max_cycles}"
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
                    previous_candidate_sha = candidate_sha
                    candidate_sha = preserve_mutating_candidate(
                        checkpoint, candidate_sha, repair_sha
                    )
                    if candidate_sha != previous_candidate_sha:
                        append_event(
                            config.resolve(repo_root, config.event_log_path),
                            event="repair_progress_preserved",
                            component="pipeline",
                            task_id=task.task_id,
                            run_id=run_id,
                            role=repair_stage.role.value,
                            detail=(
                                f"repair cycle {checkpoint.repair_cycles}: "
                                f"{previous_candidate_sha[:12]} -> {candidate_sha[:12]}"
                            ),
                            data={
                                "cycle": checkpoint.repair_cycles,
                                "model": model,
                                "verdict": repair_result.verdict.value,
                            },
                        )
                    if repair_result.verdict == Verdict.PASS:
                        checkpoint.previous_findings = None
                        checkpoint.stage_index = _find_stage_index(
                            task, task.repair.restart_review_from
                        )
                        checkpoint_store.save(checkpoint)
                        repaired = True
                        break
                    if repair_result.verdict == Verdict.BLOCKED:
                        raise PipelineBlocked(
                            terminal_failure_message(
                                "Automatic repair reached a truthful external blocker.",
                                repair_result,
                            )
                        )
                    repair_findings.extend(findings_from_result(repair_result))
                    checkpoint.previous_findings = repair_findings
                    checkpoint_store.save(checkpoint)
                if not repaired:
                    raise PipelineFailure(
                        terminal_failure_message(
                            "Every bounded Sonnet/Opus repair cycle failed; "
                            "automatic re-specification is required.",
                            repair_result or result,
                        )
                    )
                continue

            raise PipelineFailure(
                terminal_failure_message(
                    f"Stage {stage.role.value} failed and no repair path remains.",
                    result,
                )
            )

        validate_release_candidate(
            repo_root=repo_root,
            config=config,
            task=task,
            starting_sha=checkpoint.starting_sha,
            candidate_sha=candidate_sha,
            run_id=run_id,
        )

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
            # The remote is deliberately single-branch.  Local deterministic and
            # private gates approve the release commit here; the autopilot's required
            # origin/main synchronization then pushes this exact SHA and waits for CI
            # before it starts another task.
            remote_ci_summary["status"] = "pending-main-push"
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
