from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

from .catalog import (
    has_catalog_entry,
    load_task_catalog,
    task_packet_from_catalog,
    write_task_packet,
)
from .commit_messages import controller_commit_message
from .config import load_roles, load_task
from .feature_ledger import FeatureItem, FeatureLedger, save_feature_ledger
from .gitops import commit_all, is_clean
from .models import (
    AutonomyConfig,
    CommitType,
    FactoryConfig,
    Gate,
    PrivateGate,
    RepairPolicy,
    RiskTier,
    RoleName,
    SecurityPolicy,
    TaskPacket,
)
from .pipeline import run_pipeline
from .risk import apply_risk_profile, effective_risk, load_risk_profiles, planning_pipeline


class TaskPacketPolicyError(RuntimeError):
    pass


_PROTECTED_FACTORY_PATHS = {
    ".claude/**",
    "config/**",
    "prompts/**",
    "tcfactory/**",
    "schemas/**",
    "factory/state/**",
    "factory/queue/**",
    "factory/feature_ledger.yaml",
    "factory/product_definition_of_done.yaml",
    "factory/task_catalog.yaml",
    "docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md",
    "docs/MASTER_PLAN_INDEX.md",
    "docs/CONTEXT_INDEX.yaml",
    "config/risk_profiles.yaml",
    "config/context.yaml",
    "config/github.yaml",
    "scripts/gates/**",
    "Control-TrainCapsuleBuilder.ps1",
    "Install-TrainCapsuleAutonomousBuilder.ps1",
    "bootstrap/private-gates/**",
}


def planning_task_for(
    item: FeatureItem, *, profiles: dict[str, object], revision: int = 0
) -> TaskPacket:
    suffix = f"_R{revision}" if revision else ""
    planning_id = f"PLAN_{item.task_id}{suffix}"
    proposal = f"factory/proposals/{item.task_id}.yaml"
    spec = f"specs/tasks/{item.task_id}.md"
    planning_stages, planning_budget, planning_repairs = planning_pipeline(item, profiles)
    dependencies_json = json.dumps(item.depends_on, separators=(",", ":"))
    gate_command = (
        "uv run python scripts/gates/validate_proposal.py "
        f"{proposal} {item.task_id} {shlex.quote(dependencies_json)}"
    )
    return TaskPacket(
        task_id=planning_id,
        title=f"Create and independently approve task packet {item.task_id}",
        phase="Autonomous macro planning",
        goal=(
            f"Convert roadmap item {item.task_id} into one bounded executable task packet. "
            f"Outcome: {item.outcome}"
        ),
        source_of_truth=[
            "docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md",
            "docs/MASTER_PLAN_INDEX.md",
            "docs/PLANNER_LOOP.md",
            "factory/feature_ledger.yaml",
        ],
        depends_on=[],
        inputs=[
            f"Roadmap ID: {item.task_id}",
            f"Required dependencies: {', '.join(item.depends_on) or 'none'}",
            f"Lead role: {item.lead_role}",
            f"Phase: {item.phase}",
        ],
        non_goals=[
            "Implementing product code",
            "Changing the master plan or deleting roadmap requirements",
            "Approving the packet without independent review",
        ],
        acceptance_criteria=[
            f"The generated packet task_id is exactly {item.task_id}.",
            f"The generated packet depends_on is exactly {item.depends_on!r}.",
            "The packet has one machine-verifiable outcome and approximately 8-15 criteria.",
            "Allowed paths are narrow and factory authority paths are forbidden.",
            "Every claimed output has a deterministic machine gate where feasible.",
            "The packet uses fresh specification, implementation, adversarial, audit, and "
            "release authority as appropriate.",
            "Stop conditions preserve UNKNOWN instead of inventing missing semantic authority.",
        ],
        outputs=[proposal, spec],
        stop_conditions=[
            "The roadmap or source documents do not contain enough authority to specify the task.",
            "The outcome cannot be reduced to a bounded task without changing product scope.",
        ],
        security=SecurityPolicy(
            network_default="deny",
            allow_unsandboxed_commands=False,
            fail_if_sandbox_unavailable=True,
            secrets=[],
        ),
        gates=[
            Gate(
                name="proposal-policy",
                command=gate_command,
                timeout_seconds=120,
                stages=[
                    RoleName.PLANNER,
                    RoleName.ADVERSARY,
                    RoleName.AUDIT,
                    RoleName.RELEASE,
                ],
                required=True,
            )
        ],
        private_gate=PrivateGate(required=False),
        pipeline=[
            stage.model_copy(update={"machine_gates": ["proposal-policy"]})
            for stage in planning_stages
        ],
        risk_tier=effective_risk(item),
        context_keys=item.context_keys,
        commit_type=CommitType.SPEC,
        commit_subject=f"plan {item.task_id.lower()}",
        remote_ci_required=False,
        github_push=False,
        repair=RepairPolicy(
            enabled=True,
            max_cycles=planning_repairs,
            builder_models=["sonnet", "opus"],
            restart_review_from=(
                RoleName.ADVERSARY
                if any(stage.role == RoleName.ADVERSARY for stage in planning_stages)
                else RoleName.RELEASE
            ),
            mutating_role=RoleName.PLANNER,
        ),
        task_budget_usd=planning_budget,
        auto_merge=True,
        base_branch="main",
    )


def validate_product_task_packet(packet: TaskPacket, item: FeatureItem) -> None:
    errors: list[str] = []
    if packet.risk_tier != effective_risk(item):
        errors.append(
            f"risk_tier must be controller-owned {effective_risk(item).value}, "
            f"found {packet.risk_tier.value}"
        )
    if packet.task_id != item.task_id:
        errors.append(f"task_id must be {item.task_id}, found {packet.task_id}")
    if packet.depends_on != item.depends_on:
        errors.append(
            f"depends_on must be exactly {item.depends_on!r}, found {packet.depends_on!r}"
        )
    if len(packet.acceptance_criteria) > 25:
        errors.append("acceptance_criteria exceeds the hard ceiling of 25")
    if packet.security.allow_unsandboxed_commands:
        errors.append("allow_unsandboxed_commands must remain false")
    if not packet.security.fail_if_sandbox_unavailable:
        errors.append("fail_if_sandbox_unavailable must remain true")
    roles = {stage.role for stage in packet.pipeline}
    if RoleName.RELEASE not in roles:
        errors.append("pipeline must contain a release stage")
    if packet.risk_tier != RiskTier.MECHANICAL and RoleName.ADVERSARY not in roles:
        errors.append("non-mechanical pipeline must contain an adversary stage")
    if (
        packet.risk_tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}
        and RoleName.AUDIT not in roles
    ):
        errors.append("integration/trust pipeline must contain an audit stage")
    if not roles.intersection(
        {RoleName.BUILDER, RoleName.RESEARCH, RoleName.SPECIFICATION, RoleName.PLANNER}
    ):
        errors.append(
            "pipeline must contain at least one mutating implementation/specification role"
        )
    for stage in packet.pipeline:
        if stage.permission_mode == "bypassPermissions":
            errors.append(f"stage {stage.role.value} may not use bypassPermissions")
        if stage.read_only is not True:
            missing_forbidden = sorted(_PROTECTED_FACTORY_PATHS - set(stage.forbidden_paths))
            if missing_forbidden:
                errors.append(
                    f"writable stage {stage.role.value} does not forbid protected paths: "
                    f"{missing_forbidden}"
                )
        for allowed in stage.allowed_paths:
            if allowed in _PROTECTED_FACTORY_PATHS or allowed.startswith("factory/state"):
                errors.append(
                    f"stage {stage.role.value} attempts to write protected path {allowed}"
                )
    if errors:
        raise TaskPacketPolicyError("Generated task packet rejected: " + "; ".join(errors))


async def create_and_promote_task_packet(
    *,
    repo_root: Path,
    factory_config: FactoryConfig,
    autonomy_config: AutonomyConfig,
    ledger: FeatureLedger,
    item: FeatureItem,
) -> Path:
    """Create one task packet without wasting a model session when the roadmap is explicit.

    First attempts use the immutable controller-owned task catalog. A fresh planning model is
    invoked only when the catalog lacks an entry or when a failed task is being re-specified
    from concrete evidence. This keeps ordinary planning deterministic and token-frugal.
    """

    if not is_clean(repo_root):
        raise TaskPacketPolicyError("Repository must be clean before autonomous planning")
    profiles = load_risk_profiles(
        factory_config.resolve(repo_root, factory_config.risk_profiles_path)
    )
    destination = (
        factory_config.resolve(repo_root, factory_config.task_dir) / f"{item.task_id}.yaml"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    catalog_path = factory_config.resolve(repo_root, factory_config.task_catalog_path)
    catalog = (
        load_task_catalog(catalog_path) if item.revisions == 0 and catalog_path.exists() else None
    )
    if catalog is not None and has_catalog_entry(catalog, item.task_id):
        packet = task_packet_from_catalog(
            repo_root=repo_root,
            item=item,
            catalog=catalog,
            risk_profiles=profiles,
        )
        packet = packet.model_copy(update={"auto_merge": autonomy_config.auto_merge})
        validate_product_task_packet(packet, item)
        write_task_packet(destination, packet)
        planning_mode = "catalog"
    else:
        planning_task = planning_task_for(item, profiles=profiles, revision=item.revisions)
        roles = load_roles(factory_config.resolve(repo_root, factory_config.roles_path))
        await run_pipeline(
            repo_root=repo_root,
            config=factory_config,
            task=planning_task,
            role_configs=roles,
            merge_override=True,
            resume=True,
        )
        proposal = repo_root / "factory" / "proposals" / f"{item.task_id}.yaml"
        packet = load_task(proposal)
        packet = apply_risk_profile(packet, item, profiles)
        validate_product_task_packet(packet, item)
        packet = packet.model_copy(update={"auto_merge": autonomy_config.auto_merge})
        write_task_packet(destination, packet)
        planning_mode = "model-respec" if item.revisions else "model-fallback"

    item.packet_path = str(destination.relative_to(repo_root))
    item.status = "packet_approved"
    item.notes.append(f"Task packet approved through {planning_mode} planning.")
    save_feature_ledger(
        factory_config.resolve(repo_root, factory_config.feature_ledger_path), ledger
    )
    commit = commit_all(repo_root, controller_commit_message("approve", item.task_id.lower()))
    if not commit:
        raise TaskPacketPolicyError("Controller produced no task-packet promotion commit")
    return destination


def archive_failed_packet(repo_root: Path, task_path: Path, *, revision: int) -> Path:
    archive = repo_root / "factory" / "recovery" / "task-packets"
    archive.mkdir(parents=True, exist_ok=True)
    destination = archive / f"{task_path.stem}-r{revision}{task_path.suffix}"
    shutil.copy2(task_path, destination)
    return destination
