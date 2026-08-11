"""Typed scheduler configuration; selection behavior is implemented in Phase C."""

from __future__ import annotations

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Lane, WorkStatus


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
                f"scheduler WIP lanes mismatch: missing={sorted(missing)}, "
                f"extra={sorted(extra)}"
            )
        if len(self.tie_break) != len(set(self.tie_break)):
            raise ValueError("scheduler tie-break rules must be unique")
        return self
