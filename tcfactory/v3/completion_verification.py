"""Independent, content-derived verification for completion-only assertions."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field

from tcfactory.util import run_command, sanitized_subprocess_env, sha256_file

from .base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .candidate_manifest import CandidateManifest
from .completion_artifacts import DeliveryEconomicsEvidence, ReductionBoundaryEvidence
from .contracts_v31 import ActivationMode, ActivationReceiptV31
from .external_evidence import ExternalEvidenceReceipt
from .installed_runtime import InstalledControllerRuntimeManifest
from .publication import ExternalReceiptAuthorizer, PublicationError


class CompletionVerificationError(RuntimeError):
    """Completion evidence could not be derived at its trusted boundary."""


class ExactArtifactReader(Protocol):
    def read_exact(self, digest: str) -> bytes: ...


class DescriptorBoundArtifactReader:
    """Read checkpoint artifacts without following a pathname outside one root FD."""

    def __init__(self, root: Path, bindings: Mapping[str, Path]) -> None:
        self._root = root.resolve()
        self._bindings = dict(bindings)

    def read_exact(self, digest: str) -> bytes:
        path = self._bindings.get(digest)
        if path is None:
            raise CompletionVerificationError("required raw artifact is not bound")
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self._root)
        except ValueError as exc:
            raise CompletionVerificationError("raw artifact escaped its trusted root") from exc
        parts = PurePosixPath(relative.as_posix()).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise CompletionVerificationError("raw artifact path is invalid")
        root_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        current_fd = root_fd
        try:
            for part in parts[:-1]:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
                if current_fd != root_fd:
                    os.close(current_fd)
                current_fd = next_fd
            file_fd = os.open(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current_fd
            )
            try:
                metadata = os.fstat(file_fd)
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16 * 1024 * 1024:
                    raise CompletionVerificationError("raw artifact is unsafe")
                raw = b""
                while len(raw) <= 16 * 1024 * 1024:
                    chunk = os.read(file_fd, min(65_536, 16 * 1024 * 1024 + 1 - len(raw)))
                    if not chunk:
                        break
                    raw += chunk
            finally:
                os.close(file_fd)
        finally:
            if current_fd != root_fd:
                os.close(current_fd)
            os.close(root_fd)
        if sha256_digest(raw) != digest:
            raise CompletionVerificationError("raw artifact digest changed")
        return raw


class ReductionOracleDecision(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    work_item_id: Literal["V3-TRUST-005"]
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    raw_artifact_roster_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    oracle_executable_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    legal_reduction_artifact_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    legal_reduction_verdict: Literal["VERIFIED"]
    illegal_reduction_artifact_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    illegal_reduction_verdict: Literal["REJECTED"]
    oracle_result_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    receipt_id: str = Field(pattern=r"^REDUCE-[A-Z0-9_-]{8,128}$")
    issued_at: datetime
    expires_at: datetime
    nonce: str = Field(pattern=r"^[0-9a-f]{32,128}$")
    signature: str = Field(pattern=r"^[0-9a-f]{128}$")

    def result_payload(self) -> dict[str, object]:
        return self.model_dump(
            mode="json",
            by_alias=True,
            exclude={
                "oracle_result_digest",
                "receipt_id",
                "issued_at",
                "expires_at",
                "nonce",
                "signature",
            },
        )

    def signature_payload(self) -> bytes:
        return (
            json.dumps(
                self.model_dump(mode="json", by_alias=True, exclude={"signature"}),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()


class ReductionCandidateInput(V3Model):
    """Raw reduction graph presented to the independent oracle."""

    schema_version: Literal["3.1"] = "3.1"
    reduction_class: Literal["LEGAL_CANDIDATE", "ILLEGAL_CANDIDATE"]
    original_rank_ids: list[int] = Field(min_length=2, max_length=100_000)
    retained_rank_ids: list[int] = Field(min_length=1, max_length=100_000)
    collective_participants: dict[str, list[int]] = Field(min_length=1, max_length=10_000)
    omitted_required_dependency_ids: list[str] = Field(max_length=100_000)


class ExecutableReductionOracle:
    """Run a pinned outside oracle and validate its signed exact decision."""

    def __init__(
        self,
        executable: Path,
        executable_digest: str,
        public_key: Path,
        public_key_digest: str,
    ) -> None:
        self.executable = executable
        self.executable_digest = executable_digest
        self.public_key = public_key
        self.public_key_digest = public_key_digest

    def evaluate(
        self,
        evidence: ReductionBoundaryEvidence,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        artifacts: ExactArtifactReader,
        now: datetime,
    ) -> tuple[ReductionOracleDecision, bytes]:
        raw = {digest: artifacts.read_exact(digest) for digest in evidence.raw_artifact_digests}
        roster = sha256_digest((json.dumps(sorted(raw), separators=(",", ":")) + "\n").encode())
        observed_executable = f"sha256:{sha256_file(self.executable)}"
        if observed_executable != self.executable_digest:
            raise CompletionVerificationError("reduction oracle executable changed")
        request = {
            "schemaVersion": "3.1",
            "workItemId": evidence.work_item_id,
            "candidateSha": candidate_sha,
            "candidateTreeSha": candidate_tree_sha,
            "rawArtifactRosterDigest": roster,
            "oracleExecutableDigest": observed_executable,
            "legalReductionArtifactDigest": evidence.legal_reduction_artifact_digest,
            "illegalReductionArtifactDigest": evidence.illegal_reduction_artifact_digest,
            "artifacts": {digest: value.hex() for digest, value in sorted(raw.items())},
        }
        result = run_command(
            [str(self.executable), "evaluate-reduction"],
            cwd=self.executable.parent,
            check=False,
            timeout=30,
            env=sanitized_subprocess_env(),
            input_text=json.dumps(request, sort_keys=True, separators=(",", ":")),
        )
        if result.returncode != 0 or len(result.stdout.encode()) > 65_536:
            raise CompletionVerificationError("reduction oracle rejected raw evidence")
        try:
            decision = ReductionOracleDecision.model_validate_json(
                result.stdout.encode(), strict=True
            )
        except ValueError as exc:
            raise CompletionVerificationError("reduction oracle response is invalid") from exc
        expected_result = sha256_digest(
            (
                json.dumps(decision.result_payload(), sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        )
        if (
            decision.work_item_id != evidence.work_item_id
            or decision.candidate_sha != candidate_sha
            or decision.candidate_tree_sha != candidate_tree_sha
            or decision.raw_artifact_roster_digest != roster
            or decision.oracle_executable_digest != observed_executable
            or decision.legal_reduction_artifact_digest != evidence.legal_reduction_artifact_digest
            or decision.illegal_reduction_artifact_digest
            != evidence.illegal_reduction_artifact_digest
            or decision.oracle_result_digest != expected_result
            or evidence.oracle_result_digest != expected_result
            or evidence.oracle_executable_digest != observed_executable
            or decision.issued_at > now
            or now >= decision.expires_at
        ):
            raise CompletionVerificationError("reduction oracle decision binding mismatch")
        key_raw = self.public_key.read_bytes()
        if sha256_digest(key_raw) != self.public_key_digest:
            raise CompletionVerificationError("reduction oracle public key changed")
        try:
            Ed25519PublicKey.from_public_bytes(key_raw).verify(
                bytes.fromhex(decision.signature), decision.signature_payload()
            )
        except (ValueError, InvalidSignature) as exc:
            raise CompletionVerificationError("reduction oracle signature is invalid") from exc
        return decision, result.stdout.encode()


class AuthorizedReductionDecision(V3Model):
    decision: ReductionOracleDecision
    decision_file_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    machine_policy_receipt_id: str
    machine_policy_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


def evaluate_installed_reduction_oracle(
    evidence: ReductionBoundaryEvidence,
    *,
    installed_runtime: InstalledControllerRuntimeManifest,
    candidate_manifest_path: Path,
    candidate_sha: str,
    candidate_tree_sha: str,
    base_sha: str,
    source_generation_id: str,
    source_generation_digest: str,
    artifacts: ExactArtifactReader,
    now: datetime,
) -> tuple[AuthorizedReductionDecision, bytes]:
    """Execute only the installed oracle and verify its public Phase-3 authority."""

    installation = installed_runtime.reduction_oracle
    if installation is None:
        raise CompletionVerificationError("reduction oracle installation is unavailable")
    try:
        manifest_raw = candidate_manifest_path.read_bytes()
        manifest = CandidateManifest.model_validate_json(manifest_raw, strict=True)
    except (OSError, ValueError) as exc:
        raise CompletionVerificationError("reduction candidate manifest is unavailable") from exc
    if manifest_raw != manifest.canonical_json_bytes():
        raise CompletionVerificationError("reduction candidate manifest is not canonical")
    manifest_digest = sha256_digest(manifest_raw)
    if (
        manifest.work_item_id != evidence.work_item_id
        or manifest.candidate_sha != candidate_sha
        or manifest.base_sha != base_sha
    ):
        raise CompletionVerificationError("reduction candidate manifest identity mismatch")
    decision, raw = ExecutableReductionOracle(
        Path(installation.executable.path),
        installation.executable.digest,
        Path(installation.public_key.path),
        installation.public_key.digest,
    ).evaluate(
        evidence,
        candidate_sha=candidate_sha,
        candidate_tree_sha=candidate_tree_sha,
        artifacts=artifacts,
        now=now,
    )
    decision_file_digest = sha256_digest(raw)
    receipt_path = (
        Path(installation.public_receipt_root)
        / "machine-policy"
        / evidence.work_item_id
        / f"{candidate_sha}.json"
    )
    authority = ExternalReceiptAuthorizer(Path(installation.receipt_verifier.path))
    try:
        authorized = authority.authorize(
            receipt_path,
            candidate_sha=candidate_sha,
            candidate_tree_sha=candidate_tree_sha,
            base_sha=base_sha,
            work_item_id=evidence.work_item_id,
            candidate_manifest_digest=manifest_digest,
        )
    except (OSError, PublicationError) as exc:
        raise CompletionVerificationError(
            "reduction machine-policy receipt is stale, revoked, or invalid"
        ) from exc
    receipt = authorized.receipt
    expected_raw = set(evidence.raw_artifact_digests) | {
        installation.executable.digest,
        installation.public_key.digest,
        decision_file_digest,
    }
    if (
        receipt.source_generation_id != source_generation_id
        or receipt.source_generation_digest != source_generation_digest
        or receipt.independent_oracle_ids != [installation.oracle_id]
        or set(receipt.raw_evidence_artifact_hashes) != expected_raw
        or set(receipt.allowed_claims)
        != {"LEGAL_REDUCTION_VERIFIED", "ILLEGAL_REDUCTION_REJECTED"}
    ):
        raise CompletionVerificationError(
            "reduction machine-policy receipt does not bind the exact oracle result"
        )
    activation_path = Path(installation.activation_receipt_path)
    try:
        authority.verify_activation(
            activation_path,
            expected_main_sha=installed_runtime.repository_main_sha,
            source_generation_id=source_generation_id,
            source_generation_digest=source_generation_digest,
            controller_binary_digest=installed_runtime.package_manifest.digest,
            controller_config_digest=installed_runtime.effective_config.digest,
        )
        activation = ActivationReceiptV31.model_validate_json(
            activation_path.read_bytes(), strict=True
        )
    except (OSError, PublicationError, ValueError) as exc:
        raise CompletionVerificationError(
            "reduction LIVE activation is stale, revoked, or invalid"
        ) from exc
    if (
        activation.mode is not ActivationMode.LIVE
        or activation.machine_policy_receipt_id != receipt.receipt_id
        or activation.machine_policy_receipt_digest != receipt.canonical_digest()
    ):
        raise CompletionVerificationError(
            "reduction LIVE activation does not authorize the exact receipt"
        )
    return (
        AuthorizedReductionDecision(
            decision=decision,
            decision_file_digest=decision_file_digest,
            machine_policy_receipt_id=receipt.receipt_id,
            machine_policy_receipt_digest=receipt.canonical_digest(),
            activation_receipt_digest=activation.canonical_digest(),
        ),
        raw,
    )


class DeliveryMeasurement(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    phase: Literal["ORIGINAL", "PROPOSED"]
    customer_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    offer_identity_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    setup_minutes: int = Field(ge=0, le=1_000_000)
    delivery_minutes: int = Field(ge=0, le=1_000_000)
    cost_microusd: int = Field(ge=0, le=10**15)
    revenue_microusd: int = Field(gt=0, le=10**15)

    @property
    def margin_basis_points(self) -> int:
        return ((self.revenue_microusd - self.cost_microusd) * 10_000) // self.revenue_microusd


def verify_delivery_economics(
    evidence: DeliveryEconomicsEvidence,
    *,
    artifacts: ExactArtifactReader,
    receipt: ExternalEvidenceReceipt,
) -> list[DeliveryMeasurement]:
    measurements = [
        DeliveryMeasurement.model_validate_json(artifacts.read_exact(digest), strict=True)
        for digest in evidence.source_record_digests
    ]
    by_phase = {value.phase: value for value in measurements}
    if set(by_phase) != {"ORIGINAL", "PROPOSED"}:
        raise CompletionVerificationError(
            "delivery economics requires original and proposed records"
        )
    original = by_phase["ORIGINAL"]
    proposed = by_phase["PROPOSED"]
    correlation = receipt.correlation_identity
    if correlation is None:
        raise CompletionVerificationError("delivery economics receipt lacks correlation identity")
    expected = {
        "customer": evidence.customer_identity_digest,
        "offer": evidence.offer_identity_digest,
    }
    for value in measurements:
        if (
            value.customer_identity_digest != expected["customer"]
            or value.offer_identity_digest != expected["offer"]
        ):
            raise CompletionVerificationError("delivery measurement identity mismatch")
    if (
        receipt.evidence_type.value != "DELIVERY_ECONOMICS"
        or receipt.subject_id != evidence.work_item_id
        or correlation.candidate_sha != evidence.evidence_basis_sha
        or receipt.canonical_digest() != evidence.signed_external_receipt_digest
        or correlation.customer_identity_digest != expected["customer"]
        or correlation.offer_identity_digest != expected["offer"]
        or set(evidence.source_record_digests) - {artifact.digest for artifact in receipt.artifacts}
    ):
        raise CompletionVerificationError("delivery receipt does not bind its source records")
    derived = (
        original.setup_minutes,
        proposed.setup_minutes,
        original.delivery_minutes,
        proposed.delivery_minutes,
        original.cost_microusd,
        proposed.cost_microusd,
        original.margin_basis_points,
        proposed.margin_basis_points,
    )
    claimed = (
        evidence.original_setup_minutes,
        evidence.proposed_setup_minutes,
        evidence.original_delivery_minutes,
        evidence.proposed_delivery_minutes,
        evidence.original_cost_microusd,
        evidence.proposed_cost_microusd,
        evidence.original_margin_basis_points,
        evidence.proposed_margin_basis_points,
    )
    if claimed != derived:
        raise CompletionVerificationError("delivery economics does not equal its raw records")
    return measurements
