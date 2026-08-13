"""Candidate-bound TrainCheck differential derived from raw incident contracts.

The record contains no caller-authored verdict.  The controller/verifier derives the
decision differential by replaying canonical invariant observations from content-
addressed bytes and requiring a separately verified machine-policy receipt to bind
the exact candidate and oracle result.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol, cast

from pydantic import Field

from tcfactory.v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from tcfactory.v3.contracts_v31 import MachinePolicyReceiptV31, PolicyDecision


class InvariantState(StrEnum):
    HOLDS = "HOLDS"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


class IncidentInvariantObservation(V3Model):
    invariant_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    state: InvariantState
    evidence_digest: str = Field(pattern=DIGEST_PATTERN.pattern)


class IncidentContract(V3Model):
    contract_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    incident_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    source_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    required_invariant_ids: list[str] = Field(min_length=1, max_length=128)


class TrainCheckDifferentialRequest(V3Model):
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    traincheck_tool_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    incident_contract_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    baseline_observation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    candidate_observation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    independent_oracle_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")


class TrainCheckDifferentialResult(V3Model):
    work_item_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    request_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    traincheck_tool_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    contract_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    baseline_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    candidate_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    oracle_id: str
    oracle_result_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    changed_operational_decision: bool
    baseline_decision: str
    candidate_decision: str
    limitations: list[str] = Field(min_length=1, max_length=32)


class TrainCheckArtifactReader(Protocol):
    def read_exact(self, digest: str) -> bytes: ...


class TrainCheckOracleReceiptVerifier(Protocol):
    def verify(
        self,
        *,
        work_item_id: str,
        candidate_sha: str,
        candidate_tree_sha: str,
        request_digest: str,
        oracle_id: str,
        oracle_result_digest: str,
        bound_artifact_digests: list[str],
    ) -> str: ...


class VerifiedMachineReceiptTrainCheckOracle:
    """Adapter over a receipt already verified by the independent public client."""

    def __init__(self, receipt: MachinePolicyReceiptV31) -> None:
        self.receipt = receipt

    def verify(
        self,
        *,
        work_item_id: str,
        candidate_sha: str,
        candidate_tree_sha: str,
        request_digest: str,
        oracle_id: str,
        oracle_result_digest: str,
        bound_artifact_digests: list[str],
    ) -> str:
        receipt = self.receipt
        if (
            receipt.decision is not PolicyDecision.PASS
            or receipt.work_item_id != work_item_id
            or receipt.candidate_sha != candidate_sha
            or receipt.candidate_tree_sha != candidate_tree_sha
            or oracle_id not in receipt.independent_oracle_ids
            or not set(bound_artifact_digests).issubset(
                receipt.raw_evidence_artifact_hashes
            )
        ):
            raise ValueError("machine receipt does not bind the exact TrainCheck replay")
        return oracle_result_digest


def evaluate_traincheck_differential(
    request: TrainCheckDifferentialRequest,
    *,
    candidate_sha: str,
    candidate_tree_sha: str,
    artifacts: TrainCheckArtifactReader,
    receipt_verifier: TrainCheckOracleReceiptVerifier,
) -> TrainCheckDifferentialResult:
    result = replay_traincheck_differential(
        request,
        candidate_sha=candidate_sha,
        candidate_tree_sha=candidate_tree_sha,
        artifacts=artifacts,
    )
    authorize_traincheck_differential(result, receipt_verifier=receipt_verifier)
    return result


def replay_traincheck_differential(
    request: TrainCheckDifferentialRequest,
    *,
    candidate_sha: str,
    candidate_tree_sha: str,
    artifacts: TrainCheckArtifactReader,
) -> TrainCheckDifferentialResult:
    """Derive the exact result before the final candidate manifest is frozen."""

    contract_raw = _read_digest(artifacts, request.incident_contract_digest)
    baseline_raw = _read_digest(artifacts, request.baseline_observation_digest)
    candidate_raw = _read_digest(artifacts, request.candidate_observation_digest)
    _read_digest(artifacts, request.traincheck_tool_digest)
    try:
        contract = IncidentContract.model_validate_json(contract_raw, strict=True)
        baseline = _observations(baseline_raw)
        candidate = _observations(candidate_raw)
    except ValueError as exc:
        raise ValueError("TrainCheck incident differential input is invalid") from exc
    required = set(contract.required_invariant_ids)
    if set(baseline) != required or set(candidate) != required:
        raise ValueError("TrainCheck observations do not exactly cover incident invariants")
    if any(
        value.state is InvariantState.UNKNOWN
        for value in (*baseline.values(), *candidate.values())
    ):
        raise ValueError("TrainCheck differential is UNKNOWN for a required invariant")
    baseline_decision = _operational_decision(baseline)
    candidate_decision = _operational_decision(candidate)
    oracle_payload = {
        "contractDigest": request.incident_contract_digest,
        "baselineDigest": request.baseline_observation_digest,
        "candidateDigest": request.candidate_observation_digest,
        "baselineDecision": baseline_decision,
        "candidateDecision": candidate_decision,
    }
    oracle_digest = sha256_digest(
        (json.dumps(oracle_payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    )
    request_digest = request.canonical_digest()
    return TrainCheckDifferentialResult(
        work_item_id=request.work_item_id,
        candidate_sha=candidate_sha,
        candidate_tree_sha=candidate_tree_sha,
        request_digest=request_digest,
        traincheck_tool_digest=request.traincheck_tool_digest,
        contract_digest=request.incident_contract_digest,
        baseline_digest=request.baseline_observation_digest,
        candidate_digest=request.candidate_observation_digest,
        oracle_id=request.independent_oracle_id,
        oracle_result_digest=oracle_digest,
        changed_operational_decision=baseline_decision != candidate_decision,
        baseline_decision=baseline_decision,
        candidate_decision=candidate_decision,
        limitations=[
            "This candidate-bound differential is not payment, adoption, GPU, or commercial proof."
        ],
    )


def authorize_traincheck_differential(
    result: TrainCheckDifferentialResult,
    *,
    receipt_verifier: TrainCheckOracleReceiptVerifier,
) -> None:
    """Authorize a frozen result without accepting a caller-authored verdict."""

    verified_digest = receipt_verifier.verify(
        work_item_id=result.work_item_id,
        candidate_sha=result.candidate_sha,
        candidate_tree_sha=result.candidate_tree_sha,
        request_digest=result.request_digest,
        oracle_id=result.oracle_id,
        oracle_result_digest=result.oracle_result_digest,
        bound_artifact_digests=[
            result.request_digest,
            result.traincheck_tool_digest,
            result.contract_digest,
            result.baseline_digest,
            result.candidate_digest,
            result.oracle_result_digest,
            result.canonical_digest(),
        ],
    )
    if verified_digest != result.oracle_result_digest:
        raise ValueError("TrainCheck oracle receipt does not bind the derived result")


def _read_digest(reader: TrainCheckArtifactReader, digest: str) -> bytes:
    raw = reader.read_exact(digest)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("TrainCheck content-addressed artifact digest mismatch")
    return raw


def _observations(raw: bytes) -> Mapping[str, IncidentInvariantObservation]:
    value: object = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("TrainCheck observation roster must be a list")
    entries = cast(list[object], value)
    observations: list[IncidentInvariantObservation] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("TrainCheck observation entries must be objects")
        observations.append(
            IncidentInvariantObservation.model_validate_json(
                json.dumps(item, separators=(",", ":"), sort_keys=True), strict=True
            )
        )
    roster = {item.invariant_id: item for item in observations}
    if len(roster) != len(observations):
        raise ValueError("TrainCheck invariant observations must be unique")
    return roster


def _operational_decision(
    observations: Mapping[str, IncidentInvariantObservation],
) -> str:
    return (
        "REJECT_CANDIDATE"
        if any(item.state is InvariantState.VIOLATED for item in observations.values())
        else "ACCEPT_CANDIDATE"
    )


TRAINCHECK_CONTRACTS: dict[str, type[V3Model]] = {
    "incident-contract": IncidentContract,
    "incident-invariant-observation": IncidentInvariantObservation,
    "traincheck-differential-request": TrainCheckDifferentialRequest,
    "traincheck-differential-result": TrainCheckDifferentialResult,
}


__all__ = [
    "IncidentContract",
    "IncidentInvariantObservation",
    "InvariantState",
    "TRAINCHECK_CONTRACTS",
    "TrainCheckDifferentialRequest",
    "TrainCheckDifferentialResult",
    "VerifiedMachineReceiptTrainCheckOracle",
    "evaluate_traincheck_differential",
]
