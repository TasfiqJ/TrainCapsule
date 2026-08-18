from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import tcfactory.v3.milestone_runtime as milestone_runtime
from tcfactory.backends.base import ExecutionEvidenceMode
from tcfactory.completion import (
    CompletionBlocked,
    CompletionProposal,
    evaluate_v3_milestone_completion,
)
from tcfactory.v3.milestone_runtime import (
    WorkItemCompletionEvidence,
    advance_milestone_state,
    initialize_milestone_state,
    write_work_item_completion_evidence,
)
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "a" * 64


def test_milestone_advance_transaction_replays_after_state_write_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    state_path = tmp_path / "milestone-state.json"
    receipt_path = tmp_path / "milestone-decisions/M0_FACTORY_MIGRATED.json"
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    initial = initialize_milestone_state(roadmap, state_path, now=now)
    assert initial.active_milestone == "M0_FACTORY_MIGRATED"
    original_write_json = milestone_runtime.write_json
    failed = False

    def crash_before_state(path: Path, payload: object) -> None:
        nonlocal failed
        transaction = state_path.with_name(f".{state_path.name}.advance-transaction.json")
        if path == state_path and transaction.is_file() and not failed:
            failed = True
            raise OSError("simulated crash before milestone state commit")
        original_write_json(path, payload)

    monkeypatch.setattr(milestone_runtime, "write_json", crash_before_state)
    with pytest.raises(OSError, match="simulated crash"):
        advance_milestone_state(
            roadmap=roadmap,
            state_path=state_path,
            receipt_path=receipt_path,
            evidence_digests={"V3-SIM-001": "sha256:" + "a" * 64},
            expected_evidence_ids={"V3-SIM-001"},
            source_authority_digest="sha256:" + "c" * 64,
            now=now,
        )
    monkeypatch.setattr(milestone_runtime, "write_json", original_write_json)

    recovered = initialize_milestone_state(roadmap, state_path, now=now)
    assert recovered.active_milestone == "M1_NATIVE_PREFLIGHT"
    assert receipt_path.is_file()
    assert not state_path.with_name(
        f".{state_path.name}.advance-transaction.json"
    ).exists()


def test_milestone_cannot_advance_without_digest_bound_evidence(tmp_path: Path) -> None:
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    with pytest.raises(ValueError, match="without work-item evidence"):
        advance_milestone_state(
            roadmap=roadmap,
            state_path=tmp_path / "milestone-state.json",
            receipt_path=tmp_path / "decisions/M0_FACTORY_MIGRATED.json",
            evidence_digests={},
            expected_evidence_ids=set(),
            source_authority_digest=DIGEST,
            now=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="exactly every active work item"):
        advance_milestone_state(
            roadmap=roadmap,
            state_path=tmp_path / "other-milestone-state.json",
            receipt_path=tmp_path / "decisions/other-M0_FACTORY_MIGRATED.json",
            evidence_digests={"V3-SIM-001": DIGEST},
            expected_evidence_ids={"V3-SIM-001", "V3-SIM-002"},
            source_authority_digest=DIGEST,
            now=datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        )


def test_completion_evidence_rejects_self_asserted_review_boolean() -> None:
    with pytest.raises(ValueError, match="independentReviewed"):
        WorkItemCompletionEvidence.model_validate(
            {
                "workItemId": "V3-SIM-001",
                "milestoneId": "M0_FACTORY_MIGRATED",
                "candidateSha": "a" * 40,
                "baseSha": "a" * 40,
                "candidateTreeSha": "b" * 40,
                "sourceAuthorityDigest": DIGEST,
                "evidenceMode": "SIMULATION",
                "checkpointDigest": DIGEST,
                "independentReviewed": True,
                "externalReceiptRefs": [],
                "createdAt": "2026-08-12T12:00:00Z",
            }
        )


def test_completion_proposals_cannot_broaden_policy_or_repeat_expansion() -> None:
    with pytest.raises(ValueError):
        CompletionProposal(
            proposal_id="CPROP-M0-TOO_BROAD",
            milestone_id="M0_FACTORY_MIGRATED",
            summary="Too broad.",
            proposed_work=[f"new-{index}" for index in range(6)],
            candidate_sha="a" * 40,
            evidence_digests=[DIGEST],
            reviewer_artifact_digest=DIGEST,
        )
    proposal = CompletionProposal(
        proposal_id="CPROP-M0-BOUND",
        milestone_id="M0_FACTORY_MIGRATED",
        summary="Bounded proposal.",
        proposed_work=["one bounded follow-up"],
        candidate_sha="a" * 40,
        evidence_digests=[DIGEST],
        reviewer_artifact_digest=DIGEST,
        accepted=True,
        accepted_by_machine_policy_ref="MPR-EXTERNAL-001",
    )
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    milestone = roadmap.milestones[0]
    with pytest.raises(CompletionBlocked, match="expansion round one"):
        evaluate_v3_milestone_completion(
            milestone=milestone,
            work_items=WorkItemCollection(
                active_milestone=milestone.milestone_id,
                work_items=[],
            ),
            deterministic_evidence={},
            independent_review_refs=[],
            machine_policy_receipt_refs=[],
            trusted_external_receipt_refs=[],
            proposals=[proposal],
            expansion_round=0,
        )
    with pytest.raises(CompletionBlocked, match="limited to one round"):
        evaluate_v3_milestone_completion(
            milestone=milestone,
            work_items=WorkItemCollection(
                active_milestone=milestone.milestone_id,
                work_items=[],
            ),
            deterministic_evidence={},
            independent_review_refs=[],
            machine_policy_receipt_refs=[],
            trusted_external_receipt_refs=[],
            proposals=[proposal],
            expansion_round=2,
        )


def test_authorized_completion_expansion_consumes_only_round_and_evaluator_is_read_only(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "factory/feature_ledger.yaml"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("version: 2\nlegacy: immutable\n", encoding="utf-8")
    before = ledger.read_bytes()
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    milestone = roadmap.milestones[0]
    collection = WorkItemCollection(
        active_milestone=milestone.milestone_id,
        work_items=[],
    )
    accepted = CompletionProposal(
        proposal_id="CPROP-M0-AUTHORIZED",
        milestone_id=milestone.milestone_id,
        summary="One bounded, independently authorized expansion.",
        proposed_work=["one bounded follow-up"],
        candidate_sha="a" * 40,
        evidence_digests=[DIGEST],
        reviewer_artifact_digest=DIGEST,
        accepted=True,
        accepted_by_machine_policy_ref="MPR-EXTERNAL-001",
    )

    consumed = evaluate_v3_milestone_completion(
        milestone=milestone,
        work_items=collection,
        deterministic_evidence={},
        independent_review_refs=[],
        machine_policy_receipt_refs=[],
        trusted_external_receipt_refs=[],
        proposals=[accepted],
        expansion_round=1,
    )
    assert consumed.expansion_round == 1
    assert consumed.proposals == [accepted]

    with pytest.raises(CompletionBlocked, match="limited to one round"):
        evaluate_v3_milestone_completion(
            milestone=milestone,
            work_items=collection,
            deterministic_evidence={},
            independent_review_refs=[],
            machine_policy_receipt_refs=[],
            trusted_external_receipt_refs=[],
            proposals=[accepted],
            expansion_round=2,
        )

    unaccepted = accepted.model_copy(
        update={"accepted": False, "accepted_by_machine_policy_ref": None}
    )
    proposed_only = evaluate_v3_milestone_completion(
        milestone=milestone,
        work_items=collection,
        deterministic_evidence={},
        independent_review_refs=[],
        machine_policy_receipt_refs=[],
        trusted_external_receipt_refs=[],
        proposals=[unaccepted],
        expansion_round=0,
    )
    assert proposed_only.proposals == [unaccepted]
    assert ledger.read_bytes() == before


def test_completion_review_rejects_more_than_five_separate_proposals() -> None:
    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    milestone = roadmap.milestones[0]
    proposals = [
        CompletionProposal(
            proposal_id=f"CPROP-M0-BOUND-{index}",
            milestone_id=milestone.milestone_id,
                summary=f"Bounded proposal {index}.",
                proposed_work=[f"follow-up-{index}"],
                candidate_sha="a" * 40,
                evidence_digests=[DIGEST],
                reviewer_artifact_digest=DIGEST,
        )
        for index in range(6)
    ]

    with pytest.raises(CompletionBlocked, match="at most five proposals"):
        evaluate_v3_milestone_completion(
            milestone=milestone,
            work_items=WorkItemCollection(
                active_milestone=milestone.milestone_id,
                work_items=[],
            ),
            deterministic_evidence={},
            independent_review_refs=[],
            machine_policy_receipt_refs=[],
            trusted_external_receipt_refs=[],
            proposals=proposals,
            expansion_round=0,
        )


def test_completion_evidence_and_milestone_receipts_are_immutable(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    evidence = WorkItemCompletionEvidence(
        work_item_id="V3-SIM-001",
        milestone_id="M0_FACTORY_MIGRATED",
        candidate_sha="a" * 40,
        base_sha="a" * 40,
        candidate_tree_sha="c" * 40,
        source_authority_digest=DIGEST,
        evidence_mode=ExecutionEvidenceMode.CONTROLLED_VALIDATION,
        checkpoint_digest=DIGEST,
        candidate_manifest_digest=None,
        independent_review_artifacts={},
        external_receipt_refs=[],
        created_at=now,
    )
    evidence_root = tmp_path / "evidence"
    write_work_item_completion_evidence(evidence_root, evidence)
    changed = evidence.model_copy(update={"candidate_sha": "b" * 40})
    with pytest.raises(ValueError, match="immutable"):
        write_work_item_completion_evidence(evidence_root, changed)

    roadmap = MilestoneRoadmap.model_validate(
        load_yaml(ROOT / "factory/roadmap/milestones.yaml")
    )
    state_path = tmp_path / "milestone-state.json"
    receipt_path = tmp_path / "decisions/M0_FACTORY_MIGRATED.json"
    advance_milestone_state(
        roadmap=roadmap,
        state_path=state_path,
        receipt_path=receipt_path,
        evidence_digests={"V3-SIM-001": DIGEST},
        expected_evidence_ids={"V3-SIM-001"},
        source_authority_digest=DIGEST,
        now=now,
    )
    with pytest.raises(ValueError, match="immutable"):
        advance_milestone_state(
            roadmap=roadmap,
            state_path=state_path,
            receipt_path=receipt_path,
            evidence_digests={"V3-SIM-002": DIGEST},
            expected_evidence_ids={"V3-SIM-002"},
            source_authority_digest=DIGEST,
            now=now,
        )
