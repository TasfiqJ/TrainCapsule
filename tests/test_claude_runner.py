from types import SimpleNamespace

from tcfactory.claude_runner import (
    needs_report_continuation,
    provider_compatible_task_budget,
    report_continuation_overrides,
    select_result_message,
)


def test_provider_task_budget_uses_current_minimum() -> None:
    assert provider_compatible_task_budget(None) is None
    assert provider_compatible_task_budget(8_000) == 20_000
    assert provider_compatible_task_budget(20_000) == 20_000
    assert provider_compatible_task_budget(36_000) == 36_000


def test_late_plain_peer_result_does_not_replace_structured_result() -> None:
    structured = SimpleNamespace(structured_output={"verdict": "pass"})
    late_plain = SimpleNamespace(structured_output=None)

    assert select_result_message(None, structured) is structured
    assert select_result_message(structured, late_plain) is structured
    assert select_result_message(late_plain, structured) is structured


def test_later_structured_peer_result_replaces_provisional_verdict() -> None:
    provisional = SimpleNamespace(structured_output={"verdict": "fail"})
    final = SimpleNamespace(structured_output={"verdict": "pass"})

    assert select_result_message(provisional, final) is final


def test_max_turns_without_report_gets_bounded_same_session_continuation() -> None:
    max_turns = SimpleNamespace(
        structured_output=None,
        session_id="session-123",
        subtype="error_max_turns",
        terminal_reason="max_turns",
    )
    completed = SimpleNamespace(
        structured_output={"verdict": "pass"},
        session_id="session-123",
        subtype="success",
        terminal_reason="end_turn",
    )

    assert needs_report_continuation(max_turns) is True
    assert needs_report_continuation(completed) is False


def test_report_continuation_requires_a_resumable_session() -> None:
    missing_session = SimpleNamespace(
        structured_output=None,
        session_id=None,
        subtype="error_max_turns",
        terminal_reason="max_turns",
    )

    assert needs_report_continuation(None) is False
    assert needs_report_continuation(missing_session) is False


def test_report_continuation_uses_small_tool_free_limits() -> None:
    overrides = report_continuation_overrides()

    assert overrides["max_turns"] == 4
    assert overrides["task_budget"] == {"total": 20_000}
    assert overrides["max_budget_usd"] is None
    assert overrides["effort"] == "low"
    assert overrides["tools"] == []
    assert overrides["allowed_tools"] == []
    assert overrides["skills"] == []
