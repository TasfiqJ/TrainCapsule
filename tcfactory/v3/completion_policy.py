"""Typed, generated evidence policy for every active V3.1 work item and milestone.

Roadmap prose is an authoring input only.  The controller consumes this checked-in
roster, whose source digest binds the exact roadmap and milestone bytes.  This
prevents words such as "signed", "paid", or "independent" from being interpreted
ad hoc at a release or completion boundary.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from tcfactory.util import sha256_file
from tcfactory.v3.base import DIGEST_PATTERN, V3Model
from tcfactory.v3.enums import EvidenceType
from tcfactory.yamlutil import load_yaml


class EvidenceAuthority(StrEnum):
    CONTROLLER = "CONTROLLER"
    INDEPENDENT_REVIEWER = "INDEPENDENT_REVIEWER"
    INDEPENDENT_MACHINE_POLICY = "INDEPENDENT_MACHINE_POLICY"
    TRUSTED_EXTERNAL = "TRUSTED_EXTERNAL"
    LIVE_GPU_RUNNER = "LIVE_GPU_RUNNER"


class SemanticEvidence(StrEnum):
    DETERMINISTIC_ARTIFACT = "DETERMINISTIC_ARTIFACT"
    CANDIDATE_MANIFEST = "CANDIDATE_MANIFEST"
    INDEPENDENT_REVIEW = "INDEPENDENT_REVIEW"
    MACHINE_POLICY_DECISION = "MACHINE_POLICY_DECISION"
    NATIVE_VALUE_AUTHORIZATION = "NATIVE_VALUE_AUTHORIZATION"
    REACHABLE_ACCOUNT = "REACHABLE_ACCOUNT"
    ATTRIBUTABLE_SOURCE = "ATTRIBUTABLE_SOURCE"
    TRAINCHECK_INCIDENT_DIFFERENTIAL = "TRAINCHECK_INCIDENT_DIFFERENTIAL"
    SUPPORT_POLICY = "SUPPORT_POLICY"
    DELIVERY_ECONOMICS = "DELIVERY_ECONOMICS"
    THIRD_SAME_FAMILY_CASE = "THIRD_SAME_FAMILY_CASE"
    LEGAL_REDUCTION_VERIFIED = "LEGAL_REDUCTION_VERIFIED"
    ILLEGAL_REDUCTION_REJECTED = "ILLEGAL_REDUCTION_REJECTED"
    CUSTOMER_DECISION_CHANGED = "CUSTOMER_DECISION_CHANGED"
    CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT = "CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT"


class EvidenceGrade(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    CONTROLLED = "CONTROLLED"
    LIVE = "LIVE"
    EXTERNAL = "EXTERNAL"


class CorrelationField(StrEnum):
    CANDIDATE = "CANDIDATE"
    CUSTOMER = "CUSTOMER"
    FAMILY = "FAMILY"
    OFFER = "OFFER"
    PACK = "PACK"


class CorrelatedEvidenceFact(V3Model):
    """One controller-verified fact and the identities to which it applies."""

    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    customer_identity_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    family_identity_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    offer_identity_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    pack_identity_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    semantic: SemanticEvidence | None = None
    external_evidence_type: EvidenceType | None = None

    @model_validator(mode="after")
    def exactly_one_fact(self) -> CorrelatedEvidenceFact:
        if (self.semantic is None) == (self.external_evidence_type is None):
            raise ValueError("correlated evidence must carry exactly one typed fact")
        return self

    def identity(self, field: CorrelationField) -> str | None:
        return {
            CorrelationField.CANDIDATE: self.candidate_sha,
            CorrelationField.CUSTOMER: self.customer_identity_digest,
            CorrelationField.FAMILY: self.family_identity_digest,
            CorrelationField.OFFER: self.offer_identity_digest,
            CorrelationField.PACK: self.pack_identity_digest,
        }[field]


class MilestoneExitCriterionContract(V3Model):
    """One exact source-authority exit criterion and its typed evidence closure."""

    criterion_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+-EXIT-[0-9]{2}$")
    criterion_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    required_work_item_ids: list[str] = Field(min_length=1)
    required_external_evidence_types: list[EvidenceType] = Field(default_factory=list[EvidenceType])
    required_semantic_counts: dict[SemanticEvidence, int] = Field(
        default_factory=dict[SemanticEvidence, int]
    )
    machine_policy_required: bool
    required_correlation_fields: list[CorrelationField] = Field(
        default_factory=list[CorrelationField]
    )

    @model_validator(mode="after")
    def exact_roster(self) -> MilestoneExitCriterionContract:
        if len(self.required_work_item_ids) != len(set(self.required_work_item_ids)):
            raise ValueError("exit-criterion work-item IDs must be unique")
        if len(self.required_external_evidence_types) != len(
            set(self.required_external_evidence_types)
        ):
            raise ValueError("exit-criterion external evidence types must be unique")
        return self


class WorkItemEvidenceContract(V3Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    roadmap_evidence_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    minimum_grade: EvidenceGrade
    required_authorities: list[EvidenceAuthority] = Field(min_length=1)
    required_semantics: list[SemanticEvidence] = Field(min_length=1)
    allowed_external_evidence_types: list[EvidenceType] = Field(default_factory=list[EvidenceType])
    minimum_external_artifacts: int = Field(default=0, ge=0, le=10_000)
    minimum_semantic_counts: dict[SemanticEvidence, int] = Field(
        default_factory=dict[SemanticEvidence, int]
    )
    required_prior_evidence: dict[str, list[SemanticEvidence]] = Field(
        default_factory=dict[str, list[SemanticEvidence]]
    )

    @model_validator(mode="after")
    def exact_requirements(self) -> WorkItemEvidenceContract:
        if len(self.required_authorities) != len(set(self.required_authorities)):
            raise ValueError("work-item evidence authorities must be unique")
        if len(self.required_semantics) != len(set(self.required_semantics)):
            raise ValueError("work-item semantic evidence must be unique")
        if len(self.allowed_external_evidence_types) != len(
            set(self.allowed_external_evidence_types)
        ):
            raise ValueError("allowed external evidence types must be unique")
        if EvidenceAuthority.TRUSTED_EXTERNAL in self.required_authorities and not (
            self.allowed_external_evidence_types
        ):
            raise ValueError("trusted-external authority requires exact evidence types")
        if self.minimum_external_artifacts and not self.allowed_external_evidence_types:
            raise ValueError("external artifact minimum requires exact evidence types")
        for work_item_id, semantics in self.required_prior_evidence.items():
            if work_item_id == self.work_item_id or not semantics:
                raise ValueError("prior evidence dependency is empty or self-referential")
            if len(semantics) != len(set(semantics)):
                raise ValueError("prior evidence dependency semantics must be unique")
        return self


class MilestoneEvidenceContract(V3Model):
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    roadmap_evidence_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    required_external_evidence_types: list[EvidenceType] = Field(default_factory=list[EvidenceType])
    required_semantic_counts: dict[SemanticEvidence, int] = Field(
        default_factory=dict[SemanticEvidence, int]
    )
    machine_policy_required: bool
    allow_unrelated_future_lanes_while_external_wait: list[str] = Field(default_factory=list[str])
    exit_criteria: list[MilestoneExitCriterionContract] = Field(min_length=1)


class CompletionEvidencePolicy(V3Model):
    schema_version: str = Field(default="3.1", pattern=r"^3\.1$")
    work_items_sha256: str = Field(pattern=DIGEST_PATTERN.pattern)
    milestones_sha256: str = Field(pattern=DIGEST_PATTERN.pattern)
    work_items: list[WorkItemEvidenceContract] = Field(min_length=1)
    milestones: list[MilestoneEvidenceContract] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_roster(self) -> CompletionEvidencePolicy:
        item_ids = [item.work_item_id for item in self.work_items]
        milestone_ids = [item.milestone_id for item in self.milestones]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("completion work-item contracts must be unique")
        if len(milestone_ids) != len(set(milestone_ids)):
            raise ValueError("completion milestone contracts must be unique")
        return self

    def work_item(self, work_item_id: str) -> WorkItemEvidenceContract:
        matches = [item for item in self.work_items if item.work_item_id == work_item_id]
        if len(matches) != 1:
            raise ValueError(f"work item has no unique evidence contract: {work_item_id}")
        return matches[0]

    def milestone(self, milestone_id: str) -> MilestoneEvidenceContract:
        matches = [item for item in self.milestones if item.milestone_id == milestone_id]
        if len(matches) != 1:
            raise ValueError(f"milestone has no unique evidence contract: {milestone_id}")
        return matches[0]


class CompletionEvidenceObservation(V3Model):
    """Controller-derived evidence facts; candidate text cannot populate this record."""

    grade: EvidenceGrade
    authorities: list[EvidenceAuthority] = Field(min_length=1)
    semantic_counts: dict[SemanticEvidence, int] = Field(
        default_factory=dict[SemanticEvidence, int]
    )
    external_type_counts: dict[EvidenceType, int] = Field(default_factory=dict[EvidenceType, int])
    prior_evidence: dict[str, list[SemanticEvidence]] = Field(
        default_factory=dict[str, list[SemanticEvidence]]
    )


def evaluate_work_item_evidence_contract(
    contract: WorkItemEvidenceContract,
    observation: CompletionEvidenceObservation,
) -> list[str]:
    """Return exact, stable failures for one reviewed work-item contract."""

    failures: list[str] = []
    grade_rank = {
        EvidenceGrade.DETERMINISTIC: 0,
        EvidenceGrade.CONTROLLED: 1,
        EvidenceGrade.LIVE: 2,
        EvidenceGrade.EXTERNAL: 3,
    }
    if grade_rank[observation.grade] < grade_rank[contract.minimum_grade]:
        failures.append(
            f"{contract.work_item_id} evidence grade {observation.grade.value} "
            f"is below {contract.minimum_grade.value}"
        )
    observed_authorities = set(observation.authorities)
    for authority in contract.required_authorities:
        if authority not in observed_authorities:
            failures.append(f"{contract.work_item_id} lacks {authority.value} authority")
    for semantic in contract.required_semantics:
        minimum = max(1, contract.minimum_semantic_counts.get(semantic, 0))
        if observation.semantic_counts.get(semantic, 0) < minimum:
            failures.append(f"{contract.work_item_id} lacks {minimum} {semantic.value} evidence")
    if contract.allowed_external_evidence_types:
        observed_external = sum(
            observation.external_type_counts.get(evidence_type, 0)
            for evidence_type in contract.allowed_external_evidence_types
        )
        if observed_external < contract.minimum_external_artifacts:
            failures.append(
                f"{contract.work_item_id} lacks {contract.minimum_external_artifacts} "
                "typed external artifacts"
            )
        disallowed = set(observation.external_type_counts) - set(
            contract.allowed_external_evidence_types
        )
        if disallowed:
            failures.append(
                f"{contract.work_item_id} carries unrelated external evidence: "
                f"{sorted(value.value for value in disallowed)}"
            )
    for work_item_id, semantics in contract.required_prior_evidence.items():
        observed = set(observation.prior_evidence.get(work_item_id, []))
        for semantic in semantics:
            if semantic not in observed:
                failures.append(
                    f"{contract.work_item_id} lacks {semantic.value} from prior "
                    f"authority {work_item_id}"
                )
    return failures


def evaluate_milestone_exit_criteria(
    contract: MilestoneEvidenceContract,
    *,
    completed_work_item_ids: set[str],
    semantic_counts: dict[SemanticEvidence, int],
    external_type_counts: dict[EvidenceType, int],
    machine_policy_available: bool,
    correlated_facts: list[CorrelatedEvidenceFact] | None = None,
) -> list[str]:
    """Evaluate every exact roadmap exit criterion against controller facts."""

    failures: list[str] = []
    facts = correlated_facts or []
    for criterion in contract.exit_criteria:
        missing_items = set(criterion.required_work_item_ids) - completed_work_item_ids
        if missing_items:
            failures.append(
                f"{criterion.criterion_id} lacks work-item evidence: {sorted(missing_items)}"
            )
        for evidence_type in criterion.required_external_evidence_types:
            if external_type_counts.get(evidence_type, 0) < 1:
                failures.append(f"{criterion.criterion_id} lacks {evidence_type.value} evidence")
        for semantic, minimum in criterion.required_semantic_counts.items():
            if semantic_counts.get(semantic, 0) < minimum:
                failures.append(
                    f"{criterion.criterion_id} lacks {minimum} {semantic.value} evidence"
                )
        if criterion.machine_policy_required and not machine_policy_available:
            failures.append(f"{criterion.criterion_id} lacks machine-policy authorization")
        if criterion.required_correlation_fields:
            groups: dict[tuple[str, ...], list[CorrelatedEvidenceFact]] = {}
            for fact in facts:
                identity = tuple(
                    fact.identity(field) or "" for field in criterion.required_correlation_fields
                )
                if all(identity):
                    groups.setdefault(identity, []).append(fact)
            correlated = False
            for group in groups.values():
                semantics = {fact.semantic for fact in group if fact.semantic is not None}
                external = {
                    fact.external_evidence_type
                    for fact in group
                    if fact.external_evidence_type is not None
                }
                if set(criterion.required_semantic_counts).issubset(semantics) and set(
                    criterion.required_external_evidence_types
                ).issubset(external):
                    correlated = True
                    break
            if not correlated:
                failures.append(
                    f"{criterion.criterion_id} lacks one correlated "
                    f"{[field.value for field in criterion.required_correlation_fields]} "
                    "evidence closure"
                )
    return failures


def load_completion_evidence_policy(repo_root: Path) -> CompletionEvidencePolicy:
    policy = CompletionEvidencePolicy.model_validate(
        load_yaml(repo_root / "config/completion_evidence_policy.yaml")
    )
    expected_work_items = "sha256:" + sha256_file(repo_root / "factory/roadmap/work_items.yaml")
    expected_milestones = "sha256:" + sha256_file(repo_root / "factory/roadmap/milestones.yaml")
    if (
        policy.work_items_sha256 != expected_work_items
        or policy.milestones_sha256 != expected_milestones
    ):
        raise ValueError("completion evidence policy is stale for the active roadmap")
    return policy


__all__ = [
    "CompletionEvidenceObservation",
    "CompletionEvidencePolicy",
    "EvidenceAuthority",
    "EvidenceGrade",
    "MilestoneExitCriterionContract",
    "MilestoneEvidenceContract",
    "SemanticEvidence",
    "WorkItemEvidenceContract",
    "evaluate_work_item_evidence_contract",
    "evaluate_milestone_exit_criteria",
    "load_completion_evidence_policy",
]
