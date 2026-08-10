from pathlib import Path

import pytest

from scripts.gates.no_paid_usage import DISALLOWED_BILLING_ENV, verify_no_paid_usage


def test_paid_usage_is_permanently_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1]
    for name in DISALLOWED_BILLING_ENV:
        monkeypatch.delenv(name, raising=False)

    assert verify_no_paid_usage(root) == []


def test_paid_billing_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")

    failures = verify_no_paid_usage(root)

    assert any("ANTHROPIC_API_KEY" in failure for failure in failures)
