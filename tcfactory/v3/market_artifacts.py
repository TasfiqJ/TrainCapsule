"""Versioned market/research artifacts that never substitute for external outcomes."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import ConfigDict, Field, model_validator

from tcfactory.v3.base import DIGEST_PATTERN, to_camel
from tcfactory.v3.contracts_v31 import V31Model
from tcfactory.v3.source_acquisition import ResearchReport, ResearchVerdict


class MarketArtifactError(RuntimeError):
    """Raised when an artifact would overstate its attributable evidence."""


class MarketModel(V31Model):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        strict=True,
    )


class AccountResearchState(StrEnum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    EXTERNAL_EVIDENCE_REQUIRED = "EXTERNAL_EVIDENCE_REQUIRED"
    CONFLICT = "CONFLICT"


class AccountEvidenceField(MarketModel):
    value: str | None = Field(default=None, max_length=1000)
    verdict: ResearchVerdict
    claim_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    source_artifact_digests: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_evidence(self) -> AccountEvidenceField:
        if len(set(self.source_artifact_digests)) != len(self.source_artifact_digests):
            raise ValueError("account evidence digests must be unique")
        if self.verdict is ResearchVerdict.UNKNOWN:
            if self.value is not None or self.source_artifact_digests:
                raise ValueError("UNKNOWN account evidence cannot carry a value or evidence")
        elif self.value is None or not self.source_artifact_digests:
            raise ValueError("CLEAR/CONFLICT account evidence requires a value and raw evidence")
        return self


class AccountQualificationScore(MarketModel):
    incident_cost: int = Field(ge=0, le=3)
    upcoming_change: int = Field(ge=0, le=3)
    evidence_access: int = Field(ge=0, le=3)
    experiment_authority: int = Field(ge=0, le=3)
    native_gap: int = Field(ge=0, le=3)
    privacy_need: int = Field(ge=0, le=3)
    repeat_trigger: int = Field(ge=0, le=3)
    budget_owner: int = Field(ge=0, le=3)
    second_use_path: int = Field(ge=0, le=3)
    delivery_fit: int = Field(ge=0, le=3)
    total: int = Field(ge=0, le=30)

    @model_validator(mode="after")
    def validate_total(self) -> AccountQualificationScore:
        values = self.model_dump(exclude={"schema_version", "total"})
        if self.total != sum(int(value) for value in values.values()):
            raise ValueError("qualification total must equal its ten bounded dimensions")
        return self


class ReachableAccount(MarketModel):
    account_id: str = Field(pattern=r"^ACCOUNT-[0-9]{3}$")
    organization: AccountEvidenceField
    segment: AccountEvidenceField
    relationship_path: AccountEvidenceField
    relevant_workload: AccountEvidenceField
    known_incident: AccountEvidenceField
    planned_change: AccountEvidenceField
    decision_owner: AccountEvidenceField
    technical_champion: AccountEvidenceField
    budget_owner: AccountEvidenceField
    native_stack: AccountEvidenceField
    privacy_constraint: AccountEvidenceField
    qualification_score: AccountQualificationScore
    next_evidence_action: str = Field(min_length=1, max_length=1000)
    state: AccountResearchState

    @model_validator(mode="after")
    def validate_state(self) -> ReachableAccount:
        fields = [
            self.organization,
            self.segment,
            self.relationship_path,
            self.relevant_workload,
            self.known_incident,
            self.planned_change,
            self.decision_owner,
            self.technical_champion,
            self.budget_owner,
            self.native_stack,
            self.privacy_constraint,
        ]
        expected = (
            AccountResearchState.CONFLICT
            if any(field.verdict is ResearchVerdict.CONFLICT for field in fields)
            else AccountResearchState.EXTERNAL_EVIDENCE_REQUIRED
            if any(field.verdict is ResearchVerdict.UNKNOWN for field in fields)
            else AccountResearchState.RESEARCH_ONLY
        )
        if self.state is not expected:
            raise ValueError("account state does not match its attributed research verdicts")
        return self


class ReachableAccountMap(MarketModel):
    map_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    research_report_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    accounts: list[ReachableAccount] = Field(min_length=30, max_length=30)
    claim_ids: list[str] = Field(min_length=1, max_length=128)
    raw_source_artifact_digests: list[str] = Field(min_length=1, max_length=128)
    external_outcomes_demonstrated: bool = False

    @model_validator(mode="after")
    def validate_map(self) -> ReachableAccountMap:
        account_ids = [account.account_id for account in self.accounts]
        if len(set(account_ids)) != 30:
            raise ValueError("reachable account map requires 30 unique account IDs")
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("account-map claim IDs must be unique")
        if len(set(self.raw_source_artifact_digests)) != len(self.raw_source_artifact_digests):
            raise ValueError("account-map source artifacts must be unique")
        if self.external_outcomes_demonstrated:
            raise ValueError("a research account map cannot claim external outcomes")
        return self


class InterviewQuestion(MarketModel):
    question_id: str = Field(pattern=r"^Q-[0-9]{3}$")
    prompt: str = Field(min_length=1, max_length=1000)
    evidence_target: str = Field(min_length=1, max_length=500)
    disallowed_inference: str = Field(min_length=1, max_length=500)


class DiscoveryInterviewGuide(MarketModel):
    guide_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    source_generation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    questions: list[InterviewQuestion] = Field(min_length=8, max_length=32)
    required_external_receipt: bool = True
    allows_synthetic_answers: bool = False

    @model_validator(mode="after")
    def validate_guide(self) -> DiscoveryInterviewGuide:
        if len({question.question_id for question in self.questions}) != len(self.questions):
            raise ValueError("interview question IDs must be unique")
        if not self.required_external_receipt or self.allows_synthetic_answers:
            raise ValueError("interview evidence must remain external and non-synthetic")
        return self


class PilotQualificationRubric(MarketModel):
    rubric_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    source_generation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    minimum_score: int = Field(ge=1, le=30)
    required_dimensions: list[str] = Field(min_length=10, max_length=10)
    requires_real_trace_authorization: bool = True
    requires_signed_external_receipt: bool = True
    permits_research_map_as_pilot_proof: bool = False

    @model_validator(mode="after")
    def validate_rubric(self) -> PilotQualificationRubric:
        if len(set(self.required_dimensions)) != 10:
            raise ValueError("pilot rubric requires ten unique qualification dimensions")
        if (
            not self.requires_real_trace_authorization
            or not self.requires_signed_external_receipt
            or self.permits_research_map_as_pilot_proof
        ):
            raise ValueError("pilot qualification cannot be inferred from research artifacts")
        return self


def bind_reachable_account_map(
    *,
    map_id: str,
    report: ResearchReport,
    accounts: list[ReachableAccount],
) -> ReachableAccountMap:
    """Bind a 30-account research map to one exact controlled research report."""

    if report.overall_verdict is ResearchVerdict.CONFLICT:
        raise MarketArtifactError("conflicting research cannot produce a reachable account map")
    report_claims = {finding.claim_id for finding in report.findings}
    report_artifacts = {artifact.content_digest for artifact in report.artifacts}
    for account in accounts:
        for field in (
            account.organization,
            account.segment,
            account.relationship_path,
            account.relevant_workload,
            account.known_incident,
            account.planned_change,
            account.decision_owner,
            account.technical_champion,
            account.budget_owner,
            account.native_stack,
            account.privacy_constraint,
        ):
            if field.claim_id not in report_claims:
                raise MarketArtifactError("account field cites a claim outside the research report")
            if not set(field.source_artifact_digests).issubset(report_artifacts):
                raise MarketArtifactError("account field cites raw evidence outside the report")
    return ReachableAccountMap(
        schema_version="3.1",
        map_id=map_id,
        work_item_id=report.work_item_id,
        candidate_sha=report.candidate_sha,
        research_report_digest=report.canonical_digest(),
        accounts=accounts,
        claim_ids=sorted(report_claims),
        raw_source_artifact_digests=sorted(report_artifacts),
        external_outcomes_demonstrated=False,
    )


MARKET_ARTIFACT_CONTRACTS: dict[str, type[MarketModel]] = {
    "account-evidence-field": AccountEvidenceField,
    "account-qualification-score": AccountQualificationScore,
    "reachable-account": ReachableAccount,
    "reachable-account-map": ReachableAccountMap,
    "interview-question": InterviewQuestion,
    "discovery-interview-guide": DiscoveryInterviewGuide,
    "pilot-qualification-rubric": PilotQualificationRubric,
}
