from types import SimpleNamespace

from tcfactory.claude_runner import provider_compatible_task_budget, select_result_message


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
