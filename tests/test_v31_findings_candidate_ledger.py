from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/migrations/V3_1_ZH_158_ROW_FINDINGS_LEDGER.json"


def test_findings_candidate_ledger_is_exact_and_not_activation_authority() -> None:
    subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/update_v31_findings_candidate.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    payload = cast(dict[str, Any], json.loads(LEDGER.read_text(encoding="utf-8")))
    evaluation = cast(dict[str, Any], payload["candidateEvaluation"])
    assert evaluation["status"] == "IN_PROGRESS_NOT_ACCEPTED_NOT_ACTIVATED"
    assert evaluation["provenFinalCount"] == 0
    assert evaluation["activationAuthorized"] is False
    assert evaluation["controllerMustRemainStopped"] is True
    assert sum(evaluation["classificationCounts"].values()) == 158
    records = cast(list[dict[str, Any]], payload["records"])
    assert len(records) == 158
    assert len({record["requirementId"] for record in records}) == 158
    assert all(
        record["candidateAcceptance"] == "PENDING_NOT_ACTIVATION_AUTHORITY"
        for record in records
    )


def test_candidate_pending_buckets_are_exact_and_nonoverlapping() -> None:
    payload = cast(dict[str, Any], json.loads(LEDGER.read_text(encoding="utf-8")))
    records = cast(list[dict[str, Any]], payload["records"])
    observed: dict[str, set[str]] = {}
    for record in records:
        classification = cast(str, record["candidateClassification"])
        requirement_id = cast(str, record["requirementId"])
        observed.setdefault(classification, set()).add(requirement_id)
    assert {name: len(ids) for name, ids in observed.items()} == {
        "LOCAL_IMPLEMENTATION_PENDING_INTEGRATED_ACCEPTANCE": 100,
        "EXTERNAL_FACT_PENDING": 14,
        "INDEPENDENT_PROVISIONING_PENDING": 10,
        "LIVE_CANARY_PENDING": 32,
        "M0_EXTERNAL_EVIDENCE_PENDING": 2,
    }
    all_ids: set[str] = set()
    for ids in observed.values():
        all_ids.update(ids)
    assert len(all_ids) == sum(len(ids) for ids in observed.values())
