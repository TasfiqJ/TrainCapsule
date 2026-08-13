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
)
from .stage_policy import apply_objective_stage_contracts
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


def _mutating_stages(packet: TaskPacket, tier: RiskTier) -> list[Stage]:
    """Select one Claude owner for plan/research/build decisions.

    Separate specification and implementation owners fragmented context and made the
    controller decide architecture.  The owner may still delegate specialists with Claude
    Code's Agent tool, but the pipeline keeps one renewable mutating context.
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
    owner = builders[-1] if builders else researchers[-1] if researchers else proposed[-1]
    return [
        owner.model_copy(
            update={
                "allowed_paths": list(dict.fromkeys(owner.allowed_paths)),
                "require_changes": (
                    owner.require_changes if owner.require_changes is not None else True
                ),
            }
        )
    ]


def required_task_budget_tokens(context_chars: int) -> int:
    """Return a task-token ceiling that preserves work room after cached context."""

    context_token_estimate = (
        context_chars + CONTEXT_CHARS_PER_TOKEN - 1
    ) // CONTEXT_CHARS_PER_TOKEN
    return context_token_estimate + MIN_STAGE_WORK_TOKENS


def with_working_token_reserve(
    stage: Stage,
    *,
    work_until_done: bool = False,
    mutating_turn_floor: int = 200,
    review_turn_floor: int = 80,
) -> Stage:
    """Apply the runtime session policy to current and legacy task packets.

    Finite/offline callers keep the historical token-reserve behavior.  The Max OAuth
    autopilot removes the SDK task-token ceiling and raises the per-session turn budget;
    the pipeline renews fresh sessions from durable candidate commits until the feature
    passes or reaches a truthful external blocker.
    """

    if work_until_done:
        raise RiskProfileError(
            "work_until_done is forbidden in V3; use a finite retry/disposition policy"
        )

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
        "docs/source-of-truth/**",
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
    planner = with_working_token_reserve(planner, work_until_done=False)
    # Proposal policy is a deterministic exit check. Four model sessions here previously
    # reviewed the same two files and repeatedly turned controller observations into task
    # revisions. The planner now owns the living outcome contract and repairs it directly.
    return [planner], float(profile["task_budget_usd"]), int(profile["repair_cycles"])


def _private_gate_for(item: FeatureItem, packet: TaskPacket, tier: RiskTier) -> PrivateGate:
    if packet.private_gate.required:
        return packet.private_gate
    if tier not in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE}:
        return packet.private_gate
    text = f"{item.outcome} {item.phase} {item.lead_role}".lower()
    if any(marker in text for marker in ("credential", "secret", "sandbox", "security")):
        suite = "security-boundary"
    elif any(marker in text for marker in ("adapter", "integration", "import", "github")):
        suite = "integration-paths"
    elif tier == RiskTier.TRUST_CORE:
        suite = "trust-core-mutations"
    else:
        suite = "factory-negative-controls"
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
        mutating_stages.append(
            with_working_token_reserve(
                _apply_stage_profile(proposed, profile, context_chars),
                work_until_done=False,
            )
        )

    owner = mutating_stages[-1]
    stages: list[Stage] = [owner]
    # One blind verifier challenges every non-mechanical product candidate. Security,
    # performance, integration, value and release applicability are dimensions of this
    # proof node, not mandatory serial model sessions. Deterministic/private/value/CI gates
    # remain separate release authority.
    if tier != RiskTier.MECHANICAL:
        stages.append(
            with_working_token_reserve(
                _apply_stage_profile(
                    Stage(
                        role=RoleName.ADVERSARY,
                        read_only=True,
                        require_changes=False,
                        forbidden_paths=["**"],
                        allowed_domains=list(owner.allowed_domains),
                        machine_gates=[],
                        context_keys=item.context_keys,
                    ),
                    profile,
                    context_chars,
                ),
                work_until_done=False,
            )
        )

    # Machine gates run after mutations, not again after every read-only opinion. A repair
    # uses the same owner role and therefore reruns the exact gates on the changed candidate.
    owner_gates = [gate.model_copy(update={"stages": [owner.role]}) for gate in packet.gates]

    repair_models = [owner.model or "sonnet"]

    routed = packet.model_copy(
        update={
            "risk_tier": tier,
            "context_keys": list(dict.fromkeys(item.context_keys + packet.context_keys)),
            "remote_ci_required": item.remote_ci_required
            or tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE},
            "allow_test_changes": item.allow_test_changes,
            "commit_type": item.commit_type,
            "github_push": packet.github_push,
            "pipeline": stages,
            "gates": owner_gates,
            "private_gate": _private_gate_for(item, packet, tier),
            "repair": RepairPolicy(
                enabled=True,
                max_cycles=int(profile["repair_cycles"]),
                builder_models=repair_models,
                restart_review_from=(RoleName.ADVERSARY if len(stages) > 1 else owner.role),
                mutating_role=mutating_stages[-1].role,
            ),
            "task_budget_usd": float(profile["task_budget_usd"]),
            "auto_merge": False,
        }
    )
    return apply_objective_stage_contracts(routed)
