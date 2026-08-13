from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

VERIFIER_SRC = Path(__file__).resolve().parents[1] / "verifier/src"
sys.path.insert(0, str(VERIFIER_SRC))

from traincapsule_verifier.attestation import (  # noqa: E402
    InstallationError,
    attest_installation,
    rehearse_layout,
)
from traincapsule_verifier.canonical import (  # noqa: E402
    canonical_json_bytes,
    model_digest,
    sha256_digest,
)
from traincapsule_verifier.crypto import public_key_fingerprint, sign_model  # noqa: E402
from traincapsule_verifier.evaluator import (  # noqa: E402
    IndependentVerifier,
    VerificationError,
    verification_request_digest,
)
from traincapsule_verifier.filesystem import TrustedPathError  # noqa: E402
from traincapsule_verifier.models import (  # noqa: E402
    ActivationMode,
    ActivationRequest,
    AuthorityAnchor,
    CommercialCeiling,
    EngineeringCeiling,
    EvidenceMode,
    GateObservation,
    GateResult,
    NativeDisposition,
    OracleObservation,
    OracleOutcome,
    RawArtifactBinding,
    RevocationList,
    RiskPolicy,
    TrustedEvidenceManifest,
    ValueDisposition,
    VerificationRequest,
    VerifierPolicy,
)

from verifier.scripts.generate_schemas import (  # noqa: E402
    SCHEMA_ROOT,
    rendered_schemas,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
ORACLE_RUNNER = b"""#!/usr/bin/python3
import hashlib
import json
import os
import sys
request = json.load(sys.stdin)
observed = []
for artifact in request["rawEvidenceArtifacts"]:
    descriptor = os.open(
        artifact["path"],
        os.O_RDONLY | os.O_NOFOLLOW,
        dir_fd=request["evidenceRootFd"],
    )
    try:
        payload = b""
        while chunk := os.read(descriptor, 1048576):
            payload += chunk
    finally:
        os.close(descriptor)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if digest != artifact["digest"]:
        raise SystemExit(41)
    observed.append(digest)
if sorted(observed) != sorted(request["rawEvidenceArtifactHashes"]):
    raise SystemExit(42)
result = {
    "commercialCeiling": "PILOT_ELIGIBLE",
    "engineeringCeiling": "PASSED",
    "nativeDisposition": "INCREMENTAL_VALUE",
    "outcome": "PASS",
    "rawEvidenceArtifactHashes": request["rawEvidenceArtifactHashes"],
    "schemaVersion": "3.1",
    "valueDisposition": "INCREMENTAL_DECISION_VALUE_DEMONSTRATED",
}
sys.stdout.write(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\\n")
"""
ORACLE_RUNNER_DIGEST = sha256_digest(ORACLE_RUNNER)


def _private_key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _public_key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _policy(key: Ed25519PrivateKey) -> VerifierPolicy:
    return VerifierPolicy(
        schema_version="3.1",
        policy_id="POLICY:ZERO-HUMAN",
        policy_version="3.1.0",
        issuer_id="VERIFIER:INDEPENDENT:001",
        issuer_key_id="KEY:ED25519:001",
        public_key_fingerprint=public_key_fingerprint(key.public_key()),
        minimum_revocation_epoch=1,
        active_source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        active_source_generation_digest=DIGEST_A,
        private_gate_suite_id="FULL-RELEASE-V31",
        private_gate_runner_digest=DIGEST_B,
        risk_policies={
            "TRUST-CORE": RiskPolicy(
                required_gates=["FACTORY-QUALITY", "PRODUCT-CONTRACT"],
                required_oracle_ids=["ORACLE:CONFORMANCE:001"],
                oracle_runner_digests={"ORACLE:CONFORMANCE:001": ORACLE_RUNNER_DIGEST},
                oracle_runner_paths={"ORACLE:CONFORMANCE:001": "conformance-oracle.py"},
                accepted_evidence_modes=[EvidenceMode.CONTROLLED_VALIDATED],
                maximum_engineering_ceiling=EngineeringCeiling.PASSED,
                maximum_commercial_ceiling=CommercialCeiling.PILOT_ELIGIBLE,
            )
        },
        allowed_claims=["CLAIM:ENGINEERING-PASS"],
        forbidden_claims=["CLAIM:COMMERCIAL-SUPPORT"],
        allowed_publication_scopes=["packages/traincapsule-*/**"],
        maximum_receipt_lifetime_seconds=3600,
        maximum_evidence_age_seconds=3600,
    )


def _signed_revocations(key: Ed25519PrivateKey, **updates: Any) -> RevocationList:
    payload: dict[str, Any] = {
        "schemaVersion": "3.1",
        "policyId": "POLICY:ZERO-HUMAN",
        "policyVersion": "3.1.0",
        "issuerId": "VERIFIER:INDEPENDENT:001",
        "issuerKeyId": "KEY:ED25519:001",
        "revocationEpoch": 1,
        "previousListDigest": None,
        "issuedAt": NOW - timedelta(minutes=1),
        "expiresAt": NOW + timedelta(days=1),
        "revokedReceiptIds": [],
        "revokedNonces": [],
        "revokedKeyIds": [],
        "signatureAlgorithm": "ed25519",
        "signature": "A" * 88,
    }
    payload.update(updates)
    provisional = RevocationList.model_validate(payload, strict=True)
    return provisional.model_copy(update={"signature": sign_model(provisional, key)})


def _anchor(policy: VerifierPolicy, revocations: RevocationList) -> AuthorityAnchor:
    return AuthorityAnchor(
        schema_version="3.1",
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        public_key_fingerprint=policy.public_key_fingerprint,
        key_epoch=1,
        previous_key_anchor_digest=None,
        revocation_epoch=revocations.revocation_epoch,
        revocation_list_digest=model_digest(revocations),
        previous_revocation_list_digest=revocations.previous_list_digest,
    )


def _request(**updates: Any) -> VerificationRequest:
    payload: dict[str, Any] = {
        "schemaVersion": "3.1",
        "requestId": "REQUEST:VERIFY:001",
        "requestDigest": DIGEST_A,
        "nonce": "0123456789abcdef",
        "workItemId": "V3-PROD-001",
        "milestoneId": "M1_PRODUCT_WEDGE",
        "lane": "PRODUCT",
        "riskTier": "TRUST-CORE",
        "candidateSha": SHA_A,
        "candidateTreeSha": SHA_B,
        "baseSha": SHA_C,
        "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
        "sourceGenerationDigest": DIGEST_A,
        "contextManifestDigest": DIGEST_A,
        "taskPacketDigest": DIGEST_A,
        "candidateManifestDigest": DIGEST_A,
        "checkpointDigest": DIGEST_A,
        "requestedClaims": ["CLAIM:ENGINEERING-PASS"],
        "publicationScope": ["packages/traincapsule-core/src/file.py"],
        "nativeSubstituteDisposition": NativeDisposition.INCREMENTAL_VALUE,
        "decisionValueDisposition": (ValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED),
        "engineeringMaturityCeiling": EngineeringCeiling.PASSED,
        "commercialMaturityCeiling": CommercialCeiling.PILOT_ELIGIBLE,
    }
    payload.update(updates)
    preliminary = VerificationRequest.model_validate(payload, strict=True)
    return preliminary.model_copy(
        update={"request_digest": verification_request_digest(preliminary)}
    )


def _evidence(raw_digest: str, **updates: Any) -> TrustedEvidenceManifest:
    payload: dict[str, Any] = {
        "schemaVersion": "3.1",
        "evidenceMode": EvidenceMode.CONTROLLED_VALIDATED,
        "workItemId": "V3-PROD-001",
        "milestoneId": "M1_PRODUCT_WEDGE",
        "lane": "PRODUCT",
        "candidateSha": SHA_A,
        "candidateTreeSha": SHA_B,
        "baseSha": SHA_C,
        "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
        "sourceGenerationDigest": DIGEST_A,
        "contextManifestDigest": DIGEST_A,
        "taskPacketDigest": DIGEST_A,
        "candidateManifestDigest": DIGEST_A,
        "checkpointDigest": DIGEST_A,
        "gates": {
            name: GateObservation(
                candidate_sha=SHA_A,
                result=GateResult.PASS,
                evidence_digest=raw_digest,
            )
            for name in ("FACTORY-QUALITY", "PRODUCT-CONTRACT")
        },
        "privateGateSuiteId": "FULL-RELEASE-V31",
        "privateGateRunnerDigest": DIGEST_B,
        "oracles": {
            "ORACLE:CONFORMANCE:001": OracleObservation(
                oracle_id="ORACLE:CONFORMANCE:001",
                oracle_runner_digest=ORACLE_RUNNER_DIGEST,
                candidate_sha=SHA_A,
                candidate_tree_sha=SHA_B,
                outcome=OracleOutcome.PASS,
                raw_evidence_artifact_hashes=[raw_digest],
                native_disposition=NativeDisposition.INCREMENTAL_VALUE,
                value_disposition=(ValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED),
                engineering_ceiling=EngineeringCeiling.PASSED,
                commercial_ceiling=CommercialCeiling.PILOT_ELIGIBLE,
            )
        },
        "rawArtifacts": {
            "ARTIFACT:RAW:001": RawArtifactBinding(path="raw/evidence.bin", digest=raw_digest)
        },
        "observedAt": NOW,
    }
    payload.update(updates)
    return TrustedEvidenceManifest.model_validate(payload, strict=True)


class Fixture:
    key: Ed25519PrivateKey
    policy: VerifierPolicy
    revocations: RevocationList
    repo: Path
    config: Path
    state: Path
    private: Path
    receipts: Path
    evidence: Path
    anchor_root: Path
    oracle: Path
    activation: Path
    verifier: IndependentVerifier
    raw_digest: str


@pytest.fixture
def fixture(tmp_path: Path) -> Fixture:
    item = Fixture()
    item.key = Ed25519PrivateKey.generate()
    item.policy = _policy(item.key)
    item.revocations = _signed_revocations(item.key)
    item.repo = tmp_path / "candidate-repo"
    item.config = tmp_path / "external/etc"
    item.state = tmp_path / "external/state"
    item.private = tmp_path / "external/private"
    item.receipts = tmp_path / "external/receipts"
    item.evidence = tmp_path / "external/evidence"
    item.anchor_root = tmp_path / "external/anchor"
    item.oracle = tmp_path / "external/oracle"
    item.activation = tmp_path / "external/activation"
    for path in (
        item.repo,
        item.config,
        item.state,
        item.private,
        item.receipts,
        item.evidence / "raw",
        item.anchor_root,
        item.oracle,
        item.activation,
    ):
        path.mkdir(parents=True, mode=0o700)
        path.chmod(0o700)
    (item.config / "policy.json").write_bytes(canonical_json_bytes(item.policy))
    (item.config / "public-key.pem").write_bytes(_public_key_pem(item.key))
    (item.state / "revocations.json").write_bytes(canonical_json_bytes(item.revocations))
    (item.anchor_root / "authority-anchor.json").write_bytes(
        canonical_json_bytes(_anchor(item.policy, item.revocations))
    )
    key_path = item.private / "signing-key.pem"
    key_path.write_bytes(_private_key_pem(item.key))
    key_path.chmod(0o600)
    oracle_path = item.oracle / "conformance-oracle.py"
    oracle_path.write_bytes(ORACLE_RUNNER)
    oracle_path.chmod(0o700)
    raw = b"independent raw oracle evidence\n"
    (item.evidence / "raw/evidence.bin").write_bytes(raw)
    item.raw_digest = sha256_digest(raw)
    (item.evidence / "evidence.json").write_bytes(canonical_json_bytes(_evidence(item.raw_digest)))
    (item.activation / "machine-environment.json").write_bytes(b'{"machine":"fixture"}\n')
    (item.activation / "controller.py").write_bytes(b"print('controller')\n")
    (item.activation / "controller.yaml").write_bytes(b"mode: canary\n")
    uid = os.getuid()
    item.verifier = IndependentVerifier.from_external_roots(
        repository_root=item.repo,
        config_root=item.config,
        state_root=item.state,
        private_root=item.private,
        receipt_root=item.receipts,
        anchor_root=item.anchor_root,
        oracle_root=item.oracle,
        config_owner_uid=uid,
        verifier_owner_uid=uid,
    )
    return item


def _rewrite_evidence(fixture: Fixture, evidence: TrustedEvidenceManifest) -> None:
    (fixture.evidence / "evidence.json").write_bytes(canonical_json_bytes(evidence))


def _activation_request(fixture: Fixture, policy_receipt: Any, **updates: Any) -> ActivationRequest:
    payload: dict[str, Any] = {
        "schemaVersion": "3.1",
        "requestId": "REQUEST:ACTIVATE:001",
        "nonce": "activation-nonce-001",
        "verifiedMainSha": SHA_A,
        "machineEnvironmentDigest": sha256_digest(
            (fixture.activation / "machine-environment.json").read_bytes()
        ),
        "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
        "sourceGenerationDigest": DIGEST_A,
        "controllerBinaryDigest": sha256_digest(
            (fixture.activation / "controller.py").read_bytes()
        ),
        "controllerConfigDigest": sha256_digest(
            (fixture.activation / "controller.yaml").read_bytes()
        ),
        "machineEnvironmentPath": "machine-environment.json",
        "controllerBinaryPath": "controller.py",
        "controllerConfigPath": "controller.yaml",
        "machinePolicyReceipt": policy_receipt,
        "mode": ActivationMode.CANARY,
    }
    payload.update(updates)
    return ActivationRequest.model_validate(payload, strict=True)


def _external_verifier(fixture: Fixture) -> IndependentVerifier:
    return IndependentVerifier.from_external_roots(
        repository_root=fixture.repo,
        config_root=fixture.config,
        state_root=fixture.state,
        private_root=fixture.private,
        receipt_root=fixture.receipts,
        anchor_root=fixture.anchor_root,
        oracle_root=fixture.oracle,
        config_owner_uid=os.getuid(),
        verifier_owner_uid=os.getuid(),
    )


def _descriptor_count() -> int:
    descriptor_root = Path("/proc/self/fd")
    if not descriptor_root.is_dir():
        pytest.skip("descriptor accounting requires /proc/self/fd")
    return len(tuple(descriptor_root.iterdir()))


def test_independent_distribution_has_no_factory_dependency() -> None:
    source_files = list((VERIFIER_SRC / "traincapsule_verifier").glob("*.py"))
    assert source_files
    assert all("tcfactory" not in path.read_text(encoding="utf-8") for path in source_files)
    importlib.import_module("traincapsule_verifier")


def test_valid_receipt_is_exact_signed_scoped_and_check_bound(fixture: Fixture) -> None:
    request = _request()
    receipt = fixture.verifier.issue_receipt(
        request,
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    fixture.verifier.verify_receipt(receipt, request=request, now=NOW)
    assert receipt.candidate_sha == SHA_A
    assert receipt.candidate_tree_sha == SHA_B
    assert receipt.independent_oracle_ids == ["ORACLE:CONFORMANCE:001"]
    assert fixture.raw_digest in receipt.raw_evidence_artifact_hashes
    assert len(receipt.raw_evidence_artifact_hashes) == 2
    assert receipt.allowed_claims == ["CLAIM:ENGINEERING-PASS"]
    assert receipt.publication_scope == ["packages/traincapsule-core/src/file.py"]
    check = fixture.verifier.authorize_check(receipt, now=NOW)
    assert check.check_name == "TrainCapsule / Machine policy"
    assert check.candidate_sha == SHA_A
    assert check.receipt_digest == model_digest(receipt)
    assert (fixture.receipts / f"{receipt.receipt_id}.json").read_bytes() == (
        canonical_json_bytes(receipt)
    )


@pytest.mark.parametrize(
    ("request_update", "evidence_update", "message"),
    [
        ({"candidateSha": SHA_C}, {}, "candidate_sha mismatch"),
        ({"candidateTreeSha": SHA_C}, {}, "candidate_tree_sha mismatch"),
        ({"baseSha": SHA_A}, {}, "base_sha mismatch"),
        ({"sourceGenerationDigest": DIGEST_B}, {}, "wrong source generation"),
        ({"contextManifestDigest": DIGEST_B}, {}, "context_manifest_digest mismatch"),
        ({"taskPacketDigest": DIGEST_B}, {}, "task_packet_digest mismatch"),
        ({"candidateManifestDigest": DIGEST_B}, {}, "candidate_manifest_digest mismatch"),
        ({"checkpointDigest": DIGEST_B}, {}, "checkpoint_digest mismatch"),
        ({"riskTier": "UNKNOWN-RISK"}, {}, "risk tier"),
    ],
)
def test_exact_request_bindings_fail_closed(
    fixture: Fixture,
    request_update: dict[str, object],
    evidence_update: dict[str, object],
    message: str,
) -> None:
    _rewrite_evidence(fixture, _evidence(fixture.raw_digest, **evidence_update))
    with pytest.raises(VerificationError, match=message):
        fixture.verifier.issue_receipt(
            _request(**request_update),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_forged_request_digest_missing_gate_oracle_and_raw_substitution_fail(
    fixture: Fixture,
) -> None:
    request = _request().model_copy(update={"request_digest": DIGEST_A})
    with pytest.raises(VerificationError, match="request digest"):
        fixture.verifier.issue_receipt(
            request,
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_wrong_oracle_runner_and_unbound_gate_evidence_fail(fixture: Fixture) -> None:
    evidence = _evidence(fixture.raw_digest)
    oracle = evidence.oracles["ORACLE:CONFORMANCE:001"].model_copy(
        update={"oracle_runner_digest": DIGEST_A}
    )
    _rewrite_evidence(
        fixture,
        evidence.model_copy(update={"oracles": {"ORACLE:CONFORMANCE:001": oracle}}),
    )
    with pytest.raises(VerificationError, match="oracle runner digest"):
        fixture.verifier.issue_receipt(
            _request(nonce="wrong-oracle-runner"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )
    gates = {
        name: gate.model_copy(update={"evidence_digest": DIGEST_A})
        for name, gate in evidence.gates.items()
    }
    _rewrite_evidence(fixture, evidence.model_copy(update={"gates": gates}))
    with pytest.raises(VerificationError, match="gate evidence digest"):
        fixture.verifier.issue_receipt(
            _request(nonce="unbound-gate-evidence"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )

    evidence = _evidence(fixture.raw_digest)
    _rewrite_evidence(fixture, evidence.model_copy(update={"gates": {}}))
    with pytest.raises((VerificationError, ValueError), match="invalid|required gates"):
        fixture.verifier.issue_receipt(
            _request(nonce="missing-gate-0001"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )

    _rewrite_evidence(fixture, evidence.model_copy(update={"oracles": {}}))
    with pytest.raises((VerificationError, ValueError), match="invalid|oracle"):
        fixture.verifier.issue_receipt(
            _request(nonce="missing-oracle-01"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )

    _rewrite_evidence(fixture, evidence)
    (fixture.evidence / "raw/evidence.bin").write_bytes(b"substituted")
    with pytest.raises(VerificationError, match="raw evidence artifact digest"):
        fixture.verifier.issue_receipt(
            _request(nonce="substituted-raw-01"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_claim_scope_maturity_evidence_mode_and_staleness_cannot_be_laundered(
    fixture: Fixture,
) -> None:
    cases = [
        (_request(requestedClaims=["CLAIM:COMMERCIAL-SUPPORT"]), NOW, "claim"),
        (_request(publicationScope=["tcfactory/controller.py"]), NOW, "scope"),
        (
            _request(commercialMaturityCeiling=CommercialCeiling.COMMERCIALLY_SUPPORTED),
            NOW,
            "oracle consensus|policy ceiling|commercial support",
        ),
    ]
    for index, (request, observed, message) in enumerate(cases):
        request = request.model_copy(update={"nonce": f"claim-scope-case-{index:02d}"})
        request = request.model_copy(
            update={"request_digest": verification_request_digest(request)}
        )
        with pytest.raises(VerificationError, match=message):
            fixture.verifier.issue_receipt(
                request,
                evidence_root=fixture.evidence,
                repository_root=fixture.repo,
                evidence_owner_uid=os.getuid(),
                now=observed,
            )

    evidence = _evidence(fixture.raw_digest).model_copy(
        update={"evidence_mode": EvidenceMode.SIMULATED}
    )
    _rewrite_evidence(fixture, evidence)
    with pytest.raises(VerificationError, match="evidence mode"):
        fixture.verifier.issue_receipt(
            _request(nonce="simulated-evidence-1"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )
    _rewrite_evidence(
        fixture,
        _evidence(fixture.raw_digest).model_copy(update={"observed_at": NOW - timedelta(hours=2)}),
    )
    with pytest.raises(VerificationError, match="stale"):
        fixture.verifier.issue_receipt(
            _request(nonce="stale-evidence-001"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_tamper_expiry_policy_downgrade_revocation_and_nonce_replay_fail(
    fixture: Fixture,
) -> None:
    request = _request()
    receipt = fixture.verifier.issue_receipt(
        request,
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    tampered = receipt.model_copy(update={"candidate_sha": SHA_C})
    with pytest.raises(VerificationError, match="signature"):
        fixture.verifier.verify_receipt(tampered, now=NOW)
    with pytest.raises(VerificationError, match="expired"):
        fixture.verifier.verify_receipt(receipt, now=NOW + timedelta(hours=2))
    downgraded = receipt.model_copy(update={"policy_version": "3.0.0"})
    downgraded = downgraded.model_copy(update={"signature": sign_model(downgraded, fixture.key)})
    with pytest.raises(VerificationError, match="policy version"):
        fixture.verifier.verify_receipt(downgraded, now=NOW)
    revoked = _signed_revocations(fixture.key, revokedNonces=[receipt.nonce])
    revoked_verifier = IndependentVerifier(
        policy=fixture.policy,
        revocations=revoked,
        signing_key=fixture.key,
        public_key=fixture.key.public_key(),
        anchor=_anchor(fixture.policy, revoked),
        state_root=fixture.verifier.state_root,
        receipt_root=fixture.verifier.receipt_root,
        oracle_root=fixture.verifier.oracle_root,
    )
    with pytest.raises(VerificationError, match="revoked"):
        revoked_verifier.verify_receipt(receipt, now=NOW)
    with pytest.raises(TrustedPathError, match="already consumed"):
        fixture.verifier.issue_receipt(
            request,
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_expired_revocation_state_and_missing_local_receipt_fail(fixture: Fixture) -> None:
    receipt = fixture.verifier.issue_receipt(
        _request(),
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    (fixture.receipts / f"{receipt.receipt_id}.json").unlink()
    with pytest.raises(VerificationError, match="local signed receipt"):
        fixture.verifier.authorize_check(receipt, now=NOW)
    expired = _signed_revocations(
        fixture.key,
        issuedAt=NOW - timedelta(days=2),
        expiresAt=NOW - timedelta(days=1),
    )
    stale_verifier = IndependentVerifier(
        policy=fixture.policy,
        revocations=expired,
        signing_key=fixture.key,
        public_key=fixture.key.public_key(),
        anchor=_anchor(fixture.policy, expired),
        state_root=fixture.verifier.state_root,
        receipt_root=fixture.verifier.receipt_root,
        oracle_root=fixture.verifier.oracle_root,
    )
    with pytest.raises(VerificationError, match="revocation list is expired"):
        stale_verifier.verify_receipt(receipt, now=NOW)


def test_self_authored_writable_symlink_or_readable_key_roots_fail(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    repository = tmp_path / "repo"
    repository.mkdir()
    in_repo = repository / "trust"
    in_repo.mkdir()
    with pytest.raises(TrustedPathError, match="outside"):
        IndependentVerifier.from_external_roots(
            repository_root=repository,
            config_root=in_repo,
            state_root=in_repo,
            private_root=in_repo,
            receipt_root=in_repo,
            anchor_root=in_repo,
            oracle_root=in_repo,
            config_owner_uid=os.getuid(),
            verifier_owner_uid=os.getuid(),
        )

    external = tmp_path / "external"
    external.mkdir(mode=0o777)
    external.chmod(0o777)
    with pytest.raises(TrustedPathError, match="writable"):
        IndependentVerifier.from_external_roots(
            repository_root=repository,
            config_root=external,
            state_root=external,
            private_root=external,
            receipt_root=external,
            anchor_root=external,
            oracle_root=external,
            config_owner_uid=os.getuid(),
            verifier_owner_uid=os.getuid(),
        )

    layout = tmp_path / "layout"
    config, state, private, receipts, anchors, oracle = (
        layout / "config",
        layout / "state",
        layout / "private",
        layout / "receipts",
        layout / "anchors",
        layout / "oracle",
    )
    for path in (config, state, private, receipts, anchors, oracle):
        path.mkdir(parents=True, mode=0o700)
    policy = _policy(key)
    revocations = _signed_revocations(key)
    (config / "policy.json").write_bytes(canonical_json_bytes(policy))
    (config / "public-key.pem").write_bytes(_public_key_pem(key))
    (state / "revocations.json").write_bytes(canonical_json_bytes(revocations))
    (anchors / "authority-anchor.json").write_bytes(
        canonical_json_bytes(_anchor(policy, revocations))
    )
    oracle_path = oracle / "conformance-oracle.py"
    oracle_path.write_bytes(ORACLE_RUNNER)
    oracle_path.chmod(0o700)
    signing_key = private / "signing-key.pem"
    signing_key.write_bytes(_private_key_pem(key))
    signing_key.chmod(0o644)
    with pytest.raises(TrustedPathError, match="0o600"):
        IndependentVerifier.from_external_roots(
            repository_root=repository,
            config_root=config,
            state_root=state,
            private_root=private,
            receipt_root=receipts,
            anchor_root=anchors,
            oracle_root=oracle,
            config_owner_uid=os.getuid(),
            verifier_owner_uid=os.getuid(),
        )


def test_check_requires_matching_local_receipt_and_activation_binds_exact_machine(
    fixture: Fixture,
) -> None:
    policy_receipt = fixture.verifier.issue_receipt(
        _request(),
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    forged = policy_receipt.model_copy(update={"signature": base64.b64encode(b"x" * 64).decode()})
    with pytest.raises(VerificationError, match="signature"):
        fixture.verifier.authorize_check(forged, now=NOW)
    activation_request = ActivationRequest(
        schema_version="3.1",
        request_id="REQUEST:ACTIVATE:001",
        nonce="activation-nonce-001",
        verified_main_sha=SHA_A,
        machine_environment_digest=sha256_digest(
            (fixture.activation / "machine-environment.json").read_bytes()
        ),
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST_A,
        controller_binary_digest=sha256_digest((fixture.activation / "controller.py").read_bytes()),
        controller_config_digest=sha256_digest(
            (fixture.activation / "controller.yaml").read_bytes()
        ),
        machine_environment_path="machine-environment.json",
        controller_binary_path="controller.py",
        controller_config_path="controller.yaml",
        machine_policy_receipt=policy_receipt,
        mode=ActivationMode.CANARY,
    )
    with pytest.raises(VerificationError, match="observed main"):
        fixture.verifier.issue_activation(
            activation_request,
            observed_main_sha=SHA_C,
            activation_root=fixture.activation,
            repository_root=fixture.repo,
            activation_owner_uid=os.getuid(),
            now=NOW,
        )
    activation = fixture.verifier.issue_activation(
        activation_request,
        observed_main_sha=SHA_A,
        activation_root=fixture.activation,
        repository_root=fixture.repo,
        activation_owner_uid=os.getuid(),
        now=NOW,
    )
    fixture.verifier.verify_activation(
        activation,
        observed_main_sha=SHA_A,
        machine_policy_receipt=policy_receipt,
        activation_root=fixture.activation,
        repository_root=fixture.repo,
        activation_owner_uid=os.getuid(),
        now=NOW,
    )
    with pytest.raises(VerificationError, match="verified_main_sha mismatch"):
        fixture.verifier.verify_activation(
            activation,
            observed_main_sha=SHA_C,
            machine_policy_receipt=policy_receipt,
            activation_root=fixture.activation,
            repository_root=fixture.repo,
            activation_owner_uid=os.getuid(),
            now=NOW,
        )


def test_install_rehearsal_is_inactive_secret_free_and_attested(tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    destination = tmp_path / "staged"
    rehearse_layout(destination, _public_key_pem(key))
    assert (destination / "STAGED_NOT_ACTIVATED").is_file()
    assert not list(destination.rglob("*signing-key*"))
    assert not list(destination.rglob("*credential*"))
    attestation = attest_installation(
        destination,
        distribution_root=Path(__file__).resolve().parents[1] / "verifier",
        expected_owner_uid=os.getuid(),
    )
    assert attestation.state.value == "STAGED_NOT_ACTIVATED"
    assert set(attestation.missing_private_inputs) == {
        "policy.json",
        "private/signing-key.pem",
        "revocations.json",
        "authority-anchor.json",
        "live-oracle-verification",
        "live-service-verification",
    }
    assert not attestation.authority_validated
    assert not attestation.live_oracle_verified
    assert not attestation.live_service_verified
    assert attestation.public_key_fingerprint == public_key_fingerprint(key.public_key())
    with pytest.raises(InstallationError, match="already exists"):
        rehearse_layout(destination, _public_key_pem(key))
    linked = tmp_path / "linked-install"
    linked.symlink_to(destination, target_is_directory=True)
    with pytest.raises(InstallationError, match="symbolic link"):
        attest_installation(
            linked,
            distribution_root=Path(__file__).resolve().parents[1] / "verifier",
            expected_owner_uid=os.getuid(),
        )


@pytest.mark.parametrize(
    ("request_update", "evidence_update", "field"),
    [
        ({"workItemId": "V3-MKT-999"}, {}, "work_item_id"),
        ({"milestoneId": "M9_CALLER_CHOSEN"}, {}, "milestone_id"),
        ({"lane": "MARKET"}, {}, "lane"),
    ],
)
def test_caller_identity_cannot_be_laundered_into_receipt(
    fixture: Fixture,
    request_update: dict[str, object],
    evidence_update: dict[str, object],
    field: str,
) -> None:
    _rewrite_evidence(fixture, _evidence(fixture.raw_digest, **evidence_update))
    with pytest.raises(VerificationError, match=field):
        fixture.verifier.issue_receipt(
            _request(**request_update),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_traversal_scope_rejected_even_after_model_copy_bypass(fixture: Fixture) -> None:
    escaped = "packages/traincapsule-core/../../tcfactory/controller.py"
    with pytest.raises(ValueError, match="normalized"):
        _request(publicationScope=[escaped])
    copied = _request().model_copy(update={"publication_scope": [escaped]})
    copied = copied.model_copy(update={"request_digest": verification_request_digest(copied)})
    with pytest.raises(VerificationError, match="request contract"):
        fixture.verifier.issue_receipt(
            copied,
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


@pytest.mark.parametrize(
    ("root_name", "relative"),
    [
        ("config", "policy.json"),
        ("config", "public-key.pem"),
        ("state", "revocations.json"),
        ("anchor_root", "authority-anchor.json"),
        ("oracle", "conformance-oracle.py"),
    ],
)
def test_world_writable_authority_files_fail_closed(
    fixture: Fixture, root_name: str, relative: str
) -> None:
    path = getattr(fixture, root_name) / relative
    path.chmod(0o777 if root_name == "oracle" else 0o666)
    with pytest.raises(TrustedPathError, match="writable"):
        verifier = _external_verifier(fixture)
        if root_name == "oracle":
            verifier.issue_receipt(
                _request(nonce="world-writable-oracle"),
                evidence_root=fixture.evidence,
                repository_root=fixture.repo,
                evidence_owner_uid=os.getuid(),
                now=NOW,
            )


@pytest.mark.parametrize("relative", ["evidence.json", "raw/evidence.bin"])
def test_world_writable_evidence_files_fail_closed(fixture: Fixture, relative: str) -> None:
    (fixture.evidence / relative).chmod(0o666)
    with pytest.raises(TrustedPathError, match="writable"):
        fixture.verifier.issue_receipt(
            _request(nonce=f"writable-evidence-{relative.replace('/', '-')}"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )


def test_receipt_publication_uses_anchored_directory_identity(fixture: Fixture) -> None:
    moved = fixture.receipts.with_name("receipts-moved")
    fixture.receipts.rename(moved)
    fixture.receipts.mkdir(mode=0o700)
    receipt = fixture.verifier.issue_receipt(
        _request(nonce="anchored-receipt-root"),
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    assert (moved / f"{receipt.receipt_id}.json").is_file()
    assert not (fixture.receipts / f"{receipt.receipt_id}.json").exists()


def test_revocation_epoch_rollback_conflicts_with_external_anchor(fixture: Fixture) -> None:
    advanced = _signed_revocations(
        fixture.key,
        revocationEpoch=2,
        previousListDigest=model_digest(fixture.revocations),
    )
    (fixture.state / "revocations.json").write_bytes(canonical_json_bytes(advanced))
    with pytest.raises(VerificationError, match="monotonic external anchor"):
        _external_verifier(fixture)


def test_rotated_key_anchor_requires_predecessor_digest(fixture: Fixture) -> None:
    payload = _anchor(fixture.policy, fixture.revocations).model_dump(mode="python", by_alias=True)
    payload["keyEpoch"] = 2
    with pytest.raises(ValueError, match="predecessor"):
        AuthorityAnchor.model_validate(payload, strict=True)


def test_descriptor_count_stable_across_valid_and_failing_requests(
    fixture: Fixture,
) -> None:
    baseline = _descriptor_count()
    for index in range(100):
        fixture.verifier.issue_receipt(
            _request(nonce=f"fd-valid-request-{index:04d}"),
            evidence_root=fixture.evidence,
            repository_root=fixture.repo,
            evidence_owner_uid=os.getuid(),
            now=NOW,
        )
    assert _descriptor_count() <= baseline + 2

    (fixture.evidence / "raw/evidence.bin").write_bytes(b"invalid replacement\n")
    for index in range(100):
        with pytest.raises(VerificationError, match="raw evidence artifact digest"):
            fixture.verifier.issue_receipt(
                _request(nonce=f"fd-failing-request-{index:04d}"),
                evidence_root=fixture.evidence,
                repository_root=fixture.repo,
                evidence_owner_uid=os.getuid(),
                now=NOW,
            )
    assert _descriptor_count() <= baseline + 2


def test_descriptor_count_stable_across_attestations_and_verifier_context(
    fixture: Fixture, tmp_path: Path
) -> None:
    destination = tmp_path / "descriptor-attestation"
    rehearse_layout(destination, _public_key_pem(fixture.key))
    baseline = _descriptor_count()
    for _ in range(100):
        attest_installation(
            destination,
            distribution_root=Path(__file__).resolve().parents[1] / "verifier",
            expected_owner_uid=os.getuid(),
        )
    assert _descriptor_count() <= baseline + 2

    logs = destination / "var/log/traincapsule-verifier"
    moved_logs = destination / "var/log/traincapsule-verifier-real"
    logs.rename(moved_logs)
    logs.symlink_to(moved_logs, target_is_directory=True)
    for _ in range(100):
        with pytest.raises(InstallationError, match="logs trust root"):
            attest_installation(
                destination,
                distribution_root=Path(__file__).resolve().parents[1] / "verifier",
                expected_owner_uid=os.getuid(),
            )
    assert _descriptor_count() <= baseline + 2

    with _external_verifier(fixture) as scoped_verifier:
        assert _descriptor_count() <= baseline + 5
        scoped_verifier.verify_receipt(
            fixture.verifier.issue_receipt(
                _request(nonce="fd-context-policy-receipt"),
                evidence_root=fixture.evidence,
                repository_root=fixture.repo,
                evidence_owner_uid=os.getuid(),
                now=NOW,
            ),
            now=NOW,
        )
    scoped_verifier.close()
    assert _descriptor_count() <= baseline + 2
    with pytest.raises(VerificationError, match="closed"):
        scoped_verifier.verify_receipt(
            fixture.verifier.issue_receipt(
                _request(nonce="fd-closed-verifier-receipt"),
                evidence_root=fixture.evidence,
                repository_root=fixture.repo,
                evidence_owner_uid=os.getuid(),
                now=NOW,
            ),
            now=NOW,
        )


def test_activation_observes_artifacts_and_rechecks_linked_receipt(fixture: Fixture) -> None:
    policy_receipt = fixture.verifier.issue_receipt(
        _request(nonce="activation-policy-proof"),
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    bogus = _activation_request(
        fixture,
        policy_receipt,
        nonce="activation-bogus-artifact",
        machineEnvironmentDigest=DIGEST_A,
    )
    with pytest.raises(VerificationError, match="machine environment digest"):
        fixture.verifier.issue_activation(
            bogus,
            observed_main_sha=SHA_A,
            activation_root=fixture.activation,
            repository_root=fixture.repo,
            activation_owner_uid=os.getuid(),
            now=NOW,
        )

    request = _activation_request(fixture, policy_receipt, nonce="activation-valid-proof")
    activation = fixture.verifier.issue_activation(
        request,
        observed_main_sha=SHA_A,
        activation_root=fixture.activation,
        repository_root=fixture.repo,
        activation_owner_uid=os.getuid(),
        now=NOW,
    )
    revoked = _signed_revocations(
        fixture.key,
        revocationEpoch=2,
        previousListDigest=model_digest(fixture.revocations),
        revokedReceiptIds=[policy_receipt.receipt_id],
    )
    revoked_verifier = IndependentVerifier(
        policy=fixture.policy,
        revocations=revoked,
        signing_key=fixture.key,
        public_key=fixture.key.public_key(),
        anchor=_anchor(fixture.policy, revoked),
        state_root=fixture.verifier.state_root,
        receipt_root=fixture.verifier.receipt_root,
        oracle_root=fixture.verifier.oracle_root,
    )
    with pytest.raises(VerificationError, match="revoked"):
        revoked_verifier.verify_activation(
            activation,
            observed_main_sha=SHA_A,
            machine_policy_receipt=policy_receipt,
            activation_root=fixture.activation,
            repository_root=fixture.repo,
            activation_owner_uid=os.getuid(),
            now=NOW,
        )


def test_activation_future_and_excessive_lifetime_fail(fixture: Fixture) -> None:
    policy_receipt = fixture.verifier.issue_receipt(
        _request(nonce="activation-lifetime-policy"),
        evidence_root=fixture.evidence,
        repository_root=fixture.repo,
        evidence_owner_uid=os.getuid(),
        now=NOW,
    )
    activation = fixture.verifier.issue_activation(
        _activation_request(fixture, policy_receipt, nonce="activation-lifetime-valid"),
        observed_main_sha=SHA_A,
        activation_root=fixture.activation,
        repository_root=fixture.repo,
        activation_owner_uid=os.getuid(),
        now=NOW,
    )
    invalid = activation.model_copy(
        update={
            "issued_at": NOW + timedelta(days=1),
            "expires_at": NOW + timedelta(days=365),
        }
    )
    invalid = invalid.model_copy(update={"signature": sign_model(invalid, fixture.key)})
    with pytest.raises(VerificationError, match="activation receipt contract"):
        fixture.verifier.verify_activation(
            invalid,
            observed_main_sha=SHA_A,
            machine_policy_receipt=policy_receipt,
            activation_root=fixture.activation,
            repository_root=fixture.repo,
            activation_owner_uid=os.getuid(),
            now=NOW,
        )


def test_install_attestation_rejects_garbage_and_never_claims_live_ready(
    tmp_path: Path,
) -> None:
    key = Ed25519PrivateKey.generate()
    destination = tmp_path / "installed"
    rehearse_layout(destination, _public_key_pem(key))
    policy = _policy(key)
    revocations = _signed_revocations(key)
    (destination / "etc/traincapsule-verifier/policy.json").write_bytes(
        canonical_json_bytes(policy)
    )
    signing_key = destination / "var/lib/traincapsule-verifier/private/signing-key.pem"
    signing_key.write_bytes(_private_key_pem(key))
    signing_key.chmod(0o600)
    state = destination / "var/lib/traincapsule-verifier"
    (state / "revocations.json").write_bytes(canonical_json_bytes(revocations))
    (state / "authority-anchor.json").write_bytes(
        canonical_json_bytes(_anchor(policy, revocations))
    )
    oracle = state / "oracle/conformance-oracle.py"
    oracle.write_bytes(ORACLE_RUNNER)
    oracle.chmod(0o700)
    attestation = attest_installation(
        destination,
        distribution_root=Path(__file__).resolve().parents[1] / "verifier",
        expected_owner_uid=os.getuid(),
    )
    assert attestation.authority_validated
    assert attestation.state.value == "STAGED_NOT_ACTIVATED"
    assert not attestation.live_oracle_verified
    assert not attestation.live_service_verified

    (destination / "etc/traincapsule-verifier/policy.json").write_bytes(b"garbage\n")
    with pytest.raises((InstallationError, TrustedPathError), match="invalid|malformed"):
        attest_installation(
            destination,
            distribution_root=Path(__file__).resolve().parents[1] / "verifier",
            expected_owner_uid=os.getuid(),
        )


def test_no_private_key_credentials_or_minted_receipts_are_committed() -> None:
    verifier_root = Path(__file__).resolve().parents[1] / "verifier"
    forbidden_names = ("signing-key", "private-key", "credential", "receipt.json")
    files = [path for path in verifier_root.rglob("*") if path.is_file()]
    assert not [
        path for path in files if any(name in path.name.lower() for name in forbidden_names)
    ]
    for path in files:
        if path.suffix not in {".py", ".md", ".toml"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "BEGIN PRIVATE KEY" not in text
        assert "github_pat_" not in text


def test_public_schemas_and_canonical_vector_are_exact() -> None:
    expected = rendered_schemas()
    assert {path.name for path in SCHEMA_ROOT.glob("*.schema.json")} == set(expected)
    for name, content in expected.items():
        assert (SCHEMA_ROOT / name).read_bytes() == content
        assert b"\r" not in content
        schema = json.loads(content)
        assert schema["additionalProperties"] is False
        assert "schemaVersion" in schema["required"]
    vector = json.loads(
        (Path(__file__).resolve().parents[1] / "verifier/tests/canonical-vector.json").read_bytes()
    )
    payload = vector["payload"]
    canonical = canonical_json_bytes(payload)
    assert canonical.decode() == vector["canonical"]
    assert sha256_digest(canonical) == vector["digest"]
