from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tcfactory.v3.enums import Lane, WorkStatus
from tcfactory.v3.recovery import (
    FindingCounter,
    enforce_controller_restart_budget,
    value_redesign_failure,
)
from tcfactory.v3.retry_policy import RetryPolicy
from tcfactory.v3.scheduler import (
    ActiveWork,
    SchedulerConfig,
    SchedulingFacts,
    TrustedSchedulerOverride,
    schedule_cycle,
)
from tcfactory.v3.work_items import WorkItem, WorkItemCollection

NOW = datetime(2026, 8, 11, 22, 0, tzinfo=UTC)


def _item(
    work_item_id: str,
    *,
    lane: str = "PRODUCT",
    kind: str = "CODE",
    status: str = "READY",
    depends_on: list[str] | None = None,
    blocks_commercial_release: bool = False,
    milestone: str = "M1_NATIVE_PREFLIGHT",
    external_evidence_refs: list[str] | None = None,
) -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": work_item_id,
            "title": f"Work {work_item_id}",
            "lane": lane,
            "kind": kind,
            "milestone": milestone,
            "decisionContribution": "One bounded decision contribution.",
            "customerOutcome": "One bounded customer-local outcome.",
            "dependsOn": depends_on or [],
            "softDependsOn": [],
            "blocksCommercialRelease": blocks_commercial_release,
            "priority": 80,
            "riskTier": "TRUST_CORE" if lane == "TRUST" else "STANDARD",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NATIVE_ADVANTAGE_UNPROVEN",
            },
            "disposition": "KEEP",
            "status": status,
            "ownerType": (
                "EXTERNAL_PARTY"
                if kind == "EXTERNAL_EVIDENCE"
                else "MACHINE_POLICY_AUTHORITY"
                if kind == "MACHINE_POLICY_REVIEW"
                else "AI"
            ),
            "automatable": kind not in {"EXTERNAL_EVIDENCE", "MACHINE_POLICY_REVIEW"},
            "packetPath": None,
            "evidenceRequired": ["deterministic test"],
            "externalReceiptRequired": kind == "EXTERNAL_EVIDENCE",
            "machinePolicyReceiptRequired": kind == "MACHINE_POLICY_REVIEW",
            "externalEvidenceRefs": external_evidence_refs or [],
            "retryPolicy": {
                "maxPlanAttempts": (
                    0 if kind in {"EXTERNAL_EVIDENCE", "MACHINE_POLICY_REVIEW"} else 2
                ),
                "maxCandidateRepairCycles": (
                    0 if kind in {"EXTERNAL_EVIDENCE", "MACHINE_POLICY_REVIEW"} else 3
                ),
            },
        }
    )


def _collection(*items: WorkItem) -> WorkItemCollection:
    return WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=list(items),
    )


def _config() -> SchedulerConfig:
    return SchedulerConfig.model_validate(
        {
            "version": 3,
            "activeMilestone": "M1_NATIVE_PREFLIGHT",
            "wip": {
                lane: {"mutating": 1, "readOnly": 1}
                for lane in ("PRODUCT", "MARKET", "COMPETITOR", "TRUST", "FACTORY")
            },
            "factoryMaintenance": {
                "allowMutatingOnlyOnControllerFailure": True,
            },
            "weights": {
                "currentMilestoneCriticalPath": 100,
                "customerDecisionRelevance": 60,
                "externalEvidenceUnblock": 50,
                "nativeEquivalenceRisk": 40,
                "trustReleaseBlocker": 30,
                "reusableSameFamilyValue": 20,
                "shortFeedbackCycle": 10,
                "speculativeSurfaceArea": -30,
                "securityOrIntegrationBurden": -25,
                "likelyNativeDuplication": -20,
                "contextOrQuotaCost": -10,
            },
            "tieBreak": [
                "shortestCriticalPath",
                "evidenceBeforeImplementation",
                "nativeComparisonBeforeDuplication",
                "trustCoreBeforeDependentUi",
                "smallerReversibleItem",
                "workItemId",
            ],
            "waitingStatesDoNotBlockOtherLanes": [
                "WAITING_EXTERNAL",
                "DEFERRED",
                "NATIVE_SUFFICIENT",
                "REJECTED_VALUE",
            ],
        }
    )


def test_machine_policy_review_is_never_schedulable_by_the_ai_controller() -> None:
    review = _item("V3-DEC-001", kind="MACHINE_POLICY_REVIEW")
    decision = schedule_cycle(
        _collection(review),
        _config(),
        cycle_id="machine-policy-negative",
        decided_at=NOW,
    )
    assert decision.selected_work_item_ids == []
    evaluation = decision.evaluations[0]
    assert evaluation.eligible is False
    assert any("independently signed receipt" in reason for reason in evaluation.reasons)


def test_waiting_external_lane_does_not_block_product_or_competitor() -> None:
    market = _item(
        "V3-MKT-001",
        lane="MARKET",
        kind="EXTERNAL_EVIDENCE",
        status="WAITING_EXTERNAL",
    )
    product = _item("V3-PROD-001")
    competitor = _item("V3-COMP-001", lane="COMPETITOR", kind="RESEARCH")
    artifact = schedule_cycle(
        _collection(market, product, competitor),
        _config(),
        cycle_id="cycle-1",
        decided_at=NOW,
    )
    assert set(artifact.selected_work_item_ids) == {
        "V3-PROD-001",
        "V3-COMP-001",
    }
    market_evaluation = next(
        item for item in artifact.evaluations if item.work_item_id == "V3-MKT-001"
    )
    assert market_evaluation.eligible is False
    assert "WAITING_EXTERNAL" in market_evaluation.reasons[0]


def test_scheduler_order_is_deterministic_and_not_input_order() -> None:
    first = _item("V3-PROD-001")
    second = _item("V3-PROD-002")
    common: dict[str, SchedulingFacts] = {
        first.work_item_id: SchedulingFacts(critical_path_length=1),
        second.work_item_id: SchedulingFacts(critical_path_length=1),
    }
    forward = schedule_cycle(
        _collection(first, second),
        _config(),
        cycle_id="forward",
        decided_at=NOW,
        facts_by_id=common,
    )
    reverse = schedule_cycle(
        _collection(second, first),
        _config(),
        cycle_id="reverse",
        decided_at=NOW,
        facts_by_id=common,
    )
    assert forward.selected_work_item_ids == ["V3-PROD-001"]
    assert reverse.selected_work_item_ids == forward.selected_work_item_ids


def test_scheduler_rejects_ready_work_outside_active_milestone() -> None:
    current = _item("V3-PROD-001")
    future = _item("V3-PROD-002", milestone="M2_CONTROLLED_QUALIFICATION")
    artifact = schedule_cycle(
        _collection(current, future),
        _config(),
        cycle_id="active-milestone-only",
        decided_at=NOW,
    )
    assert artifact.selected_work_item_ids == [current.work_item_id]
    future_evaluation = next(
        item for item in artifact.evaluations if item.work_item_id == future.work_item_id
    )
    assert future_evaluation.eligible is False
    assert "is not active" in future_evaluation.reasons[0]


def test_scheduler_never_executes_outside_fact_even_with_a_receipt_reference() -> None:
    outside_fact = _item(
        "V3-MKT-007",
        lane="MARKET",
        kind="EXTERNAL_EVIDENCE",
        status="READY",
        external_evidence_refs=["XREC-MKT-007"],
    )
    artifact = schedule_cycle(
        _collection(outside_fact),
        _config(),
        cycle_id="external-receipt-gate-only",
        decided_at=NOW,
    )
    assert artifact.selected_work_item_ids == []
    assert "outside-fact" in artifact.evaluations[0].reasons[-1]


def test_outside_fact_cannot_claim_ready_or_passed_without_bound_receipt() -> None:
    for status in ("READY", "PASSED_ENGINEERING", "COMPLETED"):
        with pytest.raises(ValueError, match="cannot advance without a bound receipt"):
            _item(
                "V3-MKT-007",
                lane="MARKET",
                kind="EXTERNAL_EVIDENCE",
                status=status,
            )


def test_lane_wip_blocks_only_that_lane() -> None:
    product = _item("V3-PROD-001")
    trust = _item(
        "V3-TRUST-001",
        lane="TRUST",
        kind="SPECIFICATION",
        blocks_commercial_release=True,
    )
    artifact = schedule_cycle(
        _collection(product, trust),
        _config(),
        cycle_id="wip",
        decided_at=NOW,
        active_work=[
            ActiveWork(
                work_item_id="V3-PROD-999",
                lane=Lane.PRODUCT,
                mutating=True,
            )
        ],
        max_concurrent_mutating_sessions=2,
    )
    assert artifact.selected_work_item_ids == ["V3-TRUST-001"]
    product_evaluation = next(
        item for item in artifact.evaluations if item.work_item_id == "V3-PROD-001"
    )
    assert "lane WIP limit reached" in product_evaluation.reasons


def test_native_comparison_precedes_configured_duplicate_work() -> None:
    competitor = _item("V3-COMP-001", lane="COMPETITOR", kind="RESEARCH")
    product = _item("V3-PROD-001")
    artifact = schedule_cycle(
        _collection(product, competitor),
        _config(),
        cycle_id="native-first",
        decided_at=NOW,
        facts_by_id={
            product.work_item_id: SchedulingFacts(
                likely_native_duplication=1,
                requires_native_comparison_work_item=competitor.work_item_id,
            )
        },
    )
    assert artifact.selected_work_item_ids == ["V3-COMP-001"]
    product_evaluation = next(
        item for item in artifact.evaluations if item.work_item_id == product.work_item_id
    )
    assert "native comparison not complete" in product_evaluation.reasons[0]


def _override(work_item_id: str, *, valid: bool) -> TrustedSchedulerOverride:
    payload: dict[str, Any] = {
        "record": {
            "decisionId": "SOVR-MACHINE-POLICY-1",
            "workItemId": work_item_id,
            "reason": "Explicitly prioritize the smaller customer decision blocker.",
            "issuedBy": "MACHINE_POLICY_AUTHORITY",
            "issuedAt": NOW,
            "signature": {
                "algorithm": "external-trusted-root",
                "keyId": "founder-key",
                "value": "signed-value",
            },
        },
        "signatureValid": valid,
        "sourceAgentWritable": False,
    }
    return TrustedSchedulerOverride.model_validate(payload)


def test_machine_policy_override_must_be_trusted_and_is_recorded() -> None:
    first = _item("V3-PROD-001")
    second = _item("V3-PROD-002")
    with pytest.raises(ValueError, match="signature is invalid"):
        schedule_cycle(
            _collection(first, second),
            _config(),
            cycle_id="invalid-override",
            decided_at=NOW,
            override=_override(second.work_item_id, valid=False),
        )
    artifact = schedule_cycle(
        _collection(first, second),
        _config(),
        cycle_id="valid-override",
        decided_at=NOW,
        override=_override(second.work_item_id, valid=True),
    )
    assert artifact.selected_work_item_ids == [second.work_item_id]
    assert artifact.override_decision_id == "SOVR-MACHINE-POLICY-1"


def test_repeated_finding_and_value_redesign_stop_bounded_loops() -> None:
    policy = RetryPolicy(
        max_plan_attempts=2,
        max_candidate_repair_cycles=3,
        max_same_finding_repeats=2,
    )
    counter = FindingCounter()
    first = counter.record("finding-1", policy)
    second = counter.record("finding-1", policy)
    assert first.blocked is False
    assert second.blocked is True
    assert second.status is WorkStatus.BLOCKED_TECHNICAL
    assert second.candidate_preserved is True
    assert second.proposed_dispositions
    assert second.machine_policy_review_proposed is True

    redesign = value_redesign_failure(
        2,
        max_value_redesigns=1,
        native_workflow_sufficient=False,
    )
    assert redesign.status is WorkStatus.REJECTED_VALUE
    assert redesign.append_implementation_tasks is False
    native = value_redesign_failure(
        2,
        max_value_redesigns=1,
        native_workflow_sufficient=True,
    )
    assert native.status is WorkStatus.NATIVE_SUFFICIENT


def test_controller_restart_budget_writes_hard_stuck_and_stop(tmp_path: Path) -> None:
    hard_stuck = tmp_path / "state/HARD_STUCK.json"
    stop = tmp_path / "state/STOP"
    assert (
        enforce_controller_restart_budget(
            incident_id="incident-1",
            restart_count=3,
            max_controller_restarts=3,
            detected_at=NOW,
            hard_stuck_path=hard_stuck,
            stop_path=stop,
        )
        is None
    )
    record = enforce_controller_restart_budget(
        incident_id="incident-1",
        restart_count=4,
        max_controller_restarts=3,
        detected_at=NOW,
        hard_stuck_path=hard_stuck,
        stop_path=stop,
    )
    assert record is not None
    assert record.launcher_must_stop is True
    assert hard_stuck.is_file()
    assert stop.is_file()
    instructions = " ".join(record.recovery_instructions).lower()
    assert "irrecoverable controller incident" in instructions
    assert "do not clear or resume" in instructions
    assert "operator" not in instructions
    assert "acknowledg" not in instructions
