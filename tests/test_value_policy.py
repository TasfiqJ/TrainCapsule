from pathlib import Path

from tcfactory.models import ValueGateMode
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
