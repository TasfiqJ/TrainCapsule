from __future__ import annotations

import json
import re
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
from .gates import PathPolicyError, gate_argv
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
    Stage,
    TaskPacket,
    ValueContract,
    ValueGateMode,
)
from .pipeline import run_pipeline
from .risk import apply_risk_profile, effective_risk, load_risk_profiles, planning_pipeline
from .stage_policy import (
    PRODUCT_PROTECTED_PATHS,
    REVIEW_ROLES,
    apply_objective_stage_contracts,
    objective_pipeline_errors,
)
from .util import path_matches


class TaskPacketPolicyError(RuntimeError):
    pass


def add_protected_path_baseline(packet: TaskPacket) -> TaskPacket:
    """Inject controller-owned protected paths into every writable product stage."""
    pipeline: list[Stage] = []
    baseline = sorted(PRODUCT_PROTECTED_PATHS)
    for stage in packet.pipeline:
        if stage.read_only is True:
            pipeline.append(stage)
            continue
        forbidden = list(dict.fromkeys([*stage.forbidden_paths, *baseline]))
        pipeline.append(stage.model_copy(update={"forbidden_paths": forbidden}))
    return packet.model_copy(update={"pipeline": pipeline})


def apply_controller_owned_catalog_minimums(
    packet: TaskPacket, catalog_seed: TaskPacket | None
) -> TaskPacket:
    """Keep controller-owned research requirements when Claude expands a catalog seed."""

    if catalog_seed is None:
        return packet
    seed_research = next(
        (stage for stage in catalog_seed.pipeline if stage.role == RoleName.RESEARCH), None
    )
    if seed_research is None:
        seed_gates = {gate.name: gate for gate in catalog_seed.gates}
        gates = [seed_gates.get(gate.name, gate) for gate in packet.gates]
        present = {gate.name for gate in gates}
        gates.extend(gate for name, gate in seed_gates.items() if name not in present)
        return packet.model_copy(
            update={
                "source_of_truth": list(
                    dict.fromkeys([*packet.source_of_truth, *catalog_seed.source_of_truth])
                ),
                "non_goals": list(
                    dict.fromkeys([*packet.non_goals, *catalog_seed.non_goals])
                ),
                "acceptance_criteria": list(
                    dict.fromkeys(
                        [*packet.acceptance_criteria, *catalog_seed.acceptance_criteria]
                    )
                ),
                "outputs": list(dict.fromkeys([*packet.outputs, *catalog_seed.outputs])),
                "stop_conditions": list(
                    dict.fromkeys([*packet.stop_conditions, *catalog_seed.stop_conditions])
                ),
                "gates": gates,
                "value_contract": catalog_seed.value_contract,
                "context_keys": list(
                    dict.fromkeys([*packet.context_keys, *catalog_seed.context_keys])
                ),
            }
        )

    seed_gates = {gate.name: gate for gate in catalog_seed.gates}
    gates = [seed_gates.get(gate.name, gate) for gate in packet.gates]
    present_gate_names = {gate.name for gate in gates}
    gates.extend(
        gate for name, gate in seed_gates.items() if name not in present_gate_names
    )
    gate_names = [gate.name for gate in gates]

    proposed_research = next(
        (stage for stage in reversed(packet.pipeline) if stage.role == RoleName.RESEARCH),
        seed_research,
    )
    research = proposed_research.model_copy(
        update={
            "allowed_paths": list(
                dict.fromkeys([*proposed_research.allowed_paths, *seed_research.allowed_paths])
            ),
            "forbidden_paths": list(
                dict.fromkeys(
                    [*proposed_research.forbidden_paths, *seed_research.forbidden_paths]
                )
            ),
            "allowed_domains": list(
                dict.fromkeys(
                    [*proposed_research.allowed_domains, *seed_research.allowed_domains]
                )
            ),
            "acceptance_criteria": list(
                dict.fromkeys(
                    [
                        *proposed_research.acceptance_criteria,
                        *seed_research.acceptance_criteria,
                    ]
                )
            ),
            "context_keys": list(
                dict.fromkeys([*proposed_research.context_keys, *seed_research.context_keys])
            ),
            "machine_gates": gate_names,
            "read_only": False,
            "require_changes": True,
        }
    )
    pipeline = [
        stage
        for stage in packet.pipeline
        if stage.role not in {RoleName.RESEARCH, RoleName.BUILDER}
    ]
    insert_at = next(
        (index for index, stage in enumerate(pipeline) if stage.role in REVIEW_ROLES),
        len(pipeline),
    )
    pipeline.insert(insert_at, research)
    security = packet.security.model_copy(
        update={"network_default": catalog_seed.security.network_default}
    )
    return packet.model_copy(
        update={
            "source_of_truth": list(
                dict.fromkeys([*packet.source_of_truth, *catalog_seed.source_of_truth])
            ),
            "non_goals": list(dict.fromkeys([*packet.non_goals, *catalog_seed.non_goals])),
            "acceptance_criteria": list(
                dict.fromkeys(
                    [*packet.acceptance_criteria, *catalog_seed.acceptance_criteria]
                )
            ),
            "outputs": list(dict.fromkeys([*packet.outputs, *catalog_seed.outputs])),
            "stop_conditions": list(
                dict.fromkeys([*packet.stop_conditions, *catalog_seed.stop_conditions])
            ),
            "security": security,
            "gates": gates,
            "pipeline": pipeline,
            "value_contract": catalog_seed.value_contract,
            "context_keys": list(
                dict.fromkeys([*packet.context_keys, *catalog_seed.context_keys])
            ),
        }
    )


def planning_task_for(
    item: FeatureItem,
    *,
    profiles: dict[str, object],
    revision: int = 0,
    catalog_seed: TaskPacket | None = None,
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
    seed_input = (
        "Controller-owned catalog seed (starting evidence, not an approved contract): "
        + catalog_seed.model_dump_json()
        if catalog_seed is not None
        else "No controller-owned catalog seed exists; derive the contract from authority."
    )
    packet = TaskPacket(
        task_id=planning_id,
        title=f"Compile executable outcome contract {item.task_id}",
        phase="Autonomous macro planning",
        goal=(
            f"Compile roadmap item {item.task_id} into one complete executable outcome contract. "
            f"Outcome: {item.outcome}"
        ),
        source_of_truth=[
            "docs/CONTEXT_INDEX.yaml",
            "docs/source-of-truth/final-2026-08-09/00_EXECUTIVE_BUILD_DECISION.md",
            "docs/source-of-truth/final-2026-08-09/03_PRODUCT_STRATEGY_AND_REQUIREMENTS.md",
            "docs/source-of-truth/final-2026-08-09/04_TECHNICAL_ARCHITECTURE.md",
            "docs/source-of-truth/final-2026-08-09/05_TRUST_REPLAY_REDUCTION_AND_CAPSULE_SPEC.md",
            "docs/source-of-truth/final-2026-08-09/12_ROADMAP_BACKLOG_AND_MASTER_BUILD_PROMPT.md",
            "docs/source-of-truth/final-2026-08-09/13_SOURCE_REGISTER.md",
            "docs/source-of-truth/final-2026-08-09/14_CLAUDE_CODE_MASTER_BUILD_PROMPT.md",
            "factory/feature_ledger.yaml",
            "factory/task_catalog.yaml",
            "factory/product_definition_of_done.yaml",
            "config/value_policy.yaml",
        ],
        depends_on=[],
        inputs=[
            f"Roadmap ID: {item.task_id}",
            f"Required dependencies: {', '.join(item.depends_on) or 'none'}",
            f"Lead role: {item.lead_role}",
            f"Phase: {item.phase}",
            seed_input,
        ],
        non_goals=[
            "Implementing product code",
            "Changing the master plan or deleting roadmap requirements",
            "Prescribing implementation files or architecture when the outcome contract "
            "does not require it",
        ],
        acceptance_criteria=[
            f"The generated packet task_id is exactly {item.task_id}.",
            f"The generated packet depends_on is exactly {item.depends_on!r}.",
            "The packet has one coherent user-visible outcome and every required falsifiable "
            "criterion; criterion count follows completeness, not an arbitrary ceiling.",
            "Every criterion has a stable ID and maps authority -> behavior/truth state -> "
            "output -> writable owner -> gate/oracle -> evidence class.",
            "The specification includes an applicability matrix for correctness/truth, "
            "failure/recovery, security/privacy, performance, accessibility, operations/support, "
            "adoption friction, and commercial truth.",
            "The Claude owner can change every affected product surface while controller, "
            "source, credential, private-gate, and release authority stays forbidden.",
            "Every claimed output has a deterministic machine gate where feasible.",
            "The packet gives one Claude owner broad product authority and uses one independent "
            "verifier when the risk is non-mechanical.",
            "Stop conditions preserve UNKNOWN instead of inventing missing semantic authority.",
        ],
        outputs=[proposal, spec],
        stop_conditions=[
            "The roadmap or source documents do not contain enough authority to specify the task.",
            "A genuine source contradiction or unavailable external/normative fact prevents "
            "a truthful executable contract.",
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
                ],
                required=True,
            )
        ],
        private_gate=PrivateGate(required=False),
        value_contract=ValueContract(required=False, mode=ValueGateMode.NOT_REQUIRED),
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
            restart_review_from=RoleName.PLANNER,
            mutating_role=RoleName.PLANNER,
        ),
        task_budget_usd=planning_budget,
        auto_merge=False,
        base_branch="main",
    )
    return apply_objective_stage_contracts(packet)


def validate_product_task_packet(
    packet: TaskPacket,
    item: FeatureItem,
    *,
    repo_root: Path | None = None,
    catalog_seed: TaskPacket | None = None,
) -> None:
    errors: list[str] = []
    gate_root = (repo_root or Path.cwd()).resolve()
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
    if len(packet.acceptance_criteria) > 12:
        errors.append("acceptance_criteria exceeds the V3 limit of 12")
    if len(packet.outputs) > 8:
        errors.append("outputs exceeds the V3 limit of 8")
    if len(packet.source_of_truth) > 8:
        errors.append("source_of_truth exceeds the default V3 limit of 8")
    if not packet.decision_contribution.strip():
        errors.append("decision_contribution is required")
    if not packet.non_goals:
        errors.append("at least one explicit non-goal is required")
    if not packet.oracle.strip():
        errors.append("oracle is required")
    if not packet.rollback.strip():
        errors.append("rollback is required")
    if not packet.stop_conditions:
        errors.append("stop_conditions are required")
    universal = re.compile(
        r"\b(?:all|every)\s+(?:company|product|roadmap|customer|commercial)\s+"
        r"(?:criterion|criteria|requirement|task|work|need)s?\b",
        re.IGNORECASE,
    )
    generic_claim = re.compile(
        r"\b(?:production[- ]ready|enterprise[- ]ready|commercially (?:proven|validated))\b",
        re.IGNORECASE,
    )
    if any(universal.search(value) for value in packet.acceptance_criteria):
        errors.append("universal company/product criteria are forbidden")
    if any(generic_claim.search(value) for value in packet.acceptance_criteria):
        errors.append("generic production/commercial wording is forbidden")
    if item.completion_kind in {"external_validation", "commercial_validation"}:
        errors.append("AI cannot create external or commercial evidence")
    if packet.security.allow_unsandboxed_commands:
        errors.append("allow_unsandboxed_commands must remain false")
    if not packet.security.fail_if_sandbox_unavailable:
        errors.append("fail_if_sandbox_unavailable must remain true")
    roles = {stage.role for stage in packet.pipeline}
    if packet.risk_tier != RiskTier.MECHANICAL and RoleName.ADVERSARY not in roles:
        errors.append("non-mechanical pipeline must contain one independent verifier")
    owners = [
        stage
        for stage in packet.pipeline
        if stage.role
        in {RoleName.BUILDER, RoleName.RESEARCH, RoleName.SPECIFICATION, RoleName.PLANNER}
        and stage.read_only is not True
    ]
    if len(owners) != 1:
        errors.append("pipeline must contain exactly one bounded writable owner")
    writable_patterns = [path for owner in owners for path in owner.allowed_paths]
    unwritable_outputs = [
        output for output in packet.outputs if not path_matches(output, writable_patterns)
    ]
    if unwritable_outputs:
        errors.append(
            "outputs are not writable by the owner stage: "
            + ", ".join(sorted(unwritable_outputs))
        )
    scope_paths = [*packet.outputs, *writable_patterns]
    has_product = any(
        path.startswith(("packages/traincapsule-", "src/traincapsule", "tests/product/"))
        for path in scope_paths
    )
    has_factory = any(
        path.startswith(("tcfactory/", "factory/", "config/", "prompts/", "scripts/"))
        for path in scope_paths
    )
    if has_product and has_factory:
        errors.append("packet mixes product and factory mutations")
    legacy_roles = roles.intersection(
        {
            RoleName.AUDIT,
            RoleName.SECURITY,
            RoleName.PERFORMANCE,
            RoleName.RELEASE,
            RoleName.VALUE_VALIDATOR,
            RoleName.VALUE_ADVERSARY,
        }
    )
    if legacy_roles:
        errors.append(
            "pipeline contains legacy serial review stages: "
            + ", ".join(sorted(role.value for role in legacy_roles))
        )
    seed_research = (
        next(
            (
                stage
                for stage in catalog_seed.pipeline
                if stage.role == RoleName.RESEARCH
            ),
            None,
        )
        if catalog_seed is not None
        else None
    )
    if seed_research is not None:
        assert catalog_seed is not None
        if RoleName.RESEARCH not in roles:
            errors.append("catalog research task must retain a research stage")
        required_gate_names = {gate.name for gate in catalog_seed.gates}
        missing_gates = sorted(required_gate_names - {gate.name for gate in packet.gates})
        if missing_gates:
            errors.append(
                "catalog research task omitted controller-owned gates: "
                + ", ".join(missing_gates)
            )
        missing_outputs = sorted(set(catalog_seed.outputs) - set(packet.outputs))
        if missing_outputs:
            errors.append(
                "catalog research task omitted controller-owned outputs: "
                + ", ".join(missing_outputs)
            )
        if packet.security.network_default != catalog_seed.security.network_default:
            errors.append("catalog research task changed controller-owned network policy")
    errors.extend(objective_pipeline_errors(packet))
    commands: dict[str, str] = {}
    for gate in packet.gates:
        if gate.command in commands:
            errors.append(
                f"gate {gate.name!r} duplicates command from {commands[gate.command]!r}; "
                "independent gate names require distinct executable checks"
            )
        else:
            commands[gate.command] = gate.name
        try:
            gate_argv(gate.command, cwd=gate_root)
        except PathPolicyError as exc:
            errors.append(f"gate {gate.name!r} is not controller-safe: {exc}")
    for stage in packet.pipeline:
        if stage.permission_mode == "bypassPermissions":
            errors.append(f"stage {stage.role.value} may not use bypassPermissions")
        if stage.read_only is not True:
            missing_forbidden = sorted(
                PRODUCT_PROTECTED_PATHS - set(stage.forbidden_paths)
            )
            if missing_forbidden:
                errors.append(
                    f"writable stage {stage.role.value} does not forbid protected paths: "
                    f"{missing_forbidden}"
                )
        for allowed in stage.allowed_paths:
            if allowed in PRODUCT_PROTECTED_PATHS or allowed.startswith("factory/state"):
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
    """Compile a catalog seed and authority into an independently reviewed task packet."""

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
    catalog = load_task_catalog(catalog_path) if catalog_path.exists() else None
    catalog_seed: TaskPacket | None = None
    if catalog is not None and has_catalog_entry(catalog, item.task_id):
        catalog_seed = task_packet_from_catalog(
            repo_root=repo_root,
            item=item,
            catalog=catalog,
            risk_profiles=profiles,
        )
    planning_task = planning_task_for(
        item,
        profiles=profiles,
        revision=item.revisions,
        catalog_seed=catalog_seed,
    )
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
    packet = apply_controller_owned_catalog_minimums(load_task(proposal), catalog_seed)
    packet = apply_risk_profile(packet, item, profiles)
    packet = apply_objective_stage_contracts(packet)
    packet = add_protected_path_baseline(packet)
    validate_product_task_packet(
        packet,
        item,
        repo_root=repo_root,
        catalog_seed=catalog_seed,
    )
    packet = packet.model_copy(update={"auto_merge": autonomy_config.auto_merge})
    write_task_packet(destination, packet)
    planning_mode = "model-respec" if item.revisions else "catalog-seeded-model"

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
