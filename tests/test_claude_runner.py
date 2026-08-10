from tcfactory.claude_runner import provider_compatible_task_budget


def test_provider_task_budget_uses_current_minimum() -> None:
    assert provider_compatible_task_budget(None) is None
    assert provider_compatible_task_budget(8_000) == 20_000
    assert provider_compatible_task_budget(20_000) == 20_000
    assert provider_compatible_task_budget(36_000) == 36_000
