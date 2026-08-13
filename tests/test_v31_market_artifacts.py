from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from tcfactory.checkpoints import V3Checkpoint
from tcfactory.v3.completion_policy import SemanticEvidence
from tcfactory.v3.controller import V3Controller
from tcfactory.v3.market_artifacts import (
    AccountEvidenceField,
    AccountQualificationScore,
    AccountResearchState,
    DiscoveryInterviewGuide,
    InterviewQuestion,
    MarketArtifactError,
    PilotQualificationRubric,
    ReachableAccount,
    bind_reachable_account_map,
)
from tcfactory.v3.source_acquisition import (
    ControlKind,
    ResearchControl,
    ResearchFinding,
    ResearchReport,
    ResearchVerdict,
    SourceArtifact,
    SourceClass,
    SourceHopReceipt,
    SourceRetrievalReceipt,
    research_artifact_roster_digest,
    research_control_result_digest,
)
from tcfactory.v3.work_items import WorkItemCollection
from tcfactory.yamlutil import load_yaml

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
SHA = "c" * 40
ROOT = Path(__file__).resolve().parents[1]


def source_receipt() -> SourceRetrievalReceipt:
    observed = datetime(2026, 8, 12, tzinfo=UTC)
    draft = SourceRetrievalReceipt.model_construct(
        schema_version="3.1",
        receipt_id="SRCREC-" + "A" * 24,
        source_id="SOURCE-001",
        work_item_id="V3-MKT-001",
        candidate_sha=SHA,
        policy_id="RESEARCH-POLICY-001",
        plan_digest=OTHER,
        method="GET",
        requested_url="https://company.example.test/about",
        requested_url_digest=f"sha256:{hashlib.sha256(b'https://company.example.test/about').hexdigest()}",
        final_url="https://company.example.test/about",
        final_url_digest=f"sha256:{hashlib.sha256(b'https://company.example.test/about').hexdigest()}",
        redirect_chain=[],
        redirect_chain_digests=[],
        hop_receipts=[
            SourceHopReceipt(
                schema_version="3.1",
                url="https://company.example.test/about",
                url_digest=(
                    f"sha256:{hashlib.sha256(b'https://company.example.test/about').hexdigest()}"
                ),
                resolved_public_addresses=["93.184.216.34"],
                peer_address="93.184.216.34",
            )
        ],
        retrieved_at=observed,
        status_code=200,
        response_headers={"content-type": "application/json"},
        content_type="application/json",
        content_length=10,
        source_class=SourceClass.COMPANY_PRIMARY,
        query="bounded public organization fact",
        control_query="known-negative public organization fact",
        content_digest=DIGEST,
        parser_id="JSON.COMPANY",
        parser_version="1.0.0",
        freshness_policy="DAILY",
        fresh_until=observed + timedelta(days=1),
        authority_effect="ADVISORY_ONLY_NEVER_NORMATIVE",
        issuer_id="CONTROLLER:TEST:001",
        issuer_key_id="KEY:TEST:001",
        signature_algorithm="hmac-sha256",
        signature="f" * 64,
    )
    return SourceRetrievalReceipt.model_validate(
        draft.model_dump(by_alias=True),
        strict=True,
    )


def report(*, verdict: ResearchVerdict = ResearchVerdict.CLEAR) -> ResearchReport:
    artifacts = [
        SourceArtifact(
            schema_version="3.1",
            source_id="SOURCE-001",
            source_class=SourceClass.COMPANY_PRIMARY,
            requested_url="https://company.example.test/about",
            final_url="https://company.example.test/about",
            observed_at=datetime(2026, 8, 12, tzinfo=UTC),
            status_code=200,
            content_type="application/json",
            content_length=10,
            content_digest=DIGEST,
            headers_digest=OTHER,
            artifact_path="a" * 64 + ".raw",
            claim_ids=["CLAIM-ACCOUNT-001"],
            retrieval_receipt=source_receipt(),
        )
    ]
    roster_digest = research_artifact_roster_digest(artifacts)
    control_draft = [
        ResearchControl(
            schema_version="3.1",
            kind=kind,
            artifact_digest=roster_digest,
            raw_artifact_roster_digest=roster_digest,
            oracle_executable_digest=OTHER,
            oracle_result_digest="sha256:" + "0" * 64,
            expected_verdict=outcome,
            observed_verdict=outcome,
        )
        for kind, outcome in (
            (ControlKind.POSITIVE, ResearchVerdict.CLEAR),
            (ControlKind.NEGATIVE, ResearchVerdict.CONFLICT),
            (ControlKind.ERROR, ResearchVerdict.UNKNOWN),
        )
    ]
    control_result_digest = research_control_result_digest(control_draft)
    control_evidence = [
        control.model_copy(update={"oracle_result_digest": control_result_digest})
        for control in control_draft
    ]
    return ResearchReport(
        schema_version="3.1",
        report_id="RESEARCH-REPORT-001",
        plan_digest=OTHER,
        work_item_id="V3-MKT-001",
        candidate_sha=SHA,
        overall_verdict=verdict,
        artifacts=artifacts,
        controls=control_evidence,
        findings=[
            ResearchFinding(
                schema_version="3.1",
                claim_id="CLAIM-ACCOUNT-001",
                verdict=verdict,
                statement="The source supports a bounded public organization fact.",
                source_artifact_digests=[] if verdict is ResearchVerdict.UNKNOWN else [DIGEST],
            )
        ],
    )


def clear_field(value: str = "bounded public fact") -> AccountEvidenceField:
    return AccountEvidenceField(
        schema_version="3.1",
        value=value,
        verdict=ResearchVerdict.CLEAR,
        claim_id="CLAIM-ACCOUNT-001",
        source_artifact_digests=[DIGEST],
    )


def unknown_field() -> AccountEvidenceField:
    return AccountEvidenceField(
        schema_version="3.1",
        value=None,
        verdict=ResearchVerdict.UNKNOWN,
        claim_id="CLAIM-ACCOUNT-001",
        source_artifact_digests=[],
    )


def account(index: int, *, unknown_owner: bool = True) -> ReachableAccount:
    score_values = {
        "incident_cost": 0,
        "upcoming_change": 0,
        "evidence_access": 0,
        "experiment_authority": 0,
        "native_gap": 0,
        "privacy_need": 0,
        "repeat_trigger": 0,
        "budget_owner": 0,
        "second_use_path": 0,
        "delivery_fit": 0,
    }
    return ReachableAccount(
        schema_version="3.1",
        account_id=f"ACCOUNT-{index:03d}",
        organization=clear_field(f"Organization {index:03d}"),
        segment=clear_field("public AI infrastructure organization"),
        relationship_path=clear_field("public contact channel"),
        relevant_workload=clear_field("publicly described distributed training"),
        known_incident=unknown_field(),
        planned_change=unknown_field(),
        decision_owner=unknown_field() if unknown_owner else clear_field("public role"),
        technical_champion=unknown_field(),
        budget_owner=unknown_field(),
        native_stack=clear_field("PyTorch"),
        privacy_constraint=unknown_field(),
        qualification_score=AccountQualificationScore(
            schema_version="3.1", **score_values, total=0
        ),
        next_evidence_action="Acquire an attributable signed external receipt.",
        state=AccountResearchState.EXTERNAL_EVIDENCE_REQUIRED,
    )


def test_30_account_map_is_attributable_but_never_external_proof() -> None:
    current = report()
    account_map = bind_reachable_account_map(
        map_id="ACCOUNT-MAP-001",
        report=current,
        accounts=[account(index) for index in range(1, 31)],
    )
    assert len(account_map.accounts) == 30
    assert account_map.external_outcomes_demonstrated is False
    assert all(
        item.state is AccountResearchState.EXTERNAL_EVIDENCE_REQUIRED
        for item in account_map.accounts
    )


def test_controller_counts_only_named_attributable_reachable_accounts(
    tmp_path: Path,
) -> None:
    current = report()
    unknown_accounts: list[ReachableAccount] = []
    for index in range(1, 31):
        empty = unknown_field()
        unknown_accounts.append(
            account(index).model_copy(
                update={
                    name: empty
                    for name in (
                        "organization",
                        "segment",
                        "relationship_path",
                        "relevant_workload",
                        "known_incident",
                        "planned_change",
                        "decision_owner",
                        "technical_champion",
                        "budget_owner",
                        "native_stack",
                        "privacy_constraint",
                    )
                }
            )
        )
    unknown_map = bind_reachable_account_map(
        map_id="ACCOUNT-MAP-UNKNOWN",
        report=current,
        accounts=unknown_accounts,
    )
    path = tmp_path / "reachable-account-map.json"
    path.write_bytes(unknown_map.canonical_json_bytes())
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    key = "controller:research-typed-reachable-account-map"
    checkpoint = cast(
        V3Checkpoint,
        SimpleNamespace(
            stage_artifact_paths={key: str(path)},
            stage_artifact_digests={key: digest},
        ),
    )
    controller = cast(Any, object.__new__(V3Controller))
    controller.artifact_root = tmp_path
    item = next(
        item
        for item in WorkItemCollection.model_validate(
            load_yaml(ROOT / "factory/roadmap/work_items.yaml")
        ).work_items
        if item.work_item_id == "V3-MKT-001"
    )
    semantics, _ = controller._controller_semantic_evidence(
        item=item,
        checkpoint=checkpoint,
        base_sha=SHA,
        candidate_sha="d" * 40,
    )
    assert semantics[SemanticEvidence.REACHABLE_ACCOUNT] == []
    assert semantics[SemanticEvidence.ATTRIBUTABLE_SOURCE] == []

    named_map = bind_reachable_account_map(
        map_id="ACCOUNT-MAP-NAMED",
        report=current,
        accounts=[account(index) for index in range(1, 31)],
    )
    path.write_bytes(named_map.canonical_json_bytes())
    checkpoint.stage_artifact_digests[key] = (
        "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    )
    semantics, _ = controller._controller_semantic_evidence(
        item=item,
        checkpoint=checkpoint,
        base_sha=SHA,
        candidate_sha="d" * 40,
    )
    assert len(semantics[SemanticEvidence.REACHABLE_ACCOUNT]) == 30
    assert semantics[SemanticEvidence.ATTRIBUTABLE_SOURCE] == [DIGEST]


def test_map_rejects_missing_count_duplicate_ids_and_out_of_report_evidence() -> None:
    current = report()
    with pytest.raises(ValidationError, match="at least 30"):
        bind_reachable_account_map(
            map_id="ACCOUNT-MAP-001",
            report=current,
            accounts=[account(index) for index in range(1, 30)],
        )
    duplicated = [account(index) for index in range(1, 31)]
    duplicated[-1] = duplicated[-1].model_copy(update={"account_id": "ACCOUNT-001"})
    with pytest.raises(ValidationError, match="30 unique"):
        bind_reachable_account_map(map_id="ACCOUNT-MAP-001", report=current, accounts=duplicated)
    forged = [account(index) for index in range(1, 31)]
    forged[0] = forged[0].model_copy(
        update={
            "organization": clear_field().model_copy(update={"source_artifact_digests": [OTHER]})
        }
    )
    with pytest.raises(MarketArtifactError, match="outside the report"):
        bind_reachable_account_map(map_id="ACCOUNT-MAP-001", report=current, accounts=forged)


def test_conflicting_research_cannot_be_laundered_into_account_map() -> None:
    with pytest.raises(MarketArtifactError, match="conflicting research"):
        bind_reachable_account_map(
            map_id="ACCOUNT-MAP-001",
            report=report(verdict=ResearchVerdict.CONFLICT),
            accounts=[account(index) for index in range(1, 31)],
        )


def test_interview_guide_requires_non_synthetic_external_answers() -> None:
    questions = [
        InterviewQuestion(
            schema_version="3.1",
            question_id=f"Q-{index:03d}",
            prompt=f"Describe attributable evidence for decision dimension {index}.",
            evidence_target="A source, date, owner, and operational decision.",
            disallowed_inference="Do not infer payment, adoption, incident cost, or authority.",
        )
        for index in range(1, 9)
    ]
    guide = DiscoveryInterviewGuide(
        schema_version="3.1",
        guide_id="INTERVIEW-GUIDE-001",
        source_generation_digest=DIGEST,
        questions=questions,
        required_external_receipt=True,
        allows_synthetic_answers=False,
    )
    assert len(guide.questions) == 8
    with pytest.raises(ValidationError, match="external and non-synthetic"):
        DiscoveryInterviewGuide.model_validate(
            {**guide.model_dump(), "allows_synthetic_answers": True}, strict=True
        )


def test_pilot_rubric_cannot_treat_research_map_as_pilot_proof() -> None:
    dimensions = [
        "incident_cost",
        "upcoming_change",
        "evidence_access",
        "experiment_authority",
        "native_gap",
        "privacy_need",
        "repeat_trigger",
        "budget_owner",
        "second_use_path",
        "delivery_fit",
    ]
    rubric = PilotQualificationRubric(
        schema_version="3.1",
        rubric_id="PILOT-RUBRIC-001",
        source_generation_digest=DIGEST,
        minimum_score=20,
        required_dimensions=dimensions,
        requires_real_trace_authorization=True,
        requires_signed_external_receipt=True,
        permits_research_map_as_pilot_proof=False,
    )
    assert rubric.minimum_score == 20
    with pytest.raises(ValidationError, match="cannot be inferred"):
        PilotQualificationRubric.model_validate(
            {**rubric.model_dump(), "permits_research_map_as_pilot_proof": True},
            strict=True,
        )
