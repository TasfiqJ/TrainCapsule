"""Controller-side, write-only submission into the external verifier request bridge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from tcfactory.util import atomic_write_bytes

_IDENTIFIER = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
MAX_EVIDENCE_FILES = 129
MAX_EVIDENCE_BYTES = 100_000_000


class VerifierSubmissionError(RuntimeError):
    """Submission could not be staged without crossing the authority boundary."""


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _strict_object(raw: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise VerifierSubmissionError("verification request has a duplicate JSON key")
            result[key] = value
        return result

    try:
        parsed: object = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerifierSubmissionError("verification request is not strict JSON") from exc
    if not isinstance(parsed, dict):
        raise VerifierSubmissionError("verification request must be a JSON object")
    return cast(dict[str, object], parsed)


def _canonical_json(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _trusted_controller_outbox(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise VerifierSubmissionError(
            "verifier controller outbox must be an absolute real directory"
        )
    resolved = path.resolve(strict=True)
    observed = resolved.stat()
    if not stat.S_ISDIR(observed.st_mode) or observed.st_uid != os.geteuid():
        raise VerifierSubmissionError("verifier controller outbox owner/type mismatch")
    if observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise VerifierSubmissionError("verifier controller outbox cannot be group/world writable")
    return resolved


def _evidence_files(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise VerifierSubmissionError("verification evidence root is invalid")
    root = root.resolve(strict=True)
    payloads: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        observed = path.lstat()
        if path.is_dir() and not path.is_symlink():
            continue
        if path.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise VerifierSubmissionError("verification evidence must contain regular files only")
        if observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise VerifierSubmissionError("verification evidence cannot be group/world writable")
        data = path.read_bytes()
        total += len(data)
        payloads[relative] = data
        if len(payloads) > MAX_EVIDENCE_FILES or total > MAX_EVIDENCE_BYTES:
            raise VerifierSubmissionError("verification evidence exceeds its bounded size")
    if "evidence.json" not in payloads:
        raise VerifierSubmissionError("verification evidence manifest is missing")
    return payloads


def submit_verification_request(
    *,
    request_bytes: bytes,
    evidence_root: Path,
    controller_outbox: Path = Path("/var/lib/traincapsule-verifier/controller-outbox"),
) -> Path:
    """Atomically stage canonical bytes; the independent root broker decides admissibility."""

    payload = _strict_object(request_bytes)
    if request_bytes != _canonical_json(payload):
        raise VerifierSubmissionError("verification request bytes are not canonical")
    request_id = payload.get("requestId")
    if not isinstance(request_id, str) or _IDENTIFIER.fullmatch(request_id) is None:
        raise VerifierSubmissionError("verification request identity is invalid")
    outbox = _trusted_controller_outbox(controller_outbox)
    evidence = _evidence_files(evidence_root)
    evidence_name = f"{request_id}.evidence"
    request_name = f"{request_id}.request.json"
    final_evidence = outbox / evidence_name
    final_request = outbox / request_name
    if final_request.exists() or final_evidence.exists():
        if not final_request.is_file() or final_request.read_bytes() != request_bytes:
            raise VerifierSubmissionError(
                "verification request identity already has different bytes"
            )
        if final_evidence.is_symlink() or not final_evidence.is_dir():
            raise VerifierSubmissionError("verification evidence identity is invalid")
        observed = _evidence_files(final_evidence)
        if observed != evidence:
            raise VerifierSubmissionError(
                "verification evidence identity already has different bytes"
            )
        return final_request
    temporary = outbox / f".{evidence_name}.{os.getpid()}.tmp"
    try:
        temporary.mkdir(mode=0o700)
        for relative, data in evidence.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_bytes(target, data)
            target.chmod(0o600)
        os.replace(temporary, final_evidence)
        atomic_write_bytes(final_request, request_bytes)
        final_request.chmod(0o600)
        descriptor = os.open(outbox, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return final_request
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        if final_evidence.exists() and not final_request.exists():
            shutil.rmtree(final_evidence, ignore_errors=True)
        raise


def create_and_submit_verification_request(
    *,
    profile_path: Path,
    work_item_id: str,
    milestone_id: str,
    lane: str,
    candidate_sha: str,
    candidate_tree_sha: str,
    base_sha: str,
    source_generation_id: str,
    source_generation_digest: str,
    context_manifest_digest: str,
    task_packet_digest: str,
    candidate_manifest_digest: str,
    checkpoint_digest: str,
    gate_evidence: Mapping[str, Path],
    evidence_root: Path,
    controller_outbox: Path = Path("/var/lib/traincapsule-verifier/controller-outbox"),
    now: datetime | None = None,
) -> Path:
    """Create a policy-profiled request; the independent verifier still decides it."""

    if profile_path.is_symlink() or not profile_path.is_file():
        raise VerifierSubmissionError("external verification request profile is unavailable")
    profile = _strict_object(profile_path.read_bytes())
    if profile_path.read_bytes() != _canonical_json(profile):
        raise VerifierSubmissionError("external verification request profile is not canonical")
    required = {
        "schemaVersion",
        "riskTier",
        "requestedClaims",
        "publicationScope",
        "nativeDisposition",
        "valueDisposition",
        "engineeringCeiling",
        "commercialCeiling",
        "privateGateSuiteId",
        "privateGateRunnerDigest",
        "oracles",
    }
    if set(profile) != required or profile.get("schemaVersion") != "3.1":
        raise VerifierSubmissionError("external verification request profile shape is invalid")
    oracles = profile.get("oracles")
    if not isinstance(oracles, dict) or not oracles or not gate_evidence:
        raise VerifierSubmissionError("verification profile/gate evidence is incomplete")
    request_identity = _canonical_json(
        {
            "workItemId": work_item_id,
            "candidateSha": candidate_sha,
            "candidateTreeSha": candidate_tree_sha,
            "candidateManifestDigest": candidate_manifest_digest,
            "checkpointDigest": checkpoint_digest,
        }
    )
    identity_hash = hashlib.sha256(request_identity).hexdigest()
    request_id = f"REQUEST:{work_item_id}:{identity_hash[:24].upper()}"
    nonce = identity_hash
    evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    raw_artifacts: dict[str, dict[str, str]] = {}
    gates: dict[str, dict[str, str]] = {}
    raw_hashes: list[str] = []
    for index, (gate, source) in enumerate(sorted(gate_evidence.items()), 1):
        if source.is_symlink() or not source.is_file():
            raise VerifierSubmissionError(f"verification gate evidence is invalid: {gate}")
        data = source.read_bytes()
        digest = _digest(data)
        relative = f"raw/gate-{index:03d}.bin"
        target = evidence_root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_bytes(target, data)
        target.chmod(0o600)
        raw_artifacts[f"ARTIFACT:GATE:{index:03d}"] = {"path": relative, "digest": digest}
        gates[gate] = {
            "candidateSha": candidate_sha,
            "result": "PASS",
            "evidenceDigest": digest,
        }
        raw_hashes.append(digest)
    oracle_observations: dict[str, object] = {}
    for oracle_id, raw_binding in sorted(cast(dict[str, object], oracles).items()):
        if not isinstance(raw_binding, dict):
            raise VerifierSubmissionError("oracle request profile binding is invalid")
        binding = cast(dict[str, object], raw_binding)
        expected_keys = {
            "runnerDigest",
            "nativeDisposition",
            "valueDisposition",
            "engineeringCeiling",
            "commercialCeiling",
        }
        if set(binding) != expected_keys:
            raise VerifierSubmissionError("oracle request profile binding is incomplete")
        oracle_observations[oracle_id] = {
            "oracleId": oracle_id,
            "oracleRunnerDigest": binding["runnerDigest"],
            "candidateSha": candidate_sha,
            "candidateTreeSha": candidate_tree_sha,
            "outcome": "PASS",
            "rawEvidenceArtifactHashes": raw_hashes,
            "nativeDisposition": binding["nativeDisposition"],
            "valueDisposition": binding["valueDisposition"],
            "engineeringCeiling": binding["engineeringCeiling"],
            "commercialCeiling": binding["commercialCeiling"],
        }
    request: dict[str, object] = {
        "schemaVersion": "3.1",
        "requestId": request_id,
        "requestDigest": "sha256:" + "0" * 64,
        "nonce": nonce,
        "workItemId": work_item_id,
        "milestoneId": milestone_id,
        "lane": lane,
        "riskTier": profile["riskTier"],
        "candidateSha": candidate_sha,
        "candidateTreeSha": candidate_tree_sha,
        "baseSha": base_sha,
        "sourceGenerationId": source_generation_id,
        "sourceGenerationDigest": source_generation_digest,
        "contextManifestDigest": context_manifest_digest,
        "taskPacketDigest": task_packet_digest,
        "candidateManifestDigest": candidate_manifest_digest,
        "checkpointDigest": checkpoint_digest,
        "requestedClaims": profile["requestedClaims"],
        "publicationScope": profile["publicationScope"],
        "nativeSubstituteDisposition": profile["nativeDisposition"],
        "decisionValueDisposition": profile["valueDisposition"],
        "engineeringMaturityCeiling": profile["engineeringCeiling"],
        "commercialMaturityCeiling": profile["commercialCeiling"],
    }
    digest_payload = dict(request)
    digest_payload.pop("requestDigest")
    request["requestDigest"] = _digest(_canonical_json(digest_payload))
    evidence = {
        "schemaVersion": "3.1",
        "evidenceMode": "CONTROLLED_VALIDATED",
        "workItemId": work_item_id,
        "milestoneId": milestone_id,
        "lane": lane,
        "candidateSha": candidate_sha,
        "candidateTreeSha": candidate_tree_sha,
        "baseSha": base_sha,
        "sourceGenerationId": source_generation_id,
        "sourceGenerationDigest": source_generation_digest,
        "contextManifestDigest": context_manifest_digest,
        "taskPacketDigest": task_packet_digest,
        "candidateManifestDigest": candidate_manifest_digest,
        "checkpointDigest": checkpoint_digest,
        "gates": gates,
        "privateGateSuiteId": profile["privateGateSuiteId"],
        "privateGateRunnerDigest": profile["privateGateRunnerDigest"],
        "oracles": oracle_observations,
        "rawArtifacts": raw_artifacts,
        "observedAt": (
            (now or datetime.now(UTC))
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z")
        ),
    }
    atomic_write_bytes(evidence_root / "evidence.json", _canonical_json(evidence))
    (evidence_root / "evidence.json").chmod(0o600)
    return submit_verification_request(
        request_bytes=_canonical_json(request),
        evidence_root=evidence_root,
        controller_outbox=controller_outbox,
    )
