"""Independent V3.1-ZH verifier wire contracts.

These models intentionally duplicate the public wire contract rather than importing the
candidate repository's policy implementation.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from enum import StrEnum
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _normalized_relative_path(value: str) -> str:
    if (
        "\\" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("path must be normalized and relative")
    return value


type Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
type GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
type Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")]


def _reject_source_generation_whitespace(value: object) -> object:
    if isinstance(value, str) and value != value.strip():
        raise ValueError("source generation ID whitespace is forbidden")
    return value


type SourceGenerationId = Annotated[
    str,
    BeforeValidator(_reject_source_generation_whitespace),
    StringConstraints(min_length=3, max_length=128, pattern=r"^[a-z0-9][a-z0-9._:-]{2,127}$"),
]
type RelativePath = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512, pattern=r"^[^/].*$"),
    AfterValidator(_normalized_relative_path),
]


def _camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class StrictModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=_camel,
        extra="forbid",
        populate_by_name=True,
        strict=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class V31Model(StrictModel):
    schema_version: Literal["3.1"]


class EvidenceMode(StrEnum):
    SIMULATED = "SIMULATED"
    CONTROLLED_VALIDATED = "CONTROLLED_VALIDATED"
    LIVE_VALIDATED = "LIVE_VALIDATED"


class GateResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class OracleOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class NativeDisposition(StrEnum):
    NATIVE_SUFFICIENT = "NATIVE_SUFFICIENT"
    INCREMENTAL_VALUE = "INCREMENTAL_VALUE"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    UNKNOWN = "UNKNOWN"


class ValueDisposition(StrEnum):
    NATIVE_WORKFLOW_SUFFICIENT = "NATIVE_WORKFLOW_SUFFICIENT"
    NO_INCREMENTAL_DECISION_VALUE = "NO_INCREMENTAL_DECISION_VALUE"
    TECHNICALLY_VALID_BUT_NOT_ECONOMIC = "TECHNICALLY_VALID_BUT_NOT_ECONOMIC"
    INCREMENTAL_DECISION_VALUE_DEMONSTRATED = "INCREMENTAL_DECISION_VALUE_DEMONSTRATED"
    EXTERNAL_EVIDENCE_REQUIRED = "EXTERNAL_EVIDENCE_REQUIRED"
    UNKNOWN = "UNKNOWN"


class EngineeringCeiling(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    FAILED = "FAILED"
    PASSED = "PASSED"


class CommercialCeiling(StrEnum):
    NOT_EVALUATED = "NOT_EVALUATED"
    NATIVE_ADVANTAGE_UNPROVEN = "NATIVE_ADVANTAGE_UNPROVEN"
    PILOT_ELIGIBLE = "PILOT_ELIGIBLE"
    COMMERCIALLY_SUPPORTED = "COMMERCIALLY_SUPPORTED"
    WITHDRAWN = "WITHDRAWN"


class PolicyDecision(StrEnum):
    PASS = "PASS"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class ActivationMode(StrEnum):
    OBSERVATION = "OBSERVATION"
    CANARY = "CANARY"
    LIVE = "LIVE"


class GateObservation(StrictModel):
    candidate_sha: GitSha
    result: GateResult
    evidence_digest: Digest


class OracleObservation(StrictModel):
    oracle_id: Identifier
    oracle_runner_digest: Digest
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    outcome: OracleOutcome
    raw_evidence_artifact_hashes: list[Digest] = Field(min_length=1, max_length=128)
    native_disposition: NativeDisposition
    value_disposition: ValueDisposition
    engineering_ceiling: EngineeringCeiling
    commercial_ceiling: CommercialCeiling

    @field_validator("raw_evidence_artifact_hashes")
    @classmethod
    def unique_raw_hashes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("oracle raw evidence hashes must be unique")
        return value


class RawArtifactBinding(StrictModel):
    path: RelativePath
    digest: Digest

    @field_validator("path")
    @classmethod
    def normalized_path(cls, value: str) -> str:
        if "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("artifact path must be normalized and relative")
        return value


class TrustedEvidenceManifest(V31Model):
    evidence_mode: EvidenceMode
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    lane: Identifier
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    base_sha: GitSha
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    context_manifest_digest: Digest
    task_packet_digest: Digest
    candidate_manifest_digest: Digest
    checkpoint_digest: Digest
    gates: dict[Identifier, GateObservation] = Field(min_length=1, max_length=128)
    private_gate_suite_id: Identifier
    private_gate_runner_digest: Digest
    oracles: dict[Identifier, OracleObservation] = Field(min_length=1, max_length=32)
    raw_artifacts: dict[Identifier, RawArtifactBinding] = Field(min_length=1, max_length=128)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_embedded_identities(self) -> TrustedEvidenceManifest:
        for name, gate in self.gates.items():
            if gate.candidate_sha != self.candidate_sha:
                raise ValueError(f"gate {name} candidate SHA mismatch")
        for identifier, oracle in self.oracles.items():
            if identifier != oracle.oracle_id:
                raise ValueError("oracle map key does not match oracle identity")
            if (
                oracle.candidate_sha != self.candidate_sha
                or oracle.candidate_tree_sha != self.candidate_tree_sha
            ):
                raise ValueError(f"oracle {identifier} candidate identity mismatch")
        return self


class VerificationRequest(V31Model):
    request_id: Identifier
    request_digest: Digest
    nonce: str = Field(min_length=16, max_length=256)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    lane: Identifier
    risk_tier: Identifier
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    base_sha: GitSha
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    context_manifest_digest: Digest
    task_packet_digest: Digest
    candidate_manifest_digest: Digest
    checkpoint_digest: Digest
    requested_claims: list[Identifier] = Field(min_length=1, max_length=64)
    publication_scope: list[RelativePath] = Field(min_length=1, max_length=64)
    native_substitute_disposition: NativeDisposition
    decision_value_disposition: ValueDisposition
    engineering_maturity_ceiling: EngineeringCeiling
    commercial_maturity_ceiling: CommercialCeiling

    @field_validator("requested_claims", "publication_scope")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("request claims and publication scope must be unique")
        return value


class RiskPolicy(StrictModel):
    required_gates: list[Identifier] = Field(min_length=1, max_length=128)
    required_oracle_ids: list[Identifier] = Field(min_length=1, max_length=32)
    oracle_runner_digests: dict[Identifier, Digest] = Field(min_length=1, max_length=32)
    oracle_runner_paths: dict[Identifier, RelativePath] = Field(min_length=1, max_length=32)
    accepted_evidence_modes: list[EvidenceMode] = Field(min_length=1, max_length=3)
    maximum_engineering_ceiling: EngineeringCeiling
    maximum_commercial_ceiling: CommercialCeiling

    @field_validator("required_gates", "required_oracle_ids", "accepted_evidence_modes")
    @classmethod
    def unique_requirements(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("risk-policy requirements must be unique")
        return value

    @model_validator(mode="after")
    def exact_oracle_policy(self) -> RiskPolicy:
        required = set(self.required_oracle_ids)
        if required != set(self.oracle_runner_digests) or required != set(self.oracle_runner_paths):
            raise ValueError("required oracle IDs and runner bindings must match")
        return self


class VerifierPolicy(V31Model):
    policy_id: Identifier
    policy_version: str = Field(pattern=r"^[1-9][0-9]*\.[0-9]+\.[0-9]+$")
    issuer_id: Identifier
    issuer_key_id: Identifier
    public_key_fingerprint: Digest
    minimum_revocation_epoch: int = Field(ge=1)
    active_source_generation_id: SourceGenerationId
    active_source_generation_digest: Digest
    private_gate_suite_id: Identifier
    private_gate_runner_digest: Digest
    risk_policies: dict[Identifier, RiskPolicy] = Field(min_length=1, max_length=32)
    allowed_claims: list[Identifier] = Field(min_length=1, max_length=128)
    forbidden_claims: list[Identifier] = Field(default_factory=list[Identifier], max_length=128)
    allowed_publication_scopes: list[RelativePath] = Field(min_length=1, max_length=128)
    maximum_receipt_lifetime_seconds: int = Field(ge=60, le=86_400)
    maximum_evidence_age_seconds: int = Field(ge=1, le=604_800)

    @model_validator(mode="after")
    def validate_claim_policy(self) -> VerifierPolicy:
        for values, label in (
            (self.allowed_claims, "allowed claims"),
            (self.forbidden_claims, "forbidden claims"),
            (self.allowed_publication_scopes, "publication scopes"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        if set(self.allowed_claims) & set(self.forbidden_claims):
            raise ValueError("allowed and forbidden claims overlap")
        return self


class MachinePolicyReceipt(V31Model):
    receipt_id: Identifier
    policy_id: Identifier
    policy_version: str
    issuer_id: Identifier
    issuer_key_id: Identifier
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revocation_epoch: int = Field(ge=1)
    nonce: str = Field(min_length=16, max_length=256)
    request_digest: Digest
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    milestone_id: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    lane: Identifier
    risk_tier: Identifier
    candidate_sha: GitSha
    candidate_tree_sha: GitSha
    base_sha: GitSha
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    context_manifest_digest: Digest
    task_packet_digest: Digest
    candidate_manifest_digest: Digest
    checkpoint_digest: Digest
    required_gate_results: dict[Identifier, GateResult] = Field(min_length=1, max_length=128)
    private_gate_suite_id: Identifier
    private_gate_runner_digest: Digest
    independent_oracle_ids: list[Identifier] = Field(min_length=1, max_length=32)
    raw_evidence_artifact_hashes: list[Digest] = Field(min_length=1, max_length=128)
    native_substitute_disposition: NativeDisposition
    decision_value_disposition: ValueDisposition
    engineering_maturity_ceiling: EngineeringCeiling
    commercial_maturity_ceiling: CommercialCeiling
    allowed_claims: list[Identifier] = Field(min_length=1, max_length=64)
    forbidden_claims: list[Identifier] = Field(default_factory=list[Identifier], max_length=64)
    publication_scope: list[RelativePath] = Field(min_length=1, max_length=64)
    decision: Literal[PolicyDecision.PASS]
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_expiry(self) -> MachinePolicyReceipt:
        lifetime = self.expires_at.astimezone(UTC) - self.issued_at.astimezone(UTC)
        if lifetime <= timedelta(0) or lifetime > timedelta(hours=24):
            raise ValueError("receipt lifetime must be positive and at most 24 hours")
        return self


class RevocationList(V31Model):
    policy_id: Identifier
    policy_version: str
    issuer_id: Identifier
    issuer_key_id: Identifier
    revocation_epoch: int = Field(ge=1)
    previous_list_digest: Digest | None = None
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_receipt_ids: list[Identifier] = Field(
        default_factory=list[Identifier], max_length=10_000
    )
    revoked_nonces: list[str] = Field(default_factory=list[str], max_length=10_000)
    revoked_key_ids: list[Identifier] = Field(default_factory=list[Identifier], max_length=1_000)
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_revocation_list(self) -> RevocationList:
        if self.expires_at <= self.issued_at:
            raise ValueError("revocation list expiry must follow issuance")
        for values, label in (
            (self.revoked_receipt_ids, "revoked receipt IDs"),
            (self.revoked_nonces, "revoked nonces"),
            (self.revoked_key_ids, "revoked key IDs"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")
        return self


class AuthorityAnchor(V31Model):
    """Externally provisioned monotonic pin for authority and revocation state."""

    policy_id: Identifier
    policy_version: str
    issuer_id: Identifier
    issuer_key_id: Identifier
    public_key_fingerprint: Digest
    key_epoch: int = Field(ge=1)
    previous_key_anchor_digest: Digest | None = None
    revocation_epoch: int = Field(ge=1)
    revocation_list_digest: Digest
    previous_revocation_list_digest: Digest | None = None

    @model_validator(mode="after")
    def validate_chain_shape(self) -> AuthorityAnchor:
        if self.key_epoch == 1 and self.previous_key_anchor_digest is not None:
            raise ValueError("initial key anchor cannot have a predecessor digest")
        if self.key_epoch > 1 and self.previous_key_anchor_digest is None:
            raise ValueError("rotated key anchor requires the predecessor anchor digest")
        if self.revocation_epoch == 1 and self.previous_revocation_list_digest is not None:
            raise ValueError("initial authority anchor cannot have a previous list digest")
        if self.revocation_epoch > 1 and self.previous_revocation_list_digest is None:
            raise ValueError("advanced authority anchor requires the previous list digest")
        return self


class OracleExecutionResult(V31Model):
    outcome: OracleOutcome
    raw_evidence_artifact_hashes: list[Digest] = Field(min_length=1, max_length=128)
    native_disposition: NativeDisposition
    value_disposition: ValueDisposition
    engineering_ceiling: EngineeringCeiling
    commercial_ceiling: CommercialCeiling

    @field_validator("raw_evidence_artifact_hashes")
    @classmethod
    def unique_execution_hashes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("oracle execution hashes must be unique")
        return value


class ActivationRequest(V31Model):
    request_id: Identifier
    nonce: str = Field(min_length=16, max_length=256)
    verified_main_sha: GitSha
    machine_environment_digest: Digest
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    controller_binary_digest: Digest
    controller_config_digest: Digest
    machine_environment_path: RelativePath
    controller_binary_path: RelativePath
    controller_config_path: RelativePath
    machine_policy_receipt: MachinePolicyReceipt
    mode: ActivationMode


class ObservedMainReceipt(V31Model):
    observation_id: Identifier
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    verified_main_sha: GitSha
    verified_main_tree_sha: GitSha
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    ruleset_observation_digest: Digest
    required_check_digests: dict[Identifier, Digest] = Field(min_length=1, max_length=64)
    github_app_id: int = Field(gt=0)
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    issuer_id: Identifier
    issuer_key_id: Identifier
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_observation_lifetime(self) -> ObservedMainReceipt:
        lifetime = self.expires_at.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=30):
            raise ValueError("observed-main lifetime must be positive and at most thirty minutes")
        return self


class RulesetObservationReceipt(V31Model):
    observation_id: Identifier
    observation_digest: Digest
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_branch: Literal["main"]
    ruleset_id: int = Field(gt=0)
    enforcement: Literal["active"]
    required_check_app_ids: dict[str, int] = Field(min_length=1, max_length=64)
    bypass_actor_count: Literal[0]
    deletion_forbidden: Literal[True]
    force_push_forbidden: Literal[True]
    pull_request_required: Literal[True]
    branch_update_restricted: Literal[True]
    auto_merge_enabled: Literal[True]
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    issuer_id: Identifier
    issuer_key_id: Identifier
    signature_algorithm: Literal["ed25519"]
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_ruleset_lifetime(self) -> RulesetObservationReceipt:
        from .canonical import canonical_json_bytes, sha256_digest

        lifetime = self.expires_at.astimezone(UTC) - self.observed_at.astimezone(UTC)
        if lifetime <= timedelta(0) or lifetime > timedelta(minutes=30):
            raise ValueError(
                "ruleset observation lifetime must be positive and at most thirty minutes"
            )
        core = {
            "repository": self.repository,
            "baseBranch": self.base_branch,
            "rulesetId": self.ruleset_id,
            "enforcement": self.enforcement,
            "requiredCheckAppIds": self.required_check_app_ids,
            "bypassActorCount": self.bypass_actor_count,
            "deletionForbidden": self.deletion_forbidden,
            "forcePushForbidden": self.force_push_forbidden,
            "pullRequestRequired": self.pull_request_required,
            "branchUpdateRestricted": self.branch_update_restricted,
            "autoMergeEnabled": self.auto_merge_enabled,
        }
        if self.observation_digest != sha256_digest(canonical_json_bytes(core)):
            raise ValueError("ruleset observation digest does not bind the exact policy")
        return self


class ActivationSelectionEnvelope(V31Model):
    activation_request: ActivationRequest
    observed_main: ObservedMainReceipt


class ActivationReceipt(V31Model):
    receipt_id: Identifier
    verified_main_sha: GitSha
    machine_environment_digest: Digest
    source_generation_id: SourceGenerationId
    source_generation_digest: Digest
    controller_binary_digest: Digest
    controller_config_digest: Digest
    machine_environment_path: RelativePath
    controller_binary_path: RelativePath
    controller_config_path: RelativePath
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
    signature: str = Field(min_length=80, max_length=128)

    @model_validator(mode="after")
    def validate_activation_lifetime(self) -> ActivationReceipt:
        lifetime = self.expires_at.astimezone(UTC) - self.issued_at.astimezone(UTC)
        if lifetime <= timedelta(0) or lifetime > timedelta(hours=1):
            raise ValueError("activation lifetime must be positive and at most one hour")
        return self


class CheckAuthorization(V31Model):
    check_name: Literal["TrainCapsule / Machine policy"]
    candidate_sha: GitSha
    conclusion: Literal["success"]
    receipt_id: Identifier
    receipt_digest: Digest


class ActivationAuthorization(V31Model):
    verified: Literal[True]
    verified_main_sha: GitSha
    activation_receipt_id: Identifier
    activation_receipt_digest: Digest


class InstallationState(StrEnum):
    STAGED_NOT_ACTIVATED = "STAGED_NOT_ACTIVATED"
    READY = "READY"


class InstallationAttestation(V31Model):
    installation_root: str
    verifier_distribution_digest: Digest
    public_key_fingerprint: Digest
    expected_owner_uid: int = Field(ge=0)
    checked_paths: dict[str, str] = Field(min_length=1, max_length=32)
    missing_private_inputs: list[str] = Field(max_length=16)
    authority_validated: bool
    live_oracle_verified: bool
    live_service_verified: bool
    state: InstallationState
