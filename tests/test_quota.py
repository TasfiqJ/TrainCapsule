from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tcfactory.models import PauseKind
from tcfactory.quota import classify_failure_texts


def test_parses_five_hour_reset_time() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "5-hour limit reached - resets at 18:00 UTC")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.FIVE_HOUR
    assert result.resume_at == datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def test_weekly_limit_without_timestamp_uses_bounded_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "Weekly all-model limit reached")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.WEEKLY
    assert result.resume_at == now + timedelta(hours=24)


def test_transient_rate_limit_uses_short_retry() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "HTTP 429 too many requests")],
        now=now,
        transient_retry_seconds=600,
    )
    assert result is not None
    assert result.kind == PauseKind.TRANSIENT_RATE_LIMIT
    assert result.resume_at == now + timedelta(minutes=10)


def test_unrelated_failure_is_not_quota() -> None:
    result = classify_failure_texts([("stderr", "pytest assertion failed")])
    assert result is None


def test_parses_iana_timezone_reset() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "5-hour limit reached; resets at 10:30 AM (America/Toronto)")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.FIVE_HOUR
    assert result.resume_at == datetime(2026, 8, 6, 14, 30, tzinfo=UTC)


def test_machine_rate_limit_event_uses_exact_reset() -> None:
    from types import SimpleNamespace

    from tcfactory.models import PauseKind
    from tcfactory.quota import disposition_from_rate_limit_info

    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    reset = int((now + timedelta(hours=2)).timestamp())
    info = SimpleNamespace(
        status="rejected",
        rate_limit_type="five_hour",
        resets_at=reset,
        utilization=1.0,
    )
    disposition = disposition_from_rate_limit_info(info, now=now)
    assert disposition is not None
    assert disposition.kind == PauseKind.FIVE_HOUR
    assert disposition.resume_at == datetime.fromtimestamp(reset, tz=UTC)


def test_machine_rate_limit_warning_does_not_pause() -> None:
    from tcfactory.quota import disposition_from_rate_limit_info

    assert (
        disposition_from_rate_limit_info(
            {"status": "allowed_warning", "rate_limit_type": "five_hour"}
        )
        is None
    )


def test_machine_weekly_model_limit_maps_to_model_pause() -> None:
    from tcfactory.models import PauseKind
    from tcfactory.quota import disposition_from_rate_limit_info

    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    disposition = disposition_from_rate_limit_info(
        {
            "status": "rejected",
            "rate_limit_type": "seven_day_sonnet",
            "resets_at": int((now + timedelta(days=3)).timestamp()),
        },
        now=now,
    )
    assert disposition is not None
    assert disposition.kind == PauseKind.MODEL_LIMIT


def test_machine_overage_enabled_fails_closed_as_authentication() -> None:
    from tcfactory.models import PauseKind
    from tcfactory.quota import disposition_from_rate_limit_info

    disposition = disposition_from_rate_limit_info(
        {
            "status": "allowed_warning",
            "rate_limit_type": "five_hour",
            "overage_status": "allowed",
        }
    )
    assert disposition is not None
    assert disposition.kind == PauseKind.AUTHENTICATION
    assert "paid overage" in disposition.message.lower()


def test_generic_hit_your_limit_message_parses_reset() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "You've hit your limit · resets at 18:00 UTC")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.UNKNOWN_LIMIT
    assert result.resume_at == datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def test_generic_curly_apostrophe_limit_message_parses_reset() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "You’ve hit your limit · resets in 2 hours")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.UNKNOWN_LIMIT
    assert result.resume_at == now + timedelta(hours=2)


def test_rejected_overage_with_credits_disabled_does_not_claim_paid_overage() -> None:
    from tcfactory.quota import disposition_from_rate_limit_info

    disposition = disposition_from_rate_limit_info(
        {
            "status": "rejected",
            "rate_limit_type": "overage",
            "overage_status": "rejected",
        }
    )
    assert disposition is not None
    assert disposition.kind == PauseKind.UNKNOWN_LIMIT
