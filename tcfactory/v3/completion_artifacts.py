"""Strict controller-consumed artifacts for commercial evidence semantics.

These records are declared outputs, validated byte-for-byte, copied into the
controller artifact root, and independently reviewed where their work-item risk
requires it.  Narrative task output never creates completion semantics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple

from pydantic import Field, model_validator

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model


class SupportPolicyEvidence(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    work_item_id: Literal["V3-PROD-029"]
    evidence_basis_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    pack_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    pack_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    supported_versions: list[str] = Field(min_length=1, max_length=64)
    supported_scope: list[str] = Field(min_length=1, max_length=64)
    upgrade_rules: list[str] = Field(min_length=1, max_length=64)
    deprecation_rules: list[str] = Field(min_length=1, max_length=64)
    rollback_rules: list[str] = Field(min_length=1, max_length=64)
    explicit_exclusions: list[str] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_policy_rosters(self) -> SupportPolicyEvidence:
        for label, values in (
            ("versions", self.supported_versions),
            ("scope", self.supported_scope),
            ("upgrade rules", self.upgrade_rules),
            ("deprecation rules", self.deprecation_rules),
            ("rollback rules", self.rollback_rules),
            ("exclusions", self.explicit_exclusions),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"support-policy {label} must be unique")
        return self


class DeliveryEconomicsEvidence(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    work_item_id: Literal["V3-REPEAT-006"]
    evidence_basis_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_record_digests: list[str] = Field(min_length=2, max_length=2)
    signed_external_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    customer_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    offer_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    original_setup_minutes: int = Field(gt=0, le=1_000_000)
    proposed_setup_minutes: int = Field(ge=0, le=1_000_000)
    original_delivery_minutes: int = Field(gt=0, le=1_000_000)
    proposed_delivery_minutes: int = Field(ge=0, le=1_000_000)
    original_cost_microusd: int = Field(gt=0, le=10**15)
    proposed_cost_microusd: int = Field(ge=0, le=10**15)
    original_margin_basis_points: int = Field(ge=-10_000, le=10_000)
    proposed_margin_basis_points: int = Field(ge=-10_000, le=10_000)

    @model_validator(mode="after")
    def measured_improvement(self) -> DeliveryEconomicsEvidence:
        if len(set(self.source_record_digests)) != 2:
            raise ValueError("delivery-economics source records must be unique")
        if not (
            self.proposed_setup_minutes < self.original_setup_minutes
            and self.proposed_delivery_minutes < self.original_delivery_minutes
            and self.proposed_cost_microusd < self.original_cost_microusd
            and self.proposed_margin_basis_points > self.original_margin_basis_points
        ):
            raise ValueError("delivery economics must demonstrate measured improvement")
        return self


class ThirdSameFamilyCaseEvidence(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    work_item_id: Literal["V3-PACK-002"]
    evidence_basis_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    customer_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    family_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    case_identity_digests: list[str] = Field(min_length=3, max_length=3)
    case_evidence_artifact_digests: list[str] = Field(min_length=3, max_length=3)
    trust_core_before_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    trust_core_after_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    reusable_pack_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @model_validator(mode="after")
    def exact_three_without_core_rewrite(self) -> ThirdSameFamilyCaseEvidence:
        if len(set(self.case_identity_digests)) != 3:
            raise ValueError("third same-family evidence requires three unique cases")
        if len(set(self.case_evidence_artifact_digests)) != 3:
            raise ValueError("third same-family evidence requires three unique artifacts")
        if self.trust_core_before_digest != self.trust_core_after_digest:
            raise ValueError("third same-family evidence cannot include a trust-core rewrite")
        return self


class ReductionBoundaryEvidence(V3Model):
    """Independent-oracle evidence for one legal and one illegal reduction."""

    schema_version: Literal["3.1"] = "3.1"
    work_item_id: Literal["V3-TRUST-005"]
    evidence_basis_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    oracle_executable_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    oracle_result_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    raw_artifact_digests: list[str] = Field(min_length=2, max_length=64)
    legal_reduction_artifact_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    legal_reduction_verdict: Literal["VERIFIED"]
    illegal_reduction_artifact_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    illegal_reduction_verdict: Literal["REJECTED"]

    @model_validator(mode="after")
    def exact_independent_boundary(self) -> ReductionBoundaryEvidence:
        if len(self.raw_artifact_digests) != len(set(self.raw_artifact_digests)):
            raise ValueError("reduction-boundary raw artifacts must be unique")
        if self.legal_reduction_artifact_digest == self.illegal_reduction_artifact_digest:
            raise ValueError("legal and illegal reductions require different artifacts")
        if not {
            self.legal_reduction_artifact_digest,
            self.illegal_reduction_artifact_digest,
        }.issubset(self.raw_artifact_digests):
            raise ValueError("legal and illegal reduction inputs must be present in the raw roster")
        return self


class FrozenReleaseEvidenceAuthorization(V3Model):
    """Post-manifest envelope that avoids a receipt/manifest digest cycle."""

    schema_version: Literal["3.1"] = "3.1"
    authorization_id: str = Field(pattern=r"^FREA-V3-COMP-005-[0-9A-F]{12}$")
    work_item_id: Literal["V3-COMP-005"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    native_value_authorization_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    machine_policy_receipt_id: str = Field(min_length=1, max_length=256)
    machine_policy_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    traincheck_result_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    traincheck_receipt_file_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    frozen_artifact_digests: dict[str, str] = Field(min_length=7, max_length=32)
    authorized_at: datetime

    @model_validator(mode="after")
    def exact_frozen_roster(self) -> FrozenReleaseEvidenceAuthorization:
        required = {
            "request",
            "tool",
            "incident-contract",
            "baseline-observation",
            "candidate-observation",
            "result",
            "machine-policy-receipt",
        }
        if set(self.frozen_artifact_digests) != required:
            raise ValueError("release evidence authorization has an inexact frozen roster")
        if (
            self.frozen_artifact_digests["result"] != self.traincheck_result_digest
            or self.frozen_artifact_digests["machine-policy-receipt"]
            != self.traincheck_receipt_file_digest
        ):
            raise ValueError("release evidence authorization digest bindings disagree")
        return self


class SemanticOutputSpec(NamedTuple):
    output_id: str
    relative_path: str
    schema_id: str
    model: type[V3Model]
    semantic_names: tuple[str, ...]


SEMANTIC_OUTPUT_SPECS: dict[str, SemanticOutputSpec] = {
    "V3-PROD-029": SemanticOutputSpec(
        "OUT:V3:PROD:029:SUPPORT_POLICY",
        "docs/evidence/product/v3-prod-029/support-policy.json",
        "traincapsule.v3.1.support-policy-evidence",
        SupportPolicyEvidence,
        ("SUPPORT_POLICY",),
    ),
    "V3-REPEAT-006": SemanticOutputSpec(
        "OUT:V3:REPEAT:006:DELIVERY_ECONOMICS",
        "docs/market/v3-repeat-006/delivery-economics.json",
        "traincapsule.v3.1.delivery-economics-evidence",
        DeliveryEconomicsEvidence,
        ("DELIVERY_ECONOMICS",),
    ),
    "V3-PACK-002": SemanticOutputSpec(
        "OUT:V3:PACK:002:THIRD_SAME_FAMILY_CASE",
        "docs/evidence/product/v3-pack-002/third-same-family-case.json",
        "traincapsule.v3.1.third-same-family-case-evidence",
        ThirdSameFamilyCaseEvidence,
        ("THIRD_SAME_FAMILY_CASE",),
    ),
    "V3-TRUST-005": SemanticOutputSpec(
        "OUT:V3:TRUST:005:REDUCTION_BOUNDARY",
        "docs/evidence/trust/v3-trust-005/reduction-boundary.json",
        "traincapsule.v3.1.reduction-boundary-evidence",
        ReductionBoundaryEvidence,
        ("LEGAL_REDUCTION_VERIFIED", "ILLEGAL_REDUCTION_REJECTED"),
    ),
}


__all__ = [
    "DeliveryEconomicsEvidence",
    "FrozenReleaseEvidenceAuthorization",
    "ReductionBoundaryEvidence",
    "SEMANTIC_OUTPUT_SPECS",
    "SemanticOutputSpec",
    "SupportPolicyEvidence",
    "ThirdSameFamilyCaseEvidence",
]
