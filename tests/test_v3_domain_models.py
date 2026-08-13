from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from scripts.generate_v3_schemas import SCHEMAS, rendered_schemas
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.candidate_manifest import CandidateManifest
from tcfactory.v3.enums import (
    CommercialMaturity,
    Disposition,
    EngineeringMaturity,
    EvidenceType,
    Lane,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.external_evidence import ExternalEvidenceReceipt, TrustedEvidenceRecord
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.retry_policy import RetryPolicy
from tcfactory.v3.work_items import (
    WorkItem,
    WorkItemCollection,
    assert_status_transition,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 11, 21, 0, tzinfo=UTC)


def _work_item(**updates: Any) -> WorkItem:
    payload: dict[str, Any] = {
        "version": 3,
        "workItemId": "V3-PROD-001",
        "title": "Bounded work",
        "lane": "PRODUCT",
        "kind": "CODE",
        "milestone": "M1_NATIVE_PREFLIGHT",
        "decisionContribution": "Establish one bounded decision input.",
        "customerOutcome": "A truthful local result.",
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
        "packetPath": "specs/v3/V3-PROD-001.yaml",
        "evidenceRequired": ["controlled fixture"],
        "externalReceiptRequired": False,
        "retryPolicy": {
            "maxPlanAttempts": 2,
            "maxCandidateRepairCycles": 3,
        },
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    payload.update(updates)
    return WorkItem.model_validate(payload)


def _receipt(
    *,
    receipt_id: str = "XREC-PAID-PILOT-1",
    evidence_type: EvidenceType = EvidenceType.PAID_PILOT,
    synthetic: bool = False,
) -> ExternalEvidenceReceipt:
    return ExternalEvidenceReceipt.model_validate(
        {
            "receiptVersion": 1,
            "receiptId": receipt_id,
            "evidenceType": evidence_type,
            "subjectId": "V3-PROD-001",
            "issuer": {"id": "customer-1", "authority": "budget-owner"},
            "issuedAt": NOW,
            "observedAt": NOW,
            "expiresAt": NOW + timedelta(days=30),
            "revocationEpoch": 1,
            "revoked": False,
            "nonce": "c" * 32,
            "candidateOrOfferIdentity": "sha256:" + "1" * 64,
            "outcome": "The bounded decision changed.",
            "artifacts": [
                {
                    "name": "receipt",
                    "digest": "sha256:" + "2" * 64,
                    "locationClass": "TRUSTED_EXTERNAL",
                }
            ],
            "limitations": ["single account"],
            "signature": {
                "algorithm": "external-trusted-root",
                "keyId": "customer-key-1",
                "value": "signed-value",
            },
            "syntheticTestOnly": synthetic,
        }
    )


def test_exact_v3_controlled_vocabularies() -> None:
    assert [item.value for item in Lane] == [
        "PRODUCT",
        "MARKET",
        "COMPETITOR",
        "TRUST",
        "FACTORY",
    ]
    assert WorkKind.EXTERNAL_EVIDENCE.value == "EXTERNAL_EVIDENCE"
    assert WorkStatus.NATIVE_SUFFICIENT.value == "NATIVE_SUFFICIENT"
    assert Disposition.INTEGRATE_EXISTING_BACKEND.value == "INTEGRATE_EXISTING_BACKEND"
    assert EngineeringMaturity.EXTERNAL_VALIDATED.value == "EXTERNAL_VALIDATED"
    assert CommercialMaturity.COMMERCIALLY_SUPPORTED.value == "COMMERCIALLY_SUPPORTED"


def test_work_item_rejects_unknown_fields_and_unbounded_ownership() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _work_item(unknownField=True)
    with pytest.raises(ValidationError, match="AI cannot own"):
        _work_item(
            kind="EXTERNAL_EVIDENCE",
            ownerType="AI",
            automatable=False,
            externalReceiptRequired=True,
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _work_item(humanApprovalRequired=True)
    with pytest.raises(ValidationError, match="HUMAN_REVIEWER"):
        _work_item(ownerType="HUMAN_REVIEWER")
    with pytest.raises(ValidationError, match="commercial experiment"):
        _work_item(kind="COMMERCIAL_EXPERIMENT")


def test_work_item_rejects_self_overlap_and_invalid_transition() -> None:
    with pytest.raises(ValidationError, match="depend on itself"):
        _work_item(dependsOn=["V3-PROD-001"])
    with pytest.raises(ValidationError, match="overlap"):
        _work_item(dependsOn=["V3-TRUST-001"], softDependsOn=["V3-TRUST-001"])
    assert_status_transition(WorkStatus.READY, WorkStatus.QUEUED)
    with pytest.raises(ValueError, match="invalid work status transition"):
        assert_status_transition(WorkStatus.COMPLETED, WorkStatus.READY)


def test_work_item_collection_rejects_missing_duplicate_and_cycle() -> None:
    first = _work_item()
    with pytest.raises(ValidationError, match="missing dependencies"):
        WorkItemCollection(
            active_milestone="M1_NATIVE_PREFLIGHT",
            work_items=[first.model_copy(update={"depends_on": ["V3-TRUST-001"]})],
        )
    with pytest.raises(ValidationError, match="must be unique"):
        WorkItemCollection(
            active_milestone="M1_NATIVE_PREFLIGHT",
            work_items=[first, first],
        )
    second = _work_item(
        workItemId="V3-TRUST-001",
        lane="TRUST",
        dependsOn=["V3-PROD-001"],
    )
    first_with_cycle = _work_item(dependsOn=["V3-TRUST-001"])
    with pytest.raises(ValidationError, match="dependency cycle"):
        WorkItemCollection(
            active_milestone="M1_NATIVE_PREFLIGHT",
            work_items=[first_with_cycle, second],
        )


def test_commercial_completion_requires_trusted_attributable_evidence() -> None:
    completed = _work_item(
        status="COMPLETED",
        maturityTarget={
            "engineering": "EXTERNAL_VALIDATED",
            "commercial": "EXTERNAL_VALUE_DEMONSTRATED",
        },
        externalReceiptRequired=True,
        externalEvidenceRefs=["XREC-PAID-PILOT-1"],
    )
    collection = WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=[completed],
    )
    with pytest.raises(ValueError, match="exceeds trusted evidence"):
        collection.validate_completion_evidence(
            {
                "XREC-PAID-PILOT-1": TrustedEvidenceRecord(
                    receipt=_receipt(),
                    signature_valid=True,
                    source_agent_writable=False,
                )
            }
        )
    with pytest.raises(ValueError, match="synthetic evidence"):
        collection.validate_completion_evidence(
            {
                "XREC-PAID-PILOT-1": TrustedEvidenceRecord(
                    receipt=_receipt(synthetic=True),
                    signature_valid=True,
                    source_agent_writable=False,
                )
            }
        )
    with pytest.raises(ValueError, match="AI-writable"):
        collection.validate_completion_evidence(
            {
                "XREC-PAID-PILOT-1": TrustedEvidenceRecord(
                    receipt=_receipt(),
                    signature_valid=True,
                    source_agent_writable=True,
                )
            }
        )


def test_commercially_supported_requires_second_paid_action() -> None:
    completed = _work_item(
        status="COMPLETED",
        maturityTarget={
            "engineering": "EXTERNAL_VALIDATED",
            "commercial": "COMMERCIALLY_SUPPORTED",
        },
        externalReceiptRequired=True,
        externalEvidenceRefs=["XREC-PAID-PILOT-1"],
    )
    collection = WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=[completed],
    )
    with pytest.raises(ValueError, match="exceeds trusted evidence"):
        collection.validate_completion_evidence(
            {
                "XREC-PAID-PILOT-1": TrustedEvidenceRecord(
                    receipt=_receipt(),
                    signature_valid=True,
                    source_agent_writable=False,
                )
            }
        )


def test_candidate_manifest_rejects_artifact_substitution() -> None:
    artifacts = {
        "packet": b"packet",
        "context": b"context",
        "checkpoint": b"checkpoint",
        "stage:builder:report": b"stage report",
        "gate:unit": b"gate output",
        "finding:F-1": b"finding",
        "external:XREC-PAID-PILOT-1": b"receipt",
    }
    manifest = CandidateManifest.model_validate(
        {
            "manifestVersion": 3,
            "baseSha": "1" * 40,
            "candidateSha": "2" * 40,
            "candidateTreeSha": "3" * 40,
            "workItemId": "V3-PROD-001",
            "packetDigest": sha256_digest(artifacts["packet"]),
            "contextDigest": sha256_digest(artifacts["context"]),
            "executor": {
                "backend": "fake",
                "adapter": "tests.fake",
                "model": "deterministic",
                "sessionId": "session-1",
            },
            "stageOutputs": [
                {
                    "stage": "builder",
                    "name": "report",
                    "digest": sha256_digest(artifacts["stage:builder:report"]),
                }
            ],
            "gates": [
                {
                    "name": "unit",
                    "version": "1",
                    "result": "PASS",
                    "evidenceDigest": sha256_digest(artifacts["gate:unit"]),
                }
            ],
            "findings": [
                {
                    "fingerprint": "F-1",
                    "disposition": "resolved",
                    "artifactDigest": sha256_digest(artifacts["finding:F-1"]),
                }
            ],
            "externalEvidence": [
                {
                    "receiptId": "XREC-PAID-PILOT-1",
                    "recordDigest": sha256_digest(artifacts["external:XREC-PAID-PILOT-1"]),
                }
            ],
            "checkpointDigest": sha256_digest(artifacts["checkpoint"]),
            "releaseDecision": "HOLD",
            "createdAt": NOW,
        }
    )
    manifest.verify_artifacts(artifacts)
    substituted = dict(artifacts)
    substituted["stage:builder:report"] = b"different report"
    with pytest.raises(ValueError, match="digest mismatch"):
        manifest.verify_artifacts(substituted)
    nonexistent = dict(artifacts)
    nonexistent.pop("external:XREC-PAID-PILOT-1")
    with pytest.raises(ValueError, match="bound artifact set mismatch"):
        manifest.verify_artifacts(nonexistent)
    assert manifest.canonical_digest() == manifest.model_copy().canonical_digest()


def test_milestone_rejects_global_all_product_completion() -> None:
    with pytest.raises(ValidationError, match="all-product-tasks"):
        MilestoneRoadmap.model_validate(
            {
                "version": 3,
                "milestones": [
                    {
                        "milestoneId": "M1_NATIVE_PREFLIGHT",
                        "type": "ENGINEERING",
                        "status": "ACTIVE",
                        "entryCriteria": [],
                        "exitCriteria": ["All product tasks are complete"],
                        "requiredEvidence": ["controlled fixture"],
                        "forbiddenClaims": ["commercially validated"],
                    }
                ],
            }
        )


def test_retry_zero_is_finite_and_generated_schemas_are_exact() -> None:
    policy = RetryPolicy(max_plan_attempts=0, max_candidate_repair_cycles=0)
    assert policy.plan_attempts_remaining(0) == 0
    assert policy.repair_cycles_remaining(0) == 0
    rendered = rendered_schemas()
    assert set(rendered) == set(SCHEMAS)
    for name, content in rendered.items():
        assert (ROOT / "schemas/factory/v3" / name).read_text(encoding="utf-8") == content
