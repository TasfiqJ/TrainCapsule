from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast

import pytest

from tcfactory.checkpoints import V3Checkpoint
from tcfactory.v3.completion_artifacts import (
    DeliveryEconomicsEvidence,
    FrozenReleaseEvidenceAuthorization,
    ReductionBoundaryEvidence,
    SupportPolicyEvidence,
    ThirdSameFamilyCaseEvidence,
)
from tcfactory.v3.completion_policy import (
    CompletionEvidenceObservation,
    CorrelatedEvidenceFact,
    EvidenceAuthority,
    EvidenceGrade,
    SemanticEvidence,
    evaluate_milestone_exit_criteria,
    evaluate_work_item_evidence_contract,
    load_completion_evidence_policy,
)
from tcfactory.v3.completion_verification import (
    CompletionVerificationError,
    DeliveryMeasurement,
    DescriptorBoundArtifactReader,
    ExecutableReductionOracle,
    ReductionCandidateInput,
    verify_delivery_economics,
)
from tcfactory.v3.controller import V3Controller
from tcfactory.v3.enums import CommercialMaturity, EvidenceType
from tcfactory.v3.external_evidence import (
    CustomerDecisionValueAttestation,
    ExternalEvidenceReceipt,
)
from tcfactory.v3.maturity import (
    CommercialMaturityAuthorization,
    commercial_maturity_supported,
)
from tcfactory.v3.traincheck_differential import (
    IncidentContract,
    TrainCheckDifferentialRequest,
    evaluate_traincheck_differential,
)
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class _Reader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values

    def read_exact(self, digest: str) -> bytes:
        return self.values[digest]


class _Oracle:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject

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
        del (
            work_item_id,
            candidate_sha,
            candidate_tree_sha,
            request_digest,
            oracle_id,
            bound_artifact_digests,
        )
        if self.reject:
            raise ValueError("receipt rejected")
        return oracle_result_digest


def test_generated_policy_covers_exact_roadmap_and_machine_authority() -> None:
    policy = load_completion_evidence_policy(ROOT)
    roadmap = load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    assert len(policy.work_items) == len(roadmap["workItems"]) == 109
    assert {value.work_item_id for value in policy.work_items} == {
        value["workItemId"] for value in roadmap["workItems"]
    }
    trust = policy.work_item("V3-TRUST-015")
    assert EvidenceAuthority.INDEPENDENT_MACHINE_POLICY in trust.required_authorities
    assert SemanticEvidence.MACHINE_POLICY_DECISION in trust.required_semantics
    for item in roadmap["workItems"]:
        evidence_text = " ".join(item["evidenceRequired"]).lower()
        if "receipt" in evidence_text and not any(
            marker in evidence_text
            for marker in ("machine", "activation", "freshness", "scoped signed")
        ):
            assert policy.work_item(item["workItemId"]).allowed_external_evidence_types


def test_all_109_contracts_are_satisfiable_only_with_their_exact_authority() -> None:
    policy = load_completion_evidence_policy(ROOT)
    roadmap = load_yaml(ROOT / "factory/roadmap/work_items.yaml")
    by_id = {item["workItemId"]: item for item in roadmap["workItems"]}
    for contract in policy.work_items:
        observation = CompletionEvidenceObservation(
            grade=contract.minimum_grade,
            authorities=contract.required_authorities,
            semantic_counts={
                semantic: max(1, contract.minimum_semantic_counts.get(semantic, 0))
                for semantic in contract.required_semantics
            },
            external_type_counts={
                evidence_type: contract.minimum_external_artifacts
                for evidence_type in contract.allowed_external_evidence_types
            },
            prior_evidence=contract.required_prior_evidence,
        )
        assert evaluate_work_item_evidence_contract(contract, observation) == []
        if (
            by_id[contract.work_item_id]["maturityTarget"]["commercial"]
            == "NATIVE_ADVANTAGE_DEMONSTRATED"
        ):
            assert by_id[contract.work_item_id]["kind"] == "CONTROLLED_EXPERIMENT"
            assert SemanticEvidence.NATIVE_VALUE_AUTHORIZATION in contract.required_semantics


def test_external_value_items_consume_exact_prior_authority_without_self_issuing() -> None:
    policy = load_completion_evidence_policy(ROOT)
    for work_item_id in ("V3-PILOT-011", "V3-REPEAT-005"):
        contract = policy.work_item(work_item_id)
        assert EvidenceAuthority.INDEPENDENT_MACHINE_POLICY not in contract.required_authorities
        assert SemanticEvidence.NATIVE_VALUE_AUTHORIZATION not in contract.required_semantics
        observation = CompletionEvidenceObservation(
            grade=contract.minimum_grade,
            authorities=contract.required_authorities,
            semantic_counts={
                semantic: max(1, contract.minimum_semantic_counts.get(semantic, 0))
                for semantic in contract.required_semantics
            },
            external_type_counts={
                evidence_type: contract.minimum_external_artifacts
                for evidence_type in contract.allowed_external_evidence_types
            },
        )
        assert any(
            "prior authority" in failure
            for failure in evaluate_work_item_evidence_contract(contract, observation)
        )
        assert (
            evaluate_work_item_evidence_contract(
                contract,
                observation.model_copy(update={"prior_evidence": contract.required_prior_evidence}),
            )
            == []
        )


def test_every_source_exit_criterion_has_an_exact_typed_evidence_closure() -> None:
    policy = load_completion_evidence_policy(ROOT)
    roadmap = load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    for source in roadmap["milestones"]:
        contract = policy.milestone(source["milestoneId"])
        assert len(contract.exit_criteria) == len(source["exitCriteria"])
        if len(contract.exit_criteria) > 1:
            assert (
                len(
                    {
                        (
                            tuple(criterion.required_work_item_ids),
                            tuple(criterion.required_external_evidence_types),
                            tuple(criterion.required_semantic_counts.items()),
                            criterion.machine_policy_required,
                        )
                        for criterion in contract.exit_criteria
                    }
                )
                > 1
            )
        completed = {
            item_id
            for criterion in contract.exit_criteria
            for item_id in criterion.required_work_item_ids
        }
        semantic = {value: count for value, count in contract.required_semantic_counts.items()}
        external = {value: 1 for value in contract.required_external_evidence_types}
        correlated: list[CorrelatedEvidenceFact] = []
        for criterion in contract.exit_criteria:
            if not criterion.required_correlation_fields:
                continue
            correlated.extend(
                CorrelatedEvidenceFact(
                    candidate_sha="a" * 40,
                    customer_identity_digest="sha256:" + "1" * 64,
                    family_identity_digest="sha256:" + "2" * 64,
                    offer_identity_digest="sha256:" + "3" * 64,
                    pack_identity_digest="sha256:" + "4" * 64,
                    semantic=semantic,
                )
                for semantic in criterion.required_semantic_counts
            )
            correlated.extend(
                CorrelatedEvidenceFact(
                    candidate_sha="a" * 40,
                    customer_identity_digest="sha256:" + "1" * 64,
                    family_identity_digest="sha256:" + "2" * 64,
                    offer_identity_digest="sha256:" + "3" * 64,
                    pack_identity_digest="sha256:" + "4" * 64,
                    external_evidence_type=evidence_type,
                )
                for evidence_type in criterion.required_external_evidence_types
            )
        assert (
            evaluate_milestone_exit_criteria(
                contract,
                completed_work_item_ids=completed,
                semantic_counts=semantic,
                external_type_counts=external,
                machine_policy_available=contract.machine_policy_required,
                correlated_facts=correlated,
            )
            == []
        )
        missing = next(iter(completed))
        failures = evaluate_milestone_exit_criteria(
            contract,
            completed_work_item_ids=completed - {missing},
            semantic_counts=semantic,
            external_type_counts=external,
            machine_policy_available=contract.machine_policy_required,
        )
        assert any(missing in failure for failure in failures)


def test_reduction_and_customer_value_criteria_reject_shared_generic_facts() -> None:
    policy = load_completion_evidence_policy(ROOT)
    reduction = policy.milestone("M2_CONTROLLED_QUALIFICATION")
    reduction_items = {"V3-PROD-014", "V3-TRUST-005", "V3-PROD-016"}
    legal = next(value for value in reduction.exit_criteria if value.criterion_id.endswith("04"))
    illegal = next(value for value in reduction.exit_criteria if value.criterion_id.endswith("05"))
    assert (
        evaluate_milestone_exit_criteria(
            reduction.model_copy(update={"exit_criteria": [legal]}),
            completed_work_item_ids=reduction_items,
            semantic_counts={SemanticEvidence.LEGAL_REDUCTION_VERIFIED: 1},
            external_type_counts={},
            machine_policy_available=False,
        )
        == []
    )
    failures = evaluate_milestone_exit_criteria(
        reduction.model_copy(update={"exit_criteria": [illegal]}),
        completed_work_item_ids=reduction_items,
        semantic_counts={SemanticEvidence.LEGAL_REDUCTION_VERIFIED: 1},
        external_type_counts={},
        machine_policy_available=False,
    )
    assert any("ILLEGAL_REDUCTION_REJECTED" in failure for failure in failures)

    paid = policy.milestone("M4_PAID_PILOT")
    changed = next(value for value in paid.exit_criteria if value.criterion_id.endswith("01"))
    customer_value = next(
        value for value in paid.exit_criteria if value.criterion_id.endswith("03")
    )
    facts = {SemanticEvidence.CUSTOMER_DECISION_CHANGED: 1}
    correlated_changed = [
        CorrelatedEvidenceFact(
            candidate_sha="a" * 40,
            customer_identity_digest="sha256:" + "1" * 64,
            offer_identity_digest="sha256:" + "2" * 64,
            semantic=SemanticEvidence.CUSTOMER_DECISION_CHANGED,
        ),
        CorrelatedEvidenceFact(
            candidate_sha="a" * 40,
            customer_identity_digest="sha256:" + "1" * 64,
            offer_identity_digest="sha256:" + "2" * 64,
            external_evidence_type=EvidenceType.DECISION_CHANGED,
        ),
    ]
    assert (
        evaluate_milestone_exit_criteria(
            paid.model_copy(update={"exit_criteria": [changed]}),
            completed_work_item_ids={"V3-PILOT-011"},
            semantic_counts=facts,
            external_type_counts={EvidenceType.DECISION_CHANGED: 1},
            machine_policy_available=False,
            correlated_facts=correlated_changed,
        )
        == []
    )
    substituted = correlated_changed[1].model_copy(
        update={"customer_identity_digest": "sha256:" + "f" * 64}
    )
    correlation_failures = evaluate_milestone_exit_criteria(
        paid.model_copy(update={"exit_criteria": [changed]}),
        completed_work_item_ids={"V3-PILOT-011"},
        semantic_counts=facts,
        external_type_counts={EvidenceType.DECISION_CHANGED: 1},
        machine_policy_available=False,
        correlated_facts=[correlated_changed[0], substituted],
    )
    assert any("correlated" in failure for failure in correlation_failures)
    failures = evaluate_milestone_exit_criteria(
        paid.model_copy(update={"exit_criteria": [customer_value]}),
        completed_work_item_ids={"V3-PILOT-011"},
        semantic_counts=facts,
        external_type_counts={EvidenceType.DECISION_CHANGED: 1},
        machine_policy_available=False,
    )
    assert any("CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT" in failure for failure in failures)


def test_strict_semantic_artifacts_reject_laundered_claims() -> None:
    digest = "sha256:" + "1" * 64
    base = "a" * 40
    source = "sha256:" + "2" * 64
    SupportPolicyEvidence(
        work_item_id="V3-PROD-029",
        evidence_basis_sha=base,
        source_authority_digest=source,
        pack_id="PACK-1",
        pack_identity_digest=digest,
        supported_versions=["1.0"],
        supported_scope=["initial-pack"],
        upgrade_rules=["requalify"],
        deprecation_rules=["90-day-window"],
        rollback_rules=["restore-prior-pack"],
        explicit_exclusions=["unverified-topologies"],
    )
    with pytest.raises(ValueError, match="measured improvement"):
        DeliveryEconomicsEvidence(
            work_item_id="V3-REPEAT-006",
            evidence_basis_sha=base,
            source_authority_digest=source,
            source_record_digests=[digest, "sha256:" + "3" * 64],
            signed_external_receipt_digest="sha256:" + "4" * 64,
            customer_identity_digest="sha256:" + "5" * 64,
            offer_identity_digest="sha256:" + "6" * 64,
            original_setup_minutes=60,
            proposed_setup_minutes=60,
            original_delivery_minutes=120,
            proposed_delivery_minutes=120,
            original_cost_microusd=10_000,
            proposed_cost_microusd=10_000,
            original_margin_basis_points=100,
            proposed_margin_basis_points=100,
        )
    with pytest.raises(ValueError, match="three unique cases"):
        ThirdSameFamilyCaseEvidence(
            work_item_id="V3-PACK-002",
            evidence_basis_sha=base,
            source_authority_digest=source,
            customer_identity_digest="sha256:" + "9" * 64,
            family_identity_digest=digest,
            case_identity_digests=[digest, digest, digest],
            case_evidence_artifact_digests=[
                "sha256:" + "4" * 64,
                "sha256:" + "5" * 64,
                "sha256:" + "6" * 64,
            ],
            trust_core_before_digest="sha256:" + "7" * 64,
            trust_core_after_digest="sha256:" + "7" * 64,
            reusable_pack_digest="sha256:" + "8" * 64,
        )
    reduction = ReductionBoundaryEvidence(
        work_item_id="V3-TRUST-005",
        evidence_basis_sha=base,
        source_authority_digest=source,
        oracle_executable_digest="sha256:" + "a" * 64,
        oracle_result_digest="sha256:" + "b" * 64,
        raw_artifact_digests=[
            "sha256:" + "c" * 64,
            "sha256:" + "d" * 64,
            "sha256:" + "b" * 64,
        ],
        legal_reduction_artifact_digest="sha256:" + "c" * 64,
        legal_reduction_verdict="VERIFIED",
        illegal_reduction_artifact_digest="sha256:" + "d" * 64,
        illegal_reduction_verdict="REJECTED",
    )
    forged_reduction = reduction.model_dump(mode="json", by_alias=True)
    forged_reduction["illegalReductionVerdict"] = "VERIFIED"
    with pytest.raises(ValueError, match="literal_error"):
        ReductionBoundaryEvidence.model_validate(forged_reduction)


def test_customer_decision_value_attestation_is_distinct_and_artifact_bound() -> None:
    digest = "sha256:" + "1" * 64
    attestation = CustomerDecisionValueAttestation(
        decision_changed_or_materially_strengthened=True,
        value_exceeds_price_and_retained_effort=False,
        observed_price_microusd=10_000_000,
        retained_effort_minutes=30,
        attribution_artifact_digests=[digest],
    )
    assert attestation.decision_changed_or_materially_strengthened
    assert not attestation.value_exceeds_price_and_retained_effort
    now = datetime.now(UTC)
    receipt = ExternalEvidenceReceipt.model_validate(
        {
            "receiptVersion": 1,
            "receiptId": "XREC-DECISION-VALUE",
            "evidenceType": "DECISION_CHANGED",
            "subjectId": "V3-PILOT-011",
            "issuer": {"id": "CUSTOMER", "authority": "EXTERNAL"},
            "issuedAt": now.isoformat(),
            "observedAt": now.isoformat(),
            "expiresAt": (now + timedelta(hours=1)).isoformat(),
            "revocationEpoch": 1,
            "revoked": False,
            "nonce": "a" * 32,
            "candidateOrOfferIdentity": "b" * 40,
            "outcome": "DECISION_STRENGTHENED",
            "artifacts": [
                {
                    "name": "customer-attestation.json",
                    "digest": digest,
                    "locationClass": "TRUSTED_EXTERNAL",
                }
            ],
            "limitations": ["one observed decision"],
            "signature": {"algorithm": "ed25519", "keyId": "KEY-1", "value": "sig"},
            "syntheticTestOnly": False,
            "customerDecisionValue": attestation.model_dump(mode="json", by_alias=True),
        }
    )
    semantic_loader = cast(Any, V3Controller)._external_receipt_semantic_evidence
    assert semantic_loader(receipt) == {SemanticEvidence.CUSTOMER_DECISION_CHANGED: 1}
    generic = receipt.model_copy(update={"customer_decision_value": None})
    assert semantic_loader(generic) == {}


def test_frozen_release_envelope_binds_manifest_receipt_and_raw_roster() -> None:
    digests = {
        name: "sha256:" + str(index) * 64
        for index, name in enumerate(
            (
                "request",
                "tool",
                "incident-contract",
                "baseline-observation",
                "candidate-observation",
                "result",
                "machine-policy-receipt",
            ),
            start=1,
        )
    }
    envelope = FrozenReleaseEvidenceAuthorization(
        authorization_id="FREA-V3-COMP-005-AAAAAAAAAAAA",
        work_item_id="V3-COMP-005",
        candidate_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        candidate_manifest_digest="sha256:" + "8" * 64,
        native_value_authorization_digest="sha256:" + "9" * 64,
        machine_policy_receipt_id="MPREC-1",
        machine_policy_receipt_digest="sha256:" + "a" * 64,
        activation_receipt_digest="sha256:" + "b" * 64,
        traincheck_result_digest=digests["result"],
        traincheck_receipt_file_digest=digests["machine-policy-receipt"],
        frozen_artifact_digests=digests,
        authorized_at=datetime.now(UTC),
    )
    assert envelope.frozen_artifact_digests == digests
    forged = envelope.model_dump(mode="json", by_alias=True)
    forged["frozenArtifactDigests"]["result"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="digest bindings disagree"):
        FrozenReleaseEvidenceAuthorization.model_validate(forged)


def test_controller_reopens_frozen_release_envelope_and_rejects_late_tamper(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "candidate-manifest.json"
    manifest_path.write_bytes(b'{"candidate":"bound"}')
    digests = {
        name: "sha256:" + str(index) * 64
        for index, name in enumerate(
            (
                "request",
                "tool",
                "incident-contract",
                "baseline-observation",
                "candidate-observation",
                "result",
                "machine-policy-receipt",
            ),
            start=1,
        )
    }
    envelope = FrozenReleaseEvidenceAuthorization(
        authorization_id="FREA-V3-COMP-005-AAAAAAAAAAAA",
        work_item_id="V3-COMP-005",
        candidate_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        candidate_manifest_digest=_digest(manifest_path.read_bytes()),
        native_value_authorization_digest="sha256:" + "9" * 64,
        machine_policy_receipt_id="MPREC-1",
        machine_policy_receipt_digest="sha256:" + "a" * 64,
        activation_receipt_digest="sha256:" + "b" * 64,
        traincheck_result_digest=digests["result"],
        traincheck_receipt_file_digest=digests["machine-policy-receipt"],
        frozen_artifact_digests=digests,
        authorized_at=datetime.now(UTC),
    )
    envelope_path = tmp_path / "frozen-release-evidence-authorization.json"
    envelope_path.write_bytes(envelope.canonical_json_bytes())
    stage_digests = {
        "machine_policy:authorization-envelope": "sha256:" + "9" * 64,
        "machine_policy:activation-receipt": "sha256:" + "b" * 64,
        **{
            f"machine_policy:traincheck:{name}": digest
            for name, digest in digests.items()
            if name != "machine-policy-receipt"
        },
        "machine_policy:traincheck-receipt": digests["machine-policy-receipt"],
    }
    checkpoint = cast(
        V3Checkpoint,
        SimpleNamespace(
            work_item_id="V3-COMP-005",
            candidate_sha="a" * 40,
            publication_candidate_tree_sha="b" * 40,
            publication_expected_machine_policy_receipt_id="MPREC-1",
            publication_expected_machine_policy_receipt_digest=("sha256:" + "a" * 64),
            publication_authorization_envelope_path=str(envelope_path),
            publication_authorization_envelope_digest=_digest(envelope_path.read_bytes()),
            stage_artifact_digests=stage_digests,
        ),
    )
    controller = cast(Any, object.__new__(V3Controller))
    controller.artifact_root = tmp_path

    def _accept_bound_traincheck(_checkpoint: V3Checkpoint, _manifest_path: Path) -> None:
        return None

    controller._reverify_traincheck_evidence = _accept_bound_traincheck
    controller._reverify_release_evidence_authorization(checkpoint, manifest_path)

    envelope_path.write_bytes(envelope.canonical_json_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="envelope bytes changed"):
        controller._reverify_release_evidence_authorization(checkpoint, manifest_path)

    forged = envelope.model_copy(update={"native_value_authorization_digest": "sha256:" + "f" * 64})
    envelope_path.write_bytes(forged.canonical_json_bytes())
    checkpoint.publication_authorization_envelope_digest = _digest(envelope_path.read_bytes())
    with pytest.raises(RuntimeError, match="envelope identity mismatch"):
        controller._reverify_release_evidence_authorization(checkpoint, manifest_path)


def test_controller_semantic_fan_in_reopens_strict_output_and_detects_tamper(
    tmp_path: Path,
) -> None:
    source_digest = "sha256:" + "2" * 64
    base_sha = "a" * 40
    record = SupportPolicyEvidence(
        work_item_id="V3-PROD-029",
        evidence_basis_sha=base_sha,
        source_authority_digest=source_digest,
        pack_id="PACK-1",
        pack_identity_digest="sha256:" + "9" * 64,
        supported_versions=["1.0"],
        supported_scope=["initial-pack"],
        upgrade_rules=["requalify"],
        deprecation_rules=["90-day-window"],
        rollback_rules=["restore-prior-pack"],
        explicit_exclusions=["unverified-topologies"],
    )
    path = tmp_path / "support-policy.json"
    path.write_bytes(record.canonical_json_bytes())
    digest = _digest(path.read_bytes())
    key = "implementation-owner:materialized-output:OUT:V3:PROD:029:SUPPORT_POLICY"
    checkpoint = cast(
        V3Checkpoint,
        SimpleNamespace(
            stage_artifact_paths={key: str(path)},
            stage_artifact_digests={key: digest},
        ),
    )
    controller = cast(Any, object.__new__(V3Controller))
    controller.artifact_root = tmp_path
    controller.active_source = SimpleNamespace(canonical_digest=lambda: source_digest)
    item = next(
        item
        for item in WorkItemCollection.model_validate(
            load_yaml(ROOT / "factory/roadmap/work_items.yaml")
        ).work_items
        if item.work_item_id == "V3-PROD-029"
    )
    semantics, bindings = controller._controller_semantic_evidence(
        item=item,
        checkpoint=checkpoint,
        base_sha=base_sha,
        candidate_sha="b" * 40,
    )
    assert semantics == {SemanticEvidence.SUPPORT_POLICY: [digest]}
    assert bindings == {str(path.resolve()): digest}
    path.write_bytes(record.canonical_json_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="bytes changed"):
        controller._controller_semantic_evidence(
            item=item,
            checkpoint=checkpoint,
            base_sha=base_sha,
            candidate_sha="b" * 40,
        )


def test_reduction_semantics_require_fresh_independent_review_bytes(
    tmp_path: Path,
) -> None:
    source_digest = "sha256:" + "2" * 64
    base_sha = "a" * 40
    record = ReductionBoundaryEvidence(
        work_item_id="V3-TRUST-005",
        evidence_basis_sha=base_sha,
        source_authority_digest=source_digest,
        oracle_executable_digest="sha256:" + "3" * 64,
        oracle_result_digest="sha256:" + "4" * 64,
        raw_artifact_digests=[
            "sha256:" + "4" * 64,
            "sha256:" + "5" * 64,
            "sha256:" + "6" * 64,
        ],
        legal_reduction_artifact_digest="sha256:" + "5" * 64,
        legal_reduction_verdict="VERIFIED",
        illegal_reduction_artifact_digest="sha256:" + "6" * 64,
        illegal_reduction_verdict="REJECTED",
    )
    path = tmp_path / "reduction-boundary.json"
    path.write_bytes(record.canonical_json_bytes())
    output_key = "implementation-owner:materialized-output:OUT:V3:TRUST:005:REDUCTION_BOUNDARY"
    review_key = "audit:execution-report"
    checkpoint = cast(
        V3Checkpoint,
        SimpleNamespace(
            stage_artifact_paths={output_key: str(path)},
            stage_artifact_digests={
                output_key: _digest(path.read_bytes()),
                review_key: "sha256:" + "7" * 64,
            },
        ),
    )
    controller = cast(Any, object.__new__(V3Controller))
    controller.artifact_root = tmp_path
    controller.active_source = SimpleNamespace(canonical_digest=lambda: source_digest)
    item = next(
        item
        for item in WorkItemCollection.model_validate(
            load_yaml(ROOT / "factory/roadmap/work_items.yaml")
        ).work_items
        if item.work_item_id == "V3-TRUST-005"
    )
    with pytest.raises(RuntimeError, match="oracle installation is unavailable"):
        controller._controller_semantic_evidence(
            item=item,
            checkpoint=checkpoint,
            base_sha=base_sha,
            candidate_sha="b" * 40,
        )


def test_external_receipt_rejects_duplicate_name_or_digest() -> None:
    now = datetime.now(UTC)
    base = {
        "receiptVersion": 1,
        "receiptId": "XREC-DUPLICATE",
        "evidenceType": "CUSTOMER_CONVERSATION",
        "subjectId": "V3-MKT-003",
        "issuer": {"id": "CUSTOMER", "authority": "EXTERNAL"},
        "issuedAt": now.isoformat(),
        "observedAt": now.isoformat(),
        "expiresAt": (now + timedelta(hours=1)).isoformat(),
        "revocationEpoch": 1,
        "revoked": False,
        "nonce": "a" * 32,
        "candidateOrOfferIdentity": "b" * 40,
        "outcome": "OBSERVED",
        "limitations": ["bounded"],
        "signature": {"algorithm": "ed25519", "keyId": "KEY-1", "value": "sig"},
        "syntheticTestOnly": False,
        "artifacts": [
            {
                "name": "conversation.json",
                "digest": "sha256:" + "1" * 64,
                "locationClass": "TRUSTED_EXTERNAL",
            },
            {
                "name": "conversation.json",
                "digest": "sha256:" + "2" * 64,
                "locationClass": "TRUSTED_EXTERNAL",
            },
        ],
    }
    with pytest.raises(ValueError, match="names must be unique"):
        ExternalEvidenceReceipt.model_validate(base)
    duplicate_digest = {
        **base,
        "artifacts": [
            {
                "name": "conversation.json",
                "digest": "sha256:" + "1" * 64,
                "locationClass": "TRUSTED_EXTERNAL",
            },
            {
                "name": "conversation-2.json",
                "digest": "sha256:" + "1" * 64,
                "locationClass": "TRUSTED_EXTERNAL",
            },
        ],
    }
    with pytest.raises(ValueError, match="digests must be unique"):
        ExternalEvidenceReceipt.model_validate(duplicate_digest)


def test_payment_and_support_acceptance_do_not_launder_value_or_support() -> None:
    assert not commercial_maturity_supported(
        CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED,
        CommercialMaturityAuthorization(external_evidence_types=[EvidenceType.PAID_PILOT]),
    )


def test_delivery_economics_is_derived_from_exact_signed_raw_records(
    tmp_path: Path,
) -> None:
    customer = "sha256:" + "1" * 64
    offer = "sha256:" + "2" * 64
    original = DeliveryMeasurement(
        phase="ORIGINAL",
        customer_identity_digest=customer,
        offer_identity_digest=offer,
        setup_minutes=60,
        delivery_minutes=120,
        cost_microusd=80,
        revenue_microusd=100,
    )
    proposed = DeliveryMeasurement(
        phase="PROPOSED",
        customer_identity_digest=customer,
        offer_identity_digest=offer,
        setup_minutes=10,
        delivery_minutes=20,
        cost_microusd=20,
        revenue_microusd=100,
    )
    bindings: dict[str, Path] = {}
    artifacts: list[dict[str, str]] = []
    for name, record in (("original", original), ("proposed", proposed)):
        raw = record.canonical_json_bytes()
        digest = _digest(raw)
        path = tmp_path / f"{name}.json"
        path.write_bytes(raw)
        bindings[digest] = path
        artifacts.append({"name": name, "digest": digest, "locationClass": "TRUSTED_EXTERNAL"})
    now = datetime.now(UTC)
    receipt = ExternalEvidenceReceipt.model_validate(
        {
            "receiptId": "XREC-DELIVERY-ECONOMICS",
            "evidenceType": "DELIVERY_ECONOMICS",
            "subjectId": "V3-REPEAT-006",
            "issuer": {"id": "billing", "authority": "payment-processor"},
            "issuedAt": now.isoformat(),
            "observedAt": now.isoformat(),
            "expiresAt": (now + timedelta(hours=1)).isoformat(),
            "revocationEpoch": 1,
            "revoked": False,
            "nonce": "a" * 32,
            "candidateOrOfferIdentity": "b" * 40,
            "outcome": "Bound delivery measurements observed.",
            "artifacts": artifacts,
            "limitations": [],
            "signature": {
                "algorithm": "ed25519",
                "keyId": "billing-1",
                "value": "detached",
            },
            "syntheticTestOnly": False,
            "correlationIdentity": {
                "candidateSha": "b" * 40,
                "customerIdentityDigest": customer,
                "offerIdentityDigest": offer,
            },
        }
    )
    valid = DeliveryEconomicsEvidence(
        work_item_id="V3-REPEAT-006",
        evidence_basis_sha="b" * 40,
        source_authority_digest="sha256:" + "3" * 64,
        source_record_digests=list(bindings),
        signed_external_receipt_digest=receipt.canonical_digest(),
        customer_identity_digest=customer,
        offer_identity_digest=offer,
        original_setup_minutes=60,
        proposed_setup_minutes=10,
        original_delivery_minutes=120,
        proposed_delivery_minutes=20,
        original_cost_microusd=80,
        proposed_cost_microusd=20,
        original_margin_basis_points=2_000,
        proposed_margin_basis_points=8_000,
    )
    reader = DescriptorBoundArtifactReader(tmp_path, bindings)
    assert len(verify_delivery_economics(valid, artifacts=reader, receipt=receipt)) == 2
    forged = valid.model_copy(update={"proposed_cost_microusd": 1})
    with pytest.raises(CompletionVerificationError, match="raw records"):
        verify_delivery_economics(forged, artifacts=reader, receipt=receipt)


def test_reduction_oracle_binds_executable_raw_roster_result_and_signature(
    tmp_path: Path,
) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    executable = tmp_path / "reduction-oracle"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import hashlib,json,sys\n"
        "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey\n"
        f"KEY=bytes.fromhex('{private_raw.hex()}')\n"
        "request=json.load(sys.stdin)\n"
        "payload={'schemaVersion':'3.1','workItemId':request['workItemId'],"
        "'candidateSha':request['candidateSha'],'candidateTreeSha':request['candidateTreeSha'],"
        "'rawArtifactRosterDigest':request['rawArtifactRosterDigest'],"
        "'oracleExecutableDigest':request['oracleExecutableDigest'],"
        "'legalReductionArtifactDigest':request['legalReductionArtifactDigest'],"
        "'legalReductionVerdict':'VERIFIED',"
        "'illegalReductionArtifactDigest':request['illegalReductionArtifactDigest'],"
        "'illegalReductionVerdict':'REJECTED'}\n"
        "result='sha256:'+hashlib.sha256((json.dumps(payload,sort_keys=True,separators=(',',':'))+'\\n').encode()).hexdigest()\n"
        "record={**payload,'oracleResultDigest':result,'receiptId':'REDUCE-BOUND-0001',"
        "'issuedAt':'2026-08-12T00:00:00Z','expiresAt':'2027-08-12T00:00:00Z',"
        "'nonce':'a'*32}\n"
        "signed=(json.dumps(record,sort_keys=True,separators=(',',':'))+'\\n').encode()\n"
        "record['signature']=Ed25519PrivateKey.from_private_bytes(KEY).sign(signed).hex()\n"
        "print(json.dumps(record,sort_keys=True,separators=(',',':')))\n",
        encoding="utf-8",
    )
    os.chmod(executable, 0o700)
    public_key = tmp_path / "oracle.pub"
    public_key.write_bytes(public_raw)
    raw_bindings: dict[str, Path] = {}
    reduction_inputs: list[
        tuple[str, Literal["LEGAL_CANDIDATE", "ILLEGAL_CANDIDATE"], list[str]]
    ] = [
        ("legal", "LEGAL_CANDIDATE", []),
        ("illegal", "ILLEGAL_CANDIDATE", ["collective:required"]),
    ]
    for name, kind, omitted in reduction_inputs:
        value = ReductionCandidateInput(
            reduction_class=kind,
            original_rank_ids=[0, 1],
            retained_rank_ids=[0],
            collective_participants={"all-reduce": [0, 1]},
            omitted_required_dependency_ids=omitted,
        )
        raw = value.canonical_json_bytes()
        path = tmp_path / f"{name}.json"
        path.write_bytes(raw)
        raw_bindings[_digest(raw)] = path
    executable_digest = _digest(executable.read_bytes())
    roster = _digest((json.dumps(sorted(raw_bindings), separators=(",", ":")) + "\n").encode())
    payload = {
        "schemaVersion": "3.1",
        "workItemId": "V3-TRUST-005",
        "candidateSha": "b" * 40,
        "candidateTreeSha": "c" * 40,
        "rawArtifactRosterDigest": roster,
        "oracleExecutableDigest": executable_digest,
        "legalReductionArtifactDigest": next(iter(raw_bindings)),
        "legalReductionVerdict": "VERIFIED",
        "illegalReductionArtifactDigest": list(raw_bindings)[1],
        "illegalReductionVerdict": "REJECTED",
    }
    result_digest = _digest(
        (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    evidence = ReductionBoundaryEvidence(
        work_item_id="V3-TRUST-005",
        evidence_basis_sha="b" * 40,
        source_authority_digest="sha256:" + "3" * 64,
        oracle_executable_digest=executable_digest,
        oracle_result_digest=result_digest,
        raw_artifact_digests=list(raw_bindings),
        legal_reduction_artifact_digest=next(iter(raw_bindings)),
        legal_reduction_verdict="VERIFIED",
        illegal_reduction_artifact_digest=list(raw_bindings)[1],
        illegal_reduction_verdict="REJECTED",
    )
    public_key_digest = _digest(public_raw)
    decision, _ = ExecutableReductionOracle(
        executable, executable_digest, public_key, public_key_digest
    ).evaluate(
        evidence,
        candidate_sha="b" * 40,
        candidate_tree_sha="c" * 40,
        artifacts=DescriptorBoundArtifactReader(tmp_path, raw_bindings),
        now=datetime(2026, 8, 12, 1, tzinfo=UTC),
    )
    assert decision.oracle_result_digest == result_digest
    forged = evidence.model_copy(update={"oracle_result_digest": "sha256:" + "1" * 64})
    with pytest.raises(CompletionVerificationError, match="binding mismatch"):
        ExecutableReductionOracle(
            executable, executable_digest, public_key, public_key_digest
        ).evaluate(
            forged,
            candidate_sha="b" * 40,
            candidate_tree_sha="c" * 40,
            artifacts=DescriptorBoundArtifactReader(tmp_path, raw_bindings),
            now=datetime(2026, 8, 12, 1, tzinfo=UTC),
        )
    assert not commercial_maturity_supported(
        CommercialMaturity.COMMERCIALLY_SUPPORTED,
        CommercialMaturityAuthorization(
            external_evidence_types=[
                EvidenceType.SUPPORT_ACCEPTANCE,
                EvidenceType.SAME_FAMILY_CASE,
            ]
        ),
    )
    assert not commercial_maturity_supported(
        CommercialMaturity.COMMERCIALLY_SUPPORTED,
        CommercialMaturityAuthorization(
            external_evidence_types=[
                EvidenceType.SECOND_PAID_ACTION,
                EvidenceType.DECISION_CHANGED,
            ],
            exact_identity_correlation_verified=True,
        ),
    )


def test_unrelated_external_receipt_cannot_satisfy_exact_item_contract() -> None:
    policy = load_completion_evidence_policy(ROOT)
    contract = policy.work_item("V3-MKT-003")
    failures = evaluate_work_item_evidence_contract(
        contract,
        CompletionEvidenceObservation(
            grade=EvidenceGrade.EXTERNAL,
            authorities=[
                EvidenceAuthority.CONTROLLER,
                EvidenceAuthority.TRUSTED_EXTERNAL,
            ],
            semantic_counts={SemanticEvidence.DETERMINISTIC_ARTIFACT: 1},
            external_type_counts={EvidenceType.PAID_PILOT: 15},
        ),
    )
    assert any("15 typed external artifacts" in failure for failure in failures)
    assert any("unrelated external evidence" in failure for failure in failures)


def test_traincheck_replays_raw_incident_differential_without_caller_verdict() -> None:
    contract = IncidentContract(
        contract_id="CONTRACT-1",
        incident_id="INCIDENT-1",
        source_receipt_digest="sha256:" + "1" * 64,
        required_invariant_ids=["INV-1"],
    ).canonical_json_bytes()
    baseline = json.dumps(
        [
            {
                "invariantId": "INV-1",
                "state": "VIOLATED",
                "evidenceDigest": "sha256:" + "2" * 64,
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    candidate = json.dumps(
        [
            {
                "invariantId": "INV-1",
                "state": "HOLDS",
                "evidenceDigest": "sha256:" + "3" * 64,
            }
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    tool = b"content-pinned TrainCheck executable"
    values = {_digest(raw): raw for raw in (contract, baseline, candidate, tool)}
    request = TrainCheckDifferentialRequest(
        work_item_id="V3-COMP-005",
        traincheck_tool_digest=_digest(tool),
        incident_contract_digest=_digest(contract),
        baseline_observation_digest=_digest(baseline),
        candidate_observation_digest=_digest(candidate),
        independent_oracle_id="ORACLE-1",
    )
    result = evaluate_traincheck_differential(
        request,
        candidate_sha="a" * 40,
        candidate_tree_sha="b" * 40,
        artifacts=_Reader(values),
        receipt_verifier=_Oracle(),
    )
    assert result.changed_operational_decision is True
    assert result.baseline_decision == "REJECT_CANDIDATE"
    assert result.candidate_decision == "ACCEPT_CANDIDATE"

    with pytest.raises(ValueError, match="receipt rejected"):
        evaluate_traincheck_differential(
            request,
            candidate_sha="a" * 40,
            candidate_tree_sha="b" * 40,
            artifacts=_Reader(values),
            receipt_verifier=_Oracle(reject=True),
        )
    tampered = dict(values)
    tampered[_digest(candidate)] = candidate.replace(b"HOLDS", b"UNKNOWN")
    with pytest.raises(ValueError, match="digest mismatch"):
        evaluate_traincheck_differential(
            request,
            candidate_sha="a" * 40,
            candidate_tree_sha="b" * 40,
            artifacts=_Reader(tampered),
            receipt_verifier=_Oracle(),
        )

    unknown = candidate.replace(b"HOLDS", b"UNKNOWN")
    unknown_values = dict(values)
    unknown_values[_digest(unknown)] = unknown
    unknown_request = request.model_copy(update={"candidate_observation_digest": _digest(unknown)})
    with pytest.raises(ValueError, match="UNKNOWN"):
        evaluate_traincheck_differential(
            unknown_request,
            candidate_sha="a" * 40,
            candidate_tree_sha="b" * 40,
            artifacts=_Reader(unknown_values),
            receipt_verifier=_Oracle(),
        )

    missing = b"[]"
    missing_values = dict(values)
    missing_values[_digest(missing)] = missing
    missing_request = request.model_copy(update={"candidate_observation_digest": _digest(missing)})
    with pytest.raises(ValueError, match="exactly cover"):
        evaluate_traincheck_differential(
            missing_request,
            candidate_sha="a" * 40,
            candidate_tree_sha="b" * 40,
            artifacts=_Reader(missing_values),
            receipt_verifier=_Oracle(),
        )
