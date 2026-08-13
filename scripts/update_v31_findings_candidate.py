#!/usr/bin/env python3
"""Bind the 158-row Phase-0 findings ledger to one implementation candidate.

This updater deliberately does not promote any row to final acceptance.  It preserves
the immutable Phase-0 classifications and records which independent evidence class is
still required for each candidate row.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json"

EXTERNAL_FACT_PENDING = frozenset(
    [
        "B011",
        "I012",
        "I013",
        "I014",
        "I015",
        "J001",
        "J002",
        "J003",
        "J004",
        "J005",
        "J006",
        "J007",
        "J008",
        "J009",
    ]
)
INDEPENDENT_PROVISIONING_PENDING = frozenset(
    ["A006", "B006", "G003", "G004", "G005", "G006", "G007", "G012", "G013", "G014"]
)
LIVE_CANARY_PENDING = frozenset(
    [
        "B001",
        "B003",
        "D010",
        "E003",
        "E004",
        "E005",
        "E006",
        "E007",
        "E008",
        "E009",
        "E010",
        "E011",
        "E012",
        "E017",
        "F003",
        "F004",
        "F006",
        "F007",
        "F008",
        "G009",
        "G010",
        "H001",
        "H002",
        "H003",
        "H004",
        "H005",
        "H006",
        "H007",
        "H008",
        "H013",
        "H015",
        "H016",
    ]
)
M0_EXTERNAL_EVIDENCE_PENDING = frozenset(["D005", "D009"])

PENDING_BUCKETS = {
    "EXTERNAL_FACT_PENDING": EXTERNAL_FACT_PENDING,
    "INDEPENDENT_PROVISIONING_PENDING": INDEPENDENT_PROVISIONING_PENDING,
    "LIVE_CANARY_PENDING": LIVE_CANARY_PENDING,
    "M0_EXTERNAL_EVIDENCE_PENDING": M0_EXTERNAL_EVIDENCE_PENDING,
}

EVIDENCE_STATES = {
    "LOCAL_IMPLEMENTATION_PENDING_INTEGRATED_ACCEPTANCE": (
        "TARGETED_LOCAL_CONTROLS_EXIST; FULL_LOCAL, HOSTED, INSTALLATION, AND APPLICABLE "
        "LIVE PROOF REMAIN PENDING"
    ),
    "EXTERNAL_FACT_PENDING": "TRUSTED ATTRIBUTABLE EXTERNAL FACT IS ABSENT",
    "INDEPENDENT_PROVISIONING_PENDING": (
        "ROOT-OWNED INSTALLATION, TRUSTED GITHUB IDENTITY, OR SERVER POLICY IS ABSENT"
    ),
    "LIVE_CANARY_PENDING": (
        "EXACT-INSTALLED-CANDIDATE 20-CANARY OR SEVEN-EVENT OBSERVER PROOF IS ABSENT"
    ),
    "M0_EXTERNAL_EVIDENCE_PENDING": (
        "INDEPENDENT SOURCE AUTHORIZATION AND REAL PR/CI/MERGED-MAIN RECEIPTS ARE ABSENT"
    ),
}


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _candidate_classification(requirement_id: str) -> str:
    matches = [name for name, ids in PENDING_BUCKETS.items() if requirement_id in ids]
    if len(matches) > 1:
        raise ValueError(
            f"candidate requirement appears in multiple pending buckets: {requirement_id}"
        )
    return matches[0] if matches else "LOCAL_IMPLEMENTATION_PENDING_INTEGRATED_ACCEPTANCE"


def _load() -> dict[str, Any]:
    payload = cast(dict[str, Any], json.loads(LEDGER.read_text(encoding="utf-8")))
    return payload


def _candidate_sha(payload: dict[str, Any], requested: str | None, *, check: bool) -> str:
    if requested:
        sha = requested
    elif check:
        evaluation = payload.get("candidateEvaluation")
        if not isinstance(evaluation, dict):
            raise ValueError("checked ledger has no implementation candidate SHA")
        typed_evaluation = cast(dict[str, Any], evaluation)
        observed_sha = typed_evaluation.get("implementationCandidateSha")
        if not isinstance(observed_sha, str):
            raise ValueError("checked ledger has no implementation candidate SHA")
        sha = observed_sha
    else:
        sha = _git("rev-parse", "HEAD")
    return _git("rev-parse", f"{sha}^{{commit}}")


def updated_payload(*, candidate_sha: str | None, check: bool) -> dict[str, Any]:
    payload = _load()
    records_value = cast(object, payload.get("records"))
    if not isinstance(records_value, list):
        raise ValueError("findings ledger records must be a JSON array")
    record_objects = cast(list[object], records_value)
    if len(record_objects) != 158:
        raise ValueError("findings ledger must contain exactly 158 records")
    if not all(isinstance(record, dict) for record in record_objects):
        raise ValueError("every findings ledger record must be a JSON object")
    records = cast(list[dict[str, Any]], record_objects)

    raw_ids = [record.get("requirementId") for record in records]
    if not all(isinstance(item, str) for item in raw_ids):
        raise ValueError("findings ledger requirement IDs must be strings")
    ids = cast(list[str], raw_ids)
    if len(ids) != 158 or len(set(ids)) != 158:
        raise ValueError("findings ledger requirement IDs must be 158 unique strings")

    bucket_union: set[str] = set()
    for bucket in PENDING_BUCKETS.values():
        bucket_union.update(bucket)
    if not bucket_union <= set(ids):
        missing = sorted(bucket_union - set(ids))
        raise ValueError(f"pending candidate IDs are absent from ledger: {missing}")
    if sum(len(values) for values in PENDING_BUCKETS.values()) != len(bucket_union):
        raise ValueError("candidate pending buckets overlap")

    sha = _candidate_sha(payload, candidate_sha, check=check)
    tree = _git("show", "-s", "--format=%T", sha)
    committed_at = _git("show", "-s", "--format=%cI", sha)
    phase0_counts = payload.get("currentClassificationCounts")
    if not isinstance(phase0_counts, dict):
        raise ValueError("Phase-0 classification counts are missing")

    counts: Counter[str] = Counter()
    for record in records:
        requirement_id = cast(str, record["requirementId"])
        classification = _candidate_classification(requirement_id)
        counts[classification] += 1
        record["phase0Sha"] = record.get("currentSha")
        record["phase0Classification"] = record.get("currentClassification")
        record["candidateSha"] = sha
        record["candidateTree"] = tree
        record["candidateClassification"] = classification
        record["candidateEvidenceState"] = EVIDENCE_STATES[classification]
        record["candidateAcceptance"] = "PENDING_NOT_ACTIVATION_AUTHORITY"
        record["closureProof"] = "PENDING_EXACT_CANDIDATE_ACCEPTANCE_ARTIFACTS"

    expected_counts = {
        "LOCAL_IMPLEMENTATION_PENDING_INTEGRATED_ACCEPTANCE": 100,
        "EXTERNAL_FACT_PENDING": 14,
        "INDEPENDENT_PROVISIONING_PENDING": 10,
        "LIVE_CANARY_PENDING": 32,
        "M0_EXTERNAL_EVIDENCE_PENDING": 2,
    }
    if dict(counts) != expected_counts:
        raise ValueError(f"unexpected candidate classification counts: {dict(counts)}")

    payload["phase0Snapshot"] = {
        "sha": payload.get("baselineSha"),
        "generatedAt": payload.get("generatedAt"),
        "classificationCounts": phase0_counts,
        "openCount": payload.get("phase0OpenCount"),
        "immutableHistoricalFact": True,
    }
    payload["candidateEvaluation"] = {
        "implementationCandidateSha": sha,
        "implementationCandidateTree": tree,
        "implementationCandidateCommittedAt": committed_at,
        "status": "IN_PROGRESS_NOT_ACCEPTED_NOT_ACTIVATED",
        "classificationCounts": expected_counts,
        "allRowsRequireFurtherEvidence": True,
        "provenFinalCount": 0,
        "activationAuthorized": False,
        "controllerMustRemainStopped": True,
        "fullLocalAcceptance": "PENDING",
        "hostedExactShaAcceptance": "PENDING",
        "independentVerifierInstallation": "ABSENT",
        "githubAppAndRuleset": "ABSENT",
        "liveTwentyCanarySuite": "PENDING",
        "sevenEventObservation": "PENDING",
    }
    payload["classificationSemantics"] = {
        "currentClassificationCounts": "IMMUTABLE_PHASE_0_HISTORICAL_COUNTS",
        "candidateEvaluation": "PRE_ACCEPTANCE_CANDIDATE_REBASE; NOT FINAL CLOSURE EVIDENCE",
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = json.dumps(
        updated_payload(candidate_sha=args.candidate_sha, check=args.check),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    if args.check:
        return 0 if LEDGER.read_text(encoding="utf-8") == expected else 1
    LEDGER.write_text(expected, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
