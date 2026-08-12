from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.gates.active_policy_integrity import ActivePolicyError, validate_active_policy
from tcfactory.v3.migration_evidence import (
    EVIDENCE_ROOT,
    FinalMigrationEvidence,
    MigrationEvidenceError,
    PendingMigrationEvidence,
    load_evidence,
    validate_repository_evidence,
)

ROOT = Path(__file__).resolve().parents[1]


def test_v31_m0_evidence_is_explicitly_pending_not_historical_final() -> None:
    for number in range(16, 21):
        record = load_evidence(ROOT / EVIDENCE_ROOT / f"V3-MIG-{number:03d}.json")
        assert isinstance(record, PendingMigrationEvidence)
        assert record.finalization_command == [
            ".venv/bin/python",
            "scripts/finalize_v3_1_zh_m0_evidence.py",
        ]
    with pytest.raises(MigrationEvidenceError, match="is pending"):
        validate_repository_evidence(ROOT)


def test_historical_v3_final_receipt_cannot_satisfy_v31(tmp_path: Path) -> None:
    source = ROOT / "docs/migrations/evidence/V3-MIG-016.json"
    target = tmp_path / "V3-MIG-016.json"
    shutil.copy2(source, target)
    with pytest.raises(MigrationEvidenceError, match="invalid migration evidence"):
        load_evidence(target)


@pytest.mark.parametrize(
    "residue",
    [
        "WAITING_HUMAN",
        "directMainPush: true",
        "owner_directed_main_only",
        "publish directly-to-main",
        "main-only publication",
    ],
)
def test_active_policy_rejects_human_or_direct_main_residue(
    tmp_path: Path, residue: str
) -> None:
    shutil.copytree(
        ROOT,
        tmp_path / "repo",
        ignore=shutil.ignore_patterns(".git", ".venv", "worktrees"),
    )
    repo = tmp_path / "repo"
    injected = repo / "prompts/injected.md"
    injected.write_text(residue + "\n", encoding="utf-8")
    with pytest.raises(ActivePolicyError, match="active policy residue"):
        validate_active_policy(repo)


def test_pending_receipt_rejects_unknown_self_assertion(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "workItemId": "V3-MIG-019",
                "status": "PENDING_FINALIZATION",
                "finalizationCommand": ["python", "finalize.py"],
                "reason": "real PR receipts are absent",
                "selfAttestedPass": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(MigrationEvidenceError, match="invalid migration evidence"):
        load_evidence(path)


def test_final_evidence_schema_requires_independent_receipt_artifacts() -> None:
    schema = FinalMigrationEvidence.model_json_schema(by_alias=True)
    assert {
        "sourceMigrationAuthorization",
        "prAcceptanceReceipts",
        "recoveryRehearsalReceipt",
    } <= set(schema["required"])
