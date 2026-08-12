"""Strict, versioned product truth records. Factory state is deliberately excluded."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import ProductModel, digest_json

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


class IdentityStrength(StrEnum):
    FULLY_VERIFIED = "FULLY_VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    CUSTOMER_ATTESTED = "CUSTOMER_ATTESTED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICTING = "CONFLICTING"


class DataIdentityPolicy(StrEnum):
    FULL_DIGEST = "FULL_DIGEST"
    MANIFEST_DIGEST = "MANIFEST_DIGEST"
    CUSTOMER_ATTESTED = "CUSTOMER_ATTESTED"
    UNAVAILABLE = "UNAVAILABLE"


class PolicyName(StrEnum):
    PACK_FIT = "PACK_FIT"
    LOCAL_EXECUTION_AUTHORITY = "LOCAL_EXECUTION_AUTHORITY"
    PRIVACY_POLICY = "PRIVACY_POLICY"
    EXPORT_POLICY = "EXPORT_POLICY"
    SOURCE_VERSION = "SOURCE_VERSION"
    ECONOMICS = "ECONOMICS"


class VerificationOutcome(StrEnum):
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


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


class FindingAttribution(StrEnum):
    NATIVE_TOOL_FOUND = "NATIVE_TOOL_FOUND"
    TRAINCAPSULE_DERIVED = "TRAINCAPSULE_DERIVED"
    HUMAN_PROVIDED = "HUMAN_PROVIDED"
    EXTERNAL_SYSTEM_PROVIDED = "EXTERNAL_SYSTEM_PROVIDED"
    UNKNOWN = "UNKNOWN"


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


class EvidenceRole(StrEnum):
    MANDATORY_FOR_ELIGIBILITY = "MANDATORY_FOR_ELIGIBILITY"
    MANDATORY_FOR_CLAIM = "MANDATORY_FOR_CLAIM"
    OPTIONAL = "OPTIONAL"
    SUBSTITUTABLE = "SUBSTITUTABLE"
    IRRECOVERABLE_AFTER_INCIDENT = "IRRECOVERABLE_AFTER_INCIDENT"


class EligibilityOutcome(StrEnum):
    ELIGIBLE_FOR_QUALIFICATION = "ELIGIBLE_FOR_QUALIFICATION"
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
        if self.policy in {DataIdentityPolicy.FULL_DIGEST, DataIdentityPolicy.MANIFEST_DIGEST}:
            if self.manifest_digest is None:
                raise ValueError("content/manifest identity requires manifestDigest")
        elif self.manifest_digest is not None:
            raise ValueError("attested/unavailable data identity cannot carry a digest")
        return self


class WorkloadIdentity(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    workload_id: Digest
    identity_strength: IdentityStrength
    identity_conflict: bool = False
    source_identity: SourceIdentity
    entrypoint: str = Field(min_length=1)
    arguments_digest: Digest
    container_image_digest: Digest | None = None
    dependency_lock_digest: Digest
    configuration_files_digest: Digest
    relevant_environment_digest: Digest
    redaction_policy_version: str = Field(min_length=1)
    framework: FrameworkIdentity
    distributed: DistributedIdentity
    model_structure_digest: Digest | None = None
    data_identity: DataIdentity
    checkpoint_policy_digest: Digest | None = None
    privacy_class: PrivacyClass
    created_at: datetime

    @model_validator(mode="after")
    def canonical_identity_is_self_authenticating(self) -> WorkloadIdentity:
        expected_strength = (
            IdentityStrength.CONFLICTING
            if self.identity_conflict
            else {
                DataIdentityPolicy.FULL_DIGEST: IdentityStrength.FULLY_VERIFIED,
                DataIdentityPolicy.MANIFEST_DIGEST: IdentityStrength.PARTIALLY_VERIFIED,
                DataIdentityPolicy.CUSTOMER_ATTESTED: IdentityStrength.CUSTOMER_ATTESTED,
                DataIdentityPolicy.UNAVAILABLE: IdentityStrength.UNVERIFIED,
            }[self.data_identity.policy]
        )
        if self.identity_strength is not expected_strength:
            raise ValueError("identityStrength does not match workload identity evidence policy")
        material = self.model_dump(mode="json", by_alias=True)
        material.pop("workloadId", None)
        material.pop("createdAt", None)
        if not self.identity_conflict:
            material.pop("identityConflict", None)
        if self.workload_id != digest_json(material):
            raise ValueError("workloadId does not match canonical workload identity material")
        return self


class GpuIdentity(ProductModel):
    model: str | None = None
    count: int = Field(default=0, ge=0, le=131072)
    firmware_digest: Digest | None = None


class EnvironmentIdentity(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    environment_id: Digest
    identity_strength: IdentityStrength
    identity_conflict: bool = False
    identity_policy: DataIdentityPolicy
    identity_evidence_digest: Digest | None = None
    host_kernel: str = Field(min_length=1)
    container_runtime: str | None = None
    python: str = Field(min_length=1)
    packages_digest: Digest
    pytorch: str = Field(min_length=1)
    cuda_runtime: str | None = None
    cuda_driver: str | None = None
    nccl: str | None = None
    gpu: GpuIdentity
    topology_digest: Digest | None = None
    scheduler: str | None = None
    launcher: str | None = None
    network_class: str | None = None
    storage_class: str | None = None
    environment_variables_digest: Digest
    redaction_policy_version: str = Field(min_length=1)
    materialization_recipe_digest: Digest | None = None
    materialization_recipe_artifact_id: Digest | None = None
    created_at: datetime

    @model_validator(mode="after")
    def evidence_matches_identity_policy(self) -> EnvironmentIdentity:
        if self.identity_policy in {
            DataIdentityPolicy.FULL_DIGEST,
            DataIdentityPolicy.MANIFEST_DIGEST,
        }:
            if self.identity_evidence_digest is None:
                raise ValueError("verified environment identity requires identityEvidenceDigest")
        elif self.identity_evidence_digest is not None:
            raise ValueError("attested/unavailable environment identity cannot carry evidence")
        if (self.materialization_recipe_digest is None) != (
            self.materialization_recipe_artifact_id is None
        ):
            raise ValueError(
                "materialization recipe digest and artifact identity must be declared together"
            )
        expected_strength = (
            IdentityStrength.CONFLICTING
            if self.identity_conflict
            else {
                DataIdentityPolicy.FULL_DIGEST: IdentityStrength.FULLY_VERIFIED,
                DataIdentityPolicy.MANIFEST_DIGEST: IdentityStrength.PARTIALLY_VERIFIED,
                DataIdentityPolicy.CUSTOMER_ATTESTED: IdentityStrength.CUSTOMER_ATTESTED,
                DataIdentityPolicy.UNAVAILABLE: IdentityStrength.UNVERIFIED,
            }[self.identity_policy]
        )
        if self.identity_strength is not expected_strength:
            raise ValueError("identityStrength does not match environment identity evidence policy")
        material = self.model_dump(mode="json", by_alias=True)
        material.pop("environmentId", None)
        material.pop("createdAt", None)
        if not self.identity_conflict:
            material.pop("identityConflict", None)
        if self.environment_id != digest_json(material):
            raise ValueError("environmentId does not match canonical environment identity material")
        return self


class EvidenceArtifact(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    artifact_id: Digest
    case_id: Identifier
    workload_id: Digest | None = None
    baseline_environment_id: Digest | None = None
    candidate_environment_id: Digest | None = None
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
    metadata_digest: Digest

    @model_validator(mode="after")
    def content_address_is_identity(self) -> EvidenceArtifact:
        if self.artifact_id != self.content_digest:
            raise ValueError("artifactId must equal the raw content digest")
        digest_hex = self.content_digest.removeprefix("sha256:")
        expected_uri = f"cas://{self.case_id}/sha256/{digest_hex}"
        if self.customer_local_uri != expected_uri:
            raise ValueError("customerLocalUri must be the case-bound URI for contentDigest")
        material = self.model_dump(mode="json", by_alias=True)
        material.pop("metadataDigest", None)
        if self.metadata_digest != digest_json(material):
            raise ValueError("metadataDigest does not authenticate artifact metadata")
        return self


class NativeFinding(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    finding_id: Digest
    attribution: FindingAttribution
    native_system: str = Field(min_length=1)
    native_version: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    evidence_refs: list[Digest] = Field(min_length=1)
    confidence_class: NativeConfidence
    limitations: list[str] = Field(min_length=1)
    customer_decision_contribution: str = Field(min_length=1)

    @model_validator(mode="after")
    def finding_id_authenticates_the_entire_finding(self) -> NativeFinding:
        material = self.model_dump(mode="json", by_alias=True)
        material.pop("findingId", None)
        if self.finding_id != digest_json(material):
            raise ValueError("findingId does not authenticate the native finding")
        return self


class ExperimentEconomics(ProductModel):
    estimated_cost: float | None = Field(default=None, ge=0)
    estimated_duration_seconds: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    basis: str = Field(min_length=1)

    @model_validator(mode="after")
    def currency_for_known_cost(self) -> ExperimentEconomics:
        if self.estimated_cost is not None and self.currency is None:
            raise ValueError("known cost requires an ISO currency")
        return self


class MachineVerification(ProductModel):
    policy: PolicyName
    outcome: VerificationOutcome
    verifier: Literal["traincapsule-deterministic-policy"] = "traincapsule-deterministic-policy"
    verifier_version: Literal["1"] = "1"
    subject_digest: Digest
    reason: str = Field(min_length=1)


class CaseEconomics(ProductModel):
    estimated_original_run_cost: float | None = Field(default=None, ge=0)
    estimated_investigation_cost: float | None = Field(default=None, ge=0)
    estimated_delay_cost: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")


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
    role: EvidenceRole
    claim_names: list[str] = []
    substitutable_by: list[str] = []
    state: CompletenessState
    artifact_refs: list[Digest]
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def references_match_state(self) -> EvidenceRequirement:
        present = {
            CompletenessState.PRESENT_VALID,
            CompletenessState.PRESENT_PARTIAL,
            CompletenessState.PRESENT_CONFLICTING,
            CompletenessState.PRESENT_CORRUPTED,
        }
        if self.state in present and not self.artifact_refs:
            raise ValueError("present evidence requires at least one artifactRef")
        if self.state not in present and self.artifact_refs:
            raise ValueError("missing/not-applicable evidence cannot carry artifactRefs")
        if self.role is EvidenceRole.MANDATORY_FOR_CLAIM and not self.claim_names:
            raise ValueError("claim-mandatory evidence requires claimNames")
        if self.role is EvidenceRole.SUBSTITUTABLE and not self.substitutable_by:
            raise ValueError("substitutable evidence requires substitutableBy")
        return self


class EvidenceCompletenessReport(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    requirements: list[EvidenceRequirement] = Field(min_length=1)
    technical_result: TechnicalResult

    @model_validator(mode="after")
    def result_matches_requirements(self) -> EvidenceCompletenessReport:
        valid = {CompletenessState.PRESENT_VALID, CompletenessState.NOT_APPLICABLE}
        by_kind = {requirement.kind: requirement for requirement in self.requirements}
        blocking = [
            requirement
            for requirement in self.requirements
            if requirement.role is EvidenceRole.MANDATORY_FOR_ELIGIBILITY
        ]
        blocking.extend(
            requirement
            for requirement in self.requirements
            if requirement.role is EvidenceRole.SUBSTITUTABLE
            and requirement.state is not CompletenessState.PRESENT_VALID
            and not any(
                name in by_kind and by_kind[name].state is CompletenessState.PRESENT_VALID
                for name in requirement.substitutable_by
            )
        )
        invalid = {
            CompletenessState.PRESENT_CORRUPTED,
            CompletenessState.PRESENT_CONFLICTING,
        }
        expected = (
            TechnicalResult.INVALID_EVIDENCE
            if any(r.state in invalid for r in blocking)
            else TechnicalResult.PASS
            if all(r.state in valid for r in blocking)
            else TechnicalResult.UNKNOWN
        )
        if self.technical_result is not expected:
            raise ValueError("technicalResult does not match classified evidence requirements")
        return self


class EligibilityDecision(ProductModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    case_id: Identifier
    input_digest: Digest
    workload_id: Digest
    baseline_environment_id: Digest
    candidate_environment_id: Digest
    evidence_refs: list[Digest] = Field(min_length=1)
    native_baseline_digest: Digest
    policy_verifications: list[MachineVerification] = Field(min_length=1)
    original_experiment_economics: ExperimentEconomics
    proposed_experiment_economics: ExperimentEconomics
    outcome: EligibilityOutcome
    identity_strength: IdentityStrength
    technical_result: TechnicalResult
    operational_decision: OperationalDecision
    reasons: list[str] = Field(min_length=1)
    unknowns: list[str]
    generated_at: datetime

    @model_validator(mode="after")
    def weak_identity_cannot_approve(self) -> EligibilityDecision:
        if self.identity_strength is not IdentityStrength.FULLY_VERIFIED and (
            self.operational_decision is OperationalDecision.APPROVE_WITHIN_ENVELOPE
        ):
            raise ValueError("only FULLY_VERIFIED identity can approve within the envelope")
        return self


def safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("identifier contains unsafe characters")
    return value
