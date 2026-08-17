from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_independent_verifier import (
    _evidence,  # pyright: ignore[reportPrivateUsage]
    _request,  # pyright: ignore[reportPrivateUsage]
)
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.filesystem import open_trusted_root
from traincapsule_verifier.models import TrustedEvidenceManifest
from traincapsule_verifier.request_broker import RequestSubmissionError, RootRequestBroker

from tcfactory.v3.verifier_submission import (
    VerifierSubmissionError,
    create_and_submit_verification_request,
    submit_verification_request,
)


def _staged_bundle(tmp_path: Path) -> tuple[Path, str]:
    outbox = tmp_path / "controller-outbox"
    evidence_root = tmp_path / "source-evidence"
    outbox.mkdir(mode=0o700)
    (evidence_root / "raw").mkdir(parents=True, mode=0o700)
    raw = b"independent raw evidence\n"
    raw_digest = sha256_digest(raw)
    request = _request()
    evidence = _evidence(raw_digest)
    (evidence_root / "raw" / "evidence.bin").write_bytes(raw)
    (evidence_root / "raw" / "evidence.bin").chmod(0o600)
    (evidence_root / "evidence.json").write_bytes(canonical_json_bytes(evidence))
    (evidence_root / "evidence.json").chmod(0o600)
    request_name = f"{request.request_id}.request.json"
    submit_verification_request(
        request_bytes=canonical_json_bytes(request),
        evidence_root=evidence_root,
        controller_outbox=outbox,
    )
    return outbox, request_name


def test_controller_to_root_to_service_bridge_is_canonical_nested_and_idempotent(
    tmp_path: Path,
) -> None:
    controller, request_name = _staged_bundle(tmp_path)
    inbox = tmp_path / "service-inbox"
    journal = tmp_path / "journal"
    inbox.mkdir(mode=0o700)
    journal.mkdir(mode=0o700)
    with (
        open_trusted_root(controller, expected_uid=os.getuid()) as source,
        open_trusted_root(inbox, expected_uid=os.getuid()) as destination,
        open_trusted_root(journal, expected_uid=os.getuid()) as audit,
    ):
        broker = RootRequestBroker(
            controller_outbox=source,
            service_inbox=destination,
            journal_root=audit,
            service_uid=os.getuid(),
            service_gid=os.getgid(),
        )
        assert broker.submit(request_name).state == "SUBMITTED"
        assert broker.submit(request_name).state == "ALREADY_SUBMITTED"
    assert (inbox / "REQUEST:VERIFY:001.evidence/raw/evidence.bin").read_bytes() == (
        b"independent raw evidence\n"
    )
    assert (inbox / request_name).read_bytes() == (controller / request_name).read_bytes()
    assert (journal / "REQUEST:VERIFY:001.submission.json").is_file()


def test_bridge_rejects_tamper_symlink_conflict_and_noncanonical_request(
    tmp_path: Path,
) -> None:
    controller, request_name = _staged_bundle(tmp_path)
    inbox = tmp_path / "service-inbox"
    journal = tmp_path / "journal"
    inbox.mkdir(mode=0o700)
    journal.mkdir(mode=0o700)
    raw = controller / "REQUEST:VERIFY:001.evidence/raw/evidence.bin"
    raw.write_bytes(b"tampered\n")
    with (
        open_trusted_root(controller, expected_uid=os.getuid()) as source,
        open_trusted_root(inbox, expected_uid=os.getuid()) as destination,
        open_trusted_root(journal, expected_uid=os.getuid()) as audit,
    ):
        broker = RootRequestBroker(
            controller_outbox=source,
            service_inbox=destination,
            journal_root=audit,
            service_uid=os.getuid(),
            service_gid=os.getgid(),
        )
        with pytest.raises(RequestSubmissionError, match="digest mismatch"):
            broker.submit(request_name)

    clean = tmp_path / "clean"
    clean.mkdir(mode=0o700)
    evidence = tmp_path / "symlink-evidence"
    evidence.mkdir(mode=0o700)
    (evidence / "evidence.json").symlink_to(controller / request_name)
    with pytest.raises(VerifierSubmissionError, match="regular files"):
        submit_verification_request(
            request_bytes=(controller / request_name).read_bytes(),
            evidence_root=evidence,
            controller_outbox=clean,
        )
    request = (controller / request_name).read_bytes().replace(b",", b", ", 1)
    with pytest.raises(VerifierSubmissionError, match="canonical"):
        submit_verification_request(
            request_bytes=request,
            evidence_root=controller / "REQUEST:VERIFY:001.evidence",
            controller_outbox=clean,
        )


def test_controller_profile_builder_emits_strict_request_and_submits_atomically(
    tmp_path: Path,
) -> None:
    profile = {
        "commercialCeiling": "PILOT_ELIGIBLE",
        "engineeringCeiling": "PASSED",
        "nativeDisposition": "INCREMENTAL_VALUE",
        "oracles": {
            "ORACLE:CONFORMANCE:001": {
                "commercialCeiling": "PILOT_ELIGIBLE",
                "engineeringCeiling": "PASSED",
                "nativeDisposition": "INCREMENTAL_VALUE",
                "runnerDigest": "sha256:" + "c" * 64,
                "valueDisposition": "INCREMENTAL_DECISION_VALUE_DEMONSTRATED",
            }
        },
        "privateGateRunnerDigest": "sha256:" + "d" * 64,
        "privateGateSuiteId": "GATE-SUITE",
        "publicationScope": ["packages/traincapsule-core/file.py"],
        "requestedClaims": ["CLAIM:ENGINEERING-PASS"],
        "riskTier": "TRUST-CORE",
        "schemaVersion": "3.1",
        "valueDisposition": "INCREMENTAL_DECISION_VALUE_DEMONSTRATED",
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_bytes(canonical_json_bytes(profile))
    gate = tmp_path / "gate.bin"
    gate.write_bytes(b"gate evidence\n")
    outbox = tmp_path / "outbox"
    outbox.mkdir(mode=0o700)
    request_path = create_and_submit_verification_request(
        profile_path=profile_path,
        work_item_id="V3-DEC-001",
        milestone_id="M1_PRODUCT_WEDGE",
        lane="PRODUCT",
        candidate_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        base_sha="a" * 40,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        context_manifest_digest="sha256:" + "b" * 64,
        task_packet_digest="sha256:" + "c" * 64,
        candidate_manifest_digest="sha256:" + "d" * 64,
        checkpoint_digest="sha256:" + "e" * 64,
        gate_evidence={"FACTORY-QUALITY": gate},
        evidence_root=tmp_path / "evidence",
        controller_outbox=outbox,
    )
    assert request_path.is_file()
    request = request_path.read_text()
    assert '"requestDigest":"sha256:' in request
    assert '"workItemId":"V3-DEC-001"' in request
    evidence_path = outbox / request_path.name.replace(
        ".request.json", ".evidence/evidence.json"
    )
    assert evidence_path.is_file()
    evidence_raw = evidence_path.read_bytes()
    evidence = TrustedEvidenceManifest.model_validate_json(evidence_raw, strict=True)
    assert evidence_raw == canonical_json_bytes(evidence)

    oracle_bindings = profile["oracles"]
    assert isinstance(oracle_bindings, dict)
    conformance_binding = oracle_bindings["ORACLE:CONFORMANCE:001"]
    assert isinstance(conformance_binding, dict)
    conformance_binding["runnerDigest"] = "sha256:" + "f" * 64
    profile_path.write_bytes(canonical_json_bytes(profile))
    rotated_request_path = create_and_submit_verification_request(
        profile_path=profile_path,
        work_item_id="V3-DEC-001",
        milestone_id="M1_PRODUCT_WEDGE",
        lane="PRODUCT",
        candidate_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        base_sha="a" * 40,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest="sha256:" + "a" * 64,
        context_manifest_digest="sha256:" + "b" * 64,
        task_packet_digest="sha256:" + "c" * 64,
        candidate_manifest_digest="sha256:" + "d" * 64,
        checkpoint_digest="sha256:" + "e" * 64,
        gate_evidence={"FACTORY-QUALITY": gate},
        evidence_root=tmp_path / "rotated-evidence",
        controller_outbox=outbox,
    )
    assert rotated_request_path.name != request_path.name
