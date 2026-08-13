"""Strict duplicated wire contract for the external canary trust boundary."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MandatoryCanaryId(StrEnum):
    REAL_CLAUDE_MECHANICAL_TASK = "real_claude_mechanical_task"
    PROCESS_KILL_AND_RESUME = "process_kill_and_resume"
    QUOTA_PAUSE_AND_RESUME = "quota_pause_and_resume"
    AUTHENTICATION_EXPIRY_AND_RECOVERY = "authentication_expiry_and_recovery"
    REPEATED_FINDING_FINITE_STOP = "repeated_finding_finite_stop"
    EXTERNAL_WAIT_LANE_ISOLATION = "external_wait_lane_isolation"
    BAD_CANDIDATE_REJECTED_BEFORE_MAIN = "bad_candidate_rejected_before_main"
    RELEASE_TRANSACTION_CRASH_IDEMPOTENCY = "release_transaction_crash_idempotency"
    AUTOMATIC_MILESTONE_ADVANCEMENT = "automatic_milestone_advancement"
    MACHINE_RECEIPT_MISSING_INVALID_EXPIRED_REVOKED = (
        "machine_receipt_missing_invalid_expired_revoked"
    )
    DUPLICATE_CONTROLLER_REJECTION = "duplicate_controller_rejection"
    LEASE_RENEWAL_FAILURE = "lease_renewal_failure"
    STALE_CURRENT_FACTS = "stale_current_facts"
    MISSING_SOURCE_AUTHORITY = "missing_source_authority"
    MALFORMED_REPORT = "malformed_report"
    PRIVATE_GATE_MISSING_FOR_TRUST_RISK = "private_gate_missing_for_trust_risk"
    MACHINE_VERIFIER_UNAVAILABLE = "machine_verifier_unavailable"
    ACTIVATION_RECEIPT_WRONG_SHA = "activation_receipt_wrong_sha"
    RUNTIME_ROOT_OUTSIDE_REPO = "runtime_root_outside_repo"
    POST_MERGE_INVARIANT_FAILURE_AND_AUTOMATED_REVERT_PR = (
        "post_merge_invariant_failure_and_automated_revert_pr"
    )


class CanaryStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED_PREREQUISITE = "BLOCKED_PREREQUISITE"


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part.title() for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class MandatoryCanaryResult(StrictModel):
    schema_version: Literal["3.1"]
    run_id: str = Field(pattern=r"^CANARY-[A-Z0-9_-]{8,160}$")
    canary_id: MandatoryCanaryId
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    runner_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    status: CanaryStatus
    evidence_artifacts: dict[str, str] = Field(default_factory=dict, max_length=128)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    failure_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self) -> MandatoryCanaryResult:
        if self.completed_at < self.started_at:
            raise ValueError("canary completion precedes start")
        if self.status is CanaryStatus.PASS:
            if self.runner_digest is None or not self.evidence_artifacts:
                raise ValueError("PASS requires runner and evidence digests")
            if self.failure_reason is not None:
                raise ValueError("PASS cannot carry a failure reason")
        elif not self.failure_reason:
            raise ValueError("non-PASS requires a failure reason")
        return self


class MechanismPolicy(StrictModel):
    executable: str = Field(pattern=r"^/usr/libexec/traincapsule-canary-[a-z0-9_-]+$")
    executable_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    timeout_seconds: int = Field(ge=1, le=14_400)
    network_allowed: bool


class RunnerPolicy(StrictModel):
    schema_version: Literal["3.1"]
    runner_executable_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    distribution_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    mechanisms: dict[MandatoryCanaryId, MechanismPolicy]

    @model_validator(mode="after")
    def exact_roster(self) -> RunnerPolicy:
        if set(self.mechanisms) != set(MandatoryCanaryId):
            raise ValueError("runner policy must pin exactly all 20 mechanisms")
        return self


class MechanismOutcome(StrictModel):
    schema_version: Literal["3.1"]
    canary_id: MandatoryCanaryId
    run_id: str
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    status: CanaryStatus
    evidence_artifacts: dict[str, str] = Field(default_factory=dict, max_length=128)
    failure_reason: str | None = Field(default=None, max_length=2000)
    observed_at: datetime
