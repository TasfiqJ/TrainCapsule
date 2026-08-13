from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tcfactory.util import write_json
from tcfactory.v3.contracts_v31 import (
    CommercialState,
    DecisionValueDisposition,
    GateResult,
    MachinePolicyReceiptV31,
    NativeSubstituteDisposition,
    PolicyDecision,
    TechnicalState,
)
from tcfactory.v3.enums import (
    ArtifactLocationClass,
    EvidenceType,
    Lane,
    RiskTier,
    SignatureAlgorithm,
)
from tcfactory.v3.external_actions import (
    ExternalActionAdapter,
    ExternalActionBackend,
    ExternalActionChannel,
    ExternalActionInstallation,
    ExternalActionJournal,
    ExternalActionOutcome,
    ExternalActionPayload,
    ExternalActionPolicyError,
    ExternalActionReason,
    ExternalActionRequest,
    ExternalActionStatus,
    ExternalActionTemplate,
    ExternalDeliveryReceipt,
    ExternalPolicyArtifactVerifier,
    MachinePolicyReceiptVerifier,
    external_action_authorization_digest,
    external_action_digest,
)
from tcfactory.v3.external_evidence import (
    EvidenceArtifact,
    EvidenceIssuer,
    EvidenceSignature,
    ExternalActionResponseBinding,
    ExternalEvidenceAuthorityAnchor,
    ExternalEvidenceReceipt,
    ExternalEvidenceRevocationList,
    ExternalEvidenceVerificationError,
    load_verified_external_evidence_payload,
)
from tcfactory.v3.external_evidence_authority import (
    ExternalEvidenceAuthorityBroker,
    ExternalEvidenceAuthorityLedger,
    ExternalEvidenceAuthorityState,
    ExternalEvidenceAuthorityStateError,
    key_fingerprint,
    load_external_evidence_authority_state,
)
from tcfactory.v3.phase6_runtime import Phase6ControllerRuntime, Phase6RuntimeError
from tcfactory.v3.work_items import WorkItem

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
SHA = "a" * 40
SHA_B = "b" * 40
DIGEST = "sha256:" + "c" * 64
DIGEST_B = "sha256:" + "d" * 64


def receipt(**updates: Any) -> MachinePolicyReceiptV31:
    payload: dict[str, Any] = {
        "schema_version": "3.1",
        "receipt_id": "RECEIPT:EXTERNAL:001",
        "policy_id": "POLICY:EXTERNAL:001",
        "policy_version": "3.1.0",
        "issuer_id": "VERIFIER:LOCAL:001",
        "issuer_key_id": "KEY:ED25519:001",
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(hours=1),
        "revocation_epoch": 1,
        "nonce": "0123456789abcdef",
        "request_digest": DIGEST,
        "work_item_id": "V3-MKT-001",
        "milestone_id": "M3_MARKET_EVIDENCE",
        "lane": Lane.MARKET,
        "risk_tier": RiskTier.EXTERNAL,
        "candidate_sha": SHA,
        "candidate_tree_sha": SHA_B,
        "base_sha": "e" * 40,
        "source_generation_id": "traincapsule-v3.1-zh-2026-08-12",
        "source_generation_digest": DIGEST,
        "context_manifest_digest": DIGEST,
        "task_packet_digest": DIGEST,
        "candidate_manifest_digest": DIGEST,
        "checkpoint_digest": DIGEST,
        "required_gate_results": {"EXTERNAL-ACTION": GateResult.PASS},
        "private_gate_suite_id": "EXTERNAL-ACTION-V31",
        "private_gate_runner_digest": DIGEST,
        "independent_oracle_ids": ["ORACLE:EXTERNAL:001"],
        "raw_evidence_artifact_hashes": [DIGEST_B],
        "native_substitute_disposition": NativeSubstituteDisposition.INCREMENTAL_VALUE,
        "decision_value_disposition": (
            DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        ),
        "engineering_maturity_ceiling": TechnicalState.PASSED,
        "commercial_maturity_ceiling": CommercialState.PILOT_ELIGIBLE,
        "allowed_claims": ["EXTERNAL_ACTION"],
        "forbidden_claims": [],
        "publication_scope": ["factory/actions/**"],
        "decision": PolicyDecision.PASS,
        "signature_algorithm": "ed25519",
        "signature": "f" * 128,
    }
    payload.update(updates)
    return MachinePolicyReceiptV31.model_validate(payload, strict=True)


def template() -> ExternalActionTemplate:
    return ExternalActionTemplate(
        schema_version="3.1",
        template_id="TEMPLATE:EMAIL:001",
        channel=ExternalActionChannel.EMAIL,
        subject_template="Hello {name}",
        body_template="Exact approved body for {name}: {message}",
        variable_names=["name", "message"],
    )


def installation(
    policy_receipt: MachinePolicyReceiptV31 | None = None,
) -> ExternalActionInstallation:
    return ExternalActionInstallation(
        schema_version="3.1",
        machine_policy_receipt=policy_receipt or receipt(),
        independent_verifier_receipt_digest=DIGEST_B,
        credential_reference="CREDREF:MAIL/PROD",
        backend_id="BACKEND:MAIL:001",
        recipient_allowlist=["allowed@example.test"],
        legal_policy_id="LEGAL:OUTREACH:001",
        legal_policy_digest=DIGEST,
        safety_policy_id="SAFETY:OUTREACH:001",
        safety_policy_digest=DIGEST_B,
        machine_policy_scope=["factory/actions/**"],
        channel=ExternalActionChannel.EMAIL,
        template=template(),
    )


def request(policy_receipt: MachinePolicyReceiptV31 | None = None) -> ExternalActionRequest:
    bound = policy_receipt or receipt()
    return ExternalActionRequest(
        schema_version="3.1",
        action_id="ACTION:EMAIL:001",
        work_item_id=bound.work_item_id,
        candidate_sha=bound.candidate_sha,
        channel=ExternalActionChannel.EMAIL,
        recipient="allowed@example.test",
        template_id="TEMPLATE:EMAIL:001",
        variables={"name": "Ada", "message": "Approved message"},
        machine_policy_receipt_id=bound.receipt_id,
        machine_policy_receipt_digest=external_action_digest(bound),
        requested_at=NOW,
    )


def bound_action() -> tuple[
    MachinePolicyReceiptV31, ExternalActionInstallation, ExternalActionRequest
]:
    initial = receipt()
    initial_installation = installation(initial)
    initial_request = request(initial)
    authorization_digest = external_action_authorization_digest(
        initial_request, initial_installation
    )
    bound = receipt(request_digest=authorization_digest)
    return bound, installation(bound), request(bound)


class Verifier(MachinePolicyReceiptVerifier):
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls = 0

    def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> str:
        del receipt, now
        self.calls += 1
        if self.reject:
            raise ValueError("invalid signature")
        return DIGEST_B


class PolicyVerifier(ExternalPolicyArtifactVerifier):
    def verify(self, *, policy_id: str, policy_digest: str) -> bool:
        return policy_id in {"LEGAL:OUTREACH:001", "SAFETY:OUTREACH:001"} and (
            policy_digest in {DIGEST, DIGEST_B}
        )


class Backend(ExternalActionBackend):
    backend_id = "BACKEND:MAIL:001"

    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.payloads: list[ExternalActionPayload] = []

    def is_available(self, *, channel: ExternalActionChannel, credential_reference: str) -> bool:
        assert channel is ExternalActionChannel.EMAIL
        assert credential_reference == "CREDREF:MAIL/PROD"
        return self.available

    def send(self, payload: ExternalActionPayload) -> ExternalDeliveryReceipt:
        self.payloads.append(payload)
        draft = ExternalDeliveryReceipt.model_construct(
            schema_version="3.1",
            backend_id=self.backend_id,
            backend_delivery_id="DELIVERY:001",
            action_digest=payload.action_digest,
            payload_digest=external_action_digest(payload),
            idempotency_key=payload.idempotency_key,
            delivery_generation_id=payload.delivery_generation_id,
            delivered_at=NOW,
            delivery_digest="sha256:" + "0" * 64,
        )
        return ExternalDeliveryReceipt.model_validate(
            draft.model_copy(
                update={
                    "delivery_digest": external_action_digest(draft, exclude={"delivery_digest"})
                }
            ).model_dump(by_alias=True),
            strict=True,
        )


def journal(tmp_path: Path, name: str = "journal") -> ExternalActionJournal:
    root = tmp_path / name
    root.mkdir()
    return ExternalActionJournal(root.resolve())


def action_response(
    outcome: ExternalActionOutcome,
    action: ExternalActionRequest,
    *,
    receipt_id: str = "XREC-ACTION-RESPONSE-001",
    response_nonce: str = "1" * 32,
) -> ExternalEvidenceReceipt:
    delivery = outcome.delivery_receipt
    assert delivery is not None
    observed_at = NOW + timedelta(seconds=1)
    return ExternalEvidenceReceipt(
        receipt_id=receipt_id,
        evidence_type=EvidenceType.CUSTOMER_CONVERSATION,
        subject_id=outcome.work_item_id,
        issuer=EvidenceIssuer(id="CUSTOMER-1", authority="recipient"),
        issued_at=NOW,
        observed_at=observed_at,
        expires_at=NOW + timedelta(days=1),
        revocation_epoch=1,
        revoked=False,
        nonce="a" * 32,
        candidate_or_offer_identity=outcome.candidate_sha,
        outcome="recipient response",
        artifacts=[
            EvidenceArtifact(
                name="response",
                digest=DIGEST,
                location_class=ArtifactLocationClass.TRUSTED_EXTERNAL,
            )
        ],
        limitations=[],
        signature=EvidenceSignature(
            algorithm=SignatureAlgorithm.ED25519, key_id="KEY-1", value="signed"
        ),
        synthetic_test_only=False,
        action_response_binding=ExternalActionResponseBinding(
            work_item_id=outcome.work_item_id,
            candidate_sha=outcome.candidate_sha,
            action_id=outcome.action_id,
            action_digest=outcome.request_digest,
            payload_digest=delivery.payload_digest,
            delivery_digest=delivery.delivery_digest,
            backend_delivery_id=delivery.backend_delivery_id,
            idempotency_key=delivery.idempotency_key,
            delivery_generation_id=delivery.delivery_generation_id,
            response_receipt_id=receipt_id,
            response_nonce=response_nonce,
            channel=action.channel.value,
            recipient=action.recipient,
            template_id=action.template_id,
            requested_at=action.requested_at,
            delivered_at=delivery.delivered_at,
            response_observed_at=observed_at,
            response_expires_at=observed_at + timedelta(minutes=15),
        ),
    )


def commercial_item() -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": "V3-MKT-001",
            "title": "Bounded commercial outreach",
            "lane": "MARKET",
            "kind": "COMMERCIAL_EXPERIMENT",
            "milestone": "M3_MARKET_EVIDENCE",
            "decisionContribution": "Request one bounded response.",
            "customerOutcome": "No claim before a verified response.",
            "dependsOn": [],
            "softDependsOn": [],
            "blocksCommercialRelease": True,
            "priority": 80,
            "riskTier": "EXTERNAL",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NOT_EVALUATED",
            },
            "disposition": "KEEP",
            "status": "PROPOSED",
            "ownerType": "EXTERNAL_PARTY",
            "automatable": False,
            "evidenceRequired": ["verified response"],
            "externalReceiptRequired": True,
            "retryPolicy": {
                "maxPlanAttempts": 2,
                "maxCandidateRepairCycles": 2,
                "maxSameFindingRepeats": 2,
                "maxCandidateRestarts": 1,
            },
        }
    )


def test_phase6_runtime_routes_exact_action_once_before_waiting_for_response(
    tmp_path: Path,
) -> None:
    bound, installed, action_request = bound_action()
    request_root = tmp_path / "requests"
    request_root.mkdir()
    write_json(
        request_root / "V3-MKT-001.json",
        action_request.model_dump(mode="json", by_alias=True),
    )
    backend = Backend()
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=backend,
        journal=journal(tmp_path),
    )
    runtime = Phase6ControllerRuntime(
        research_plan_root=tmp_path / "plans",
        research_acquirer=None,
        parser_registry=None,
        source_receipt_authority=None,
        external_request_root=request_root,
        external_action_adapter=adapter,
        external_outcome_root=tmp_path / "outcomes",
        external_action_item_ids=frozenset({"V3-MKT-001"}),
    )

    first = runtime.execute_commercial_action(
        item=commercial_item(), candidate_sha=SHA, now=NOW
    )
    second = runtime.execute_commercial_action(
        item=commercial_item(), candidate_sha=SHA, now=NOW
    )

    assert bound.receipt_id == action_request.machine_policy_receipt_id
    assert first.status is second.status is ExternalActionStatus.SENT
    assert first.request_digest == second.request_digest
    assert len(backend.payloads) == 1
    assert (tmp_path / "outcomes/V3-MKT-001.json").is_file()

    write_json(
        request_root / "V3-MKT-001.json",
        action_request.model_copy(update={"candidate_sha": SHA_B}).model_dump(
            mode="json", by_alias=True
        ),
    )
    with pytest.raises(Phase6RuntimeError, match="identity mismatch"):
        runtime.execute_commercial_action(
            item=commercial_item(), candidate_sha=SHA, now=NOW
        )
    assert len(backend.payloads) == 1


@pytest.mark.parametrize(
    ("adapter", "reason"),
    [
        (ExternalActionAdapter(), ExternalActionReason.ADAPTER_NOT_INSTALLED),
        (
            ExternalActionAdapter(installation=installation()),
            ExternalActionReason.VERIFIER_NOT_INSTALLED,
        ),
        (
            ExternalActionAdapter(installation=installation(), verifier=Verifier()),
            ExternalActionReason.POLICY_VERIFIER_NOT_INSTALLED,
        ),
        (
            ExternalActionAdapter(
                installation=installation(),
                verifier=Verifier(),
                policy_verifier=PolicyVerifier(),
            ),
            ExternalActionReason.BACKEND_NOT_INSTALLED,
        ),
    ],
)
def test_missing_external_prerequisite_waits_without_blocking_other_lanes(
    adapter: ExternalActionAdapter, reason: ExternalActionReason
) -> None:
    outcome = adapter.execute(request(), now=NOW)
    assert outcome.status is ExternalActionStatus.WAITING_EXTERNAL_CHANNEL
    assert outcome.reason is reason
    assert outcome.unrelated_lanes_may_continue is True
    assert outcome.delivery_receipt is None


def test_unverified_expired_or_unavailable_channel_waits_fail_closed(
    tmp_path: Path,
) -> None:
    _, installed, action = bound_action()
    rejected = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(reject=True),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path, "rejected"),
    ).execute(action, now=NOW)
    assert rejected.reason is ExternalActionReason.MACHINE_POLICY_UNVERIFIED

    expired = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path, "expired"),
    ).execute(action, now=NOW + timedelta(hours=2))
    assert expired.reason is ExternalActionReason.MACHINE_POLICY_EXPIRED

    unavailable = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(available=False),
        journal=journal(tmp_path, "unavailable"),
    ).execute(action, now=NOW)
    assert unavailable.reason is ExternalActionReason.CHANNEL_UNAVAILABLE


def test_exact_installed_action_sends_only_rendered_bounded_payload(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    backend = Backend()
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=backend,
        journal=journal(tmp_path),
    ).execute(action, now=NOW)

    assert outcome.status is ExternalActionStatus.SENT
    assert outcome.reason is ExternalActionReason.DELIVERED
    assert len(backend.payloads) == 1
    payload = backend.payloads[0]
    assert payload.recipient == "allowed@example.test"
    assert payload.subject == "Hello Ada"
    assert payload.body == "Exact approved body for Ada: Approved message"
    assert payload.credential_reference == "CREDREF:MAIL/PROD"
    assert outcome.delivery_receipt is not None
    assert outcome.delivery_receipt.idempotency_key == outcome.request_digest


def test_external_response_is_reverse_bound_to_exact_delivered_action(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path),
    ).execute(action, now=NOW)
    delivery = outcome.delivery_receipt
    assert delivery is not None
    binding = ExternalActionResponseBinding(
        work_item_id=outcome.work_item_id,
        candidate_sha=outcome.candidate_sha,
        action_id=outcome.action_id,
        action_digest=outcome.request_digest,
        payload_digest=delivery.payload_digest,
        delivery_digest=delivery.delivery_digest,
        backend_delivery_id=delivery.backend_delivery_id,
        idempotency_key=delivery.idempotency_key,
        delivery_generation_id=delivery.delivery_generation_id,
        response_receipt_id="XREC-ACTION-RESPONSE-001",
        response_nonce="1" * 32,
        channel=action.channel.value,
        recipient=action.recipient,
        template_id=action.template_id,
        requested_at=action.requested_at,
        delivered_at=delivery.delivered_at,
        response_observed_at=NOW + timedelta(seconds=1),
        response_expires_at=NOW + timedelta(minutes=15),
    )
    receipt = ExternalEvidenceReceipt(
        receipt_id="XREC-ACTION-RESPONSE-001",
        evidence_type=EvidenceType.CUSTOMER_CONVERSATION,
        subject_id=outcome.work_item_id,
        issuer=EvidenceIssuer(id="CUSTOMER-1", authority="recipient"),
        issued_at=NOW,
        observed_at=NOW + timedelta(seconds=1),
        expires_at=NOW + timedelta(days=1),
        revocation_epoch=1,
        revoked=False,
        nonce="b" * 32,
        candidate_or_offer_identity=outcome.candidate_sha,
        outcome="recipient response",
        artifacts=[
            EvidenceArtifact(
                name="response",
                digest=DIGEST,
                location_class=ArtifactLocationClass.TRUSTED_EXTERNAL,
            )
        ],
        limitations=[],
        signature=EvidenceSignature(
            algorithm=SignatureAlgorithm.ED25519, key_id="KEY-1", value="signed"
        ),
        synthetic_test_only=False,
        action_response_binding=binding,
    )
    receipt.require_exact_action_response(outcome, now=NOW + timedelta(seconds=2))
    for update in (
        {"action_digest": DIGEST},
        {"recipient": "attacker@example.test"},
        {"candidate_sha": SHA_B},
        {"response_observed_at": NOW - timedelta(seconds=1)},
    ):
        forged = receipt.model_copy(
            update={"action_response_binding": binding.model_copy(update=update)}
        )
        with pytest.raises(ValueError):
            forged.require_exact_action_response(outcome, now=NOW + timedelta(seconds=2))


def test_external_response_has_bounded_consumption_lifetime(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path),
    ).execute(action, now=NOW)
    response = action_response(outcome, action)

    response.require_exact_action_response(outcome, now=NOW + timedelta(minutes=14))
    with pytest.raises(ValueError, match="stale or impossible"):
        response.require_exact_action_response(outcome, now=NOW + timedelta(minutes=30))
    with pytest.raises(ValueError, match="stale or impossible"):
        response.require_exact_action_response(outcome, now=NOW + timedelta(days=365))
    with pytest.raises(ValueError, match="stale, revoked"):
        response.model_copy(update={"revoked": True}).require_current(now=NOW)
    with pytest.raises(ValueError, match="stale, revoked"):
        response.model_copy(update={"expires_at": NOW}).require_current(now=NOW)


def test_response_consumption_is_atomic_recoverable_and_one_use(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    action_journal = journal(tmp_path)
    backend = Backend()
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=backend,
        journal=action_journal,
    )
    outcome = adapter.execute(action, now=NOW)
    recovered_outcome = adapter.execute(action, now=NOW + timedelta(seconds=1))
    assert recovered_outcome == outcome
    assert len(backend.payloads) == 1
    response = action_response(outcome, action)
    binding = response.action_response_binding
    assert binding is not None
    response_digest = "sha256:" + hashlib.sha256(response.canonical_json_bytes()).hexdigest()

    first = action_journal.reserve_response_consumption(
        outcome,
        response_receipt_id=response.receipt_id,
        response_nonce=binding.response_nonce,
        response_digest=response_digest,
    )
    assert first.disposition.value == "RESERVED"

    # A crash before the terminal queue transition reopens the one durable
    # reservation.  It does not send again or create another consumption.
    reopened = ExternalActionJournal(action_journal.root)
    recovery = reopened.reserve_response_consumption(
        recovered_outcome,
        response_receipt_id=response.receipt_id,
        response_nonce=binding.response_nonce,
        response_digest=response_digest,
    )
    assert recovery.disposition.value == "RECOVERABLE"
    reopened.commit_response_consumption(recovered_outcome, recovery)

    with pytest.raises(ExternalActionPolicyError, match="already consumed"):
        reopened.reserve_response_consumption(
            outcome,
            response_receipt_id=response.receipt_id,
            response_nonce=binding.response_nonce,
            response_digest=response_digest,
        )


def test_response_cannot_cross_delivery_generation_or_receipt_nonce(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    action_journal = journal(tmp_path)
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=action_journal,
    ).execute(action, now=NOW)
    response = action_response(outcome, action)
    binding = response.action_response_binding
    delivery = outcome.delivery_receipt
    assert binding is not None and delivery is not None
    digest = "sha256:" + hashlib.sha256(response.canonical_json_bytes()).hexdigest()
    action_journal.reserve_response_consumption(
        outcome,
        response_receipt_id=response.receipt_id,
        response_nonce=binding.response_nonce,
        response_digest=digest,
    )
    second = action_response(
        outcome,
        action,
        receipt_id="XREC-ACTION-RESPONSE-002",
        response_nonce="2" * 32,
    )
    second_binding = second.action_response_binding
    assert second_binding is not None
    with pytest.raises(ExternalActionPolicyError, match="another response"):
        action_journal.reserve_response_consumption(
            outcome,
            response_receipt_id=second.receipt_id,
            response_nonce=second_binding.response_nonce,
            response_digest="sha256:"
            + hashlib.sha256(second.canonical_json_bytes()).hexdigest(),
        )

    replacement_draft = delivery.model_copy(
        update={
            "delivery_generation_id": "3" * 32,
            "delivery_digest": "sha256:" + "0" * 64,
        }
    )
    replacement = ExternalDeliveryReceipt.model_validate(
        replacement_draft.model_copy(
            update={
                "delivery_digest": external_action_digest(
                    replacement_draft, exclude={"delivery_digest"}
                )
            }
        ).model_dump(by_alias=True),
        strict=True,
    )
    repeated_generation = ExternalActionOutcome.model_validate(
        outcome.model_copy(update={"delivery_receipt": replacement}).model_dump(
            by_alias=True
        ),
        strict=True,
    )
    with pytest.raises(ValueError, match="exact delivered action"):
        response.require_exact_action_response(
            repeated_generation, now=NOW + timedelta(seconds=2)
        )


def test_trusted_receipt_loader_rejects_nonexistent_and_late_substitution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tcfactory.v3.external_evidence as evidence_module

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    key = tmp_path / "external.pub"
    key.write_text("fixture key", encoding="utf-8")
    state_path = tmp_path / "authority-state.json"
    state_path.write_text("{}", encoding="utf-8")
    environment = {
        "ROOT": str(trusted),
        "KEY": str(key),
        "A": str(state_path),
        "TCF_EXTERNAL_EVIDENCE_AUTHORITY_STATE": str(state_path),
    }

    def accept_path(_: Path) -> None:
        return None

    def accept_signature(*, receipt: Path, signature: Path, public_key: Path) -> None:
        del receipt, signature, public_key

    monkeypatch.setattr(evidence_module, "_assert_privileged_read_only", accept_path)
    monkeypatch.setattr(
        evidence_module, "_verify_detached_ed25519_signature", accept_signature
    )
    with pytest.raises(ExternalEvidenceVerificationError, match="missing"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            trusted_authority_state_environment_variable="A",
            environment=environment,
        )


def test_external_revocation_anchor_rejects_rollback_rotation_mismatch_and_revocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tcfactory.v3.external_evidence as evidence_module

    trusted = tmp_path / "trusted-authority"
    trusted.mkdir()
    key = tmp_path / "authority.pub"
    key.write_text("fixture key", encoding="utf-8")
    state_path = tmp_path / "authority-state.json"
    state_path.write_text("{}", encoding="utf-8")
    environment = {
        "ROOT": str(trusted),
        "KEY": str(key),
        "A": str(state_path),
        "TCF_EXTERNAL_EVIDENCE_AUTHORITY_STATE": str(state_path),
    }

    def accept_path(_: Path) -> None:
        return None

    def accept_signature(*, receipt: Path, signature: Path, public_key: Path) -> None:
        del receipt, signature, public_key

    monkeypatch.setattr(evidence_module, "_assert_privileged_read_only", accept_path)
    monkeypatch.setattr(
        evidence_module, "_verify_detached_ed25519_signature", accept_signature
    )

    def matching_ledger(_: Path) -> ExternalEvidenceAuthorityLedger:
        anchor = ExternalEvidenceAuthorityAnchor.model_validate_json(
            (trusted / "authority-anchor.json").read_bytes(), strict=True
        )
        raw_revocations = (trusted / "revocation-list.json").read_bytes()
        return ExternalEvidenceAuthorityLedger.model_construct(
            ledger_version=1,
            entries=[
                ExternalEvidenceAuthorityState(
                    authority_id=anchor.authority_id,
                    epoch=anchor.epoch,
                    anchor_digest="sha256:"
                    + hashlib.sha256(anchor.canonical_json_bytes()).hexdigest(),
                    revocation_list_digest="sha256:"
                    + hashlib.sha256(raw_revocations).hexdigest(),
                    key_fingerprint=key_fingerprint(key.read_bytes()),
                    previous_state_digest=(None if anchor.epoch == 1 else DIGEST),
                    advanced_at=NOW,
                )
            ]
        )

    monkeypatch.setattr(
        evidence_module, "load_external_evidence_authority_state", matching_ledger
    )
    _, installed, action = bound_action()
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path, "revocation-journal"),
    ).execute(action, now=NOW)
    initial_receipt = action_response(outcome, action)

    def publish_authority(
        receipt: ExternalEvidenceReceipt,
        revocations: ExternalEvidenceRevocationList,
    ) -> None:
        (trusted / "V3-MKT-001.json").write_bytes(receipt.canonical_json_bytes())
        (trusted / "V3-MKT-001.json.sig").write_bytes(b"signature")
        raw_revocations = revocations.canonical_json_bytes()
        (trusted / "revocation-list.json").write_bytes(raw_revocations)
        (trusted / "revocation-list.json.sig").write_bytes(b"signature")
        anchor = ExternalEvidenceAuthorityAnchor(
            authority_id=revocations.authority_id,
            issuer_id=revocations.issuer_id,
            key_id=revocations.key_id,
            epoch=revocations.epoch,
            current_revocation_digest=(
                "sha256:" + hashlib.sha256(raw_revocations).hexdigest()
            ),
            previous_revocation_digest=revocations.previous_list_digest,
            issued_at=revocations.issued_at,
            expires_at=revocations.expires_at,
        )
        (trusted / "authority-anchor.json").write_bytes(anchor.canonical_json_bytes())
        (trusted / "authority-anchor.json.sig").write_bytes(b"signature")

    epoch_one = ExternalEvidenceRevocationList(
        authority_id="AUTHORITY:EXTERNAL:001",
        issuer_id="CUSTOMER-1",
        key_id="KEY-1",
        epoch=1,
        previous_list_digest=None,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=1),
        revoked_receipt_ids=[],
        revoked_nonces=[],
    )
    (trusted / "V3-MKT-001.json").write_bytes(initial_receipt.canonical_json_bytes())
    (trusted / "V3-MKT-001.json.sig").write_bytes(b"signature")
    with pytest.raises(ExternalEvidenceVerificationError, match="revocation-list.json"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )


    publish_authority(initial_receipt, epoch_one)
    loaded = load_verified_external_evidence_payload(
        repo_root=tmp_path / "repo",
        subject_id="V3-MKT-001",
        trusted_root_environment_variable="ROOT",
        trusted_public_key_environment_variable="KEY",
        environment=environment,
        now=NOW + timedelta(seconds=2),
    )
    assert loaded.record.receipt.receipt_id == initial_receipt.receipt_id

    revoked = epoch_one.model_copy(
        update={"revoked_receipt_ids": [initial_receipt.receipt_id]}
    )
    publish_authority(initial_receipt, revoked)
    with pytest.raises(ExternalEvidenceVerificationError, match="receipt is revoked"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    rolled_forward_receipt = initial_receipt.model_copy(update={"revocation_epoch": 2})
    publish_authority(rolled_forward_receipt, epoch_one)
    with pytest.raises(ExternalEvidenceVerificationError, match="epoch"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    publish_authority(
        initial_receipt,
        epoch_one.model_copy(update={"key_id": "WRONG-KEY"}),
    )
    with pytest.raises(ExternalEvidenceVerificationError, match="key"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    previous_digest = "sha256:" + hashlib.sha256(
        epoch_one.canonical_json_bytes()
    ).hexdigest()
    rotated_receipt = rolled_forward_receipt.model_copy(
        update={
            "signature": rolled_forward_receipt.signature.model_copy(
                update={"key_id": "KEY-2"}
            )
        }
    )
    epoch_two = epoch_one.model_copy(
        update={
            "key_id": "KEY-2",
            "epoch": 2,
            "previous_list_digest": previous_digest,
        }
    )
    publish_authority(rotated_receipt, epoch_two)
    assert (
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        ).record.receipt.signature.key_id
        == "KEY-2"
    )
    publish_authority(rotated_receipt, epoch_two.model_copy(update={"issuer_id": "OTHER"}))
    with pytest.raises(ExternalEvidenceVerificationError, match="issuer"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    stale = epoch_two.model_copy(update={"expires_at": NOW + timedelta(seconds=1)})
    publish_authority(rotated_receipt, stale)
    with pytest.raises(ExternalEvidenceVerificationError, match="stale"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    _, installed, action = bound_action()
    outcome = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path, "late-swap-journal"),
    ).execute(action, now=NOW)
    receipt_path = trusted / "V3-MKT-001.json"
    receipt_path.write_bytes(action_response(outcome, action).canonical_json_bytes())
    receipt_path.with_suffix(".json.sig").write_bytes(b"fixture signature")
    revocations = ExternalEvidenceRevocationList(
        authority_id="AUTHORITY:EXTERNAL:001",
        issuer_id="CUSTOMER-1",
        key_id="KEY-1",
        epoch=1,
        previous_list_digest=None,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=1),
        revoked_receipt_ids=[],
        revoked_nonces=[],
    )
    revocation_path = trusted / "revocation-list.json"
    revocation_path.write_bytes(revocations.canonical_json_bytes())
    revocation_path.with_suffix(".json.sig").write_bytes(b"fixture signature")
    revocation_digest = "sha256:" + hashlib.sha256(
        revocations.canonical_json_bytes()
    ).hexdigest()
    anchor = ExternalEvidenceAuthorityAnchor(
        authority_id=revocations.authority_id,
        issuer_id=revocations.issuer_id,
        key_id=revocations.key_id,
        epoch=revocations.epoch,
        current_revocation_digest=revocation_digest,
        previous_revocation_digest=None,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=1),
    )
    anchor_path = trusted / "authority-anchor.json"
    anchor_path.write_bytes(anchor.canonical_json_bytes())
    anchor_path.with_suffix(".json.sig").write_bytes(b"fixture signature")
    state_path.unlink(missing_ok=True)
    broker = ExternalEvidenceAuthorityBroker(
        state_path, expected_owner_uid=state_path.parent.stat().st_uid
    )
    genesis_state = ExternalEvidenceAuthorityState(
        authority_id=anchor.authority_id,
        epoch=anchor.epoch,
        anchor_digest="sha256:"
        + hashlib.sha256(anchor.canonical_json_bytes()).hexdigest(),
        revocation_list_digest=revocation_digest,
        key_fingerprint=key_fingerprint(key.read_bytes()),
        previous_state_digest=None,
        advanced_at=NOW,
    )
    broker.provision_genesis(genesis_state)
    def load_test_state(path: Path) -> ExternalEvidenceAuthorityLedger:
        return load_external_evidence_authority_state(
            path, expected_owner_uid=path.stat().st_uid
        )

    monkeypatch.setattr(
        evidence_module,
        "load_external_evidence_authority_state",
        load_test_state,
    )
    epoch_two_for_rollback = revocations.model_copy(
        update={
            "epoch": 2,
            "previous_list_digest": revocation_digest,
            "issued_at": NOW,
        }
    )
    epoch_two_raw = epoch_two_for_rollback.canonical_json_bytes()
    epoch_two_digest = "sha256:" + hashlib.sha256(epoch_two_raw).hexdigest()
    epoch_two_anchor = anchor.model_copy(
        update={
            "epoch": 2,
            "current_revocation_digest": epoch_two_digest,
            "previous_revocation_digest": revocation_digest,
            "issued_at": NOW,
        }
    )
    revocation_path.write_bytes(epoch_two_raw)
    anchor_path.write_bytes(epoch_two_anchor.canonical_json_bytes())
    broker.rotate(
        ExternalEvidenceAuthorityState(
            authority_id=anchor.authority_id,
            epoch=2,
            anchor_digest="sha256:"
            + hashlib.sha256(epoch_two_anchor.canonical_json_bytes()).hexdigest(),
            revocation_list_digest=epoch_two_digest,
            key_fingerprint=key_fingerprint(key.read_bytes()),
            previous_state_digest="sha256:"
            + hashlib.sha256(genesis_state.canonical_json_bytes()).hexdigest(),
            advanced_at=NOW + timedelta(seconds=1),
        )
    )
    assert (
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            trusted_authority_state_environment_variable="A",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        ).record.receipt.receipt_id
        == "XREC-ACTION-RESPONSE-001"
    )
    revocation_path.write_bytes(revocations.canonical_json_bytes())
    anchor_path.write_bytes(anchor.canonical_json_bytes())
    with pytest.raises(ExternalEvidenceVerificationError, match="monotonic state"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            trusted_authority_state_environment_variable="A",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )

    def substitute_after_verification(**_: object) -> None:
        receipt_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        evidence_module,
        "_verify_detached_ed25519_signature",
        substitute_after_verification,
    )
    with pytest.raises(ExternalEvidenceVerificationError, match="changed after signature"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            trusted_authority_state_environment_variable="A",
            environment=environment,
        )
    monkeypatch.setattr(
        evidence_module, "_verify_detached_ed25519_signature", accept_signature
    )
    publish_authority(initial_receipt, epoch_one)
    alternate = tmp_path / "substituted-revocation-list.json"
    alternate.write_bytes(epoch_one.canonical_json_bytes())
    revocation_path.unlink()
    revocation_path.symlink_to(alternate)
    with pytest.raises(ExternalEvidenceVerificationError, match="escapes its trusted root"):
        load_verified_external_evidence_payload(
            repo_root=tmp_path / "repo",
            subject_id="V3-MKT-001",
            trusted_root_environment_variable="ROOT",
            trusted_public_key_environment_variable="KEY",
            trusted_authority_state_environment_variable="A",
            environment=environment,
            now=NOW + timedelta(seconds=2),
        )


def test_monotonic_authority_broker_rejects_rollback_replay_and_key_rollback(
    tmp_path: Path,
) -> None:
    state_path = (tmp_path / "protected" / "authority-ledger.json").resolve()
    owner = tmp_path.stat().st_uid
    broker = ExternalEvidenceAuthorityBroker(state_path, expected_owner_uid=owner)
    genesis = ExternalEvidenceAuthorityState(
        authority_id="AUTHORITY:EXTERNAL:001",
        epoch=1,
        anchor_digest="sha256:" + "1" * 64,
        revocation_list_digest="sha256:" + "2" * 64,
        key_fingerprint="sha256:" + "3" * 64,
        previous_state_digest=None,
        advanced_at=NOW,
    )
    broker.provision_genesis(genesis)
    broker.provision_genesis(genesis)
    previous = "sha256:" + hashlib.sha256(genesis.canonical_json_bytes()).hexdigest()
    second = ExternalEvidenceAuthorityState(
        authority_id=genesis.authority_id,
        epoch=2,
        anchor_digest="sha256:" + "4" * 64,
        revocation_list_digest="sha256:" + "5" * 64,
        key_fingerprint="sha256:" + "6" * 64,
        previous_state_digest=previous,
        advanced_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(RuntimeError, match="simulated broker crash"):
        broker.rotate(second, crash_after_publish=True)
    assert (
        load_external_evidence_authority_state(
            state_path, expected_owner_uid=owner
        ).current
        == second
    )
    broker.rotate(second)
    with pytest.raises(ExternalEvidenceAuthorityStateError, match="exact next"):
        broker.rotate(genesis)
    with pytest.raises(ExternalEvidenceAuthorityStateError, match="exact next"):
        broker.rotate(second.model_copy(update={"anchor_digest": "sha256:" + "7" * 64}))
    previous_second = "sha256:" + hashlib.sha256(
        second.canonical_json_bytes()
    ).hexdigest()
    with pytest.raises(ExternalEvidenceAuthorityStateError, match="exact next"):
        broker.rotate(
            ExternalEvidenceAuthorityState(
                authority_id=genesis.authority_id,
                epoch=3,
                anchor_digest="sha256:" + "8" * 64,
                revocation_list_digest="sha256:" + "9" * 64,
                key_fingerprint=genesis.key_fingerprint,
                previous_state_digest=previous_second,
                advanced_at=NOW + timedelta(seconds=2),
            )
        )


def test_signed_snapshot_broker_derives_state_and_rejects_alternate_genesis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tcfactory.v3.external_evidence as evidence_module

    staged = tmp_path / "staged-authority"
    staged.mkdir()
    public_key = tmp_path / "authority.pub"
    public_key.write_bytes(b"fixture authority key")
    revocations = ExternalEvidenceRevocationList(
        authority_id="AUTHORITY:EXTERNAL:001",
        issuer_id="CUSTOMER-1",
        key_id="KEY-1",
        epoch=1,
        previous_list_digest=None,
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(days=1),
        revoked_receipt_ids=[],
        revoked_nonces=[],
    )

    def publish(snapshot: ExternalEvidenceRevocationList) -> None:
        raw = snapshot.canonical_json_bytes()
        (staged / "revocation-list.json").write_bytes(raw)
        (staged / "revocation-list.json.sig").write_bytes(b"signature")
        anchor = ExternalEvidenceAuthorityAnchor(
            authority_id=snapshot.authority_id,
            issuer_id=snapshot.issuer_id,
            key_id=snapshot.key_id,
            epoch=snapshot.epoch,
            current_revocation_digest="sha256:" + hashlib.sha256(raw).hexdigest(),
            previous_revocation_digest=snapshot.previous_list_digest,
            issued_at=snapshot.issued_at,
            expires_at=snapshot.expires_at,
        )
        (staged / "authority-anchor.json").write_bytes(anchor.canonical_json_bytes())
        (staged / "authority-anchor.json.sig").write_bytes(b"signature")

    def accept_privileged(_: Path) -> None:
        return None

    def read_fixture(
        *, path: Path, signature: Path, public_key: Path
    ) -> bytes:
        del signature, public_key
        return path.read_bytes()

    monkeypatch.setattr(
        evidence_module, "assert_privileged_read_only", accept_privileged
    )
    monkeypatch.setattr(
        evidence_module,
        "load_verified_external_evidence_bytes",
        read_fixture,
    )
    publish(revocations)
    ledger = tmp_path / "protected" / "authority-ledger.json"
    broker = ExternalEvidenceAuthorityBroker(
        ledger, expected_owner_uid=tmp_path.stat().st_uid
    )
    promoted = broker.promote_signed_snapshot(
        staged_root=staged,
        public_key=public_key,
        now=NOW,
    )
    assert promoted.revocation_list_digest == (
        "sha256:" + hashlib.sha256(revocations.canonical_json_bytes()).hexdigest()
    )
    assert promoted.key_fingerprint == key_fingerprint(public_key.read_bytes())
    replayed = broker.promote_signed_snapshot(
        staged_root=staged,
        public_key=public_key,
        now=NOW + timedelta(minutes=5),
    )
    assert replayed.model_copy(update={"advanced_at": promoted.advanced_at}) == promoted

    publish(
        revocations.model_copy(
            update={"revoked_receipt_ids": ["XREC-ALTERNATE-GENESIS"]}
        )
    )
    with pytest.raises(ExternalEvidenceAuthorityStateError, match="genesis"):
        broker.promote_signed_snapshot(
            staged_root=staged,
            public_key=public_key,
            now=NOW,
        )


def test_authority_path_unit_bootstraps_preexisting_signed_genesis() -> None:
    root = Path(__file__).resolve().parents[1]
    path_unit = (
        root / "config/traincapsule-external-evidence-authority.path"
    ).read_text(encoding="utf-8")
    service_unit = (
        root / "config/traincapsule-external-evidence-authority.service"
    ).read_text(encoding="utf-8")
    assert (
        "PathExists=/var/lib/traincapsule-external-evidence/"
        "staged-authority/authority-anchor.json"
    ) in path_unit
    assert "Unit=traincapsule-external-evidence-authority.service" in path_unit
    assert "WantedBy=multi-user.target" in path_unit
    assert "WantedBy=multi-user.target" not in service_unit


def test_recipient_template_variables_and_receipt_binding_are_exact(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path),
    )
    for updates in (
        {"recipient": "other@example.test"},
        {"template_id": "TEMPLATE:EMAIL:OTHER"},
        {"variables": {"name": "Ada"}},
        {"machine_policy_receipt_digest": DIGEST},
    ):
        hostile = action.model_copy(update=updates)
        with pytest.raises(ExternalActionPolicyError):
            adapter.execute(hostile, now=NOW)


def test_invalid_template_credential_and_policy_installation_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ExternalActionTemplate(
            schema_version="3.1",
            template_id="TEMPLATE:EMAIL:001",
            channel=ExternalActionChannel.EMAIL,
            subject_template="Hello {name.__class__}",
            body_template="Body",
            variable_names=["name"],
        )
    invalid_installation = installation().model_dump(by_alias=True)
    invalid_installation["credentialReference"] = "https://secret.test/token"
    with pytest.raises(ValidationError):
        ExternalActionInstallation.model_validate(invalid_installation, strict=True)
    with pytest.raises(ValidationError, match="claims must equal"):
        installation(receipt(allowed_claims=["ENGINEERING_PASS"]))


def test_durable_idempotency_recovers_without_a_second_send(tmp_path: Path) -> None:
    _, installed, action = bound_action()
    backend = Backend()
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=backend,
        journal=journal(tmp_path),
    )
    first = adapter.execute(action, now=NOW)
    repeated = adapter.execute(action, now=NOW)
    assert first == repeated
    assert len(backend.payloads) == 1


def test_unbound_machine_receipt_cannot_authorize_exact_action(tmp_path: Path) -> None:
    unbound = receipt()
    installed = installation(unbound)
    action = request(unbound)
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path),
    )
    with pytest.raises(ExternalActionPolicyError, match="exact external action"):
        adapter.execute(action, now=NOW)


def test_policy_digest_and_verifier_receipt_are_actually_verified(tmp_path: Path) -> None:
    _, installed, action = bound_action()

    class RejectPolicy:
        def verify(self, *, policy_id: str, policy_digest: str) -> bool:
            del policy_id, policy_digest
            return False

    rejected_policy = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=RejectPolicy(),
        backend=Backend(),
        journal=journal(tmp_path, "policy"),
    ).execute(action, now=NOW)
    assert rejected_policy.reason is ExternalActionReason.POLICY_ARTIFACT_UNVERIFIED

    class WrongVerifierDigest(Verifier):
        def verify(self, receipt: MachinePolicyReceiptV31, *, now: datetime) -> str:
            super().verify(receipt, now=now)
            return DIGEST

    rejected_verifier = ExternalActionAdapter(
        installation=installed,
        verifier=WrongVerifierDigest(),
        policy_verifier=PolicyVerifier(),
        backend=Backend(),
        journal=journal(tmp_path, "verifier"),
    ).execute(action, now=NOW)
    assert rejected_verifier.reason is ExternalActionReason.MACHINE_POLICY_UNVERIFIED


def test_ambiguous_backend_failure_stays_pending_and_never_resends(tmp_path: Path) -> None:
    _, installed, action = bound_action()

    class AmbiguousBackend(Backend):
        def send(self, payload: ExternalActionPayload) -> ExternalDeliveryReceipt:
            self.payloads.append(payload)
            raise TimeoutError("delivery result lost after possible send")

    backend = AmbiguousBackend()
    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=backend,
        journal=journal(tmp_path),
    )
    first = adapter.execute(action, now=NOW)
    repeated = adapter.execute(action, now=NOW)
    assert first.reason is ExternalActionReason.IDEMPOTENCY_PENDING
    assert repeated.reason is ExternalActionReason.IDEMPOTENCY_PENDING
    assert len(backend.payloads) == 1


def test_unbound_delivery_digest_is_rejected(tmp_path: Path) -> None:
    _, installed, action = bound_action()

    class ForgingBackend(Backend):
        def send(self, payload: ExternalActionPayload) -> ExternalDeliveryReceipt:
            self.payloads.append(payload)
            return ExternalDeliveryReceipt.model_construct(
                schema_version="3.1",
                backend_id=self.backend_id,
                backend_delivery_id="DELIVERY:FORGED",
                action_digest=payload.action_digest,
                payload_digest=external_action_digest(payload),
                idempotency_key=payload.idempotency_key,
                delivered_at=NOW,
                delivery_digest="sha256:" + "0" * 64,
            )

    adapter = ExternalActionAdapter(
        installation=installed,
        verifier=Verifier(),
        policy_verifier=PolicyVerifier(),
        backend=ForgingBackend(),
        journal=journal(tmp_path),
    )
    with pytest.raises(ExternalActionPolicyError, match="delivery receipt is invalid"):
        adapter.execute(action, now=NOW)
