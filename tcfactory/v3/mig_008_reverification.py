"""Deterministic, fail-closed re-verification for V3-MIG-008.

This record proves the checked-in engineering implementation and tests.  It
deliberately does not manufacture the controller, independent reviewer, or
independent machine-policy authority required for completion eligibility.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from tcfactory.v3.completion_policy import (
    CompletionEvidenceObservation,
    EvidenceAuthority,
    EvidenceGrade,
    SemanticEvidence,
    evaluate_work_item_evidence_contract,
    load_completion_evidence_policy,
)
from tcfactory.yamlutil import load_yaml

WORK_ITEM_ID = "V3-MIG-008"
EVIDENCE_PATH = Path(
    "docs/migrations/evidence/v3.1-zh/V3-MIG-008-reverification.json"
)
SCHEMA_PATH = Path("schemas/migrations/v3-mig-008-reverification.schema.json")
COMPONENTS = {
    "COMPLETION_POLICY": Path("config/completion_evidence_policy.yaml"),
    "COMPLETION_POLICY_EVALUATOR": Path("tcfactory/v3/completion_policy.py"),
    "MACHINE_POLICY_IMPLEMENTATION": Path("tcfactory/v3/pipeline_services.py"),
    "MACHINE_POLICY_REGRESSION": Path("tests/test_v3_machine_policy.py"),
    "TASK_REVERIFICATION_REGRESSION": Path(
        "tests/test_v3_mig_008_reverification.py"
    ),
}

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]


class Mig008ReverificationError(RuntimeError):
    """The V3-MIG-008 engineering or authority boundary cannot be verified."""


def _canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_required(repo_root: Path, relative: Path) -> bytes:
    path = repo_root / relative
    if not path.is_file():
        raise Mig008ReverificationError(f"required component is missing: {relative}")
    return path.read_bytes()


def _load_json(data: bytes, relative: Path) -> JsonObject:
    try:
        value = cast(JsonValue, json.loads(data))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Mig008ReverificationError(f"invalid JSON component: {relative}") from exc
    if not isinstance(value, dict):
        raise Mig008ReverificationError(f"component must be a JSON object: {relative}")
    return cast(JsonObject, value)


def _engineering_only_policy_failures(repo_root: Path) -> list[str]:
    """Probe the contract without pretending the simulated facts are attestations."""

    contract = load_completion_evidence_policy(repo_root).work_item(WORK_ITEM_ID)
    observation = CompletionEvidenceObservation(
        grade=EvidenceGrade.CONTROLLED,
        authorities=[EvidenceAuthority.CONTROLLER],
        semantic_counts={SemanticEvidence.DETERMINISTIC_ARTIFACT: 1},
    )
    return evaluate_work_item_evidence_contract(contract, observation)


def build_reverification(repo_root: Path) -> dict[str, Any]:
    """Build the canonical engineering proof and explicit authorization gap."""

    component_bytes = {
        role: _read_required(repo_root, path) for role, path in COMPONENTS.items()
    }
    roadmap = load_yaml(repo_root / "factory/roadmap/work_items.yaml")
    roadmap_item = next(
        (
            item
            for item in roadmap.get("workItems", [])
            if item.get("workItemId") == WORK_ITEM_ID
        ),
        None,
    )
    if roadmap_item is None:
        raise Mig008ReverificationError(f"roadmap lacks {WORK_ITEM_ID}")
    contract = load_completion_evidence_policy(repo_root).work_item(WORK_ITEM_ID)
    failures = _engineering_only_policy_failures(repo_root)
    expected_failures = [
        f"{WORK_ITEM_ID} lacks INDEPENDENT_MACHINE_POLICY authority",
        f"{WORK_ITEM_ID} lacks INDEPENDENT_REVIEWER authority",
        f"{WORK_ITEM_ID} lacks 1 INDEPENDENT_REVIEW evidence",
        f"{WORK_ITEM_ID} lacks 1 MACHINE_POLICY_DECISION evidence",
    ]
    if failures != expected_failures:
        raise Mig008ReverificationError(
            "engineering-only completion-policy probe did not fail closed exactly"
        )

    body: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceType": "ENGINEERING_REVERIFICATION_WITH_AUTHORIZATION_GAP",
        "workItemId": WORK_ITEM_ID,
        "roadmapStatus": roadmap_item.get("status"),
        "componentBindings": [
            {
                "role": role,
                "path": str(COMPONENTS[role]),
                "bytes": len(component_bytes[role]),
                "sha256": _sha256(component_bytes[role]),
            }
            for role in sorted(COMPONENTS)
        ],
        "engineeringVerification": {
            "status": "VERIFIED",
            "claims": [
                "positive independently-verified record acceptance",
                "negative invalid trust-state rejection",
                "expired and not-yet-valid receipt rejection",
                "candidate SHA mismatch rejection",
                "artifact and authority-manifest digest binding",
            ],
            "testSelectors": [
                "tests/test_v3_machine_policy.py::test_machine_policy_gate_requires_independently_verified_record",
                "tests/test_v3_machine_policy.py::test_machine_policy_gate_binds_scope_candidate_artifacts_and_authority",
                "tests/test_v3_mig_008_reverification.py::test_machine_policy_gate_rejects_expired_and_future_receipts",
                "tests/test_v3_mig_008_reverification.py::test_completed_roadmap_item_without_admissible_authority_fails_closed",
            ],
        },
        "completionContract": {
            "minimumGrade": contract.minimum_grade.value,
            "requiredAuthorities": [value.value for value in contract.required_authorities],
            "requiredSemantics": [value.value for value in contract.required_semantics],
        },
        "authorityBoundary": {
            "admissibleCompletionEvidencePresent": False,
            "completionEligible": False,
            "controllerAttestationPresent": False,
            "independentMachinePolicyReceiptPresent": False,
            "independentReviewerAttestationPresent": False,
            "engineeringOnlyProbeUsesSimulatedControllerEnum": True,
            "simulationIsNotAnAttestation": True,
            "failClosedReasons": failures,
            "limitation": (
                "Engineering behavior is re-verified, but no controller-derived completion "
                "observation, independently signed machine-policy receipt, or independent "
                "reviewer attestation is asserted by this repository-authored artifact."
            ),
        },
    }
    body["evidenceDigest"] = _sha256(_canonical_bytes(body))
    return body


def validate_reverification(repo_root: Path) -> dict[str, Any]:
    """Validate schema, bindings, policy semantics, and the authority boundary."""

    schema = cast(
        dict[str, Any],
        _load_json(_read_required(repo_root, SCHEMA_PATH), SCHEMA_PATH),
    )
    evidence = cast(
        dict[str, Any],
        _load_json(_read_required(repo_root, EVIDENCE_PATH), EVIDENCE_PATH),
    )
    raw_errors = Draft202012Validator(schema).iter_errors(evidence)  # pyright: ignore[reportUnknownMemberType]
    errors: list[ValidationError] = sorted(
        raw_errors, key=lambda error: list(error.path)
    )
    if errors:
        raise Mig008ReverificationError(f"schema validation failed: {errors[0].message}")
    bindings = {
        value["role"]: value for value in evidence.get("componentBindings", [])
    }
    for role, relative in COMPONENTS.items():
        data = _read_required(repo_root, relative)
        binding = bindings.get(role)
        if binding is None or binding.get("bytes") != len(data) or binding.get(
            "sha256"
        ) != _sha256(data):
            raise Mig008ReverificationError(
                f"checked-in V3-MIG-008 component binding does not match: {role}"
            )
    expected = build_reverification(repo_root)
    if evidence != expected:
        raise Mig008ReverificationError(
            "checked-in V3-MIG-008 re-verification does not match its bound components"
        )
    return evidence


def render_reverification(repo_root: Path) -> bytes:
    """Return byte-stable JSON suitable for the checked-in evidence artifact."""

    return json.dumps(build_reverification(repo_root), indent=2, sort_keys=True).encode() + b"\n"
