"""Regression: a turn ceiling must not burn the whole bounded retry budget.

Durable evidence: factory/state/pipelines/T001.json recorded three research attempts,
each ending with ``Reached maximum number of turns (18)`` against an unchanged 18-turn
stage budget, which exhausted re-specification and failed the task.
"""

from __future__ import annotations

from tcfactory.models import RoleConfig, RoleName, Stage, StageResult, Verdict
from tcfactory.pipeline import (
    MAX_STAGE_TURNS,
    escalated_turn_budget,
    retry_stage_update,
    stage_hit_turn_ceiling,
)

# Verbatim from factory/state/pipelines/T001.json results[2].error.
T001_TURN_CEILING_ERROR = (
    "Exception: Claude Code returned an error result: "
    "Reached maximum number of turns (18)"
)


def _result(**overrides: object) -> StageResult:
    fields: dict[str, object] = {
        "task_id": "T001",
        "run_id": "20260810T162445Z",
        "role": RoleName.RESEARCH,
        "attempt": 1,
        "model": "opus",
        "verdict": Verdict.FAIL,
        "artifact_dir": "factory/artifacts/T001/20260810T162445Z/research-a1",
    }
    fields.update(overrides)
    return StageResult.model_validate(fields)


def _role_config(max_turns: int = 25) -> RoleConfig:
    return RoleConfig(
        prompt_file="prompts/research.md",
        model="opus",
        max_turns=max_turns,
        tools=["Read"],
    )


def test_recorded_t001_error_is_recognized_as_a_turn_ceiling() -> None:
    # The report-continuation path rescues a structured report, so terminal_reason
    # reads "completed" while the durable error still records the ceiling.
    result = _result(error=T001_TURN_CEILING_ERROR, terminal_reason="completed")
    assert stage_hit_turn_ceiling(result) is True


def test_sdk_max_turns_terminal_reason_is_recognized() -> None:
    assert stage_hit_turn_ceiling(_result(terminal_reason="max_turns")) is True
    assert stage_hit_turn_ceiling(_result(error="subtype=error_max_turns")) is True


def test_truthful_product_rejection_is_not_a_turn_ceiling() -> None:
    result = _result(
        error="Candidate appears to convert an uncertainty/error status into PASS",
        terminal_reason="completed",
    )
    assert stage_hit_turn_ceiling(result) is False


def test_retry_after_turn_ceiling_raises_the_stage_turn_budget() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus", max_turns=18)
    result = _result(error=T001_TURN_CEILING_ERROR, terminal_reason="completed")

    update = retry_stage_update(stage, result, _role_config(), "sonnet")

    assert update["model"] == "sonnet"
    assert update["max_turns"] == 36
    replacement = stage.model_copy(update=update)
    assert replacement.max_turns > stage.max_turns


def test_retry_without_turn_ceiling_keeps_the_original_turn_budget() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus", max_turns=18)
    result = _result(error="Acceptance criterion 3 has no attributable evidence")

    update = retry_stage_update(stage, result, _role_config(), "sonnet")

    assert update == {"model": "sonnet"}


def test_stage_without_explicit_turns_escalates_from_the_role_default() -> None:
    stage = Stage(role=RoleName.RESEARCH, model="opus")
    result = _result(terminal_reason="max_turns")

    update = retry_stage_update(stage, result, _role_config(max_turns=25), "sonnet")

    assert update["max_turns"] == 50


def test_escalation_is_bounded_by_the_stage_schema_ceiling() -> None:
    assert escalated_turn_budget(150) == MAX_STAGE_TURNS
    assert escalated_turn_budget(MAX_STAGE_TURNS) is None
    # The escalated value must remain constructible as a Stage field.
    stage = Stage(role=RoleName.RESEARCH, max_turns=escalated_turn_budget(150))
    assert stage.max_turns == MAX_STAGE_TURNS


def test_escalated_budget_never_shrinks_a_stage() -> None:
    for current in (1, 6, 18, 25, 99):
        assert (escalated_turn_budget(current) or current) > current
