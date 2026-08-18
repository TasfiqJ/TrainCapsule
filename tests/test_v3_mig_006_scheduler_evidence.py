from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tcfactory.v3.enums import Lane
from tcfactory.v3.scheduler import SchedulerConfig, SchedulingFacts, schedule_cycle
from tcfactory.v3.work_items import WorkItem, WorkItemCollection

TASK_ID = "V3-MIG-006"
SOURCE_COMMIT = "1b154679285c57f1d275035b50e332ab64c206f4"
NOW = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "docs/migrations/evidence/V3-MIG-006-scheduler-simulation.json"


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_bytes(value)).hexdigest()}"


def _config() -> SchedulerConfig:
    return SchedulerConfig.model_validate(
        {
            "version": 3,
            "activeMilestone": "M1_NATIVE_PREFLIGHT",
            "wip": {
                lane: {"mutating": 1, "readOnly": 1}
                for lane in ("PRODUCT", "MARKET", "COMPETITOR", "TRUST", "FACTORY")
            },
            "factoryMaintenance": {"allowMutatingOnlyOnControllerFailure": True},
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


def _item(identifier: str, lane: Lane) -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": identifier,
            "title": f"Scheduler simulation {identifier}",
            "lane": lane.value,
            "kind": "RESEARCH",
            "milestone": "M1_NATIVE_PREFLIGHT",
            "decisionContribution": "Exercise deterministic lane scheduling.",
            "customerOutcome": "Bound starvation without exceeding lane WIP.",
            "dependsOn": [],
            "softDependsOn": [],
            "blocksCommercialRelease": False,
            "priority": 80,
            "riskTier": "STANDARD",
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NATIVE_ADVANTAGE_UNPROVEN",
            },
            "disposition": "KEEP",
            "status": "READY",
            "ownerType": "AI",
            "automatable": True,
            "packetPath": None,
            "evidenceRequired": ["deterministic scheduler simulation"],
            "externalReceiptRequired": False,
            "machinePolicyReceiptRequired": False,
            "externalEvidenceRefs": [],
            "retryPolicy": {"maxPlanAttempts": 2, "maxCandidateRepairCycles": 3},
        }
    )


def _collection(*items: WorkItem) -> WorkItemCollection:
    return WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=list(items),
    )


def _simulation() -> list[dict[str, Any]]:
    items = (
        _item("V3-PROD-901", Lane.PRODUCT),
        _item("V3-MKT-901", Lane.MARKET),
        _item("V3-COMP-901", Lane.COMPETITOR),
        _item("V3-TRUST-901", Lane.TRUST),
    )
    records: list[dict[str, Any]] = []
    for offset, cursor in enumerate((Lane.PRODUCT, Lane.MARKET, Lane.COMPETITOR, Lane.TRUST)):
        artifact = schedule_cycle(
            _collection(*items),
            _config(),
            cycle_id=f"{TASK_ID}-cycle-{offset + 1}",
            decided_at=NOW + timedelta(minutes=offset),
            lane_cursor=cursor,
            max_concurrent_read_only_sessions=1,
            max_concurrent_mutating_sessions=1,
        )
        records.append(
            {
                "cycleId": artifact.cycle_id,
                "laneCursor": cursor.value,
                "selectedWorkItemIds": artifact.selected_work_item_ids,
                "selectedCount": len(artifact.selected_work_item_ids),
                "decisionArtifactDigest": artifact.canonical_digest(),
            }
        )
    return records


def test_exact_weighted_score_components_and_contributions() -> None:
    item = _item("V3-PROD-999", Lane.PRODUCT)
    facts = SchedulingFacts(
        current_milestone_critical_path=0.75,
        customer_decision_relevance=0.5,
        external_evidence_unblock=0.2,
        native_equivalence_risk=0.4,
        trust_release_blocker=1.0,
        reusable_same_family_value=0.3,
        short_feedback_cycle=0.6,
        speculative_surface_area=0.5,
        security_or_integration_burden=0.2,
        likely_native_duplication=0.25,
        context_or_quota_cost=0.8,
    )
    artifact = schedule_cycle(
        _collection(item),
        _config(),
        cycle_id="exact-weighted-score",
        decided_at=NOW,
        facts_by_id={item.work_item_id: facts},
    )
    evaluation = artifact.evaluations[0]
    assert [
        (component.name, component.weight, component.factor, component.contribution)
        for component in evaluation.components
    ] == [
        ("current_milestone_critical_path", 100, 0.75, 75.0),
        ("customer_decision_relevance", 60, 0.5, 30.0),
        ("external_evidence_unblock", 50, 0.2, 10.0),
        ("native_equivalence_risk", 40, 0.4, 16.0),
        ("trust_release_blocker", 30, 1.0, 30.0),
        ("reusable_same_family_value", 20, 0.3, 6.0),
        ("short_feedback_cycle", 10, 0.6, 6.0),
        ("speculative_surface_area", -30, 0.5, -15.0),
        ("security_or_integration_burden", -25, 0.2, -5.0),
        ("likely_native_duplication", -20, 0.25, -5.0),
        ("context_or_quota_cost", -10, 0.8, -8.0),
    ]
    assert evaluation.score == 140.0


def test_unequal_scores_order_work_within_the_same_lane() -> None:
    lower_identifier = _item("V3-PROD-001", Lane.PRODUCT)
    higher_score = _item("V3-PROD-999", Lane.PRODUCT)
    artifact = schedule_cycle(
        _collection(lower_identifier, higher_score),
        _config(),
        cycle_id="same-lane-score-order",
        decided_at=NOW,
        facts_by_id={
            lower_identifier.work_item_id: SchedulingFacts(customer_decision_relevance=0.1),
            higher_score.work_item_id: SchedulingFacts(customer_decision_relevance=1.0),
        },
        max_concurrent_read_only_sessions=1,
    )
    assert artifact.selected_work_item_ids == [higher_score.work_item_id]
    scores = {value.work_item_id: value.score for value in artifact.evaluations}
    assert scores == {"V3-PROD-001": 6.0, "V3-PROD-999": 60.0}


def test_identical_inputs_have_identical_canonical_artifact_and_digest() -> None:
    first = _item("V3-PROD-001", Lane.PRODUCT)
    second = _item("V3-PROD-002", Lane.PRODUCT)
    facts = {
        first.work_item_id: SchedulingFacts(customer_decision_relevance=0.5),
        second.work_item_id: SchedulingFacts(customer_decision_relevance=0.75),
    }
    forward = schedule_cycle(
        _collection(first, second),
        _config(),
        cycle_id="canonical-identical-input",
        decided_at=NOW,
        facts_by_id=facts,
    )
    reverse = schedule_cycle(
        _collection(second, first),
        _config(),
        cycle_id="canonical-identical-input",
        decided_at=NOW,
        facts_by_id=facts,
    )
    assert forward.canonical_json_bytes() == reverse.canonical_json_bytes()
    assert forward.canonical_digest() == reverse.canonical_digest()


def test_persisted_simulation_is_task_config_and_commit_bound(tmp_path: Path) -> None:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert evidence["taskId"] == TASK_ID
    assert evidence["sourceCommit"] == SOURCE_COMMIT
    assert evidence["configDigest"] == _config().canonical_digest()
    assert evidence["authorityClaim"] is False
    assert evidence["simulation"] == _simulation()
    assert [record["selectedCount"] for record in evidence["simulation"]] == [1, 1, 1, 1]
    assert [record["selectedWorkItemIds"][0] for record in evidence["simulation"]] == [
        "V3-PROD-901",
        "V3-MKT-901",
        "V3-COMP-901",
        "V3-TRUST-901",
    ]
    unsigned = {key: value for key, value in evidence.items() if key != "evidenceDigest"}
    assert evidence["evidenceDigest"] == _digest(unsigned)
    persisted = tmp_path / EVIDENCE_PATH.name
    persisted.write_bytes(_canonical_bytes(evidence))
    assert json.loads(persisted.read_bytes()) == evidence
