"""Strict V3.1-ZH wire contracts and lossless V3 migration envelopes.

This module is intentionally declarative.  Runtime code must opt in explicitly; defining a
contract here does not activate autonomy, publish code, or confer evidence/maturity.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from tcfactory.backends.base import AgentCapabilityReport, AgentTaskRequest
from tcfactory.checkpoints import V3Checkpoint
from tcfactory.handoffs import V3Handoff
from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model, to_camel
from tcfactory.v3.candidate_manifest import CandidateManifest
from tcfactory.v3.enums import Lane, RiskTier
from tcfactory.v3.pipeline_services import V3Finding
from tcfactory.v3.planning import V3TaskPacket
from tcfactory.v3.work_items import WorkItem

type Digest = Annotated[str, StringConstraints(pattern=DIGEST_PATTERN.pattern)]
type GitSha = Annotated[str, StringConstraints(pattern=SHA_PATTERN.pattern)]
type Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")]
type RelativePath = Annotated[
    str, StringConstraints(min_length=1, max_length=512, pattern=r"^[^/].*$")
]


class V31Model(V3Model):
    """Base for V3.1 records with strict Python and JSON validation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        strict=True,
    )

    schema_version: Literal["3.1"]


class EvidenceMode(StrEnum):
    SIMULATED = "SIMULATED"
    CONTROLLED_VALIDATED = "CONTROLLED_VALIDATED"
    LIVE_VALIDATED = "LIVE_VALIDATED"


class FreshnessState(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    RECHECK_REQUIRED = "RECHECK_REQUIRED"
    UNKNOWN = "UNKNOWN"


class OutputKind(StrEnum):
    FILE = "FILE"
    DIRECTORY_MANIFEST = "DIRECTORY_MANIFEST"
    REPORT = "REPORT"
    RECEIPT = "RECEIPT"
    SCHEMA = "SCHEMA"


class SessionState(StrEnum):
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExecutionOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class FingerprintDisposition(StrEnum):
    NEW = "NEW"
    KNOWN = "KNOWN"
    REPEATED = "REPEATED"
    HARD_STUCK = "HARD_STUCK"


class NativeSubstituteDisposition(StrEnum):
    NATIVE_SUFFICIENT = "NATIVE_SUFFICIENT"
    INCREMENTAL_VALUE = "INCREMENTAL_VALUE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN = "UNKNOWN"


class DecisionValueDisposition(StrEnum):
    NATIVE_WORKFLOW_SUFFICIENT = "NATIVE_WORKFLOW_SUFFICIENT"
    NO_INCREMENTAL_DECISION_VALUE = "NO_INCREMENTAL_DECISION_VALUE"
    TECHNICALLY_VALID_BUT_NOT_ECONOMIC = "TECHNICALLY_VALID_BUT_NOT_ECONOMIC"
    INCREMENTAL_DECISION_VALUE_DEMONSTRATED = "INCREMENTAL_DECISION_VALUE_DEMONSTRATED"
    EXTERNAL_EVIDENCE_REQUIRED = "EXTERNAL_EVIDENCE_REQUIRED"
    UNKNOWN = "UNKNOWN"


class TechnicalState(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    FAILED = "FAILED"
    PASSED = "PASSED"


class EpistemicState(StrEnum):
    UNKNOWN = "UNKNOWN"
    CONTROLLED = "CONTROLLED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"


class ValueState(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    REJECTED = "REJECTED"
    NATIVE_SUFFICIENT = "NATIVE_SUFFICIENT"
    INCREMENTAL_VALUE = "INCREMENTAL_VALUE"


class ReleaseState(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    BLOCKED = "BLOCKED"
    AUTHORIZED = "AUTHORIZED"
    PUBLISHED = "PUBLISHED"
    REVERTED = "REVERTED"


class CommercialState(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    NATIVE_ADVANTAGE_UNPROVEN = "NATIVE_ADVANTAGE_UNPROVEN"
    PILOT_ELIGIBLE = "PILOT_ELIGIBLE"
    COMMERCIALLY_SUPPORTED = "COMMERCIALLY_SUPPORTED"
    WITHDRAWN = "WITHDRAWN"


class PolicyDecision(StrEnum):
    PASS = "PASS"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class GateResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class ActivationMode(StrEnum):
    OBSERVATION = "OBSERVATION"
    CANARY = "CANARY"
    LIVE = "LIVE"


class PRPublicationPhase(StrEnum):
    PREPARED = "PREPARED"
    PR_OPEN = "PR_OPEN"
    CHECKS_PENDING = "CHECKS_PENDING"
    POLICY_PENDING = "POLICY_PENDING"
    READY_TO_MERGE = "READY_TO_MERGE"
    MERGED = "MERGED"
    FAILED = "FAILED"
    REVERTED = "REVERTED"


class RuntimeMode(StrEnum):
    STOPPED = "STOPPED"
    READ_ONLY = "READ_ONLY"
    SIMULATION = "SIMULATION"
    CANARY = "CANARY"
    LIVE = "LIVE"


class RuntimeEventKind(StrEnum):
    STARTED = "STARTED"
    STOPPED = "STOPPED"
    WORK_ITEM_TRANSITION = "WORK_ITEM_TRANSITION"
    CHECKPOINTED = "CHECKPOINTED"
    POLICY_DECIDED = "POLICY_DECIDED"
    PUBLICATION_TRANSITION = "PUBLICATION_TRANSITION"
    EXTERNAL_WAIT = "EXTERNAL_WAIT"
    HARD_STUCK = "HARD_STUCK"


def _require_forward_time(
    issued: AwareDatetime, expires: AwareDatetime, *, maximum: timedelta
) -> None:
    issued_utc = issued.astimezone(UTC)
    expires_utc = expires.astimezone(UTC)
    if expires_utc <= issued_utc or expires_utc - issued_utc > maximum:
        raise ValueError(f"expiry must be positive and at most {maximum}")


def _require_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_relative_path(value: str) -> None:
    if "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("path must be a normalized repository-relative POSIX path")


class SourceGenerationV31(V31Model):
    generation_id: Identifier
    manifest_digest: Digest
    source_digests: dict[RelativePath, Digest] = Field(min_length=1, max_length=256)
    active_normative: Literal[True]
    supersedes_generation_id: Identifier
    created_at: AwareDatetime

    @field_validator("source_digests")
    @classmethod
    def normalized_source_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for path in value:
            _require_relative_path(path)
        return value


class SourceFreshnessReceiptV31(V31Model):
    receipt_id: Identifier
    generation_id: Identifier
    generation_digest: Digest
    source_id: Identifier
    source_digest: Digest
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    state: FreshnessState
    conflict_artifact_digests: list[Digest] = Field(default_factory=list, max_length=32)
    wedge_work_item_id: str | None = Field(default=None, pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    issuer_id: Identifier
    issuer_key_id: Identifier
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=32, max_length=1024)

    @model_validator(mode="after")
    def validate_freshness(self) -> SourceFreshnessReceiptV31:
        _require_forward_time(self.observed_at, self.expires_at, maximum=timedelta(days=90))
        if self.state in {FreshnessState.STALE, FreshnessState.RECHECK_REQUIRED}:
            if not self.conflict_artifact_digests or self.wedge_work_item_id is None:
                raise ValueError(
                    "stale/recheck freshness requires conflict evidence and wedge work"
                )
        elif self.conflict_artifact_digests or self.wedge_work_item_id is not None:
            raise ValueError("fresh/unknown receipt cannot carry a stale transition")
        return self


class OutputDeclarationV31(V31Model):
    output_id: Identifier
    path: RelativePath
    kind: OutputKind
    media_type: str = Field(min_length=3, max_length=127)
    required: bool
    maximum_bytes: int = Field(ge=1, le=10_000_000_000)
    content_digest: Digest | None = None
    producer_work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    retention_days: int = Field(ge=1, le=3650)

    @field_validator("path")
    @classmethod
    def normalized_output_path(cls, value: str) -> str:
        _require_relative_path(value)
        return value


class SessionReferenceV31(V31Model):
    session_id: Identifier
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    provider: str = Field(min_length=1, max_length=64)
    backend: str = Field(min_length=1, max_length=64)
    task_packet_digest: Digest
    state: SessionState
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    transcript_digest: Digest | None = None

    @model_validator(mode="after")
    def validate_terminal_session(self) -> SessionReferenceV31:
        terminal = self.state in {
            SessionState.COMPLETED,
            SessionState.FAILED,
            SessionState.CANCELLED,
        }
        if terminal != (self.ended_at is not None and self.transcript_digest is not None):
            raise ValueError("terminal session requires end time and transcript digest")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("session end cannot precede start")
        return self


class ExecutionReportV31(V31Model):
    execution_id: Identifier
    session: SessionReferenceV31
    evidence_mode: EvidenceMode
    command_digest: Digest
    started_at: AwareDatetime
    finished_at: AwareDatetime
    exit_code: int = Field(ge=0, le=255)
    outcome: ExecutionOutcome
    attempt: int = Field(ge=1, le=100)
    maximum_attempts: int = Field(ge=1, le=100)
    stdout_artifact_digest: Digest
    stderr_artifact_digest: Digest
    outputs: list[OutputDeclarationV31] = Field(
        default_factory=list[OutputDeclarationV31], max_length=64
    )

    @model_validator(mode="after")
    def validate_execution(self) -> ExecutionReportV31:
        if self.finished_at < self.started_at:
            raise ValueError("execution finish cannot precede start")
        if self.attempt > self.maximum_attempts:
            raise ValueError("attempt exceeds maximumAttempts")
        if (self.exit_code == 0) != (self.outcome is ExecutionOutcome.PASS):
            raise ValueError("exitCode and outcome disagree")
        _require_unique([output.output_id for output in self.outputs], "output IDs")
        return self


class FingerprintCounterV31(V31Model):
    fingerprint: Digest
    count: int = Field(ge=1, le=1000)
    maximum_occurrences: int = Field(ge=1, le=1000)
    disposition: FingerprintDisposition
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime

    @model_validator(mode="after")
    def validate_counter(self) -> FingerprintCounterV31:
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("lastSeenAt cannot precede firstSeenAt")
        expected = (
            FingerprintDisposition.HARD_STUCK
            if self.count >= self.maximum_occurrences
            else FingerprintDisposition.REPEATED
            if self.count > 1
            else FingerprintDisposition.NEW
        )
        if self.disposition not in {expected, FingerprintDisposition.KNOWN}:
            raise ValueError("fingerprint disposition disagrees with bounded counter")
        return self


class NativeSubstituteBenchmarkV31(V31Model):
    benchmark_id: Identifier
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    baseline_environment_digest: Digest
    candidate_environment_digest: Digest
    native_tool: str = Field(min_length=1, max_length=128)
    native_tool_version: str = Field(min_length=1, max_length=64)
    native_evidence_digests: list[Digest] = Field(min_length=1, max_length=64)
    candidate_evidence_digests: list[Digest] = Field(min_length=1, max_length=64)
    independent_oracle_ids: list[Identifier] = Field(min_length=1, max_length=16)
    native_effort_minutes: float = Field(gt=0, le=1_000_000)
    candidate_effort_minutes: float = Field(gt=0, le=1_000_000)
    decision_changed: bool
    disposition: NativeSubstituteDisposition

    @model_validator(mode="after")
    def validate_benchmark(self) -> NativeSubstituteBenchmarkV31:
        _require_unique(self.native_evidence_digests, "native evidence digests")
        _require_unique(self.candidate_evidence_digests, "candidate evidence digests")
        _require_unique(self.independent_oracle_ids, "independent oracle IDs")
        if (
            self.disposition is NativeSubstituteDisposition.INCREMENTAL_VALUE
            and not self.decision_changed
        ):
            raise ValueError("incremental value requires a changed operational decision")
        if (
            self.disposition is NativeSubstituteDisposition.NATIVE_SUFFICIENT
            and self.decision_changed
        ):
            raise ValueError("native sufficiency cannot claim a candidate-caused decision change")
        return self


class DecisionValueResultV31(V31Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    evaluated: Literal[True] = True
    disposition: DecisionValueDisposition
    native_benchmark_digest: Digest
    evidence_refs: list[Digest] = Field(min_length=1, max_length=64)
    original_experiment_cost: float = Field(gt=0, le=1_000_000_000)
    proposed_experiment_cost: float = Field(gt=0, le=1_000_000_000)
    original_experiment_minutes: float = Field(gt=0, le=1_000_000)
    proposed_experiment_minutes: float = Field(gt=0, le=1_000_000)
    decision_changed: bool
    rationale: str = Field(min_length=1, max_length=4000)
    value_state: ValueState

    @model_validator(mode="after")
    def validate_value(self) -> DecisionValueResultV31:
        _require_unique(self.evidence_refs, "value evidence references")
        demonstrated = (
            self.disposition is DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        )
        if demonstrated != (
            self.decision_changed and self.value_state is ValueState.INCREMENTAL_VALUE
        ):
            raise ValueError("incremental value disposition, decision change, and state must agree")
        if (
            self.disposition is DecisionValueDisposition.NATIVE_WORKFLOW_SUFFICIENT
            and self.value_state is not ValueState.NATIVE_SUFFICIENT
        ):
            raise ValueError(
                "native sufficiency disposition requires NATIVE_SUFFICIENT value state"
            )
        return self


class MachinePolicyReceiptV31(V31Model):
    receipt_id: Identifier
    policy_id: Identifier
    policy_version: str = Field(min_length=1, max_length=64)
    issuer_id: Identifier
    issuer_key_id: Identifier
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revocation_epoch: int = Field(ge=1)
    nonce: str = Field(min_length=16, max_length=256)
    request_digest: Digest
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    lane: Lane
    risk_tier: RiskTier
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    base_sha: GitSha
    source_generation_id: Identifier
    source_generation_digest: Digest
    context_manifest_digest: Digest
    task_packet_digest: Digest
    candidate_manifest_digest: Digest
    checkpoint_digest: Digest
    required_gate_results: dict[Identifier, GateResult] = Field(min_length=1, max_length=64)
    private_gate_suite_id: Identifier
    private_gate_runner_digest: Digest
    independent_oracle_ids: list[Identifier] = Field(min_length=1, max_length=32)
    raw_evidence_artifact_hashes: list[Digest] = Field(min_length=1, max_length=128)
    native_substitute_disposition: NativeSubstituteDisposition
    decision_value_disposition: DecisionValueDisposition
    engineering_maturity_ceiling: TechnicalState
    commercial_maturity_ceiling: CommercialState
    allowed_claims: list[Identifier] = Field(min_length=1, max_length=64)
    forbidden_claims: list[Identifier] = Field(default_factory=list, max_length=64)
    publication_scope: list[RelativePath] = Field(min_length=1, max_length=64)
    decision: PolicyDecision
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=32, max_length=1024)

    @model_validator(mode="after")
    def validate_receipt(self) -> MachinePolicyReceiptV31:
        _require_forward_time(self.issued_at, self.expires_at, maximum=timedelta(hours=24))
        for values, label in (
            (self.independent_oracle_ids, "independent oracle IDs"),
            (self.raw_evidence_artifact_hashes, "raw evidence hashes"),
            (self.allowed_claims, "allowed claims"),
            (self.forbidden_claims, "forbidden claims"),
            (self.publication_scope, "publication scope"),
        ):
            _require_unique(values, label)
        overlap = set(self.allowed_claims) & set(self.forbidden_claims)
        if overlap:
            raise ValueError(f"allowed and forbidden claims overlap: {sorted(overlap)}")
        gates_pass = all(
            result is GateResult.PASS for result in self.required_gate_results.values()
        )
        if (self.decision is PolicyDecision.PASS) != gates_pass:
            raise ValueError("policy PASS requires every named gate to PASS")
        for path in self.publication_scope:
            _require_relative_path(path)
        if (
            self.commercial_maturity_ceiling is CommercialState.COMMERCIALLY_SUPPORTED
            and self.decision_value_disposition
            is not DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        ):
            raise ValueError("commercial support requires demonstrated incremental decision value")
        return self


class MachinePolicyRevocationListV31(V31Model):
    policy_id: Identifier
    policy_version: str = Field(min_length=1, max_length=64)
    issuer_id: Identifier
    issuer_key_id: Identifier
    revocation_epoch: int = Field(ge=1)
    previous_list_digest: Digest | None = None
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_receipt_ids: list[Identifier] = Field(default_factory=list, max_length=10_000)
    revoked_nonces: list[str] = Field(default_factory=list, max_length=10_000)
    revoked_key_ids: list[Identifier] = Field(default_factory=list, max_length=1_000)
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=32, max_length=1024)

    @model_validator(mode="after")
    def validate_revocations(self) -> MachinePolicyRevocationListV31:
        _require_forward_time(self.issued_at, self.expires_at, maximum=timedelta(days=30))
        for values, label in (
            (self.revoked_receipt_ids, "revoked receipt IDs"),
            (self.revoked_nonces, "revoked nonces"),
            (self.revoked_key_ids, "revoked key IDs"),
        ):
            _require_unique(values, label)
        return self


class ActivationReceiptV31(V31Model):
    receipt_id: Identifier
    verified_main_sha: GitSha
    machine_environment_digest: Digest
    source_generation_id: Identifier
    source_generation_digest: Digest
    controller_binary_digest: Digest
    controller_config_digest: Digest
    machine_policy_receipt_id: Identifier
    machine_policy_receipt_digest: Digest
    mode: ActivationMode
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revocation_epoch: int = Field(ge=1)
    nonce: str = Field(min_length=16, max_length=256)
    issuer_id: Identifier
    issuer_key_id: Identifier
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=32, max_length=1024)

    @model_validator(mode="after")
    def validate_activation(self) -> ActivationReceiptV31:
        _require_forward_time(self.issued_at, self.expires_at, maximum=timedelta(hours=24))
        return self


class PRPublicationTransactionV31(V31Model):
    transaction_id: Identifier
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    base_branch: Literal["main"] = "main"
    candidate_branch: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,126}[A-Za-z0-9])?$")
    base_sha: GitSha
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    pull_request_number: int | None = Field(default=None, ge=1)
    pull_request_url: str | None = Field(
        default=None, pattern=r"^https://github\.com/.+/pull/[1-9][0-9]*$"
    )
    machine_policy_receipt_id: Identifier
    machine_policy_receipt_digest: Digest
    phase: PRPublicationPhase
    attempt: int = Field(ge=1, le=20)
    maximum_attempts: int = Field(ge=1, le=20)
    automated_merge: Literal[True] = True
    required_human_approvals: Literal[0] = 0
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_publication(self) -> PRPublicationTransactionV31:
        if self.updated_at < self.created_at or self.attempt > self.maximum_attempts:
            raise ValueError("publication timestamps or retry budget are inconsistent")
        opened = self.phase not in {PRPublicationPhase.PREPARED, PRPublicationPhase.FAILED}
        if opened != (self.pull_request_number is not None and self.pull_request_url is not None):
            raise ValueError("open/terminal PR phases require number and URL")
        return self


class MilestoneCompletionProposalV31(V31Model):
    proposal_id: Identifier
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    candidate_sha: GitSha
    work_item_ids: list[str] = Field(min_length=1, max_length=256)
    completion_evidence_digests: list[Digest] = Field(min_length=1, max_length=256)
    technical_state: TechnicalState
    epistemic_state: EpistemicState
    value_state: ValueState
    release_state: ReleaseState
    commercial_state: CommercialState
    external_evidence_refs: list[Digest] = Field(default_factory=list, max_length=128)
    machine_policy_receipt_id: Identifier
    machine_policy_receipt_digest: Digest
    proposed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_proposal(self) -> MilestoneCompletionProposalV31:
        _require_unique(self.work_item_ids, "work item IDs")
        _require_unique(self.completion_evidence_digests, "completion evidence digests")
        if (
            self.release_state in {ReleaseState.AUTHORIZED, ReleaseState.PUBLISHED}
            and self.technical_state is not TechnicalState.PASSED
        ):
            raise ValueError("release authorization requires passed technical state")
        commercial_advanced = self.commercial_state in {
            CommercialState.PILOT_ELIGIBLE,
            CommercialState.COMMERCIALLY_SUPPORTED,
        }
        externally_verified = bool(self.external_evidence_refs) and (
            self.epistemic_state is EpistemicState.EXTERNALLY_VERIFIED
        )
        if commercial_advanced and not externally_verified:
            raise ValueError("commercial advancement requires external verified evidence")
        return self


class RuntimeStatusV31(V31Model):
    snapshot_id: Identifier
    observed_at: AwareDatetime
    mode: RuntimeMode
    autonomy_enabled: bool
    activation_receipt_id: Identifier | None = None
    activation_receipt_digest: Digest | None = None
    source_generation_id: Identifier
    source_generation_digest: Digest
    controller_binary_digest: Digest
    controller_config_digest: Digest
    current_work_item_id: str | None = Field(default=None, pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    technical_state: TechnicalState
    epistemic_state: EpistemicState
    value_state: ValueState
    release_state: ReleaseState
    commercial_state: CommercialState
    queued_count: int = Field(ge=0, le=1_000_000)
    blocked_count: int = Field(ge=0, le=1_000_000)

    @model_validator(mode="after")
    def validate_runtime(self) -> RuntimeStatusV31:
        live = self.mode in {RuntimeMode.CANARY, RuntimeMode.LIVE}
        bound = (
            self.activation_receipt_id is not None and self.activation_receipt_digest is not None
        )
        if live != (self.autonomy_enabled and bound):
            raise ValueError("canary/live runtime requires autonomy and a bound activation receipt")
        return self


class RuntimeEventV31(V31Model):
    event_id: Identifier
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime
    kind: RuntimeEventKind
    mode: RuntimeMode
    work_item_id: str | None = Field(default=None, pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    previous_state: str | None = Field(default=None, max_length=128)
    current_state: str = Field(min_length=1, max_length=128)
    evidence_digests: list[Digest] = Field(default_factory=list, max_length=128)
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator("evidence_digests")
    @classmethod
    def unique_evidence(cls, value: list[str]) -> list[str]:
        _require_unique(value, "runtime event evidence digests")
        return value


class MigratedWorkItemV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: WorkItem


class MigratedTaskPacketV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: V3TaskPacket


class MigratedAgentRequestV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: AgentTaskRequest


class MigratedAgentCapabilityV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: AgentCapabilityReport


class MigratedFindingV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: V3Finding


class MigratedCheckpointV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: V3Checkpoint


class MigratedHandoffV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: V3Handoff


class MigratedCandidateManifestV31(V31Model):
    migrated_from_schema_version: Literal["3"]
    payload: CandidateManifest


type MigratedV31Contract = (
    MigratedWorkItemV31
    | MigratedTaskPacketV31
    | MigratedAgentRequestV31
    | MigratedAgentCapabilityV31
    | MigratedFindingV31
    | MigratedCheckpointV31
    | MigratedHandoffV31
    | MigratedCandidateManifestV31
)


REUSABLE_V3_MIGRATIONS: dict[str, type[V31Model]] = {
    "work-item": MigratedWorkItemV31,
    "task-packet": MigratedTaskPacketV31,
    "agent-request": MigratedAgentRequestV31,
    "agent-capability": MigratedAgentCapabilityV31,
    "finding": MigratedFindingV31,
    "checkpoint": MigratedCheckpointV31,
    "handoff": MigratedHandoffV31,
    "candidate-manifest": MigratedCandidateManifestV31,
}


def migrate_v3_contract(contract_name: str, payload: object) -> MigratedV31Contract:
    """Validate V3 bytes and preserve them in an explicit V3.1 migration envelope.

    No defaults representing new evidence, policy decisions, or maturity are invented.
    """

    model = REUSABLE_V3_MIGRATIONS.get(contract_name)
    if model is None:
        raise ValueError(f"unsupported V3 contract migration: {contract_name}")
    result = model.model_validate(
        {
            "schemaVersion": "3.1",
            "migratedFromSchemaVersion": "3",
            "payload": payload,
        },
        strict=True,
    )
    return result  # type: ignore[return-value]


V31_NATIVE_CONTRACTS: dict[str, type[V31Model]] = {
    "source-generation": SourceGenerationV31,
    "source-freshness-receipt": SourceFreshnessReceiptV31,
    "output-declaration": OutputDeclarationV31,
    "session-reference": SessionReferenceV31,
    "execution-report": ExecutionReportV31,
    "fingerprint-counter": FingerprintCounterV31,
    "native-substitute-benchmark": NativeSubstituteBenchmarkV31,
    "decision-value": DecisionValueResultV31,
    "machine-policy-receipt": MachinePolicyReceiptV31,
    "machine-policy-revocation-list": MachinePolicyRevocationListV31,
    "activation-receipt": ActivationReceiptV31,
    "pr-publication-transaction": PRPublicationTransactionV31,
    "milestone-completion-proposal": MilestoneCompletionProposalV31,
    "runtime-status": RuntimeStatusV31,
    "runtime-event": RuntimeEventV31,
}


def validate_v31_contract(contract_name: str, payload: object) -> V31Model:
    """Validate a native V3.1 record by its stable contract name."""

    model = V31_NATIVE_CONTRACTS.get(contract_name)
    if model is None:
        raise ValueError(f"unsupported V3.1 contract: {contract_name}")
    return model.model_validate(payload, strict=True)
