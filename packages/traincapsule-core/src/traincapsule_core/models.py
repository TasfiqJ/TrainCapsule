"""Versioned TrainCapsule product-domain records, isolated from factory types."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from .base import ProductModel

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]


class TechnicalResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    INVALID_EVIDENCE = "INVALID_EVIDENCE"
    INVALID_ORACLE = "INVALID_ORACLE"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    EXPIRED = "EXPIRED"


class OperationalDecision(StrEnum):
    APPROVE_WITHIN_ENVELOPE = "APPROVE_WITHIN_ENVELOPE"
    BLOCK_CHANGE = "BLOCK_CHANGE"
    REQUIRE_MORE_EVIDENCE = "REQUIRE_MORE_EVIDENCE"
    NO_DECISION = "NO_DECISION"
    NATIVE_WORKFLOW_SUFFICIENT = "NATIVE_WORKFLOW_SUFFICIENT"
    TECHNICALLY_VALID_BUT_NOT_ECONOMIC = "TECHNICALLY_VALID_BUT_NOT_ECONOMIC"


class DataIdentityPolicy(StrEnum):
    FULL_DIGEST = "FULL_DIGEST"
    MANIFEST_DIGEST = "MANIFEST_DIGEST"
    CUSTOMER_ATTESTED = "CUSTOMER_ATTESTED"
    UNAVAILABLE = "UNAVAILABLE"


class PrivacyClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class EvidenceIntegrity(StrEnum):
    VALID = "VALID"
    CORRUPTED = "CORRUPTED"
    UNKNOWN = "UNKNOWN"


class NativeConfidence(StrEnum):
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"
    DERIVED_ALIGNMENT = "DERIVED_ALIGNMENT"
    TOOL_HEURISTIC = "TOOL_HEURISTIC"
    UNVERIFIED_NARRATIVE = "UNVERIFIED_NARRATIVE"


class CompletenessState(StrEnum):
    PRESENT_VALID = "PRESENT_VALID"
    PRESENT_PARTIAL = "PRESENT_PARTIAL"
    PRESENT_CONFLICTING = "PRESENT_CONFLICTING"
    PRESENT_CORRUPTED = "PRESENT_CORRUPTED"
    MISSING_NOT_CAPTURED = "MISSING_NOT_CAPTURED"
    MISSING_POLICY_RESTRICTED = "MISSING_POLICY_RESTRICTED"
    MISSING_TECHNICALLY_INACCESSIBLE = "MISSING_TECHNICALLY_INACCESSIBLE"
    MISSING_VERSION_UNSUPPORTED = "MISSING_VERSION_UNSUPPORTED"
    IDENTITY_UNBOUND = "IDENTITY_UNBOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityOutcome(StrEnum):
    ELIGIBLE_FOR_QUALIFICATION = "ELIGIBLE_FOR_QUALIFICATION"
    ELIGIBLE_WITH_HUMAN_REVIEW = "ELIGIBLE_WITH_HUMAN_REVIEW"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"
    NATIVE_WORKFLOW_SUFFICIENT = "NATIVE_WORKFLOW_SUFFICIENT"
    TECHNICALLY_POSSIBLE_BUT_UNECONOMIC = "TECHNICALLY_POSSIBLE_BUT_UNECONOMIC"
    OUTSIDE_SUPPORTED_ENVELOPE = "OUTSIDE_SUPPORTED_ENVELOPE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    UNKNOWN = "UNKNOWN"


class SourceIdentity(ProductModel):
    repository_digest: Digest
    dirty_patch_digest: Digest | None = None


class FrameworkIdentity(ProductModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class DistributedIdentity(ProductModel):
    strategy: str = Field(min_length=1)
    world_size: int = Field(ge=1, le=131072)
    process_groups_digest: Digest


class DataIdentity(ProductModel):
    policy: DataIdentityPolicy
    manifest_digest: Digest | None = None

    @model_validator(mode="after")
    def digest_matches_policy(self) -> DataIdentity:
        if self.policy in {
            DataIdentityPolicy.FULL_DIGEST,
            DataIdentityPolicy.MANIFEST_DIGEST,
        } and self.manifest_digest is None:
            raise ValueError("content/manifest identity requires manifestDigest")
        if self.policy is DataIdentityPolicy.UNAVAILABLE and self.manifest_digest is not None:
            raise ValueError("UNAVAILABLE data identity cannot carry a digest")
        return self


class WorkloadIdentity(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    workload_id: Digest
    source_identity: SourceIdentity
    entrypoint: str = Field(min_length=1)
    arguments_digest: Digest
    container_image_digest: Digest | None = None
    dependency_lock_digest: Digest
    framework: FrameworkIdentity
    distributed: DistributedIdentity
    model_structure_digest: Digest | None = None
    data_identity: DataIdentity
    checkpoint_policy_digest: Digest | None = None
    privacy_class: PrivacyClass
    created_at: datetime


class EnvironmentIdentity(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    environment_id: Digest
    host_kernel: str = Field(min_length=1)
    container_runtime: str | None = None
    python: str = Field(min_length=1)
    pytorch: str = Field(min_length=1)
    cuda_runtime: str | None = None
    cuda_driver: str | None = None
    nccl: str | None = None
    gpu_model: str | None = None
    gpu_count: int = Field(default=0, ge=0, le=131072)
    gpu_firmware_digest: Digest | None = None
    topology_digest: Digest | None = None
    scheduler: str | None = None
    network_class: str | None = None
    storage_class: str | None = None
    environment_variables_digest: Digest
    redaction_policy_version: str = Field(min_length=1)
    materialization_recipe_digest: Digest | None = None
    created_at: datetime


class EvidenceArtifact(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    artifact_id: Digest
    case_id: Identifier
    kind: str = Field(min_length=1)
    source_adapter: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    captured_at: datetime
    content_digest: Digest
    size_bytes: int = Field(ge=0)
    compression: str = "none"
    encryption: str = "none"
    privacy_class: PrivacyClass
    customer_local_uri: str = Field(pattern=r"^cas://[A-Za-z0-9._/-]+$")
    export_policy: str = Field(min_length=1)
    provenance: dict[str, str]
    integrity_status: EvidenceIntegrity

    @model_validator(mode="after")
    def content_address_is_identity(self) -> EvidenceArtifact:
        if self.artifact_id != self.content_digest:
            raise ValueError("artifactId must equal the raw content digest")
        return self


class NativeFinding(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    finding_id: Digest
    native_system: str = Field(min_length=1)
    native_version: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    evidence_refs: list[Digest]
    confidence_class: NativeConfidence
    limitations: list[str]
    customer_decision_contribution: str


class CaseEconomics(ProductModel):
    estimated_original_run_cost: float | None = Field(default=None, ge=0)
    estimated_investigation_cost: float | None = Field(default=None, ge=0)
    estimated_delay_cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def currency_for_known_cost(self) -> CaseEconomics:
        known = any(
            value is not None
            for value in (
                self.estimated_original_run_cost,
                self.estimated_investigation_cost,
                self.estimated_delay_cost,
            )
        )
        if known and self.currency is None:
            raise ValueError("known cost requires an ISO currency")
        return self


class IncidentCase(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    decision_owner: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    decision_deadline: datetime
    incident_summary: str = Field(min_length=1)
    baseline_environment_id: Digest | None = None
    candidate_environment_id: Digest | None = None
    workload_id: Digest | None = None
    evidence_refs: list[Digest]
    native_findings: list[NativeFinding]
    pack_candidate: str = Field(min_length=1)
    economics: CaseEconomics
    privacy_policy: str = Field(min_length=1)
    status: str = Field(min_length=1)


class EvidenceRequirement(ProductModel):
    kind: str = Field(min_length=1)
    state: CompletenessState
    artifact_refs: list[Digest]
    detail: str = Field(min_length=1)


class EvidenceCompletenessReport(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    requirements: list[EvidenceRequirement] = Field(min_length=1)
    technical_result: TechnicalResult

    @model_validator(mode="after")
    def result_matches_requirements(self) -> EvidenceCompletenessReport:
        states = {requirement.state for requirement in self.requirements}
        valid = {CompletenessState.PRESENT_VALID, CompletenessState.NOT_APPLICABLE}
        if states <= valid and self.technical_result is not TechnicalResult.PASS:
            raise ValueError("complete evidence must have PASS technical result")
        if states - valid and self.technical_result is TechnicalResult.PASS:
            raise ValueError("incomplete evidence cannot have PASS technical result")
        return self


class EligibilityDecision(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    outcome: EligibilityOutcome
    technical_result: TechnicalResult
    operational_decision: OperationalDecision
    reasons: list[str] = Field(min_length=1)
    unknowns: list[str]
    generated_at: datetime


def safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("identifier contains unsafe characters")
    return value
