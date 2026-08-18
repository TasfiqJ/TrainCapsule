"""Independent engineering and commercial maturity rules."""

from __future__ import annotations

import json

from pydantic import Field, model_validator

from tcfactory.v3.base import DIGEST_PATTERN, V3Model, sha256_digest
from tcfactory.v3.enums import CommercialMaturity, EngineeringMaturity, EvidenceType

from .completion_policy import CorrelatedEvidenceFact, SemanticEvidence


class MaturityTarget(V3Model):
    engineering: EngineeringMaturity
    commercial: CommercialMaturity


class MaturityState(V3Model):
    engineering: EngineeringMaturity = EngineeringMaturity.DESIGN_ONLY
    commercial: CommercialMaturity = CommercialMaturity.NOT_EVALUATED
    engineering_evidence: list[str] = Field(default_factory=list[str])
    external_evidence_refs: list[str] = Field(default_factory=list[str])


def _authorization_digest(
    lineage: str,
    facts: list[CorrelatedEvidenceFact],
    receipts: list[str],
) -> str:
    payload = {
        "productLineageDigest": lineage,
        "correlatedFacts": [
            fact.model_dump(mode="json", by_alias=True) for fact in facts
        ],
        "verifiedReceiptDigests": receipts,
    }
    return sha256_digest(
        (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )


def _fact_key(fact: CorrelatedEvidenceFact) -> tuple[str, str, str, str]:
    return (
        fact.source_work_item_id,
        fact.evidence_digest,
        fact.semantic.value if fact.semantic is not None else "",
        fact.external_evidence_type.value if fact.external_evidence_type is not None else "",
    )


class CommercialMaturityAuthorization(V3Model):
    """Canonical controller-derived facts backed by verified signed receipts."""

    product_lineage_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    correlated_facts: list[CorrelatedEvidenceFact] = Field(min_length=1, max_length=256)
    verified_receipt_digests: list[str] = Field(min_length=1, max_length=256)
    authorization_digest: str = Field(pattern=DIGEST_PATTERN.pattern)

    @model_validator(mode="after")
    def derived_not_asserted(self) -> CommercialMaturityAuthorization:
        if self.correlated_facts != sorted(self.correlated_facts, key=_fact_key):
            raise ValueError("commercial facts are not in canonical order")
        if self.verified_receipt_digests != sorted(set(self.verified_receipt_digests)):
            raise ValueError("verified commercial receipt roster is not canonical")
        keys = [_fact_key(fact) for fact in self.correlated_facts]
        if len(keys) != len(set(keys)):
            raise ValueError("commercial fact roster contains duplicates")
        trusted = set(self.verified_receipt_digests)
        for fact in self.correlated_facts:
            if fact.product_lineage_digest != self.product_lineage_digest:
                raise ValueError("commercial facts mix product lineages")
            if fact.authority_receipt_digest not in trusted:
                raise ValueError("commercial fact is not backed by a verified receipt")
            if fact.external_evidence_type is not None and (
                fact.evidence_digest != fact.authority_receipt_digest
            ):
                raise ValueError("external fact digest differs from its signed receipt")
        if self.authorization_digest != _authorization_digest(
            self.product_lineage_digest,
            self.correlated_facts,
            self.verified_receipt_digests,
        ):
            raise ValueError("commercial authorization digest is caller-authored or stale")
        return self


def derive_commercial_maturity_authorization(
    facts: list[CorrelatedEvidenceFact],
    verified_receipt_digests: list[str],
) -> CommercialMaturityAuthorization:
    """Derive an immutable authorization; callers cannot supply a correlation verdict."""

    lineages = {fact.product_lineage_digest for fact in facts}
    if len(lineages) != 1:
        raise ValueError("commercial facts do not share one stable product lineage")
    ordered = sorted(facts, key=_fact_key)
    receipts = sorted(set(verified_receipt_digests))
    lineage = next(iter(lineages))
    return CommercialMaturityAuthorization(
        product_lineage_digest=lineage,
        correlated_facts=ordered,
        verified_receipt_digests=receipts,
        authorization_digest=_authorization_digest(lineage, ordered, receipts),
    )


def _semantic(
    authorization: CommercialMaturityAuthorization, semantic: SemanticEvidence
) -> list[CorrelatedEvidenceFact]:
    return [fact for fact in authorization.correlated_facts if fact.semantic is semantic]


def _external(
    authorization: CommercialMaturityAuthorization, evidence_type: EvidenceType
) -> list[CorrelatedEvidenceFact]:
    return [
        fact
        for fact in authorization.correlated_facts
        if fact.external_evidence_type is evidence_type
    ]


def _correlated(
    groups: list[list[CorrelatedEvidenceFact]], fields: tuple[str, ...]
) -> bool:
    if any(not group for group in groups):
        return False
    for anchor in groups[0]:
        identity = tuple(getattr(anchor, field) for field in fields)
        if any(value is None for value in identity):
            continue
        if all(
            any(tuple(getattr(fact, field) for field in fields) == identity for fact in group)
            for group in groups[1:]
        ):
            return True
    return False


def commercial_maturity_supported(
    maturity: CommercialMaturity,
    authorization: CommercialMaturityAuthorization | None,
) -> bool:
    """Return whether one exact signed lineage supports the claimed state."""

    if maturity in {
        CommercialMaturity.NOT_EVALUATED,
        CommercialMaturity.NATIVE_ADVANTAGE_UNPROVEN,
        CommercialMaturity.WITHDRAWN,
    }:
        return True
    if authorization is None:
        return False
    try:
        authorization = CommercialMaturityAuthorization.model_validate(
            authorization.model_dump(mode="python")
        )
    except ValueError:
        return False
    native = _semantic(authorization, SemanticEvidence.NATIVE_VALUE_AUTHORIZATION)
    if maturity is CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED:
        return bool(native)
    decision = _external(authorization, EvidenceType.DECISION_CHANGED)
    changed = _semantic(authorization, SemanticEvidence.CUSTOMER_DECISION_CHANGED)
    valuable = _semantic(
        authorization, SemanticEvidence.CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT
    )
    value_supported = _correlated(
        [decision, changed, valuable],
        ("product_lineage_digest", "customer_identity_digest", "offer_identity_digest"),
    ) and _correlated([decision, native], ("product_lineage_digest",))
    if maturity is CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED:
        return value_supported
    if maturity is CommercialMaturity.COMMERCIALLY_SUPPORTED:
        repeat = _external(authorization, EvidenceType.SECOND_PAID_ACTION)
        economics = _semantic(authorization, SemanticEvidence.DELIVERY_ECONOMICS)
        same_family = _external(authorization, EvidenceType.SAME_FAMILY_CASE)
        third_case = _semantic(authorization, SemanticEvidence.THIRD_SAME_FAMILY_CASE)
        support = _external(authorization, EvidenceType.SUPPORT_ACCEPTANCE)
        support_policy = _semantic(authorization, SemanticEvidence.SUPPORT_POLICY)
        return (
            value_supported
            and _correlated(
                [decision, repeat, economics],
                (
                    "product_lineage_digest",
                    "customer_identity_digest",
                    "offer_identity_digest",
                ),
            )
            and _correlated(
                [decision, repeat, same_family, third_case],
                ("product_lineage_digest", "customer_identity_digest"),
            )
            and _correlated(
                [same_family, third_case, support, support_policy],
                (
                    "product_lineage_digest",
                    "family_identity_digest",
                    "pack_identity_digest",
                ),
            )
        )
    return False


__all__ = [
    "CommercialMaturityAuthorization",
    "MaturityState",
    "MaturityTarget",
    "commercial_maturity_supported",
    "derive_commercial_maturity_authorization",
]
