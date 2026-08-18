"""Direct acceptance tests for V3-MIG-005 domain models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tcfactory.v3.dispositions import DispositionLedger, DispositionRecord
from tcfactory.v3.enums import (
    CommercialMaturity,
    Disposition,
    EngineeringMaturity,
    MilestoneStatus,
    MilestoneType,
    OwnerType,
)
from tcfactory.v3.maturity import MaturityState, MaturityTarget
from tcfactory.v3.milestones import Milestone

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 18, 12, tzinfo=UTC)


def _record(
    record_id: str,
    *,
    previous: Disposition,
    decision: Disposition,
    decided_at: datetime,
    work_item_id: str = "V3-MIG-005",
    evidence_refs: list[str] | None = None,
) -> DispositionRecord:
    return DispositionRecord(
        record_id=record_id,
        work_item_id=work_item_id,
        previous=previous,
        decision=decision,
        rationale="Bounded evidence changed the disposition.",
        evidence_refs=[] if evidence_refs is None else evidence_refs,
        decided_by=OwnerType.AI,
        decided_at=decided_at,
    )


def _milestone(criterion: str) -> Milestone:
    return Milestone(
        milestone_id="M0_FACTORY_MIGRATED",
        type=MilestoneType.ENGINEERING,
        status=MilestoneStatus.ACTIVE,
        entry_criteria=[],
        exit_criteria=[criterion],
        required_evidence=["deterministic-test-receipt.json"],
        forbidden_claims=[],
    )


def test_maturity_models_are_directly_validated_and_have_standalone_schemas() -> None:
    target = MaturityTarget(
        engineering=EngineeringMaturity.EXTERNAL_VALIDATED,
        commercial=CommercialMaturity.COMMERCIALLY_SUPPORTED,
    )
    assert target.engineering is EngineeringMaturity.EXTERNAL_VALIDATED

    state = MaturityState(
        engineering=EngineeringMaturity.EXTERNAL_VALIDATED,
        commercial=CommercialMaturity.COMMERCIALLY_SUPPORTED,
        engineering_evidence=["controlled-gate.json"],
        external_evidence_refs=["sha256:" + "a" * 64],
    )
    assert state.commercial is CommercialMaturity.COMMERCIALLY_SUPPORTED
    for name, title in (
        ("maturity-state.schema.json", "MaturityState"),
        ("maturity-target.schema.json", "MaturityTarget"),
    ):
        schema = (ROOT / "schemas/factory/v3" / name).read_text(encoding="utf-8")
        assert f'"title": "{title}"' in schema


@pytest.mark.parametrize(
    "payload, message",
    [
        (
            {"engineering": EngineeringMaturity.IMPLEMENTED_EXPERIMENTAL},
            "elevated engineering maturity",
        ),
        (
            {
                "engineering": EngineeringMaturity.EXTERNAL_VALIDATED,
                "engineering_evidence": ["controlled.json"],
            },
            "external engineering validation",
        ),
        (
            {"commercial": CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED},
            "elevated commercial maturity",
        ),
        (
            {
                "engineering_evidence": ["same.json", "same.json"],
            },
            "must be unique",
        ),
        (
            {"external_evidence_refs": ["  "]},
            "non-empty printable",
        ),
    ],
)
def test_elevated_maturity_fails_closed_without_valid_evidence(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        MaturityState.model_validate(payload)


def test_disposition_ledger_enforces_canonical_history_and_continuity() -> None:
    first = _record(
        "DISP-ONE",
        previous=Disposition.NOT_REVIEWED,
        decision=Disposition.NARROW,
        decided_at=NOW,
    )
    second = _record(
        "DISP-TWO",
        previous=Disposition.NARROW,
        decision=Disposition.KEEP,
        decided_at=NOW + timedelta(minutes=1),
        evidence_refs=["review.json"],
    )
    assert DispositionLedger(records=[first, second]).records[-1].decision is Disposition.KEEP

    with pytest.raises(ValueError, match="chronological canonical order"):
        DispositionLedger(records=[second, first])
    discontinuous = second.model_copy(update={"previous": Disposition.PAUSE})
    with pytest.raises(ValueError, match="does not continue"):
        DispositionLedger(records=[first, discontinuous])


@pytest.mark.parametrize(
    "change, message",
    [
        ({"decided_at": datetime(2026, 8, 18, 12)}, "include a timezone"),
        ({"evidence_refs": ["same", "same"]}, "must be unique"),
        ({"evidence_refs": ["\n"]}, "non-empty printable"),
        ({"decision": Disposition.STOP, "evidence_refs": []}, "require evidence"),
    ],
)
def test_disposition_records_reject_unauditable_evidence_and_time(
    change: dict[str, object], message: str
) -> None:
    payload = _record(
        "DISP-BASE",
        previous=Disposition.NOT_REVIEWED,
        decision=Disposition.KEEP,
        decided_at=NOW,
    ).model_dump(mode="python")
    payload.update(change)
    with pytest.raises(ValueError, match=message):
        DispositionRecord.model_validate(payload)


@pytest.mark.parametrize(
    "criterion",
    [
        "Every product feature is complete.",
        "The whole repository is ready.",
        "Everything is done.",
        "Zero remaining work items are closed.",
        "100 percent of requirements are satisfied.",
        "All product tasks shipped.",
    ],
)
def test_milestone_rejects_unbounded_completion_wording(criterion: str) -> None:
    with pytest.raises(ValueError, match="unbounded global completion"):
        _milestone(criterion)


def test_milestone_accepts_explicitly_bounded_completion_wording() -> None:
    milestone = _milestone("All M0_FACTORY_MIGRATED tasks are complete.")
    assert milestone.exit_criteria
