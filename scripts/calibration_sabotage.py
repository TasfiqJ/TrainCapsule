from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from tcfactory.gates import PathPolicyError, validate_changed_paths
from tcfactory.models import PauseKind
from tcfactory.quota import classify_failure_texts

CONTROLS: list[dict[str, str]] = []


def record_pass(control_id: str, detail: str) -> None:
    CONTROLS.append({"id": control_id, "status": "pass", "detail": detail})


def expect_raises(control_id: str, expected: type[Exception], function: object) -> None:
    try:
        function()  # type: ignore[operator]
    except expected as exc:
        record_pass(control_id, f"rejected with {type(exc).__name__}")
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"negative control {control_id} raised the wrong exception: {type(exc).__name__}"
        ) from exc
    raise AssertionError(f"negative control did not fail: {control_id}")


def classify(control_id: str, text: str, expected: PauseKind, now: datetime) -> None:
    disposition = classify_failure_texts([(control_id, text)], now=now)
    assert disposition is not None, control_id
    assert disposition.kind == expected, (control_id, disposition.kind, expected)
    record_pass(control_id, f"classified as {expected.value}")


def main() -> None:
    expect_raises(
        "forbidden_path_write",
        PathPolicyError,
        lambda: validate_changed_paths(
            [".claude/settings.json"],
            allowed=["src/**"],
            forbidden=[".claude/**"],
            read_only=False,
        ),
    )
    expect_raises(
        "read_only_reviewer_write",
        PathPolicyError,
        lambda: validate_changed_paths(["README.md"], allowed=[], forbidden=["**"], read_only=True),
    )

    now = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    five_hour = classify_failure_texts(
        [
            (
                "five_hour_reset",
                "You have reached your five-hour usage limit. Resets in 2 hours 15 minutes",
            )
        ],
        now=now,
    )
    assert five_hour is not None
    assert five_hour.kind == PauseKind.FIVE_HOUR
    assert five_hour.resume_at == now + timedelta(hours=1)
    record_pass("five_hour_reset", "scheduled an hourly availability probe")

    classify(
        "weekly_limit",
        "Your weekly usage limit has been reached. Resets in 6 days",
        PauseKind.WEEKLY,
        now,
    )
    classify(
        "model_limit",
        "Your Sonnet model limit has been reached. Resets in 4 hours",
        PauseKind.MODEL_LIMIT,
        now,
    )
    classify(
        "transient_429",
        "Request failed with status code 429: too many requests",
        PauseKind.TRANSIENT_RATE_LIMIT,
        now,
    )
    classify(
        "service_capacity",
        "Service temporarily unavailable because capacity is overloaded",
        PauseKind.SERVICE_CAPACITY,
        now,
    )
    classify(
        "authentication_expiry",
        "HTTP 401 unauthorized: OAuth token expired; login required",
        PauseKind.AUTHENTICATION,
        now,
    )

    assert len(CONTROLS) >= 8
    print(json.dumps({"status": "pass", "controls": CONTROLS}, indent=2))


if __name__ == "__main__":
    main()
