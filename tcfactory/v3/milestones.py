"""Bounded V3 milestones and their truth-preserving completion rules."""

from __future__ import annotations

import re

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import MilestoneStatus, MilestoneType


class Milestone(V3Model):
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    type: MilestoneType
    status: MilestoneStatus
    entry_criteria: list[str]
    exit_criteria: list[str] = Field(min_length=1)
    required_evidence: list[str] = Field(min_length=1)
    forbidden_claims: list[str]
    human_approval_required: bool
    human_approval_refs: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_bounded_completion(self) -> Milestone:
        for criterion in self.exit_criteria:
            normalized = re.sub(r"[^a-z0-9]+", " ", criterion.lower()).strip()
            if "all product tasks" in normalized and (
                "done" in normalized or "complete" in normalized
            ):
                raise ValueError("global all-product-tasks completion is forbidden")
        if (
            self.status is MilestoneStatus.COMPLETED
            and self.human_approval_required
            and not self.human_approval_refs
        ):
            raise ValueError("completed milestone lacks required human approval")
        return self


class MilestoneRoadmap(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    milestones: list[Milestone] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_milestones(self) -> MilestoneRoadmap:
        identifiers = [milestone.milestone_id for milestone in self.milestones]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("milestone IDs must be unique")
        return self

    def milestone(self, milestone_id: str) -> Milestone:
        for milestone in self.milestones:
            if milestone.milestone_id == milestone_id:
                return milestone
        raise KeyError(milestone_id)
