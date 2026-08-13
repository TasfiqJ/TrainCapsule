"""Fail-closed runtime bridge for independently authorized native/value transitions.

The controller may consume the returned transition, but it cannot construct one: every
candidate artifact is bound by the signed candidate manifest, the machine-policy receipt
is verified by the separately installed Phase 3 client, and LIVE activation must link the
same receipt.  This module deliberately does not mutate the queue or maturity state.
"""

from __future__ import annotations

import hashlib
import stat
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import Field, ValidationError

from tcfactory.v3.candidate_manifest import CandidateManifest
from tcfactory.v3.contracts_v31 import (
    ActivationMode,
    ActivationReceiptV31,
    DecisionValueResultV31,
    MachinePolicyReceiptV31,
    NativeSubstituteBenchmarkV31,
    SourceFreshnessReceiptV31,
    V31Model,
)
from tcfactory.v3.native_value_gate import (
    ArtifactReader,
    AuthorizedValueTransitionV31,
    FreshnessReceiptVerifier,
    MachineReceiptVerifier,
    NativeValueGateError,
    NativeValueGatePolicyV31,
    authorize_value_transition,
    evaluate_native_value_candidate,
)
from tcfactory.v3.publication import ExternalReceiptAuthorizer, PublicationError

BENCHMARK_FILE = "native-substitute-benchmark.json"
VALUE_RESULT_FILE = "decision-value-result.json"
POLICY_FILE = "native-value-gate-policy.json"
FRESHNESS_DIRECTORY = "source-freshness"
BENCHMARK_BINDING = "native-value-runtime/native-substitute-benchmark.json"
VALUE_RESULT_BINDING = "native-value-runtime/decision-value-result.json"
POLICY_BINDING = "native-value-runtime/native-value-gate-policy.json"


class NativeValueRuntimeError(RuntimeError):
    """The runtime artifact set or independent authority failed closed."""


class RuntimeAuthorizedNativeValueV31(V31Model):
    transition: AuthorizedValueTransitionV31
    machine_receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    candidate_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    freshness_receipt_digests: list[str] = Field(min_length=1, max_length=64)
    raw_artifact_digests: list[str] = Field(min_length=1, max_length=256)

    def completion_evidence_refs(self) -> list[str]:
        transition = self.transition
        return [
            f"candidate-manifest:{self.candidate_manifest_digest}",
            f"machine-policy-receipt:{transition.machine_receipt_digest}",
            f"native-benchmark:{transition.benchmark_digest}",
            f"decision-value:{transition.value_result_digest}",
            f"native-policy:{self.policy_digest}",
            f"activation-receipt:{self.activation_receipt_digest}",
            *(f"source-freshness:{digest}" for digest in self.freshness_receipt_digests),
            *(f"raw-artifact:{digest}" for digest in self.raw_artifact_digests),
        ]


class Phase3NativeValueAuthority(Protocol):
    def verify_machine_receipt(
        self,
        receipt_path: Path,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
    ) -> MachinePolicyReceiptV31: ...

    def verify_activation(
        self,
        activation_path: Path,
        *,
        expected_main_sha: str,
        source_generation_id: str,
        source_generation_digest: str,
        controller_binary_digest: str,
        controller_config_digest: str,
    ) -> ActivationReceiptV31: ...


class ExternalPhase3NativeValueAuthority:
    """Adapter over the public Phase 3 verifier client; no private oracle import."""

    def __init__(self, executable: Path) -> None:
        self._client = ExternalReceiptAuthorizer(executable)

    def verify_machine_receipt(
        self,
        receipt_path: Path,
        *,
        candidate_sha: str,
        candidate_tree_sha: str,
        base_sha: str,
        work_item_id: str,
        candidate_manifest_digest: str,
    ) -> MachinePolicyReceiptV31:
        try:
            return self._client.authorize(
                receipt_path,
                candidate_sha=candidate_sha,
                candidate_tree_sha=candidate_tree_sha,
                base_sha=base_sha,
                work_item_id=work_item_id,
                candidate_manifest_digest=candidate_manifest_digest,
            ).receipt
        except (FileNotFoundError, PublicationError, ValidationError) as exc:
            raise NativeValueRuntimeError("Phase 3 machine-policy receipt was rejected") from exc

    def verify_activation(
        self,
        activation_path: Path,
        *,
        expected_main_sha: str,
        source_generation_id: str,
        source_generation_digest: str,
        controller_binary_digest: str,
        controller_config_digest: str,
    ) -> ActivationReceiptV31:
        try:
            authorization = self._client.verify_activation(
                activation_path,
                expected_main_sha=expected_main_sha,
                source_generation_id=source_generation_id,
                source_generation_digest=source_generation_digest,
                controller_binary_digest=controller_binary_digest,
                controller_config_digest=controller_config_digest,
            )
            raw = _read_stable_regular(activation_path, label="activation receipt")
            receipt = ActivationReceiptV31.model_validate_json(raw, strict=True)
        except (FileNotFoundError, PublicationError, ValidationError) as exc:
            raise NativeValueRuntimeError("Phase 3 activation receipt was rejected") from exc
        if authorization.activation_receipt_digest != receipt.canonical_digest():
            raise NativeValueRuntimeError("activation authorization digest mismatch")
        return receipt


class ContentAddressedRuntimeArtifacts(ArtifactReader):
    """Strict read-only convention: ``ROOT/sha256/<64 lowercase hex>``."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir() or self.root.is_symlink():
            raise NativeValueRuntimeError("raw artifact store must be a regular directory")

    def read_exact(self, digest: str) -> bytes:
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise NativeValueRuntimeError("raw artifact digest has the wrong shape")
        hexadecimal = digest.removeprefix("sha256:")
        if any(character not in "0123456789abcdef" for character in hexadecimal):
            raise NativeValueRuntimeError("raw artifact digest is not canonical lowercase hex")
        path = self.root / "sha256" / hexadecimal
        raw = _read_stable_regular(path, label="raw evidence artifact")
        if f"sha256:{hashlib.sha256(raw).hexdigest()}" != digest:
            raise NativeValueRuntimeError("raw evidence artifact was substituted")
        return raw


class _AlreadyVerifiedReceipt(MachineReceiptVerifier):
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> None:
        if receipt.canonical_digest() != self.digest:
            raise NativeValueRuntimeError("machine-policy receipt changed after verification")
        if receipt.expires_at.astimezone(UTC) <= now:
            raise NativeValueRuntimeError("machine-policy receipt expired after verification")


class _ReceiptBoundFreshness(FreshnessReceiptVerifier):
    def __init__(self, digests: Sequence[str]) -> None:
        self.digests = frozenset(digests)

    def verify(self, receipt: SourceFreshnessReceiptV31, *, now: datetime) -> None:
        del now
        if receipt.canonical_digest() not in self.digests:
            raise NativeValueRuntimeError(
                "freshness receipt is not bound by the independently verified policy receipt"
            )


def load_authorized_native_value_transition(
    *,
    artifact_directory: Path,
    candidate_manifest_path: Path,
    raw_artifacts: ArtifactReader,
    receipt_root: Path,
    activation_path: Path,
    authority: Phase3NativeValueAuthority,
    freshness_verifier: FreshnessReceiptVerifier | None = None,
    work_item_id: str,
    candidate_sha: str,
    candidate_tree_sha: str,
    base_sha: str,
    expected_main_sha: str,
    source_generation_id: str,
    source_generation_digest: str,
    controller_binary_digest: str,
    controller_config_digest: str,
    now: datetime | None = None,
) -> RuntimeAuthorizedNativeValueV31:
    """Load one exact runtime bundle and return its independently authorized transition."""

    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    directory = artifact_directory.resolve(strict=True)
    expected_names = {
        BENCHMARK_FILE,
        VALUE_RESULT_FILE,
        POLICY_FILE,
        FRESHNESS_DIRECTORY,
    }
    if directory.is_symlink() or {path.name for path in directory.iterdir()} != expected_names:
        raise NativeValueRuntimeError(
            "native/value runtime directory violates the exact convention"
        )

    benchmark_raw = _read_stable_regular(directory / BENCHMARK_FILE, label="native benchmark")
    value_raw = _read_stable_regular(directory / VALUE_RESULT_FILE, label="decision value result")
    policy_raw = _read_stable_regular(directory / POLICY_FILE, label="native/value policy")
    manifest_raw = _read_stable_regular(candidate_manifest_path, label="candidate manifest")
    try:
        benchmark = NativeSubstituteBenchmarkV31.model_validate_json(benchmark_raw, strict=True)
        stored_value = DecisionValueResultV31.model_validate_json(value_raw, strict=True)
        policy = NativeValueGatePolicyV31.model_validate_json(policy_raw, strict=True)
        manifest = CandidateManifest.model_validate_json(manifest_raw, strict=True)
    except ValidationError as exc:
        raise NativeValueRuntimeError("native/value runtime contract is invalid") from exc
    canonical_inputs = (
        (benchmark_raw, benchmark.canonical_json_bytes(), "native benchmark"),
        (value_raw, stored_value.canonical_json_bytes(), "decision value result"),
        (policy_raw, policy.canonical_json_bytes(), "native/value policy"),
        (manifest_raw, manifest.canonical_json_bytes(), "candidate manifest"),
    )
    for raw, canonical, label in canonical_inputs:
        if raw != canonical:
            raise NativeValueRuntimeError(f"{label} bytes are not canonical JSON")

    if (
        benchmark.work_item_id != work_item_id
        or benchmark.candidate_sha != candidate_sha
        or benchmark.candidate_tree_sha != candidate_tree_sha
        or manifest.work_item_id != work_item_id
        or manifest.candidate_sha != candidate_sha
        or manifest.base_sha != base_sha
    ):
        raise NativeValueRuntimeError("runtime artifacts do not match the exact candidate identity")
    manifest_digest = _digest(manifest_raw)
    if _binding_digest(manifest, BENCHMARK_BINDING) != _digest(benchmark_raw):
        raise NativeValueRuntimeError("candidate manifest does not bind the exact native benchmark")
    if _binding_digest(manifest, VALUE_RESULT_BINDING) != _digest(value_raw):
        raise NativeValueRuntimeError("candidate manifest does not bind the exact value result")
    if _binding_digest(manifest, POLICY_BINDING) != _digest(policy_raw):
        raise NativeValueRuntimeError(
            "candidate manifest does not bind the exact native/value policy"
        )

    receipt_path = (
        receipt_root.resolve(strict=True)
        / "machine-policy"
        / work_item_id
        / f"{candidate_sha}.json"
    )
    receipt = authority.verify_machine_receipt(
        receipt_path,
        candidate_sha=candidate_sha,
        candidate_tree_sha=candidate_tree_sha,
        base_sha=base_sha,
        work_item_id=work_item_id,
        candidate_manifest_digest=manifest_digest,
    )
    if receipt.candidate_manifest_digest != manifest_digest:
        raise NativeValueRuntimeError("machine-policy receipt does not bind the candidate manifest")
    if (
        receipt.base_sha != base_sha
        or receipt.source_generation_id != source_generation_id
        or receipt.source_generation_digest != source_generation_digest
        or receipt.context_manifest_digest != manifest.context_digest
        or receipt.task_packet_digest != manifest.packet_digest
        or receipt.checkpoint_digest != manifest.checkpoint_digest
    ):
        raise NativeValueRuntimeError(
            "machine-policy receipt does not bind the exact candidate execution context"
        )
    manifest_gate_names = {binding.name for binding in manifest.gates}
    if set(receipt.required_gate_results) != manifest_gate_names or any(
        result.value != "PASS" for result in receipt.required_gate_results.values()
    ):
        raise NativeValueRuntimeError(
            "machine-policy receipt does not bind the exact passing candidate gates"
        )
    if not set(benchmark.source_freshness_receipts).issubset(receipt.raw_evidence_artifact_hashes):
        raise NativeValueRuntimeError(
            "machine-policy receipt does not bind every source freshness receipt"
        )

    activation = authority.verify_activation(
        activation_path,
        expected_main_sha=expected_main_sha,
        source_generation_id=source_generation_id,
        source_generation_digest=source_generation_digest,
        controller_binary_digest=controller_binary_digest,
        controller_config_digest=controller_config_digest,
    )
    if activation.mode is not ActivationMode.LIVE:
        raise NativeValueRuntimeError("native/value maturity transition requires LIVE activation")
    if (
        activation.machine_policy_receipt_id != receipt.receipt_id
        or activation.machine_policy_receipt_digest != receipt.canonical_digest()
    ):
        raise NativeValueRuntimeError("activation does not bind the verified machine receipt")

    freshness = _load_freshness_receipts(
        directory / FRESHNESS_DIRECTORY, benchmark.source_freshness_receipts
    )
    try:
        derived_value = evaluate_native_value_candidate(
            benchmark=benchmark,
            policy=policy,
            candidate_sha=candidate_sha,
            candidate_tree_sha=candidate_tree_sha,
            artifact_reader=raw_artifacts,
            freshness_receipts=freshness,
            freshness_verifier=(
                freshness_verifier
                if freshness_verifier is not None
                else _ReceiptBoundFreshness(receipt.raw_evidence_artifact_hashes)
            ),
            now=observed_now,
        )
        if derived_value.canonical_digest() != stored_value.canonical_digest():
            raise NativeValueRuntimeError("stored value decision differs from deterministic replay")
        transition = authorize_value_transition(
            benchmark=benchmark,
            value_result=derived_value,
            policy=policy,
            receipt=receipt,
            receipt_verifier=_AlreadyVerifiedReceipt(receipt.canonical_digest()),
            now=observed_now,
        )
        return RuntimeAuthorizedNativeValueV31(
            schema_version="3.1",
            transition=transition,
            machine_receipt_id=receipt.receipt_id,
            candidate_manifest_digest=manifest_digest,
            policy_digest=_digest(policy_raw),
            activation_receipt_digest=activation.canonical_digest(),
            freshness_receipt_digests=benchmark.source_freshness_receipts,
            raw_artifact_digests=benchmark.raw_artifact_hashes,
        )
    except NativeValueGateError as exc:
        raise NativeValueRuntimeError("native/value transition replay failed closed") from exc


def _load_freshness_receipts(
    root: Path, expected_digests: Sequence[str]
) -> list[SourceFreshnessReceiptV31]:
    if not root.is_dir() or root.is_symlink():
        raise NativeValueRuntimeError("source freshness directory is unavailable")
    expected_names = {f"{digest.removeprefix('sha256:')}.json" for digest in expected_digests}
    if {path.name for path in root.iterdir()} != expected_names:
        raise NativeValueRuntimeError("source freshness receipt roster differs from the benchmark")
    receipts: list[SourceFreshnessReceiptV31] = []
    for digest in expected_digests:
        raw = _read_stable_regular(
            root / f"{digest.removeprefix('sha256:')}.json", label="source freshness receipt"
        )
        try:
            receipt = SourceFreshnessReceiptV31.model_validate_json(raw, strict=True)
        except ValidationError as exc:
            raise NativeValueRuntimeError("source freshness receipt contract is invalid") from exc
        if receipt.canonical_digest() != digest:
            raise NativeValueRuntimeError("source freshness receipt was substituted")
        receipts.append(receipt)
    return receipts


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise NativeValueRuntimeError(f"{label} must be a regular non-symlink file")
    raw = path.read_bytes()
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ) or path.read_bytes() != raw:
        raise NativeValueRuntimeError(f"{label} changed while it was read")
    return raw


def _digest(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _binding_digest(manifest: CandidateManifest, name: str) -> str | None:
    matches = [binding.digest for binding in manifest.stage_outputs if binding.name == name]
    if len(matches) != 1:
        raise NativeValueRuntimeError(f"candidate manifest must bind exactly one {name}")
    return matches[0]


__all__ = [
    "BENCHMARK_BINDING",
    "BENCHMARK_FILE",
    "ContentAddressedRuntimeArtifacts",
    "ExternalPhase3NativeValueAuthority",
    "FRESHNESS_DIRECTORY",
    "NativeValueRuntimeError",
    "Phase3NativeValueAuthority",
    "POLICY_BINDING",
    "POLICY_FILE",
    "VALUE_RESULT_BINDING",
    "VALUE_RESULT_FILE",
    "RuntimeAuthorizedNativeValueV31",
    "load_authorized_native_value_transition",
]
