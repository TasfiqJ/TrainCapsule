"""Independent engineering and commercial maturity rules."""

from __future__ import annotations

from pydantic import Field

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import CommercialMaturity, EngineeringMaturity, EvidenceType

from .completion_policy import SemanticEvidence


class MaturityTarget(V3Model):
    engineering: EngineeringMaturity
    commercial: CommercialMaturity


class MaturityState(V3Model):
    engineering: EngineeringMaturity = EngineeringMaturity.DESIGN_ONLY
    commercial: CommercialMaturity = CommercialMaturity.NOT_EVALUATED
    engineering_evidence: list[str] = Field(default_factory=list[str])
    external_evidence_refs: list[str] = Field(default_factory=list[str])


class CommercialMaturityAuthorization(V3Model):
    """Controller-derived typed authorization; receipt type strings are insufficient."""

    external_evidence_types: list[EvidenceType] = Field(default_factory=list[EvidenceType])
    semantic_evidence: list[SemanticEvidence] = Field(default_factory=list[SemanticEvidence])
    exact_identity_correlation_verified: bool = False


def commercial_maturity_supported(
    maturity: CommercialMaturity,
    authorization: CommercialMaturityAuthorization,
) -> bool:
    """Return whether attributable evidence can support the claimed state."""

    evidence = set(authorization.external_evidence_types)
    semantics = set(authorization.semantic_evidence)
    if maturity in {
        CommercialMaturity.NOT_EVALUATED,
        CommercialMaturity.NATIVE_ADVANTAGE_UNPROVEN,
        CommercialMaturity.WITHDRAWN,
    }:
        return True
    if maturity is CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED:
        return SemanticEvidence.NATIVE_VALUE_AUTHORIZATION in semantics
    # Payment, authorization, scheduling, and engagement are attributable facts,
    # but none proves that the product changed or strengthened a decision.
    value_types = {EvidenceType.DECISION_CHANGED}
    if maturity is CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED:
        return (
            bool(evidence & value_types)
            and authorization.exact_identity_correlation_verified
            and SemanticEvidence.CUSTOMER_DECISION_CHANGED in semantics
            and SemanticEvidence.CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT in semantics
        )
    if maturity is CommercialMaturity.COMMERCIALLY_SUPPORTED:
        return (
            authorization.exact_identity_correlation_verified
            and EvidenceType.SECOND_PAID_ACTION in evidence
            and EvidenceType.DECISION_CHANGED in evidence
            and EvidenceType.SUPPORT_ACCEPTANCE in evidence
            and EvidenceType.SAME_FAMILY_CASE in evidence
            and {
                SemanticEvidence.NATIVE_VALUE_AUTHORIZATION,
                SemanticEvidence.SUPPORT_POLICY,
                SemanticEvidence.THIRD_SAME_FAMILY_CASE,
                SemanticEvidence.DELIVERY_ECONOMICS,
            }.issubset(semantics)
        )
    return False
