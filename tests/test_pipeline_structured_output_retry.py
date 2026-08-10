"""Regression: a lost review report must not be spent as a bounded repair cycle.

Durable provenance: the checkpoint
``factory/state/pipelines/FACTORY_REPAIR_20260810T232826Z_1.json`` records a ``results``
entry with ``role="audit"``, ``attempt=1``,
``terminal_reason="structured_output_retry_exhausted"`` and the error text reproduced
verbatim in ``STRUCTURED_OUTPUT_ERROR`` below. That same checkpoint shows
``stage_failures={"audit": 1}`` alongside ``repair_cycles=2``: the SDK gave up
serializing the reviewer's report, so no audit verdict ever existed, yet the pipeline
routed the stage into ``repair.max_cycles`` and handed the transport error to the
mutating role as if it were a reviewer finding.

These tests pin the classifier, the bounded in-place review retry, and the recovery
classification, plus their negative controls (a truthful rejection and an unattributed
failure must keep the old behaviour).
"""

from __future__ import annotations

import inspect

from tcfactory.autopilot import is_infrastructure_failure
from tcfactory.models import RoleName, StageResult, Verdict
from tcfactory.pipeline import (
    MAX_REVIEW_INFRA_RETRIES,
    review_infra_retry_update,
    run_pipeline,
    stage_hit_structured_output_fault,
    stage_hit_turn_ceiling,
    terminal_failure_message,
)

# Verbatim copy of results[].error for role=="audit" in the durable checkpoint
# factory/state/pipelines/FACTORY_REPAIR_20260810T232826Z_1.json.
STRUCTURED_OUTPUT_ERROR = (
    "Exception: Claude Code returned an error result: Failed to provide valid "
    "structured output after 5 attempts; Structured output validation failed: "
    "1 validation error for AgentReport\n  Input should be a valid dictionary or "
    "instance of AgentReport [type=model_type, input_value=None, "
    "input_type=NoneType]\n    For further information visit "
    "https://errors.pydantic.dev/2.13/v/model_type; Claude result "
    "subtype=error_max_structured_output_retries, "
    "terminal_reason=structured_output_retry_exhausted, "
    "errors=['Failed to provide valid structured output after 5 attempts']"
)
TURN_CEILING_ERROR = (
    "Exception: Claude Code returned an error result: Reached maximum number of turns (10)"
)


def _result(**overrides: object) -> StageResult:
    fields: dict[str, object] = {
        "task_id": "FACTORY_REPAIR_20260810T232826Z_1",
        "run_id": "20260810T232826Z",
        "role": RoleName.AUDIT,
        "attempt": 1,
        "model": "opus",
        "verdict": Verdict.FAIL,
        "artifact_dir": "factory/artifacts/x/20260810T232826Z/adversary-a1",
    }
    fields.update(overrides)
    return StageResult.model_validate(fields)


def test_durable_structured_output_error_text_is_recognized() -> None:
    assert stage_hit_structured_output_fault(_result(error=STRUCTURED_OUTPUT_ERROR))


def test_bare_terminal_reason_is_recognized_without_error_text() -> None:
    """A result may carry only ``terminal_reason``; it is still a transport fault."""
    assert stage_hit_structured_output_fault(
        _result(terminal_reason="structured_output_retry_exhausted")
    )


def test_truthful_review_rejection_is_not_a_structured_output_fault() -> None:
    """Negative control: a reviewer that reported real findings keeps its verdict."""
    rejection = _result(
        terminal_reason="completed",
        error="Adversary rejected the candidate: gate evidence is missing",
    )
    assert not stage_hit_structured_output_fault(rejection)
    assert review_infra_retry_update(rejection, 1) is None


def test_turn_ceiling_is_not_reclassified_as_a_structured_output_fault() -> None:
    """The two transport faults stay distinct so each keeps its own bounded remedy."""
    ceiling = _result(error=TURN_CEILING_ERROR, terminal_reason="max_turns")
    assert stage_hit_turn_ceiling(ceiling)
    assert not stage_hit_structured_output_fault(ceiling)


def test_review_retry_is_in_place_and_changes_no_resource_ceiling() -> None:
    """The reviewer's budget is untouched: only its report serialization failed."""
    update = review_infra_retry_update(_result(error=STRUCTURED_OUTPUT_ERROR), 1)
    assert update == {}


def test_review_retry_is_bounded_and_then_yields_to_the_normal_path() -> None:
    """A persistently wedged reviewer must still reach repair/failure, not loop."""
    fault = _result(error=STRUCTURED_OUTPUT_ERROR)
    for failure_count in range(1, MAX_REVIEW_INFRA_RETRIES + 1):
        assert review_infra_retry_update(fault, failure_count) == {}
    assert review_infra_retry_update(fault, MAX_REVIEW_INFRA_RETRIES + 1) is None
    assert review_infra_retry_update(fault, 99) is None


def test_review_infra_retry_is_wired_into_the_review_branch() -> None:
    """Pins the earlier defect: the classifier existed but was never called.

    This asserts the call site exists, not that the whole pipeline behaves; no test in
    this repository drives ``run_pipeline`` end to end.
    """
    source = inspect.getsource(run_pipeline)
    assert "review_infra_retry_update(" in source
    assert "if infra_update is not None:" in source


def test_lost_review_report_earns_recovery_not_a_specification_revision() -> None:
    """The terminal wrapper must stay classifiable after ``terminal_failure_message``."""
    message = terminal_failure_message(
        "Stage adversary failed and no repair path remains.",
        _result(error=STRUCTURED_OUTPUT_ERROR),
    )
    assert is_infrastructure_failure(message)


def test_unattributed_failure_still_consumes_a_revision() -> None:
    """Negative control: an unclassifiable failure must not earn a free requeue."""
    message = terminal_failure_message(
        "Stage adversary failed and no repair path remains.", _result()
    )
    assert "unknown" in message
    assert not is_infrastructure_failure(message)
