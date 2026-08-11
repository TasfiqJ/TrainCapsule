import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tcfactory.models import (
    Gate,
    RoleName,
    Stage,
    TaskPacket,
    ValueContract,
    ValueEvidenceClass,
    ValueGateMode,
    ValueStatus,
)
from tcfactory.value import ValueGateError, evaluate_value_contract, value_contract_digest
from tcfactory.value_policy import contract_for_task, load_value_policy

ROOT = Path(__file__).resolve().parents[1]


def test_every_catalog_task_has_predeclared_value_contract() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    for task_id in ("T001", "T041", "T119", "T124"):
        contract = contract_for_task(policy, task_id)
        assert contract.target_user
        assert contract.customer_outcome
        assert contract.revenue_linkage
        assert "lines of code" in contract.prohibited_proxies


def test_measured_milestone_has_frozen_threshold() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T012")
    assert contract.mode == ValueGateMode.MEASURED
    assert contract.minimum_material_improvement is not None
    assert contract.evidence_path
    assert contract.falsification_criteria
    assert "target_user_outcome_demonstrated_end_to_end" in contract.required_conditions
    assert "protected_source_requirements_satisfied" in contract.required_conditions
    assert "component completion without a usable supported workflow" in contract.prohibited_proxies
    assert any("target user cannot complete" in item for item in contract.falsification_criteria)


def test_external_demand_cannot_be_synthesized() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T119")
    assert contract.mode == ValueGateMode.EXTERNAL
    assert contract.required_evidence_classes


def test_foundational_contract_gets_a_machine_evidence_path() -> None:
    policy = load_value_policy(ROOT / "config/value_policy.yaml")
    contract = contract_for_task(policy, "T001")
    assert contract.mode == ValueGateMode.FOUNDATIONAL
    assert contract.evidence_path == "docs/evidence/T001/capability-value.json"


def _foundation_task(contract: ValueContract) -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="Foundation",
        phase="P0",
        goal="Prove one dependency",
        source_of_truth=["README.md"],
        acceptance_criteria=["Dependency works"],
        outputs=[contract.evidence_path or ""],
        stop_conditions=["Authority missing"],
        gates=[Gate(name="quality", command="true")],
        pipeline=[
            Stage(
                role=RoleName.BUILDER,
                allowed_paths=["**"],
                machine_gates=["quality"],
            )
        ],
        value_contract=contract,
    )


def test_foundational_value_cannot_pass_from_prose_alone(tmp_path: Path) -> None:
    contract = ValueContract(
        mode=ValueGateMode.FOUNDATIONAL,
        parent_milestone="sellable workflow",
        evidence_path="docs/evidence/T900/capability-value.json",
        required_conditions=["real boundary works"],
        falsification_criteria=["negative control rejects corruption"],
    )
    with pytest.raises(ValueGateError, match="Required value evidence is missing"):
        evaluate_value_contract(repo_root=tmp_path, task=_foundation_task(contract))


def test_foundational_value_pass_requires_hashed_candidate_evidence(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("authority\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    contract = ValueContract(
        mode=ValueGateMode.FOUNDATIONAL,
        parent_milestone="sellable workflow",
        evidence_path="docs/evidence/T900/capability-value.json",
        required_conditions=["real boundary works"],
        falsification_criteria=["negative control rejects corruption"],
    )
    raw_path = tmp_path / "docs/evidence/T900/raw/result.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text('{"observed":"real boundary"}\n', encoding="utf-8")
    evidence_path = tmp_path / (contract.evidence_path or "")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(
            {
                "task_id": "T900",
                "metric": contract.primary_metric,
                "passed": True,
                "conditions": {"real boundary works": True},
                "method": "Execute the real dependency boundary and a corrupt control.",
                "measurement_command": "pytest tests/e2e/test_boundary.py",
                "source_commit": head,
                "preregistered_contract_sha256": value_contract_digest(contract),
                "raw_artifacts": ["docs/evidence/T900/raw/result.json"],
                "artifact_hashes": {
                    "docs/evidence/T900/raw/result.json": hashlib.sha256(
                        raw_path.read_bytes()
                    ).hexdigest()
                },
                "evidence_classes": [ValueEvidenceClass.FOUNDATIONAL.value],
                "falsification_results": {
                    "negative control rejects corruption": True
                },
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_value_contract(repo_root=tmp_path, task=_foundation_task(contract))
    assert result.assessment.status == ValueStatus.PASS
