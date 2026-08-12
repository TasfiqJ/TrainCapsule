"""Qualification records for bounded, evidence-first product decisions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator
from traincapsule_core.base import ProductModel
from traincapsule_core.models import (
    Digest,
    EvidenceCompletenessReport,
    Identifier,
    NativeFinding,
)


class CostHypothesis(StrEnum):
    VIABLE = "VIABLE"
    UNECONOMIC = "UNECONOMIC"
    UNKNOWN = "UNKNOWN"


class NativeBaseline(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    tool_name: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    command: list[str] = Field(min_length=1)
    configuration: dict[str, object]
    findings: list[NativeFinding]
    evidence_refs: list[Digest] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    unresolved_customer_decision: str = Field(min_length=1)
    executed_at: datetime
    human_reviewed: bool
    reviewer: str | None = None

    @model_validator(mode="after")
    def reviewer_matches_review_status(self) -> NativeBaseline:
        if self.human_reviewed and not self.reviewer:
            raise ValueError("human-reviewed native baseline requires reviewer")
        if not self.human_reviewed and self.reviewer:
            raise ValueError("unreviewed native baseline cannot name a reviewer")
        return self


class PreflightInputs(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    decision_type: str = Field(min_length=1)
    decision_deadline: datetime
    evaluated_at: datetime
    baseline_access: bool | None
    candidate_access: bool | None
    evidence_identity_bound: bool | None
    pack_fit: bool | None
    local_execution_available: bool | None
    cost_hypothesis: CostHypothesis
    privacy_policy_allows_processing: bool | None
    export_policy_allows_required_flow: bool | None
    complete_native_baseline: bool | None
    native_workflow_resolves_decision: bool | None
    human_expertise_available: bool | None
    source_version_supported: bool | None
    completeness_report: EvidenceCompletenessReport
    native_baseline: NativeBaseline | None = None

    @model_validator(mode="after")
    def baseline_claim_has_record(self) -> PreflightInputs:
        if self.complete_native_baseline is True and self.native_baseline is None:
            raise ValueError("completeNativeBaseline=true requires nativeBaseline")
        if self.native_workflow_resolves_decision is True and not self.complete_native_baseline:
            raise ValueError(
                "native workflow cannot resolve the decision without a complete baseline"
            )
        if self.completeness_report.case_id != self.case_id:
            raise ValueError("completeness report belongs to a different case")
        if self.native_baseline and self.native_baseline.case_id != self.case_id:
            raise ValueError("native baseline belongs to a different case")
        return self
