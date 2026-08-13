#!/usr/bin/env python3
"""Generate the reviewed 109-row typed completion/evidence roster."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


EXTERNAL_OVERRIDES: dict[str, tuple[list[str], int]] = {
    "V3-MKT-003": (["CUSTOMER_CONVERSATION"], 15),
    "V3-MKT-004": (["INCIDENT_TIMELINE"], 5),
    "V3-MKT-005": (["UPCOMING_CHANGE"], 3),
    "V3-MKT-006": (["PILOT_CANDIDATE"], 2),
    "V3-MKT-007": (["INCIDENT_ARCHIVE_ACCESS"], 1),
    "V3-MKT-008": (["CUSTOMER_AUTHORIZATION"], 1),
    "V3-MKT-010": (["CUSTOMER_AUTHORIZATION"], 1),
    "V3-PILOT-001": (["PAID_PILOT"], 1),
    "V3-PILOT-011": (["DECISION_CHANGED"], 1),
    "V3-PILOT-013": (["SECOND_ACTION_COMMITMENT"], 1),
    "V3-REPEAT-001": (["SECOND_PAID_ACTION"], 1),
    "V3-MKT-011": (["SUPPORT_ACCEPTANCE"], 1),
    # These non-EXTERNAL_EVIDENCE rows still cannot support the named maturity
    # without exact external provenance.
    "V3-PROD-026": (["GPU_EXECUTION"], 1),
    "V3-PACK-002": (["SAME_FAMILY_CASE"], 1),
    "V3-TRUST-009": (["INDEPENDENT_OPERATOR"], 1),
    "V3-TRUST-012": (["PROVIDER_ACCEPTANCE"], 1),
    "V3-TRUST-013": (["PROVIDER_ACCEPTANCE"], 1),
    "V3-REPEAT-004": (["INDEPENDENT_OPERATOR"], 1),
    "V3-REPEAT-005": (["DECISION_CHANGED"], 1),
    "V3-REPEAT-006": (["DELIVERY_ECONOMICS"], 2),
}


SEMANTIC_OVERRIDES: dict[str, dict[str, int]] = {
    "V3-MKT-001": {"REACHABLE_ACCOUNT": 30, "ATTRIBUTABLE_SOURCE": 1},
    "V3-COMP-005": {"TRAINCHECK_INCIDENT_DIFFERENTIAL": 1},
    "V3-PROD-029": {"SUPPORT_POLICY": 1},
    "V3-REPEAT-006": {"DELIVERY_ECONOMICS": 1},
    "V3-PACK-002": {"THIRD_SAME_FAMILY_CASE": 1},
    "V3-TRUST-005": {
        "LEGAL_REDUCTION_VERIFIED": 1,
        "ILLEGAL_REDUCTION_REJECTED": 1,
    },
    "V3-PILOT-011": {
        "CUSTOMER_DECISION_CHANGED": 1,
        "CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT": 1,
    },
}

PRIOR_EVIDENCE_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "V3-PILOT-011": {
        "V3-PILOT-003": ["NATIVE_VALUE_AUTHORIZATION"],
    },
    "V3-REPEAT-005": {
        "V3-PILOT-003": ["NATIVE_VALUE_AUTHORIZATION"],
    },
}


MILESTONE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "M0_FACTORY_MIGRATED": {
        "external": [],
        "semantic": {"MACHINE_POLICY_DECISION": 1},
        "machine": True,
        "future": [],
    },
    "M1_NATIVE_PREFLIGHT": {
        "external": [
            "CUSTOMER_CONVERSATION",
            "INCIDENT_TIMELINE",
            "UPCOMING_CHANGE",
            "PILOT_CANDIDATE",
            "INCIDENT_ARCHIVE_ACCESS",
        ],
        "semantic": {
            "REACHABLE_ACCOUNT": 30,
            "ATTRIBUTABLE_SOURCE": 1,
            "NATIVE_VALUE_AUTHORIZATION": 1,
        },
        "machine": True,
        "future": ["PRODUCT", "FACTORY"],
    },
    "M2_CONTROLLED_QUALIFICATION": {
        "external": ["GPU_EXECUTION", "INDEPENDENT_OPERATOR"],
        "semantic": {
            "NATIVE_VALUE_AUTHORIZATION": 1,
            "TRAINCHECK_INCIDENT_DIFFERENTIAL": 1,
            "LEGAL_REDUCTION_VERIFIED": 1,
            "ILLEGAL_REDUCTION_REJECTED": 1,
        },
        "machine": True,
        "future": [],
    },
    "M3_PAID_PREFLIGHT": {
        "external": [
            "INCIDENT_ARCHIVE_ACCESS",
            "CUSTOMER_AUTHORIZATION",
            "PROVIDER_ACCEPTANCE",
        ],
        "semantic": {"MACHINE_POLICY_DECISION": 1},
        "machine": True,
        "future": [],
    },
    "M4_PAID_PILOT": {
        "external": ["PAID_PILOT", "DECISION_CHANGED", "SECOND_ACTION_COMMITMENT"],
        "semantic": {
            "NATIVE_VALUE_AUTHORIZATION": 1,
            "CUSTOMER_DECISION_CHANGED": 1,
            "CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT": 1,
        },
        "machine": True,
        "future": [],
    },
    "M5_PAID_REPEAT": {
        "external": [
            "SECOND_PAID_ACTION",
            "INDEPENDENT_OPERATOR",
            "DECISION_CHANGED",
            "DELIVERY_ECONOMICS",
        ],
        "semantic": {"DELIVERY_ECONOMICS": 1},
        "machine": True,
        "future": [],
    },
    "M6_COMMERCIALLY_SUPPORTED_PACK": {
        "external": [
            "DECISION_CHANGED",
            "SECOND_PAID_ACTION",
            "SAME_FAMILY_CASE",
            "SUPPORT_ACCEPTANCE",
        ],
        "semantic": {
            "THIRD_SAME_FAMILY_CASE": 1,
            "SUPPORT_POLICY": 1,
            "NATIVE_VALUE_AUTHORIZATION": 1,
        },
        "machine": True,
        "future": [],
    },
}

# Reviewed, exact closure for each authoritative exit criterion.  The keys are
# source-stable IDs, not prose matching rules.  A changed criterion makes the
# policy generator fail until this roster is deliberately reviewed.
EXIT_CRITERION_WORK_ITEMS: dict[str, tuple[str, ...]] = {
    "M0_FACTORY_MIGRATED-EXIT-01": ("V3-MIG-003", "V3-MIG-004"),
    "M0_FACTORY_MIGRATED-EXIT-02": ("V3-MIG-003",),
    "M0_FACTORY_MIGRATED-EXIT-03": ("V3-MIG-005",),
    "M0_FACTORY_MIGRATED-EXIT-04": ("V3-MIG-007", "V3-MIG-014"),
    "M0_FACTORY_MIGRATED-EXIT-05": ("V3-MIG-008", "V3-MIG-009"),
    "M0_FACTORY_MIGRATED-EXIT-06": ("V3-MIG-010",),
    "M0_FACTORY_MIGRATED-EXIT-07": ("V3-MIG-008", "V3-MIG-012", "V3-MIG-016"),
    "M0_FACTORY_MIGRATED-EXIT-08": ("V3-MIG-013",),
    "M0_FACTORY_MIGRATED-EXIT-09": ("V3-MIG-015",),
    "M0_FACTORY_MIGRATED-EXIT-10": ("V3-MIG-019",),
    "M0_FACTORY_MIGRATED-EXIT-11": ("V3-MIG-017",),
    "M0_FACTORY_MIGRATED-EXIT-12": ("V3-MIG-004", "V3-MIG-016"),
    "M1_NATIVE_PREFLIGHT-EXIT-01": ("V3-PROD-001",),
    "M1_NATIVE_PREFLIGHT-EXIT-02": ("V3-PROD-002",),
    "M1_NATIVE_PREFLIGHT-EXIT-03": ("V3-PROD-006",),
    "M1_NATIVE_PREFLIGHT-EXIT-04": ("V3-TRUST-001", "V3-PROD-003", "V3-PROD-004", "V3-PROD-005"),
    "M1_NATIVE_PREFLIGHT-EXIT-05": ("V3-COMP-001", "V3-COMP-003", "V3-PROD-007", "V3-PROD-008"),
    "M1_NATIVE_PREFLIGHT-EXIT-06": ("V3-PROD-009",),
    "M1_NATIVE_PREFLIGHT-EXIT-07": ("V3-PROD-010",),
    "M1_NATIVE_PREFLIGHT-EXIT-08": (
        "V3-MKT-001",
        "V3-MKT-003",
        "V3-MKT-004",
        "V3-MKT-005",
        "V3-MKT-006",
        "V3-MKT-007",
    ),
    "M1_NATIVE_PREFLIGHT-EXIT-09": ("V3-COMP-002", "V3-COMP-003", "V3-COMP-004"),
    "M1_NATIVE_PREFLIGHT-EXIT-10": (
        "V3-TRUST-001",
        "V3-TRUST-002",
        "V3-TRUST-003",
        "V3-MKT-002",
        "V3-DEC-001",
    ),
    "M2_CONTROLLED_QUALIFICATION-EXIT-01": (
        "V3-PROD-018",
        "V3-PROD-020",
        "V3-PROD-024",
        "V3-PROD-025",
    ),
    "M2_CONTROLLED_QUALIFICATION-EXIT-02": ("V3-PROD-020", "V3-PROD-024"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-03": ("V3-PROD-020", "V3-PROD-024"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-04": ("V3-PROD-014", "V3-TRUST-005", "V3-PROD-016"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-05": ("V3-PROD-014", "V3-TRUST-005", "V3-PROD-016"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-06": ("V3-PROD-019", "V3-TRUST-007"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-07": ("V3-PROD-016", "V3-PROD-021", "V3-PROD-027"),
    "M2_CONTROLLED_QUALIFICATION-EXIT-08": ("V3-PROD-023",),
    "M2_CONTROLLED_QUALIFICATION-EXIT-09": ("V3-PROD-026",),
    "M2_CONTROLLED_QUALIFICATION-EXIT-10": ("V3-TRUST-009",),
    "M2_CONTROLLED_QUALIFICATION-EXIT-11": ("V3-TRUST-010", "V3-DEC-002"),
    "M3_PAID_PREFLIGHT-EXIT-01": ("V3-PROD-028",),
    "M3_PAID_PREFLIGHT-EXIT-02": ("V3-COMP-006", "V3-MKT-010"),
    "M3_PAID_PREFLIGHT-EXIT-03": ("V3-MKT-008", "V3-MKT-009", "V3-TRUST-011"),
    "M3_PAID_PREFLIGHT-EXIT-04": ("V3-TRUST-012", "V3-TRUST-013"),
    "M3_PAID_PREFLIGHT-EXIT-05": ("V3-DEC-003",),
    "M4_PAID_PILOT-EXIT-01": ("V3-PILOT-011",),
    "M4_PAID_PILOT-EXIT-02": (
        "V3-PILOT-003",
        "V3-PILOT-005",
        "V3-PILOT-006",
        "V3-PILOT-007",
        "V3-PILOT-009",
    ),
    "M4_PAID_PILOT-EXIT-03": ("V3-PILOT-011",),
    "M4_PAID_PILOT-EXIT-04": ("V3-PILOT-012",),
    "M4_PAID_PILOT-EXIT-05": ("V3-PILOT-013",),
    "M5_PAID_REPEAT-EXIT-01": ("V3-REPEAT-001",),
    "M5_PAID_REPEAT-EXIT-02": ("V3-REPEAT-003",),
    "M5_PAID_REPEAT-EXIT-03": ("V3-REPEAT-005", "V3-REPEAT-006"),
    "M5_PAID_REPEAT-EXIT-04": ("V3-REPEAT-002", "V3-REPEAT-003"),
    "M5_PAID_REPEAT-EXIT-05": ("V3-REPEAT-004",),
    "M5_PAID_REPEAT-EXIT-06": ("V3-REPEAT-006",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-01": ("V3-REPEAT-005",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-02": ("V3-REPEAT-001",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-03": ("V3-PACK-002",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-04": ("V3-PACK-002",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-05": ("V3-TRUST-015",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-06": ("V3-TRUST-014", "V3-PROD-029", "V3-MKT-011"),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-07": ("V3-COMP-007",),
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-08": ("V3-PROD-029",),
}

EXIT_CRITERION_EXTERNAL: dict[str, list[str]] = {
    "M1_NATIVE_PREFLIGHT-EXIT-08": MILESTONE_REQUIREMENTS["M1_NATIVE_PREFLIGHT"]["external"],
    "M2_CONTROLLED_QUALIFICATION-EXIT-09": ["GPU_EXECUTION"],
    "M2_CONTROLLED_QUALIFICATION-EXIT-10": ["INDEPENDENT_OPERATOR"],
    "M3_PAID_PREFLIGHT-EXIT-01": ["INCIDENT_ARCHIVE_ACCESS"],
    "M3_PAID_PREFLIGHT-EXIT-02": ["CUSTOMER_AUTHORIZATION"],
    "M4_PAID_PILOT-EXIT-01": ["DECISION_CHANGED"],
    "M4_PAID_PILOT-EXIT-03": ["DECISION_CHANGED"],
    "M4_PAID_PILOT-EXIT-05": ["SECOND_ACTION_COMMITMENT"],
    "M5_PAID_REPEAT-EXIT-01": ["SECOND_PAID_ACTION"],
    "M5_PAID_REPEAT-EXIT-03": ["DECISION_CHANGED", "DELIVERY_ECONOMICS"],
    "M5_PAID_REPEAT-EXIT-05": ["INDEPENDENT_OPERATOR"],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-01": ["DECISION_CHANGED"],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-02": ["SECOND_PAID_ACTION"],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-03": ["SAME_FAMILY_CASE"],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-06": ["SUPPORT_ACCEPTANCE"],
}

EXIT_CRITERION_SEMANTICS: dict[str, dict[str, int]] = {
    "M1_NATIVE_PREFLIGHT-EXIT-08": {"REACHABLE_ACCOUNT": 30, "ATTRIBUTABLE_SOURCE": 1},
    "M2_CONTROLLED_QUALIFICATION-EXIT-01": {"TRAINCHECK_INCIDENT_DIFFERENTIAL": 1},
    "M2_CONTROLLED_QUALIFICATION-EXIT-02": {"TRAINCHECK_INCIDENT_DIFFERENTIAL": 1},
    "M2_CONTROLLED_QUALIFICATION-EXIT-03": {"TRAINCHECK_INCIDENT_DIFFERENTIAL": 1},
    "M2_CONTROLLED_QUALIFICATION-EXIT-04": {"LEGAL_REDUCTION_VERIFIED": 1},
    "M2_CONTROLLED_QUALIFICATION-EXIT-05": {"ILLEGAL_REDUCTION_REJECTED": 1},
    "M4_PAID_PILOT-EXIT-01": {"CUSTOMER_DECISION_CHANGED": 1},
    "M4_PAID_PILOT-EXIT-03": {"CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT": 1},
    "M4_PAID_PILOT-EXIT-02": {"NATIVE_VALUE_AUTHORIZATION": 1},
    "M5_PAID_REPEAT-EXIT-03": {"DELIVERY_ECONOMICS": 1},
    "M5_PAID_REPEAT-EXIT-06": {"DELIVERY_ECONOMICS": 1},
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-03": {"THIRD_SAME_FAMILY_CASE": 1},
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-04": {"THIRD_SAME_FAMILY_CASE": 1},
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-06": {"SUPPORT_POLICY": 1},
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-07": {"NATIVE_VALUE_AUTHORIZATION": 1},
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-08": {"SUPPORT_POLICY": 1},
}

EXIT_CRITERION_MACHINE = {
    "M0_FACTORY_MIGRATED-EXIT-05",
    "M0_FACTORY_MIGRATED-EXIT-07",
    "M0_FACTORY_MIGRATED-EXIT-12",
    "M2_CONTROLLED_QUALIFICATION-EXIT-10",
    "M2_CONTROLLED_QUALIFICATION-EXIT-11",
    "M3_PAID_PREFLIGHT-EXIT-04",
    "M4_PAID_PILOT-EXIT-02",
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-05",
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-07",
}

EXIT_CRITERION_CORRELATION: dict[str, list[str]] = {
    "M4_PAID_PILOT-EXIT-01": ["PRODUCT_LINEAGE", "CUSTOMER", "OFFER"],
    "M4_PAID_PILOT-EXIT-03": ["PRODUCT_LINEAGE", "CUSTOMER", "OFFER"],
    "M5_PAID_REPEAT-EXIT-03": ["PRODUCT_LINEAGE", "CUSTOMER", "OFFER"],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-03": [
        "PRODUCT_LINEAGE",
        "CUSTOMER",
        "FAMILY",
        "PACK",
    ],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-04": [
        "PRODUCT_LINEAGE",
        "CUSTOMER",
        "FAMILY",
        "PACK",
    ],
    "M6_COMMERCIALLY_SUPPORTED_PACK-EXIT-06": ["PRODUCT_LINEAGE", "PACK"],
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_digest(item: dict[str, Any]) -> str:
    raw = yaml.safe_dump(
        {
            "workItemId": item["workItemId"],
            "kind": item["kind"],
            "riskTier": item["riskTier"],
            "maturityTarget": item["maturityTarget"],
            "evidenceRequired": item["evidenceRequired"],
            "externalReceiptRequired": item["externalReceiptRequired"],
            "machinePolicyReceiptRequired": item.get("machinePolicyReceiptRequired", False),
        },
        sort_keys=True,
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def work_contract(item: dict[str, Any]) -> dict[str, Any]:
    identifier = str(item["workItemId"])
    authorities = ["CONTROLLER"]
    semantics = ["DETERMINISTIC_ARTIFACT"]
    external_types, minimum_external = EXTERNAL_OVERRIDES.get(identifier, ([], 0))
    if item["riskTier"] in {"INTEGRATION", "TRUST_CORE"}:
        authorities.append("INDEPENDENT_REVIEWER")
        semantics.append("INDEPENDENT_REVIEW")
    explicit_machine = bool(item.get("machinePolicyReceiptRequired")) or (
        item["kind"] == "MACHINE_POLICY_REVIEW"
    )
    evidence_text = " ".join(str(value).lower() for value in item["evidenceRequired"])
    if any(
        marker in evidence_text
        for marker in (
            "machine-policy",
            "machine authorization",
            "signed policy",
            "scoped signed receipt",
            "continue/narrow/stop",
        )
    ):
        explicit_machine = True
    if explicit_machine:
        authorities.append("INDEPENDENT_MACHINE_POLICY")
        semantics.append("MACHINE_POLICY_DECISION")
    commercial = str(item["maturityTarget"]["commercial"])
    if item["kind"] == "CONTROLLED_EXPERIMENT" or commercial == ("NATIVE_ADVANTAGE_DEMONSTRATED"):
        authorities.append("INDEPENDENT_MACHINE_POLICY")
        semantics.append("NATIVE_VALUE_AUTHORIZATION")
    if external_types or item["externalReceiptRequired"]:
        if not external_types:
            raise ValueError(f"ambiguous external evidence requires reviewed mapping: {identifier}")
        authorities.append("TRUSTED_EXTERNAL")
    engineering = str(item["maturityTarget"]["engineering"])
    minimum_grade = {
        "DESIGN_ONLY": "DETERMINISTIC",
        "IMPLEMENTED_EXPERIMENTAL": "CONTROLLED",
        "CONTROLLED_VALIDATED": "CONTROLLED",
        "EXTERNAL_VALIDATED": (
            "EXTERNAL" if external_types or item["externalReceiptRequired"] else "LIVE"
        ),
        "DEPRECATED": "DETERMINISTIC",
    }[engineering]
    semantic_counts = SEMANTIC_OVERRIDES.get(identifier, {})
    semantics.extend(semantic_counts)
    if item["kind"] not in {"EXTERNAL_EVIDENCE", "MACHINE_POLICY_REVIEW"}:
        semantics.append("CANDIDATE_MANIFEST")
    return {
        "workItemId": identifier,
        "milestoneId": item["milestone"],
        "roadmapEvidenceDigest": evidence_digest(item),
        "minimumGrade": minimum_grade,
        "requiredAuthorities": sorted(set(authorities)),
        "requiredSemantics": sorted(set(semantics)),
        "allowedExternalEvidenceTypes": sorted(external_types),
        "minimumExternalArtifacts": minimum_external,
        "minimumSemanticCounts": semantic_counts,
        "requiredPriorEvidence": PRIOR_EVIDENCE_REQUIREMENTS.get(identifier, {}),
    }


def exit_criterion_contracts(
    milestone: dict[str, Any], items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Bind every source exit criterion to the exact milestone evidence closure."""

    milestone_id = str(milestone["milestoneId"])
    known_items = {str(item["workItemId"]) for item in items}
    contracts: list[dict[str, Any]] = []
    for index, criterion in enumerate(milestone["exitCriteria"], start=1):
        criterion_id = f"{milestone_id}-EXIT-{index:02d}"
        required_items = EXIT_CRITERION_WORK_ITEMS.get(criterion_id)
        if required_items is None:
            raise ValueError(f"exit criterion lacks a reviewed closure: {criterion_id}")
        if set(required_items) - known_items:
            raise ValueError(f"exit criterion references an unknown work item: {criterion_id}")
        contracts.append(
            {
                "criterionId": criterion_id,
                "criterionDigest": "sha256:" + hashlib.sha256(str(criterion).encode()).hexdigest(),
                "requiredWorkItemIds": list(required_items),
                "requiredExternalEvidenceTypes": EXIT_CRITERION_EXTERNAL.get(criterion_id, []),
                "requiredSemanticCounts": EXIT_CRITERION_SEMANTICS.get(criterion_id, {}),
                "machinePolicyRequired": criterion_id in EXIT_CRITERION_MACHINE,
                "requiredCorrelationFields": EXIT_CRITERION_CORRELATION.get(criterion_id, []),
            }
        )
    return contracts


def generate() -> str:
    work_path = ROOT / "factory/roadmap/work_items.yaml"
    milestone_path = ROOT / "factory/roadmap/milestones.yaml"
    items = yaml.safe_load(work_path.read_text(encoding="utf-8"))["workItems"]
    milestones = yaml.safe_load(milestone_path.read_text(encoding="utf-8"))["milestones"]
    if len(items) != 109:
        raise ValueError(f"expected exact 109-row active roadmap, observed {len(items)}")
    if set(EXTERNAL_OVERRIDES) - {item["workItemId"] for item in items}:
        raise ValueError("external evidence override references an unknown work item")
    if {item["milestoneId"] for item in milestones} != set(MILESTONE_REQUIREMENTS):
        raise ValueError("milestone evidence mapping does not cover the exact roadmap")
    expected_criteria = {
        f"{milestone['milestoneId']}-EXIT-{index:02d}"
        for milestone in milestones
        for index, _ in enumerate(milestone["exitCriteria"], start=1)
    }
    if set(EXIT_CRITERION_WORK_ITEMS) != expected_criteria:
        raise ValueError("reviewed exit-criterion roster does not exactly cover the roadmap")
    if (
        set(EXIT_CRITERION_EXTERNAL) | set(EXIT_CRITERION_SEMANTICS) | set(EXIT_CRITERION_MACHINE)
    ) - expected_criteria:
        raise ValueError("exit-criterion evidence mapping references an unknown criterion")
    payload = {
        "schemaVersion": "3.1",
        "workItemsSha256": digest(work_path),
        "milestonesSha256": digest(milestone_path),
        "workItems": [work_contract(item) for item in items],
        "milestones": [
            {
                "milestoneId": item["milestoneId"],
                "roadmapEvidenceDigest": "sha256:"
                + hashlib.sha256(yaml.safe_dump(item, sort_keys=True).encode()).hexdigest(),
                "requiredExternalEvidenceTypes": MILESTONE_REQUIREMENTS[item["milestoneId"]][
                    "external"
                ],
                "requiredSemanticCounts": MILESTONE_REQUIREMENTS[item["milestoneId"]]["semantic"],
                "machinePolicyRequired": MILESTONE_REQUIREMENTS[item["milestoneId"]]["machine"],
                "allowUnrelatedFutureLanesWhileExternalWait": MILESTONE_REQUIREMENTS[
                    item["milestoneId"]
                ]["future"],
                "exitCriteria": exit_criterion_contracts(item, items),
            }
            for item in milestones
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "config/completion_evidence_policy.yaml"
    rendered = generate()
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
            raise SystemExit("completion evidence policy is stale")
        print("PASS: exact 109-row completion evidence policy")
        return 0
    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"WROTE {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
