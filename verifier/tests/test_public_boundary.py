from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from traincapsule_verifier.canonical import canonical_json_bytes, model_digest, sha256_digest
from traincapsule_verifier.check_publisher import (
    CheckDeliveryReceipt,
    CheckEvent,
    CheckPublisherBackend,
    CheckPublisherPolicy,
    CheckPublisherUnavailable,
    CheckPublisherWorker,
    CheckPublishRequest,
)
from traincapsule_verifier.crypto import public_key_fingerprint, sign_model
from traincapsule_verifier.filesystem import open_trusted_root
from traincapsule_verifier.models import (
    ActivationMode,
    ActivationReceipt,
    AuthorityAnchor,
    CommercialCeiling,
    EngineeringCeiling,
    EvidenceMode,
    GateResult,
    MachinePolicyReceipt,
    NativeDisposition,
    PolicyDecision,
    RevocationList,
    RiskPolicy,
    ValueDisposition,
    VerifierPolicy,
)
from traincapsule_verifier.public_cli import validate_public_executable
from traincapsule_verifier.public_verifier import (
    PublicVerificationError,
    PublicVerifier,
    validate_root_owned_ancestry,
)

NOW = datetime.now(UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SHA_A = "a" * 40
SHA_B = "b" * 40


def _signed[T: RevocationList | MachinePolicyReceipt | ActivationReceipt](
    model: T, key: Ed25519PrivateKey
) -> T:
    return model.model_copy(update={"signature": sign_model(model, key)})


@dataclass
class PublicFixture:
    repository: Path
    config: Path
    state: Path
    receipts: Path
    journal: Path
    key: Ed25519PrivateKey
    policy: VerifierPolicy
    revocations: RevocationList
    machine: MachinePolicyReceipt
    activation: ActivationReceipt

    def verifier(self) -> PublicVerifier:
        return PublicVerifier.from_public_roots(
            repository_root=self.repository,
            config_root=self.config,
            state_root=self.state,
            receipt_root=self.receipts,
            expected_owner_uid=os.getuid(),
        )


@pytest.fixture
def public_fixture(tmp_path: Path) -> PublicFixture:
    repository = tmp_path / "repository"
    external = tmp_path / "authority"
    config = external / "etc"
    state = external / "state"
    receipts = state / "receipts"
    journal = external / "check-journal"
    for path in (repository, config, state, receipts, journal):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)

    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    policy = VerifierPolicy(
        schema_version="3.1",
        policy_id="POLICY:PUBLIC",
        policy_version="3.1.0",
        issuer_id="ISSUER:PUBLIC",
        issuer_key_id="KEY:PUBLIC",
        public_key_fingerprint=public_key_fingerprint(key.public_key()),
        minimum_revocation_epoch=1,
        active_source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        active_source_generation_digest=DIGEST_A,
        private_gate_suite_id="GATES:PRIVATE",
        private_gate_runner_digest=DIGEST_B,
        risk_policies={
            "HIGH": RiskPolicy(
                required_gates=["GATE:ONE"],
                required_oracle_ids=["ORACLE:ONE"],
                oracle_runner_digests={"ORACLE:ONE": DIGEST_A},
                oracle_runner_paths={"ORACLE:ONE": "oracle.py"},
                accepted_evidence_modes=[EvidenceMode.CONTROLLED_VALIDATED],
                maximum_engineering_ceiling=EngineeringCeiling.PASSED,
                maximum_commercial_ceiling=CommercialCeiling.PILOT_ELIGIBLE,
            )
        },
        allowed_claims=["CLAIM:VERIFIED"],
        forbidden_claims=["CLAIM:FORBIDDEN"],
        allowed_publication_scopes=["dist/result.json"],
        maximum_receipt_lifetime_seconds=3600,
        maximum_evidence_age_seconds=3600,
    )
    unsigned_revocations = RevocationList(
        schema_version="3.1",
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        revocation_epoch=1,
        previous_list_digest=None,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=2),
        revoked_receipt_ids=[],
        revoked_nonces=[],
        revoked_key_ids=[],
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    revocations = _signed(unsigned_revocations, key)
    anchor = AuthorityAnchor(
        schema_version="3.1",
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        public_key_fingerprint=policy.public_key_fingerprint,
        key_epoch=1,
        previous_key_anchor_digest=None,
        revocation_epoch=1,
        revocation_list_digest=model_digest(revocations),
        previous_revocation_list_digest=None,
    )
    unsigned_machine = MachinePolicyReceipt(
        schema_version="3.1",
        receipt_id="MPOL:PUBLIC-BOUNDARY",
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revocation_epoch=1,
        nonce="machine-nonce-0001",
        request_digest=DIGEST_A,
        work_item_id="V3-IMPL-001",
        milestone_id="M6_PUBLIC",
        lane="PUBLIC",
        risk_tier="HIGH",
        candidate_sha=SHA_A,
        candidate_tree_sha=SHA_B,
        base_sha="c" * 40,
        source_generation_id=policy.active_source_generation_id,
        source_generation_digest=policy.active_source_generation_digest,
        context_manifest_digest=DIGEST_A,
        task_packet_digest=DIGEST_B,
        candidate_manifest_digest=DIGEST_A,
        checkpoint_digest=DIGEST_B,
        required_gate_results={"GATE:ONE": GateResult.PASS},
        private_gate_suite_id=policy.private_gate_suite_id,
        private_gate_runner_digest=policy.private_gate_runner_digest,
        independent_oracle_ids=["ORACLE:ONE"],
        raw_evidence_artifact_hashes=[DIGEST_A],
        native_substitute_disposition=NativeDisposition.INCREMENTAL_VALUE,
        decision_value_disposition=ValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED,
        engineering_maturity_ceiling=EngineeringCeiling.PASSED,
        commercial_maturity_ceiling=CommercialCeiling.PILOT_ELIGIBLE,
        allowed_claims=["CLAIM:VERIFIED"],
        forbidden_claims=["CLAIM:FORBIDDEN"],
        publication_scope=["dist/result.json"],
        decision=PolicyDecision.PASS,
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    machine = _signed(unsigned_machine, key)
    unsigned_activation = ActivationReceipt(
        schema_version="3.1",
        receipt_id="ACT:PUBLIC-BOUNDARY",
        verified_main_sha=SHA_A,
        machine_environment_digest=DIGEST_B,
        source_generation_id=policy.active_source_generation_id,
        source_generation_digest=policy.active_source_generation_digest,
        controller_binary_digest=DIGEST_A,
        controller_config_digest=DIGEST_B,
        machine_environment_path="machine.json",
        controller_binary_path="controller.bin",
        controller_config_path="controller.json",
        machine_policy_receipt_id=machine.receipt_id,
        machine_policy_receipt_digest=model_digest(machine),
        mode=ActivationMode.LIVE,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        revocation_epoch=1,
        nonce="activation-nonce-01",
        issuer_id=policy.issuer_id,
        issuer_key_id=policy.issuer_key_id,
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    activation = _signed(unsigned_activation, key)
    values = {
        config / "policy.json": canonical_json_bytes(policy),
        config / "public-key.pem": public_pem,
        state / "revocations.json": canonical_json_bytes(revocations),
        state / "authority-anchor.json": canonical_json_bytes(anchor),
        receipts / f"{machine.receipt_id}.json": canonical_json_bytes(machine),
        receipts / f"{activation.receipt_id}.json": canonical_json_bytes(activation),
    }
    for path, value in values.items():
        path.write_bytes(value)
        path.chmod(0o600)
    private = state / "private"
    private.mkdir(mode=0o700)
    (private / "signing-key.pem").write_bytes(b"must-not-be-read")
    (private / "signing-key.pem").chmod(0)
    return PublicFixture(
        repository, config, state, receipts, journal, key, policy, revocations, machine, activation
    )


def _authorize(verifier: PublicVerifier, fixture: PublicFixture) -> Any:
    return verifier.authorize_receipt(
        fixture.machine,
        candidate_sha=SHA_A,
        candidate_tree_sha=SHA_B,
        base_sha="c" * 40,
        work_item_id="V3-IMPL-001",
        candidate_manifest_digest=DIGEST_A,
        now=NOW + timedelta(minutes=1),
    )


def test_public_verifier_has_no_private_key_dependency_and_emits_exact_contract(
    public_fixture: PublicFixture,
) -> None:
    import traincapsule_verifier.public_cli as public_cli
    import traincapsule_verifier.public_verifier as public_verifier

    assert "load_private_key" not in Path(public_verifier.__file__).read_text()
    assert "attestation" not in Path(public_cli.__file__).read_text()
    source_root = Path(public_cli.__file__).resolve().parents[1]
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(source_root)!r}); "
                "import traincapsule_verifier.public_cli; "
                "assert 'traincapsule_verifier.crypto' not in sys.modules; "
                "assert 'traincapsule_verifier.evaluator' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert probe.returncode == 0, probe.stderr
    with public_fixture.verifier() as verifier:
        authorization = _authorize(verifier, public_fixture)
    assert authorization.model_dump(mode="json", by_alias=True) == {
        "schemaVersion": "3.1",
        "checkName": "TrainCapsule / Machine policy",
        "candidateSha": SHA_A,
        "conclusion": "success",
        "receiptId": public_fixture.machine.receipt_id,
        "receiptDigest": model_digest(public_fixture.machine),
    }


def test_wrong_sha_tamper_expiry_revocation_and_writable_root_fail_closed(
    public_fixture: PublicFixture,
) -> None:
    with public_fixture.verifier() as verifier:
        with pytest.raises(PublicVerificationError, match="candidate SHA mismatch"):
            verifier.authorize_receipt(
                public_fixture.machine,
                candidate_sha="f" * 40,
                candidate_tree_sha=SHA_B,
                base_sha="c" * 40,
                work_item_id="V3-IMPL-001",
                candidate_manifest_digest=DIGEST_A,
                now=NOW,
            )
        tampered = public_fixture.machine.model_copy(update={"candidate_sha": "f" * 40})
        with pytest.raises(PublicVerificationError, match="signature"):
            verifier.verify_machine_receipt(tampered, now=NOW)
        with pytest.raises(PublicVerificationError, match="expired"):
            verifier.verify_machine_receipt(public_fixture.machine, now=NOW + timedelta(hours=2))

    revoked_unsigned = public_fixture.revocations.model_copy(
        update={
            "revoked_receipt_ids": [public_fixture.machine.receipt_id],
            "signature": "A" * 88,
        }
    )
    revoked = _signed(revoked_unsigned, public_fixture.key)
    anchor = AuthorityAnchor(
        schema_version="3.1",
        policy_id=public_fixture.policy.policy_id,
        policy_version=public_fixture.policy.policy_version,
        issuer_id=public_fixture.policy.issuer_id,
        issuer_key_id=public_fixture.policy.issuer_key_id,
        public_key_fingerprint=public_fixture.policy.public_key_fingerprint,
        key_epoch=1,
        previous_key_anchor_digest=None,
        revocation_epoch=1,
        revocation_list_digest=model_digest(revoked),
        previous_revocation_list_digest=None,
    )
    (public_fixture.state / "revocations.json").write_bytes(canonical_json_bytes(revoked))
    (public_fixture.state / "authority-anchor.json").write_bytes(canonical_json_bytes(anchor))
    with (
        public_fixture.verifier() as verifier,
        pytest.raises(PublicVerificationError, match="revoked"),
    ):
        verifier.verify_machine_receipt(public_fixture.machine, now=NOW)

    public_fixture.config.chmod(0o777)
    with pytest.raises(PublicVerificationError, match="trust state|matching authority"):
        public_fixture.verifier()


def test_activation_is_exact_current_linked_and_signed(public_fixture: PublicFixture) -> None:
    with public_fixture.verifier() as verifier:
        authorization = verifier.authorize_activation(
            public_fixture.activation,
            main_sha=SHA_A,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
            source_generation_digest=DIGEST_A,
            controller_binary_digest=DIGEST_A,
            controller_config_digest=DIGEST_B,
            now=NOW + timedelta(minutes=1),
        )
        assert authorization.verified is True
        with pytest.raises(PublicVerificationError, match="main SHA mismatch"):
            verifier.authorize_activation(
                public_fixture.activation,
                main_sha="f" * 40,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
                source_generation_digest=DIGEST_A,
                controller_binary_digest=DIGEST_A,
                controller_config_digest=DIGEST_B,
                now=NOW,
            )


def test_activation_rechecks_linked_receipt_revocation(public_fixture: PublicFixture) -> None:
    revoked_unsigned = public_fixture.revocations.model_copy(
        update={
            "revoked_receipt_ids": [public_fixture.machine.receipt_id],
            "signature": "A" * 88,
        }
    )
    revoked = _signed(revoked_unsigned, public_fixture.key)
    anchor = AuthorityAnchor(
        schema_version="3.1",
        policy_id=public_fixture.policy.policy_id,
        policy_version=public_fixture.policy.policy_version,
        issuer_id=public_fixture.policy.issuer_id,
        issuer_key_id=public_fixture.policy.issuer_key_id,
        public_key_fingerprint=public_fixture.policy.public_key_fingerprint,
        key_epoch=1,
        previous_key_anchor_digest=None,
        revocation_epoch=1,
        revocation_list_digest=model_digest(revoked),
        previous_revocation_list_digest=None,
    )
    (public_fixture.state / "revocations.json").write_bytes(canonical_json_bytes(revoked))
    (public_fixture.state / "authority-anchor.json").write_bytes(canonical_json_bytes(anchor))
    with (
        public_fixture.verifier() as verifier,
        pytest.raises(PublicVerificationError, match="revoked"),
    ):
        verifier.authorize_activation(
            public_fixture.activation,
            main_sha=SHA_A,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
            source_generation_digest=DIGEST_A,
            controller_binary_digest=DIGEST_A,
            controller_config_digest=DIGEST_B,
            now=NOW,
        )


def test_public_roots_are_descriptor_pinned_and_symlink_ancestry_fails(
    public_fixture: PublicFixture, tmp_path: Path
) -> None:
    verifier = public_fixture.verifier()
    moved = public_fixture.state / "receipts-original"
    public_fixture.receipts.rename(moved)
    public_fixture.receipts.mkdir(mode=0o700)
    try:
        assert _authorize(verifier, public_fixture).candidate_sha == SHA_A
    finally:
        verifier.close()

    linked = tmp_path / "linked-root"
    linked.symlink_to(moved, target_is_directory=True)
    with pytest.raises(PublicVerificationError, match="trust state"):
        PublicVerifier.from_public_roots(
            repository_root=public_fixture.repository,
            config_root=public_fixture.config,
            state_root=public_fixture.state,
            receipt_root=linked,
            expected_owner_uid=os.getuid(),
        )
    with pytest.raises(PublicVerificationError, match="root-controlled"):
        validate_root_owned_ancestry(tmp_path / "authority")


@pytest.mark.parametrize(
    "root_name,relative",
    [
        ("config", "policy.json"),
        ("state", "revocations.json"),
        ("state", "authority-anchor.json"),
        ("receipts", "MPOL:PUBLIC-BOUNDARY.json"),
    ],
)
def test_world_writable_public_file_fails_closed(
    public_fixture: PublicFixture, root_name: str, relative: str
) -> None:
    (getattr(public_fixture, root_name) / relative).chmod(0o666)
    with (
        pytest.raises(PublicVerificationError, match="trust state|matching authority"),
        public_fixture.verifier() as verifier,
    ):
        _authorize(verifier, public_fixture)


def test_stale_public_revocation_state_fails_closed(public_fixture: PublicFixture) -> None:
    stale_unsigned = public_fixture.revocations.model_copy(
        update={
            "issued_at": NOW - timedelta(hours=2),
            "expires_at": NOW - timedelta(hours=1),
            "signature": "A" * 88,
        }
    )
    stale = _signed(stale_unsigned, public_fixture.key)
    anchor = AuthorityAnchor(
        schema_version="3.1",
        policy_id=public_fixture.policy.policy_id,
        policy_version=public_fixture.policy.policy_version,
        issuer_id=public_fixture.policy.issuer_id,
        issuer_key_id=public_fixture.policy.issuer_key_id,
        public_key_fingerprint=public_fixture.policy.public_key_fingerprint,
        key_epoch=1,
        previous_key_anchor_digest=None,
        revocation_epoch=1,
        revocation_list_digest=model_digest(stale),
        previous_revocation_list_digest=None,
    )
    (public_fixture.state / "revocations.json").write_bytes(canonical_json_bytes(stale))
    (public_fixture.state / "authority-anchor.json").write_bytes(canonical_json_bytes(anchor))
    with (
        public_fixture.verifier() as verifier,
        pytest.raises(PublicVerificationError, match="revocation list is expired"),
    ):
        verifier.verify_machine_receipt(public_fixture.machine, now=NOW)


def test_public_executable_rejects_writable_and_detects_swap(tmp_path: Path) -> None:
    parent = tmp_path / "root-bin"
    parent.mkdir(mode=0o700)
    executable = parent / "verifier"
    executable.write_text("#!/bin/sh\nexit 1\n")
    executable.chmod(0o500)
    identity = validate_public_executable(str(executable), expected_owner_uid=os.getuid())
    executable.unlink()
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o500)
    with pytest.raises(PublicVerificationError, match="identity changed"):
        identity.revalidate()
    identity.close()
    executable.chmod(0o777)
    with pytest.raises(PublicVerificationError, match="writable"):
        validate_public_executable(str(executable), expected_owner_uid=os.getuid())


def test_public_cli_exact_arguments_output_and_service_unavailability(
    public_fixture: PublicFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    from traincapsule_verifier import public_cli

    bin_root = tmp_path / "root-bin"
    bin_root.mkdir(mode=0o700)
    executable = bin_root / "traincapsule-verifier-verify-receipt"
    executable.write_text("#!/bin/sh\nexit 1\n")
    executable.chmod(0o500)
    for name in ("revocations.json", "authority-anchor.json"):
        (public_fixture.config / name).write_bytes(
            (public_fixture.state / name).read_bytes()
        )
    monkeypatch.setattr(public_cli, "CONFIG_ROOT", public_fixture.config)
    monkeypatch.setattr(public_cli, "STATE_ROOT", public_fixture.state)
    monkeypatch.setattr(public_cli, "RECEIPT_ROOT", public_fixture.receipts)
    monkeypatch.setattr(public_cli, "EXPECTED_OWNER_UID", os.getuid())
    arguments = [
        str(executable),
        "verify-receipt",
        "--receipt",
        str(public_fixture.receipts / f"{public_fixture.machine.receipt_id}.json"),
        "--candidate-sha",
        SHA_A,
        "--candidate-tree-sha",
        SHA_B,
        "--base-sha",
        "c" * 40,
        "--work-item-id",
        "V3-IMPL-001",
        "--candidate-manifest-digest",
        DIGEST_A,
    ]
    monkeypatch.setattr(sys, "argv", arguments)
    assert public_cli.main() == 0
    output = capfd.readouterr()
    assert output.err == ""
    assert b"CREDENTIAL" not in output.out.encode()
    assert '"candidateSha":"' + SHA_A + '"' in output.out

    wrong = list(arguments)
    wrong[wrong.index(SHA_A)] = "f" * 40
    monkeypatch.setattr(sys, "argv", wrong)
    assert public_cli.main() == 1
    rejected = capfd.readouterr()
    assert rejected.out == ""
    assert rejected.err == "independent public verifier rejected authorization\n"

    monkeypatch.setattr(public_cli, "CONFIG_ROOT", tmp_path / "missing-service")
    monkeypatch.setattr(sys, "argv", arguments)
    assert public_cli.main() == 1
    unavailable = capfd.readouterr()
    assert unavailable.out == ""
    assert unavailable.err == "independent public verifier rejected authorization\n"


class FakeBackend(CheckPublisherBackend):
    def __init__(self, events: list[CheckEvent]) -> None:
        self.events = events
        self.deliveries: dict[str, CheckDeliveryReceipt] = {}
        self.publish_calls = 0
        self.fail_after_first_publish = False

    @property
    def backend_id(self) -> str:
        return "GITHUB:APP"

    @property
    def github_app_id(self) -> int:
        return 456

    def poll(self, *, after_event_id: str | None, limit: int) -> list[CheckEvent]:
        return self.events[:limit]

    def lookup(self, *, request: CheckPublishRequest) -> CheckDeliveryReceipt | None:
        return self.deliveries.get(request.action_digest)

    def publish(self, request: CheckPublishRequest) -> CheckDeliveryReceipt:
        self.publish_calls += 1
        delivery = CheckDeliveryReceipt(
            schema_version="3.1",
            action_digest=request.action_digest,
            backend_id=self.backend_id,
            repository=request.repository,
            github_app_id=request.github_app_id,
            installation_id=request.installation_id,
            external_check_id=f"check-{self.publish_calls}",
            check_name=request.check_name,
            candidate_sha=request.candidate_sha,
            conclusion=request.conclusion,
            receipt_id=request.receipt_id,
            receipt_digest=request.receipt_digest,
        )
        self.deliveries[request.action_digest] = delivery
        if self.fail_after_first_publish and self.publish_calls == 1:
            raise RuntimeError("ambiguous transport failure")
        return delivery


class WrongAppBackend(FakeBackend):
    @property
    def github_app_id(self) -> int:
        return 999


def _event(fixture: PublicFixture) -> CheckEvent:
    return CheckEvent(
        schema_version="3.1",
        event_id="EVENT:ONE",
        repository="owner/repository",
        github_app_id=456,
        installation_id=123,
        candidate_sha=fixture.machine.candidate_sha,
        candidate_tree_sha=fixture.machine.candidate_tree_sha,
        base_sha=fixture.machine.base_sha,
        work_item_id=fixture.machine.work_item_id,
        candidate_manifest_digest=fixture.machine.candidate_manifest_digest,
        receipt_id=fixture.machine.receipt_id,
        receipt_digest=model_digest(fixture.machine),
    )


def test_check_worker_reconciles_ambiguous_replay_without_second_send(
    public_fixture: PublicFixture,
) -> None:
    event = _event(public_fixture)
    duplicate_callback = event.model_copy(update={"event_id": "EVENT:TWO"})
    backend = FakeBackend([event, duplicate_callback])
    backend.fail_after_first_publish = True
    with public_fixture.verifier() as verifier, open_trusted_root(
        public_fixture.journal, expected_uid=os.getuid()
    ) as journal:
        worker = CheckPublisherWorker(
            verifier=verifier,
            policy=CheckPublisherPolicy(
                schema_version="3.1",
                repository="owner/repository",
                github_app_id=456,
                installation_id=123,
                backend_id="GITHUB:APP",
                credential_reference="CREDENTIAL:GITHUB-APP",
                check_name="TrainCapsule / Machine policy",
            ),
            journal_root=journal,
            backend=backend,
        )
        results = worker.run_once()
        assert [result.state for result in results] == [
            "WAITING_EXTERNAL_CHANNEL",
            "PUBLISHED",
        ]
        assert worker.process(event).state == "ALREADY_PUBLISHED"
    assert backend.publish_calls == 1


def test_check_worker_rejects_wrong_candidate_and_unavailable_service(
    public_fixture: PublicFixture,
) -> None:
    event = _event(public_fixture)
    wrong = event.model_copy(update={"candidate_sha": "f" * 40})
    backend = FakeBackend([])
    with public_fixture.verifier() as verifier, open_trusted_root(
        public_fixture.journal, expected_uid=os.getuid()
    ) as journal:
        worker = CheckPublisherWorker(
            verifier=verifier,
            policy=CheckPublisherPolicy(
                schema_version="3.1",
                repository="owner/repository",
                github_app_id=456,
                installation_id=123,
                backend_id="GITHUB:APP",
                credential_reference="CREDENTIAL:GITHUB-APP",
                check_name="TrainCapsule / Machine policy",
            ),
            journal_root=journal,
            backend=backend,
        )
        with pytest.raises(PublicVerificationError, match="candidate SHA mismatch"):
            worker.process(wrong)
        backend.events = [event]
        backend.publish = lambda request: (_ for _ in ()).throw(  # type: ignore[method-assign]
            RuntimeError("SECRET-CREDENTIAL-VALUE")
        )
        with pytest.raises(CheckPublisherUnavailable) as exc_info:
            worker.process(event)
        assert exc_info.value.state == "WAITING_EXTERNAL_CHANNEL"
        assert "SECRET" not in str(exc_info.value)
        assert exc_info.value.__cause__ is None


def test_check_worker_rejects_wrong_app_receipt_and_delivery(
    public_fixture: PublicFixture,
) -> None:
    event = _event(public_fixture)
    backend = FakeBackend([])
    with public_fixture.verifier() as verifier, open_trusted_root(
        public_fixture.journal, expected_uid=os.getuid()
    ) as journal:
        policy = CheckPublisherPolicy(
            schema_version="3.1",
            repository="owner/repository",
            github_app_id=456,
            installation_id=123,
            backend_id="GITHUB:APP",
            credential_reference="CREDENTIAL:GITHUB-APP",
            check_name="TrainCapsule / Machine policy",
        )
        worker = CheckPublisherWorker(
            verifier=verifier, policy=policy, journal_root=journal, backend=backend
        )
        with pytest.raises(ValueError, match="repository or installation"):
            worker.process(event.model_copy(update={"github_app_id": 999}))
        with pytest.raises(ValueError, match="receipt digest"):
            worker.process(event.model_copy(update={"receipt_digest": DIGEST_B}))

        def wrong_delivery(request: CheckPublishRequest) -> CheckDeliveryReceipt:
            return CheckDeliveryReceipt.model_construct(
                schema_version="3.1",
                action_digest=request.action_digest,
                backend_id=request.backend_id,
                repository=request.repository,
                github_app_id=request.github_app_id,
                installation_id=request.installation_id,
                external_check_id="spoofed-check",
                check_name="Wrong check",
                candidate_sha=request.candidate_sha,
                conclusion=request.conclusion,
                receipt_id=request.receipt_id,
                receipt_digest=request.receipt_digest,
            )

        backend.publish = wrong_delivery  # type: ignore[method-assign]
        with pytest.raises(CheckPublisherUnavailable):
            worker.process(event)

    wrong_backend = WrongAppBackend([])
    with public_fixture.verifier() as verifier, open_trusted_root(
        public_fixture.journal, expected_uid=os.getuid()
    ) as journal, pytest.raises(ValueError, match="GitHub App identity"):
        CheckPublisherWorker(
            verifier=verifier,
            policy=policy,
            journal_root=journal,
            backend=wrong_backend,
        )


def test_public_outputs_never_expose_credential_reference(public_fixture: PublicFixture) -> None:
    event = _event(public_fixture)
    backend = FakeBackend([event])
    with public_fixture.verifier() as verifier, open_trusted_root(
        public_fixture.journal, expected_uid=os.getuid()
    ) as journal:
        result = CheckPublisherWorker(
            verifier=verifier,
            policy=CheckPublisherPolicy(
                schema_version="3.1",
                repository="owner/repository",
                github_app_id=456,
                installation_id=123,
                backend_id="GITHUB:APP",
                credential_reference="CREDENTIAL:DO-NOT-EMIT",
                check_name="TrainCapsule / Machine policy",
            ),
            journal_root=journal,
            backend=backend,
        ).run_once()[0]
    assert b"CREDENTIAL" not in canonical_json_bytes(result)
    assert b"CREDENTIAL" not in canonical_json_bytes(next(iter(backend.deliveries.values())))


def test_independent_wheel_sources_never_import_factory() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    assert not any("tcfactory" in path.read_text() for path in source_root.rglob("*.py"))
    assert sha256_digest(b"public-boundary").startswith("sha256:")
