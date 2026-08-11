from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from .feature_ledger import FeatureItem
from .models import (
    PrivateGate,
    RepairPolicy,
    RiskTier,
    RoleName,
    Stage,
    TaskPacket,
    ValueGateMode,
)
from .yamlutil import load_yaml

CONTEXT_CHARS_PER_TOKEN = 4
MIN_STAGE_WORK_TOKENS = 24_000

_RANK = {
    RiskTier.MECHANICAL: 0,
    RiskTier.STANDARD: 1,
    RiskTier.INTEGRATION: 2,
    RiskTier.TRUST_CORE: 3,
}

_SECURITY_WORDS = {
    "security",
    "sandbox",
    "credential",
    "secret",
    "auth",
    "oauth",
    "containment",
    "sanitization",
    "air-gapped",
    "private",
    "supply-chain",
    "signature",
}
_PERFORMANCE_WORDS = {"performance", "benchmark", "latency", "throughput", "load test"}
_INTEGRATION_WORDS = {
    "adapter",
    "integration",
    "container",
    "github",
    "bisection",
    "materializer",
    "dynamo",
    "brev",
    "opentelemetry",
}
_TRUST_WORDS = {
    "independent oracle",
    "profile contract",
    "canonical fixture",
    "status classification",
    "legal transform",
    "semantic invariant",
    "mutation pack",
    "failure minimizer",
    "failure capsule",
    "release policy decision",
    "oracle independence",
}


class RiskProfileError(RuntimeError):
    pass


def load_risk_profiles(path: Path) -> dict[str, Any]:
    raw = load_yaml(path)
    if not isinstance(raw, dict):
        raise RiskProfileError(f"Invalid risk profile file: {path}")
    typed_raw = cast(dict[str, Any], raw)
    if not isinstance(typed_raw.get("profiles"), dict):
        raise RiskProfileError(f"Invalid risk profile file: {path}")
    return typed_raw


def max_risk(*tiers: RiskTier) -> RiskTier:
    return max(tiers, key=lambda value: _RANK[value])


def infer_minimum_risk(item: FeatureItem) -> RiskTier:
    text = f"{item.outcome} {item.lead_role} {item.phase}".lower()
    if item.trust_core or any(word in text for word in _TRUST_WORDS):
        return RiskTier.TRUST_CORE
    if any(word in text for word in _SECURITY_WORDS | _INTEGRATION_WORDS):
        return RiskTier.INTEGRATION
    if any(word in text for word in {"format", "rename", "metadata", "generated docs"}):
        return RiskTier.MECHANICAL
    return RiskTier.STANDARD


def effective_risk(item: FeatureItem) -> RiskTier:
    return max_risk(item.risk_tier, infer_minimum_risk(item))


def _role_override(profile: dict[str, Any], role: RoleName) -> dict[str, Any]:
    roles = profile.get("roles", {})
    if not isinstance(roles, dict):
        raise RiskProfileError("Risk profile roles must be a mapping")
    value = cast(dict[str, Any], roles).get(role.value)
    if not isinstance(value, dict):
        raise RiskProfileError(f"Risk profile has no configuration for role {role.value}")
    typed_value = cast(dict[str, Any], value)
    return deepcopy(typed_value)


def _needs_security(item: FeatureItem, packet: TaskPacket) -> bool:
    text = " ".join([item.outcome, item.lead_role, packet.title, packet.goal]).lower()
    return any(word in text for word in _SECURITY_WORDS)


def _needs_performance(item: FeatureItem, packet: TaskPacket) -> bool:
    text = " ".join([item.outcome, item.lead_role, packet.title, packet.goal]).lower()
    return any(word in text for word in _PERFORMANCE_WORDS)


def _mutating_stages(packet: TaskPacket, tier: RiskTier) -> list[Stage]:
    """Select the minimum useful write stages for the task risk.

    The controller-owned catalog already provides the task contract. Ordinary work therefore
    needs one implementation/research session. Integration and trust work may retain one
    independent specification session before the implementation session. Research-only trust
    tasks may retain specification plus research. The sequence is capped at two write stages.
    """

    proposed = [
        stage
        for stage in packet.pipeline
        if stage.role in {RoleName.RESEARCH, RoleName.SPECIFICATION, RoleName.BUILDER}
    ]
    if not proposed:
        lead = f"{packet.title} {packet.goal}".lower()
        role = RoleName.RESEARCH if "research" in lead or "source" in lead else RoleName.BUILDER
        proposed = [Stage(role=role, allowed_paths=list(packet.outputs), require_changes=True)]

    builders = [stage for stage in proposed if stage.role == RoleName.BUILDER]
    researchers = [stage for stage in proposed if stage.role == RoleName.RESEARCH]
    specifications = [stage for stage in proposed if stage.role == RoleName.SPECIFICATION]

    if tier == RiskTier.MECHANICAL:
        return [builders[-1] if builders else researchers[-1] if researchers else proposed[-1]]

    if builders:
        selected: list[Stage] = []
        if tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE} and specifications:
            selected.append(specifications[0])
        elif tier == RiskTier.TRUST_CORE and researchers:
            selected.append(researchers[0])
        selected.append(builders[-1])
        return selected[:2]

    if researchers:
        if tier == RiskTier.TRUST_CORE and specifications:
            return [specifications[0], researchers[-1]]
        return [researchers[-1]]

    return [specifications[0] if specifications else proposed[-1]]


def required_task_budget_tokens(context_chars: int) -> int:
    """Return a task-token ceiling that preserves work room after cached context."""

    context_token_estimate = (
        context_chars + CONTEXT_CHARS_PER_TOKEN - 1
    ) // CONTEXT_CHARS_PER_TOKEN
    return context_token_estimate + MIN_STAGE_WORK_TOKENS


def with_working_token_reserve(stage: Stage) -> Stage:
    """Upgrade legacy packets whose context can consume their whole task budget."""

    if stage.max_context_chars is None:
        return stage
    required = required_task_budget_tokens(stage.max_context_chars)
    if (stage.task_budget_tokens or 0) >= required:
        return stage
    return stage.model_copy(update={"task_budget_tokens": required})


def _apply_stage_profile(stage: Stage, profile: dict[str, Any], context_chars: int) -> Stage:
    override = _role_override(profile, stage.role)
    effective_context_chars = min(
        stage.max_context_chars or context_chars,
        context_chars,
    )
    override["max_context_chars"] = effective_context_chars
    # Claude's task budget includes the cache-creation tokens for controller-provided
    # context. Several live planner/reviewer sessions consumed ~24k tokens before their
    # first tool call, leaving only hundreds of tokens under the old profile values.
    # Reserve a bounded working allowance after the maximum context payload. This is a
    # Max-subscription token ceiling only; it does not enable paid usage or raise the
    # controller's dollar caps.
    override["task_budget_tokens"] = max(
        int(override.get("task_budget_tokens") or 0),
        required_task_budget_tokens(effective_context_chars),
    )
    override["context_keys"] = list(dict.fromkeys(stage.context_keys))
    return stage.model_copy(update=override)


def planning_pipeline(
    item: FeatureItem, profiles: dict[str, Any]
) -> tuple[list[Stage], float, int]:
    tier = effective_risk(item)
    profile = profiles["profiles"][tier.value]
    context_chars = int(profile["context_chars"])
    writable = [
        f"factory/proposals/{item.task_id}.yaml",
        f"specs/tasks/{item.task_id}.md",
    ]
    forbidden = [
        ".claude/**",
        "config/**",
        "prompts/**",
        "tcfactory/**",
        "schemas/**",
        "factory/state/**",
        "factory/queue/**",
        "factory/feature_ledger.yaml",
        "factory/product_definition_of_done.yaml",
        "docs/TrainCapsule_Matrix_Definitive_Master_Plan_v1.0.md",
        "docs/MASTER_PLAN_INDEX.md",
        "docs/CONTEXT_INDEX.yaml",
    ]
    planner = _apply_stage_profile(
        Stage(
            role=RoleName.PLANNER,
            allowed_paths=writable,
            forbidden_paths=forbidden,
            require_changes=True,
            context_keys=item.context_keys,
        ),
        profile,
        context_chars,
    )
    stages = [planner]
    # Task-packet planning is deliberately cheaper than implementation review.
    # Mechanical work relies on schema/path validation. Standard and integration work add
    # one read-only release sanity check. Trust-core planning also receives an independent
    # Opus adversary because an underspecified contract can invalidate the product.
    if tier == RiskTier.TRUST_CORE:
        stages.append(
            _apply_stage_profile(
                Stage(role=RoleName.ADVERSARY, read_only=True, forbidden_paths=["**"]),
                profile,
                context_chars,
            )
        )
    if tier != RiskTier.MECHANICAL:
        stages.append(
            _apply_stage_profile(
                Stage(role=RoleName.RELEASE, read_only=True, forbidden_paths=["**"]),
                profile,
                context_chars,
            )
        )
    return stages, float(profile["task_budget_usd"]), int(profile["repair_cycles"])


def _private_gate_for(item: FeatureItem, packet: TaskPacket, tier: RiskTier) -> PrivateGate:
    if packet.private_gate.required:
        return packet.private_gate
    if tier not in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}:
        return packet.private_gate
    numeric = (
        int(item.task_id[1:]) if item.task_id.startswith("T") and item.task_id[1:].isdigit() else 0
    )
    mature_trust = numeric in set(range(17, 21)) | set(range(39, 42)) | set(range(45, 48)) | {
        54,
        60,
    }
    suite = (
        "trust-core-mutations"
        if tier == RiskTier.TRUST_CORE and mature_trust
        else "factory-negative-controls"
    )
    return PrivateGate(required=True, suite=suite, timeout_seconds=3600)


def apply_risk_profile(
    packet: TaskPacket,
    item: FeatureItem,
    profiles: dict[str, Any],
) -> TaskPacket:
    """Apply controller-owned routing after the planning model writes task content.

    The model proposes scope, paths, criteria, and gates. The deterministic controller owns
    model selection, effort, reviewer depth, repair ceilings, and minimum risk. Risk can only
    move upward.
    """

    tier = effective_risk(item)
    profile = profiles["profiles"][tier.value]
    context_chars = int(profile["context_chars"])
    mutating_stages: list[Stage] = []
    for proposed in _mutating_stages(packet, tier):
        if proposed.read_only:
            proposed = proposed.model_copy(update={"read_only": False})
        mutating_stages.append(_apply_stage_profile(proposed, profile, context_chars))

    stages: list[Stage] = list(mutating_stages)
    reviewers = list(profile.get("reviewers", []))
    if _needs_security(item, packet) and "security" not in reviewers:
        reviewers.insert(-1 if reviewers else 0, "security")
    if _needs_performance(item, packet) and "performance" not in reviewers:
        reviewers.insert(-1 if reviewers else 0, "performance")

    # Measured milestones receive two explicit commercial-materiality reviews. They run
    # only on the small set of predeclared milestone tasks; ordinary feature work relies
    # on the deterministic value contract and avoids this extra model cost. The release
    # reviewer remains last so it sees the technical and value-adversarial verdicts.
    if packet.value_contract.mode == ValueGateMode.MEASURED:
        release_positions = [index for index, name in enumerate(reviewers) if name == "release"]
        insert_at = release_positions[0] if release_positions else len(reviewers)
        reviewers[insert_at:insert_at] = ["value_validator", "value_adversary"]

    for name in reviewers:
        role = RoleName(name)
        stages.append(
            _apply_stage_profile(
                Stage(
                    role=role,
                    read_only=True,
                    require_changes=False,
                    forbidden_paths=["**"],
                    machine_gates=[gate.name for gate in packet.gates],
                    context_keys=item.context_keys,
                ),
                profile,
                context_chars,
            )
        )

    protected_output = any(
        value.startswith(("src/", "tests/", "profiles/", "corpus/", "contracts/"))
        or "/src/" in value
        for value in packet.outputs
    )
    private_gate = packet.private_gate
    if tier == RiskTier.TRUST_CORE and (protected_output or item.allow_test_changes):
        private_gate = PrivateGate(
            required=True,
            suite=packet.private_gate.suite or f"traincapsule-trust-{packet.task_id.lower()}",
            timeout_seconds=max(packet.private_gate.timeout_seconds, 1800),
        )
    elif tier == RiskTier.INTEGRATION and item.allow_test_changes:
        private_gate = PrivateGate(
            required=True,
            suite=packet.private_gate.suite or f"traincapsule-integration-{packet.task_id.lower()}",
            timeout_seconds=max(packet.private_gate.timeout_seconds, 1200),
        )

    repair_models = ["sonnet"]
    if tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}:
        repair_models.append("opus")

    return packet.model_copy(
        update={
            "risk_tier": tier,
            "context_keys": list(dict.fromkeys(item.context_keys + packet.context_keys)),
            "remote_ci_required": item.remote_ci_required
            or tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE},
            "allow_test_changes": item.allow_test_changes,
            "commit_type": item.commit_type,
            "github_push": True,
            "pipeline": stages,
            "private_gate": _private_gate_for(
                item, packet.model_copy(update={"private_gate": private_gate}), tier
            ),
            "repair": RepairPolicy(
                enabled=True,
                max_cycles=int(profile["repair_cycles"]),
                builder_models=repair_models,
                restart_review_from=(
                    RoleName.ADVERSARY
                    if any(stage.role == RoleName.ADVERSARY for stage in stages)
                    else RoleName.RELEASE
                ),
                mutating_role=mutating_stages[-1].role,
            ),
            "task_budget_usd": float(profile["task_budget_usd"]),
        }
    )
