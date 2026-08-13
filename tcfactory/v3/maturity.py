"""Independent engineering and commercial maturity rules."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import CommercialMaturity, EngineeringMaturity, EvidenceType


class MaturityTarget(V3Model):
    engineering: EngineeringMaturity
    commercial: CommercialMaturity


class MaturityState(V3Model):
    engineering: EngineeringMaturity = EngineeringMaturity.DESIGN_ONLY
    commercial: CommercialMaturity = CommercialMaturity.NOT_EVALUATED
    engineering_evidence: list[str] = Field(default_factory=list[str])
    external_evidence_refs: list[str] = Field(default_factory=list[str])


def commercial_maturity_supported(
    maturity: CommercialMaturity,
    trusted_evidence_types: Iterable[EvidenceType],
) -> bool:
    """Return whether attributable evidence can support the claimed state."""

    evidence = set(trusted_evidence_types)
    if maturity in {
        CommercialMaturity.NOT_EVALUATED,
        CommercialMaturity.NATIVE_ADVANTAGE_UNPROVEN,
        CommercialMaturity.WITHDRAWN,
    }:
        return True
    if maturity is CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED:
        return bool(evidence)
    # Payment, authorization, scheduling, and engagement are attributable facts,
    # but none proves that the product changed or strengthened a decision.
    value_types = {EvidenceType.DECISION_CHANGED}
    if maturity is CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED:
        return bool(evidence & value_types)
    if maturity is CommercialMaturity.COMMERCIALLY_SUPPORTED:
        return EvidenceType.SECOND_PAID_ACTION in evidence and bool(evidence & value_types)
    return False
