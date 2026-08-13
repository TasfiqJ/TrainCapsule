"""Deterministic, lane-aware scheduling for bounded V3 work."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Lane, OwnerType, WorkKind, WorkStatus
from tcfactory.v3.external_evidence import EvidenceSignature
from tcfactory.v3.work_items import WorkItem, WorkItemCollection


class LaneWipLimit(V3Model):
    mutating: int = Field(ge=0, le=4)
    read_only: int = Field(alias="readOnly", ge=0, le=8)


class FactoryMaintenancePolicy(V3Model):
    allow_mutating_only_on_controller_failure: bool


class SchedulerWeights(V3Model):
    current_milestone_critical_path: int
    customer_decision_relevance: int
    external_evidence_unblock: int
    native_equivalence_risk: int
    trust_release_blocker: int
    reusable_same_family_value: int
    short_feedback_cycle: int
    speculative_surface_area: int
    security_or_integration_burden: int
    likely_native_duplication: int
    context_or_quota_cost: int

    def as_mapping(self) -> dict[str, int]:
        return self.model_dump(mode="python")


class SchedulerConfig(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    active_milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    wip: dict[Lane, LaneWipLimit]
    factory_maintenance: FactoryMaintenancePolicy
    weights: SchedulerWeights
    tie_break: list[str] = Field(min_length=1)
    waiting_states_do_not_block_other_lanes: list[WorkStatus]

    @model_validator(mode="after")
    def validate_limits(self) -> SchedulerConfig:
        if set(self.wip) != set(Lane):
            missing = set(Lane) - set(self.wip)
            extra = set(self.wip) - set(Lane)
            raise ValueError(
                f"scheduler WIP lanes mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if len(self.tie_break) != len(set(self.tie_break)):
            raise ValueError("scheduler tie-break rules must be unique")
        required_waiting = {
            WorkStatus.WAITING_EXTERNAL,
            WorkStatus.DEFERRED,
            WorkStatus.NATIVE_SUFFICIENT,
            WorkStatus.REJECTED_VALUE,
        }
        if not required_waiting.issubset(self.waiting_states_do_not_block_other_lanes):
            raise ValueError("scheduler waiting-state isolation is incomplete")
        return self


class SchedulingFacts(V3Model):
    current_milestone_critical_path: float = Field(default=0, ge=0, le=1)
    customer_decision_relevance: float = Field(default=0, ge=0, le=1)
    external_evidence_unblock: float = Field(default=0, ge=0, le=1)
    native_equivalence_risk: float = Field(default=0, ge=0, le=1)
    trust_release_blocker: float = Field(default=0, ge=0, le=1)
    reusable_same_family_value: float = Field(default=0, ge=0, le=1)
    short_feedback_cycle: float = Field(default=0, ge=0, le=1)
    speculative_surface_area: float = Field(default=0, ge=0, le=1)
    security_or_integration_burden: float = Field(default=0, ge=0, le=1)
    likely_native_duplication: float = Field(default=0, ge=0, le=1)
    context_or_quota_cost: float = Field(default=0, ge=0, le=1)
    critical_path_length: int = Field(default=100, ge=0)
    reversible_size: float = Field(default=0.5, ge=0, le=1)
    requires_native_comparison_work_item: str | None = Field(
        default=None,
        pattern=r"^V3-[A-Z]+-[0-9]{3}$",
    )

    def factors(self) -> dict[str, float]:
        values = self.model_dump(mode="python")
        values.pop("critical_path_length")
        values.pop("reversible_size")
        values.pop("requires_native_comparison_work_item")
        return values


class ActiveWork(V3Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    lane: Lane
    mutating: bool


class SchedulerOverride(V3Model):
    decision_id: str = Field(pattern=r"^SOVR-[A-Z0-9_-]+$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    reason: str = Field(min_length=1)
    issued_by: Literal[OwnerType.MACHINE_POLICY_AUTHORITY]
    issued_at: datetime
    signature: EvidenceSignature


class TrustedSchedulerOverride(V3Model):
    record: SchedulerOverride
    signature_valid: bool
    source_agent_writable: bool

    def require_trusted(self) -> SchedulerOverride:
        if self.source_agent_writable:
            raise ValueError("AI-writable scheduler override is not trusted")
        if not self.signature_valid:
            raise ValueError("scheduler override signature is invalid")
        return self.record


class ScoreComponent(V3Model):
    name: str
    weight: int
    factor: float
    contribution: float


class SchedulerEvaluation(V3Model):
    work_item_id: str
    lane: Lane
    eligible: bool
    reasons: list[str]
    score: float
    components: list[ScoreComponent]
    selected: bool = False


class SchedulerDecisionArtifact(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    cycle_id: str = Field(min_length=1)
    decided_at: datetime
    active_milestone: str
    config_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evaluations: list[SchedulerEvaluation]
    selected_work_item_ids: list[str]
    override_decision_id: str | None = None


MUTATING_KINDS = {
    WorkKind.CODE,
    WorkKind.SPECIFICATION,
    WorkKind.RESEARCH,
    WorkKind.CONTROLLED_EXPERIMENT,
    WorkKind.MAINTENANCE,
    WorkKind.MIGRATION,
}
SATISFIED_DEPENDENCY_STATES = {
    WorkStatus.PASSED_ENGINEERING,
    WorkStatus.COMPLETED,
}
CORE_SCHEDULING_LANES = (
    Lane.PRODUCT,
    Lane.MARKET,
    Lane.COMPETITOR,
    Lane.TRUST,
)


def is_mutating(item: WorkItem) -> bool:
    return item.kind in MUTATING_KINDS


def default_scheduling_facts(item: WorkItem, active_milestone: str) -> SchedulingFacts:
    """Derive conservative facts; callers may provide reviewed explicit facts."""

    return SchedulingFacts(
        current_milestone_critical_path=float(item.milestone == active_milestone),
        external_evidence_unblock=float(item.kind is WorkKind.EXTERNAL_EVIDENCE),
        native_equivalence_risk=float(item.lane is Lane.COMPETITOR),
        trust_release_blocker=float(item.lane is Lane.TRUST and item.blocks_commercial_release),
        short_feedback_cycle=float(item.kind in {WorkKind.RESEARCH, WorkKind.SPECIFICATION}),
        security_or_integration_burden=float(item.risk_tier.value in {"INTEGRATION", "TRUST_CORE"}),
    )


def _score(
    config: SchedulerConfig,
    facts: SchedulingFacts,
) -> tuple[float, list[ScoreComponent]]:
    weights = config.weights.as_mapping()
    components = [
        ScoreComponent(
            name=name,
            weight=weights[name],
            factor=factor,
            contribution=weights[name] * factor,
        )
        for name, factor in facts.factors().items()
    ]
    return sum(component.contribution for component in components), components


def _tie_key(item: WorkItem, facts: SchedulingFacts) -> tuple[int, int, int, int, float, str]:
    evidence_first = int(
        item.kind
        not in {
            WorkKind.RESEARCH,
            WorkKind.EXTERNAL_EVIDENCE,
            WorkKind.CONTROLLED_EXPERIMENT,
        }
    )
    native_first = int(item.lane is not Lane.COMPETITOR)
    trust_first = int(item.lane is not Lane.TRUST)
    return (
        facts.critical_path_length,
        evidence_first,
        native_first,
        trust_first,
        facts.reversible_size,
        item.work_item_id,
    )


def schedule_cycle(
    collection: WorkItemCollection,
    config: SchedulerConfig,
    *,
    cycle_id: str,
    decided_at: datetime,
    facts_by_id: Mapping[str, SchedulingFacts] | None = None,
    active_work: Sequence[ActiveWork] = (),
    max_concurrent_mutating_sessions: int = 1,
    max_concurrent_read_only_sessions: int = 1,
    controller_failure: bool = False,
    migration_bootstrap: bool = False,
    override: TrustedSchedulerOverride | None = None,
    lane_cursor: Lane | None = None,
    eligible_future_milestones: Mapping[Lane, frozenset[str]] | None = None,
) -> SchedulerDecisionArtifact:
    """Select deterministic independent-lane work and explain every decision."""

    if max_concurrent_mutating_sessions <= 0 or max_concurrent_read_only_sessions <= 0:
        raise ValueError("global scheduler concurrency limits must be positive")
    items = {item.work_item_id: item for item in collection.work_items}
    active_ids = [active.work_item_id for active in active_work]
    if len(active_ids) != len(set(active_ids)):
        raise ValueError("duplicate active work item")
    active_lane_mode = Counter((active.lane, active.mutating) for active in active_work)
    global_mutating = sum(active.mutating for active in active_work)
    global_read_only = len(active_work) - global_mutating
    explicit_facts = facts_by_id or {}
    ranked: list[
        tuple[float, tuple[int, int, int, int, float, str], WorkItem, SchedulingFacts]
    ] = []
    evaluations: dict[str, SchedulerEvaluation] = {}
    future_milestones = eligible_future_milestones or {}

    for identifier in sorted(items):
        item = items[identifier]
        facts = explicit_facts.get(identifier) or default_scheduling_facts(
            item,
            config.active_milestone,
        )
        score, components = _score(config, facts)
        reasons: list[str] = []
        if item.milestone != config.active_milestone and item.milestone not in (
            future_milestones.get(item.lane, frozenset())
        ):
            reasons.append(f"milestone {item.milestone} is not active ({config.active_milestone})")
        if item.status is not WorkStatus.READY:
            reasons.append(f"status {item.status} is not READY")
        if item.external_receipt_required:
            reasons.append(
                "outside-fact work advances only through the trusted external receipt gate"
            )
        if item.machine_policy_receipt_required:
            reasons.append(
                "machine-policy review advances only through an independently signed receipt"
            )
        if identifier in active_ids:
            reasons.append("work item is already active")
        unsatisfied = [
            dependency
            for dependency in item.depends_on
            if items[dependency].status not in SATISFIED_DEPENDENCY_STATES
        ]
        if unsatisfied:
            reasons.append(f"unsatisfied hard dependencies: {sorted(unsatisfied)}")
        native_dependency = facts.requires_native_comparison_work_item
        if native_dependency is not None:
            native_item = items.get(native_dependency)
            if native_item is None or native_item.status not in SATISFIED_DEPENDENCY_STATES:
                reasons.append(f"native comparison not complete: {native_dependency}")
        mutating = is_mutating(item)
        lane_limit = config.wip[item.lane]
        limit = lane_limit.mutating if mutating else lane_limit.read_only
        factory_exception = controller_failure or (
            migration_bootstrap
            and item.milestone == "M0_FACTORY_MIGRATED"
            and item.kind is WorkKind.MIGRATION
        )
        if item.lane is Lane.FACTORY and mutating and factory_exception and limit == 0:
            # The normative WIP rule is "0 unless controller failure". A zero in
            # configuration is therefore a closed normal lane, not a permanent ban.
            limit = 1
        if active_lane_mode[(item.lane, mutating)] >= limit:
            reasons.append("lane WIP limit reached")
        if (
            item.lane is Lane.FACTORY
            and mutating
            and config.factory_maintenance.allow_mutating_only_on_controller_failure
            and not factory_exception
        ):
            reasons.append("mutating factory maintenance requires controller failure")
        eligible = not reasons
        evaluations[identifier] = SchedulerEvaluation(
            work_item_id=identifier,
            lane=item.lane,
            eligible=eligible,
            reasons=reasons,
            score=score,
            components=components,
        )
        if eligible:
            ranked.append((-score, _tie_key(item, facts), item, facts))

    ranked.sort(key=lambda candidate: (candidate[0], candidate[1]))
    cursor = lane_cursor if lane_cursor in CORE_SCHEDULING_LANES else Lane.PRODUCT
    start = CORE_SCHEDULING_LANES.index(cursor)
    fair_lanes = (
        *CORE_SCHEDULING_LANES[start:],
        *CORE_SCHEDULING_LANES[:start],
        Lane.FACTORY,
    )
    override_record = override.require_trusted() if override is not None else None
    if override_record is not None:
        match = next(
            (
                candidate
                for candidate in ranked
                if candidate[2].work_item_id == override_record.work_item_id
            ),
            None,
        )
        if match is None:
            raise ValueError("trusted scheduler override targets an ineligible work item")
        ranked.remove(match)
        ranked.insert(0, match)
        fair_lanes = (
            match[2].lane,
            *(lane for lane in fair_lanes if lane is not match[2].lane),
        )

    selected: list[str] = []
    selected_lane_mode: Counter[tuple[Lane, bool]] = Counter()
    remaining = list(ranked)
    for mutating_mode in (False, True):
        capacity = (
            max_concurrent_mutating_sessions - global_mutating
            if mutating_mode
            else max_concurrent_read_only_sessions - global_read_only
        )
        while capacity > 0:
            chosen_index: int | None = None
            for lane in fair_lanes:
                for index, (_, _, item, _) in enumerate(remaining):
                    if item.lane is not lane or is_mutating(item) is not mutating_mode:
                        continue
                    lane_limit = config.wip[item.lane]
                    limit = lane_limit.mutating if mutating_mode else lane_limit.read_only
                    factory_exception = controller_failure or (
                        migration_bootstrap
                        and item.milestone == "M0_FACTORY_MIGRATED"
                        and item.kind is WorkKind.MIGRATION
                    )
                    if (
                        item.lane is Lane.FACTORY
                        and mutating_mode
                        and factory_exception
                        and limit == 0
                    ):
                        limit = 1
                    current_lane = active_lane_mode[(item.lane, mutating_mode)]
                    if current_lane + selected_lane_mode[(item.lane, mutating_mode)] >= limit:
                        continue
                    chosen_index = index
                    break
                if chosen_index is not None:
                    break
            if chosen_index is None:
                break
            _, _, chosen, _ = remaining.pop(chosen_index)
            selected.append(chosen.work_item_id)
            selected_lane_mode[(chosen.lane, mutating_mode)] += 1
            capacity -= 1
            if mutating_mode:
                global_mutating += 1
            else:
                global_read_only += 1

    for identifier in selected:
        evaluations[identifier].selected = True
    return SchedulerDecisionArtifact(
        cycle_id=cycle_id,
        decided_at=decided_at,
        active_milestone=config.active_milestone,
        config_digest=config.canonical_digest(),
        evaluations=[evaluations[identifier] for identifier in sorted(evaluations)],
        selected_work_item_ids=selected,
        override_decision_id=(override_record.decision_id if override_record is not None else None),
    )
