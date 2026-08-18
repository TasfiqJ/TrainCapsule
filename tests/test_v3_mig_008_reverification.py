from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tcfactory.v3.completion_policy import (
    CompletionEvidenceObservation,
    EvidenceAuthority,
    EvidenceGrade,
    SemanticEvidence,
    evaluate_work_item_evidence_contract,
    load_completion_evidence_policy,
)
from tcfactory.v3.enums import PolicyScope
from tcfactory.v3.mig_008_reverification import (
    COMPONENTS,
    EVIDENCE_PATH,
    SCHEMA_PATH,
    Mig008ReverificationError,
    build_reverification,
    render_reverification,
    validate_reverification,
)
from tcfactory.v3.pipeline_services import (
    MachinePolicyGateReceipt,
    TrustedMachinePolicyRecord,
    evaluate_machine_policy_gate,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
SHA = "b" * 40


def _record(*, issued_at: datetime, expires_at: datetime) -> TrustedMachinePolicyRecord:
    receipt = MachinePolicyGateReceipt.model_validate(
        {
            "issuer": "INDEPENDENT_MACHINE_POLICY_VERIFIER",
            "scope": "ROADMAP_EXPANSION",
            "candidateSha": SHA,
            "artifactDigests": {"review": DIGEST},
            "authorityManifestDigest": DIGEST,
            "issuedAt": issued_at,
            "expiresAt": expires_at,
            "nonce": "v3-mig-008-window-test",
            "revocationEpoch": 7,
            "signature": {
                "algorithm": "ed25519",
                "keyId": "independent-test-key",
                "value": "synthetic-test-signature-never-used-as-evidence",
            },
        }
    )
    return TrustedMachinePolicyRecord(
        receipt=receipt,
        signature_valid=True,
        issuer_authorized=True,
        source_agent_writable=False,
        nonce_fresh=True,
        revoked=False,
    )


def _copy_fixture(tmp_path: Path) -> Path:
    extra = (
        Path("factory/roadmap/work_items.yaml"),
        Path("factory/roadmap/milestones.yaml"),
    )
    for relative in (*COMPONENTS.values(), SCHEMA_PATH, EVIDENCE_PATH, *extra):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def test_v3_mig_008_reverification_is_exact_and_non_authoritative() -> None:
    first = build_reverification(ROOT)
    assert first == build_reverification(ROOT)
    assert render_reverification(ROOT) == render_reverification(ROOT)
    assert validate_reverification(ROOT) == first
    boundary = first["authorityBoundary"]
    assert boundary["admissibleCompletionEvidencePresent"] is False
    assert boundary["completionEligible"] is False
    assert boundary["simulationIsNotAnAttestation"] is True


def test_machine_policy_gate_rejects_expired_and_future_receipts() -> None:
    for record in (
        _record(issued_at=NOW - timedelta(minutes=10), expires_at=NOW),
        _record(issued_at=NOW + timedelta(minutes=1), expires_at=NOW + timedelta(minutes=5)),
    ):
        with pytest.raises(ValueError, match="not currently valid"):
            evaluate_machine_policy_gate(
                record,
                scope=PolicyScope.ROADMAP_EXPANSION,
                candidate_sha=SHA,
                artifact_digests={"review": DIGEST},
                authority_manifest_digest=DIGEST,
                now=NOW,
            )


def test_completed_roadmap_item_without_admissible_authority_fails_closed() -> None:
    contract = load_completion_evidence_policy(ROOT).work_item("V3-MIG-008")
    failures = evaluate_work_item_evidence_contract(
        contract,
        CompletionEvidenceObservation(
            grade=EvidenceGrade.CONTROLLED,
            authorities=[EvidenceAuthority.CONTROLLER],
            semantic_counts={SemanticEvidence.DETERMINISTIC_ARTIFACT: 1},
        ),
    )
    assert failures == [
        "V3-MIG-008 lacks INDEPENDENT_MACHINE_POLICY authority",
        "V3-MIG-008 lacks INDEPENDENT_REVIEWER authority",
        "V3-MIG-008 lacks 1 INDEPENDENT_REVIEW evidence",
        "V3-MIG-008 lacks 1 MACHINE_POLICY_DECISION evidence",
    ]
    evidence = validate_reverification(ROOT)
    assert evidence["roadmapStatus"] == "COMPLETED"
    assert evidence["authorityBoundary"]["completionEligible"] is False


@pytest.mark.parametrize("role", sorted(COMPONENTS))
def test_v3_mig_008_reverification_rejects_tampered_components(
    tmp_path: Path, role: str
) -> None:
    repo = _copy_fixture(tmp_path)
    path = repo / COMPONENTS[role]
    path.write_bytes(path.read_bytes() + b"\nTAMPERED\n")
    with pytest.raises(Mig008ReverificationError):
        validate_reverification(repo)


def test_v3_mig_008_reverification_rejects_forged_authority(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    evidence_path = repo / EVIDENCE_PATH
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["authorityBoundary"]["completionEligible"] = True
    evidence["authorityBoundary"]["independentMachinePolicyReceiptPresent"] = True
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(Mig008ReverificationError, match="schema validation failed"):
        validate_reverification(repo)


def test_v3_mig_008_reverification_rejects_digest_tamper(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)
    evidence_path = repo / EVIDENCE_PATH
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["evidenceDigest"] = "sha256:" + "0" * 64
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(Mig008ReverificationError, match="does not match"):
        validate_reverification(repo)
