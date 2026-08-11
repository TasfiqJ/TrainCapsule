from __future__ import annotations

from tcfactory.models import (
    Gate,
    MetricDirection,
    RiskTier,
    RoleName,
    Stage,
    TaskPacket,
    ValueContract,
    ValueEvidenceClass,
    ValueGateMode,
)
from tcfactory.self_repair import build_self_repair_task
from tcfactory.stage_policy import (
    apply_objective_stage_contracts,
    objective_pipeline_errors,
    objective_stage_criteria,
)


def _packet(*stages: Stage, risk: RiskTier = RiskTier.INTEGRATION) -> TaskPacket:
    return TaskPacket(
        task_id="T900",
        title="Objective outcome",
        phase="P0",
        goal="Deliver one real outcome",
        source_of_truth=["README.md"],
        acceptance_criteria=["Outcome is executable"],
        outputs=["src/**"],
        stop_conditions=["Missing authority"],
        gates=[Gate(name="quality", command="bash scripts/gates/fast_quality.sh")],
        pipeline=list(stages),
        risk_tier=risk,
    )


def _stage(role: RoleName, *, read_only: bool) -> Stage:
    return Stage(
        role=role,
        read_only=read_only,
        require_changes=not read_only,
        allowed_paths=[] if read_only else ["src/**"],
        forbidden_paths=["**"] if read_only else ["factory/**"],
        machine_gates=["quality"],
    )


def test_every_product_role_has_objective_evidence_exit_criteria() -> None:
    for role in RoleName:
        criteria = " ".join(objective_stage_criteria(role)).lower()
        assert "candidate sha" in criteria
        assert "evidence" in criteria
        assert "unknown" in criteria or "blocked" in criteria
    assert "pre-register" in " ".join(objective_stage_criteria(RoleName.RESEARCH)).lower()
    assert "real supported user journey" in " ".join(
        objective_stage_criteria(RoleName.BUILDER)
    ).lower()
    assert "install" in " ".join(objective_stage_criteria(RoleName.RELEASE)).lower()


def test_runtime_contracts_extend_instead_of_replace_task_specific_criteria() -> None:
    packet = _packet(
        _stage(RoleName.BUILDER, read_only=False).model_copy(
            update={"acceptance_criteria": ["Keep the task-specific invariant"]}
        ),
        _stage(RoleName.ADVERSARY, read_only=True),
        _stage(RoleName.AUDIT, read_only=True),
        _stage(RoleName.RELEASE, read_only=True),
    )
    hardened = apply_objective_stage_contracts(packet)
    builder = hardened.pipeline[0]
    assert builder.acceptance_criteria[0] == "Keep the task-specific invariant"
    assert len(builder.acceptance_criteria) > 5
    assert len(builder.acceptance_criteria) == len(set(builder.acceptance_criteria))


def test_objective_pipeline_rejects_review_before_mutation_and_nonfinal_release() -> None:
    packet = _packet(
        _stage(RoleName.ADVERSARY, read_only=True),
        _stage(RoleName.BUILDER, read_only=False),
        _stage(RoleName.AUDIT, read_only=True),
        _stage(RoleName.RELEASE, read_only=True),
        _stage(RoleName.SECURITY, read_only=True),
    )
    errors = objective_pipeline_errors(packet)
    assert any("release stage" in error for error in errors)
    assert any("cannot run after independent review" in error for error in errors)


def test_measured_pipeline_uses_deterministic_value_gate_not_serial_value_models() -> None:
    packet = _packet(
        _stage(RoleName.BUILDER, read_only=False),
        _stage(RoleName.ADVERSARY, read_only=True),
    ).model_copy(
        update={
            "value_contract": ValueContract(
                required=True,
                mode=ValueGateMode.MEASURED,
                primary_metric="workflow success",
                metric_direction=MetricDirection.INCREASE,
                minimum_material_improvement=1,
                measurement_unit="success",
                evidence_path=".factory/external-evidence/T900.json",
                required_conditions=["real workflow passes"],
                threshold_rationale="A complete workflow is the minimum useful outcome.",
                falsification_criteria=["workflow does not finish"],
                required_evidence_classes=[ValueEvidenceClass.DETERMINISTIC],
            )
        }
    )
    assert objective_pipeline_errors(packet) == []


def test_valid_integration_pipeline_satisfies_objective_order() -> None:
    packet = _packet(
        _stage(RoleName.BUILDER, read_only=False),
        _stage(RoleName.ADVERSARY, read_only=True),
    )
    assert objective_pipeline_errors(packet) == []


def test_read_only_self_repair_reviewers_satisfy_objective_policy() -> None:
    packet = apply_objective_stage_contracts(
        build_self_repair_task(reason="controller regression", attempt=1, task_id="T002")
    )
    assert objective_pipeline_errors(packet) == []
