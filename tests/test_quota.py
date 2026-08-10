from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from tcfactory.models import PauseKind, StageResult
from tcfactory.quota import classify_failure_texts


def test_five_hour_rejection_uses_hourly_probe_even_with_reset_time() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "5-hour limit reached - resets at 18:00 UTC")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.FIVE_HOUR
    assert result.resume_at == now + timedelta(hours=1)


def test_weekly_limit_without_timestamp_uses_hourly_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "Weekly all-model limit reached")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.WEEKLY
    assert result.resume_at == now + timedelta(hours=1)


def test_transient_rate_limit_uses_configured_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "HTTP 429 too many requests")],
        now=now,
        transient_retry_seconds=3600,
    )
    assert result is not None
    assert result.kind == PauseKind.TRANSIENT_RATE_LIMIT
    assert result.resume_at == now + timedelta(hours=1)


def test_unrelated_failure_is_not_quota() -> None:
    result = classify_failure_texts([("stderr", "pytest assertion failed")])
    assert result is None


def test_reset_timezone_does_not_override_hourly_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "5-hour limit reached; resets at 10:30 AM (America/Toronto)")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.FIVE_HOUR
    assert result.resume_at == now + timedelta(hours=1)


def test_machine_rate_limit_rejection_uses_hourly_probe() -> None:
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
    assert disposition.resume_at == now + timedelta(hours=1)


def test_machine_rate_limit_warning_does_not_pause() -> None:
    from tcfactory.quota import disposition_from_rate_limit_info

    assert (
        disposition_from_rate_limit_info(
            {"status": "allowed_warning", "rate_limit_type": "five_hour"}
        )
        is None
    )


def test_machine_allowed_rate_limit_event_does_not_pause() -> None:
    from tcfactory.quota import disposition_from_rate_limit_info

    assert (
        disposition_from_rate_limit_info(
            {"status": "allowed", "rate_limit_type": "five_hour", "utilization": None}
        )
        is None
    )


def test_allowed_rate_limit_metadata_text_does_not_pause() -> None:
    result = classify_failure_texts(
        [("stderr", 'status allowed, rate_limit_type="five_hour", available at 18:00 UTC')]
    )

    assert result is None


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


def test_generic_hit_your_limit_message_uses_hourly_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "You've hit your limit · resets at 18:00 UTC")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.UNKNOWN_LIMIT
    assert result.resume_at == now + timedelta(hours=1)


def test_generic_curly_apostrophe_limit_message_uses_hourly_probe() -> None:
    now = datetime(2026, 8, 6, 13, 0, tzinfo=UTC)
    result = classify_failure_texts(
        [("stderr", "You’ve hit your limit · resets in 2 hours")],
        now=now,
    )
    assert result is not None
    assert result.kind == PauseKind.UNKNOWN_LIMIT
    assert result.resume_at == now + timedelta(hours=1)


def test_allowed_transcript_and_model_budget_text_are_not_quota(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from tcfactory.quota import stage_failure_texts

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"rate_limit_info":{"status":"allowed","rate_limit_type":"five_hour"},'
        '"_type":"RateLimitEvent"}\n'
        '{"structured_output":{"summary":"internal token/USD budget exhausted"},'
        '"error":null,"_type":"AssistantMessage"}\n',
        encoding="utf-8",
    )
    result = cast(StageResult, SimpleNamespace(error=None, terminal_reason=None))

    assert stage_failure_texts(result, tmp_path) == []


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
