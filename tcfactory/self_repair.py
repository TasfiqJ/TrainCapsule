from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .auth import assert_max_oauth_only
from .catalog import write_task_packet
from .config import load_roles
from .models import (
    AutonomyConfig,
    CommitType,
    FactoryConfig,
    Gate,
    PrivateGate,
    RepairPolicy,
    RoleName,
    SecurityPolicy,
    Stage,
    TaskPacket,
)
from .pipeline import run_pipeline
from .quota import AuthenticationPause, QuotaLimitPause
from .util import write_json


@dataclass(frozen=True)
class SelfRepairOutcome:
    applied: bool
    task_id: str
    artifact_path: str
    detail: str


def _safe_reason(reason: str) -> str:
    compact = " ".join(reason.split())[:4000]
    compact = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[redacted]", compact)
    return re.sub(r"(?i)(oauth[_ -]?token[=: ]+)[^ ]+", r"\1[redacted]", compact)


def build_self_repair_task(*, reason: str, attempt: int, task_id: str) -> TaskPacket:
    model = "opus" if attempt >= 2 else "sonnet"
    allowed_paths = [
        "tcfactory/**",
        "tests/**",
        "scripts/worker_loop.sh",
        "scripts/windows_task_entrypoint.sh",
        "scripts/recover_factory.sh",
        "scripts/systemd_entrypoint.sh",
        "scripts/factory_control.sh",
        "scripts/verify_autonomous_loop.sh",
        "Control-TrainCapsuleBuilder.ps1",
    ]
    forbidden_paths = [
        "tcfactory/auth.py",
        "config/**",
        ".claude/**",
        ".factory/source-locks/**",
        "bootstrap/private-gates/**",
        "docs/source-of-truth/**",
        "factory/product_definition_of_done.yaml",
        "factory/feature_ledger.yaml",
        "scripts/gates/**",
        "scripts/configure*token.sh",
        "scripts/load_factory_env.sh",
    ]
    gates = [
        Gate(name="no-paid-usage", command="bash scripts/gates/no_paid_usage.sh"),
        Gate(name="secret-scan", command="bash scripts/gates/secret_scan.sh"),
        Gate(
            name="fast-quality",
            command="bash scripts/gates/fast_quality.sh",
            timeout_seconds=1800,
        ),
        Gate(name="protected-controls", command="bash scripts/gates/no_protected_changes.sh"),
    ]
    common_criteria = [
        "Reproduce or deterministically explain the supplied factory/controller failure.",
        "Fix the smallest causal controller, recovery, or loop defect and add a regression test.",
        "Preserve every product truth, value, security, private, and release gate.",
        "Never add an API key, paid provider, usage-credit path, auto-purchase, or "
        "billing fallback.",
        "Do not change product source-of-truth documents or invent evidence.",
        "A broader loop improvement is allowed only when evidence shows it improves "
        "autonomous reliability, product quality, or time-to-verified-value without "
        "weakening a gate.",
        "Return blocked rather than changing protected controls when no safe verified "
        "repair exists.",
    ]
    return TaskPacket(
        task_id=task_id,
        title="Repair or improve the autonomous TrainCapsule factory",
        phase="factory-self-repair",
        goal=(
            "Independently diagnose and repair the autonomous factory so verified product work "
            f"can continue. Failure evidence: {_safe_reason(reason)}"
        ),
        source_of_truth=[
            "tcfactory/autopilot.py",
            "tcfactory/pipeline.py",
            "scripts/windows_task_entrypoint.sh",
            "config/factory.yaml",
            "config/autonomy.yaml",
        ],
        inputs=["Durable factory state, failure artifacts, event logs, and current tests"],
        non_goals=[
            "Changing TrainCapsule product requirements to make a failing result pass.",
            "Enabling paid Claude usage or bypassing subscription limits.",
        ],
        acceptance_criteria=common_criteria,
        outputs=["A verified minimal factory repair with regression evidence"],
        stop_conditions=[
            "The only available path requires paid usage, credentials, user impersonation, "
            "or weakened gates.",
            "The failure is a truthful product/evidence rejection rather than a controller defect.",
        ],
        security=SecurityPolicy(
            network_default="deny",
            allow_unsandboxed_commands=False,
            fail_if_sandbox_unavailable=True,
        ),
        gates=gates,
        private_gate=PrivateGate(required=False),
        pipeline=[
            Stage(
                role=RoleName.RECOVERY,
                model=model,
                effort="high",
                max_turns=20,
                task_budget_tokens=100_000,
                tools=["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
                disallowed_tools=["WebFetch", "WebSearch", "Agent"],
                permission_mode="acceptEdits",
                allowed_paths=allowed_paths,
                forbidden_paths=forbidden_paths,
                acceptance_criteria=common_criteria,
                machine_gates=[gate.name for gate in gates],
                read_only=False,
                require_changes=True,
            ),
            Stage(
                role=RoleName.ADVERSARY,
                model=model,
                effort="high",
                max_turns=8,
                task_budget_tokens=40_000,
                tools=["Read", "Grep", "Glob", "Bash"],
                disallowed_tools=["Write", "Edit", "WebFetch", "WebSearch", "Agent"],
                permission_mode="dontAsk",
                allowed_paths=allowed_paths,
                forbidden_paths=forbidden_paths,
                acceptance_criteria=common_criteria,
                read_only=True,
                require_changes=False,
            ),
            Stage(
                role=RoleName.AUDIT,
                model="sonnet",
                effort="high",
                max_turns=7,
                task_budget_tokens=32_000,
                tools=["Read", "Grep", "Glob", "Bash"],
                disallowed_tools=["Write", "Edit", "WebFetch", "WebSearch", "Agent"],
                permission_mode="dontAsk",
                allowed_paths=allowed_paths,
                forbidden_paths=forbidden_paths,
                acceptance_criteria=common_criteria,
                read_only=True,
                require_changes=False,
            ),
            Stage(
                role=RoleName.RELEASE,
                model="sonnet",
                effort="medium",
                max_turns=6,
                task_budget_tokens=24_000,
                tools=["Read", "Grep", "Glob", "Bash"],
                disallowed_tools=["Write", "Edit", "WebFetch", "WebSearch", "Agent"],
                permission_mode="dontAsk",
                allowed_paths=allowed_paths,
                forbidden_paths=forbidden_paths,
                acceptance_criteria=common_criteria,
                machine_gates=[gate.name for gate in gates],
                read_only=True,
                require_changes=False,
            ),
        ],
        allow_test_changes=True,
        remote_ci_required=False,
        github_push=False,
        commit_type=CommitType.FIX,
        commit_subject="repair autonomous factory",
        repair=RepairPolicy(
            enabled=True,
            max_cycles=2,
            builder_models=["sonnet", "opus"],
            restart_review_from=RoleName.ADVERSARY,
            mutating_role=RoleName.RECOVERY,
        ),
        task_budget_usd=20.0,
        auto_merge=True,
    )


async def attempt_factory_self_repair(
    *,
    repo_root: Path,
    factory: FactoryConfig,
    autonomy: AutonomyConfig,
    reason: str,
    attempt: int,
) -> SelfRepairOutcome:
    if not autonomy.auto_repair_factory:
        return SelfRepairOutcome(False, "disabled", "", "automatic factory repair is disabled")
    if factory.allow_paid_usage or autonomy.allow_paid_usage:
        return SelfRepairOutcome(False, "refused", "", "paid usage invariant is not false")
    assert_max_oauth_only(
        require_long_lived_token=factory.require_long_lived_oauth_for_autopilot
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    task_id = f"FACTORY_REPAIR_{stamp}_{attempt}"
    packet = build_self_repair_task(reason=reason, attempt=attempt, task_id=task_id)
    # Runtime repair packets must not dirty main before the clean-main pipeline gate.
    # factory/state is durable across restarts and intentionally ignored by Git.
    packet_path = repo_root / "factory" / "state" / "self-repair" / f"{task_id}.yaml"
    write_task_packet(packet_path, packet)
    outcome_path = packet_path.with_suffix(".result.json")
    try:
        summary = await run_pipeline(
            repo_root=repo_root,
            config=factory,
            task=packet,
            role_configs=load_roles(factory.resolve(repo_root, factory.roles_path)),
            merge_override=True,
            resume=False,
        )
    except (QuotaLimitPause, AuthenticationPause):
        raise
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}: {exc}"
        write_json(
            outcome_path,
            {"applied": False, "task_id": task_id, "detail": detail, "attempt": attempt},
        )
        return SelfRepairOutcome(False, task_id, str(outcome_path), detail)
    applied = bool(summary.get("merged"))
    detail = (
        "verified repair merged; controller restart required" if applied else "no repair change"
    )
    write_json(
        outcome_path,
        {
            "applied": applied,
            "task_id": task_id,
            "detail": detail,
            "attempt": attempt,
            "summary": summary,
        },
    )
    return SelfRepairOutcome(applied, task_id, str(outcome_path), detail)


def write_hard_stuck(
    *,
    repo_root: Path,
    autonomy: AutonomyConfig,
    reason: str,
    required_action: str,
    attempts: int,
    artifact_path: str | None,
) -> Path:
    path = repo_root / autonomy.hard_stuck_path
    write_json(
        path,
        {
            "status": "hard_stuck",
            "at": datetime.now(UTC).isoformat(),
            "reason": _safe_reason(reason),
            "required_action": required_action,
            "self_repair_attempts": attempts,
            "last_repair_artifact": artifact_path,
            "paid_usage_allowed": False,
        },
    )
    return path


def clear_hard_stuck(repo_root: Path, autonomy: AutonomyConfig) -> None:
    (repo_root / autonomy.hard_stuck_path).unlink(missing_ok=True)
