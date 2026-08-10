from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from .models import PauseKind, QuotaPauseRecord, StageResult

_LIMIT_MARKERS: tuple[tuple[PauseKind, re.Pattern[str]], ...] = (
    (
        PauseKind.FIVE_HOUR,
        re.compile(
            r"(?i)(?=[^\n]{0,300}(?:5[- ]hour|five[- ]hour|session))"
            r"(?=[^\n]{0,300}(?:limit|cap))"
            r"(?=[^\n]{0,300}(?:reached|exceeded|hit))[^\n]{1,300}"
        ),
    ),
    (
        PauseKind.WEEKLY,
        re.compile(
            r"(?i)(?=[^\n]{0,300}(?:weekly|week))"
            r"(?=[^\n]{0,300}(?:limit|cap))"
            r"(?=[^\n]{0,300}(?:reached|exceeded|hit))[^\n]{1,300}"
        ),
    ),
    (
        PauseKind.MODEL_LIMIT,
        re.compile(
            r"(?i)(?=[^\n]{0,300}(?:opus|sonnet|fable|model))"
            r"(?=[^\n]{0,300}(?:limit|cap))"
            r"(?=[^\n]{0,300}(?:reached|exceeded|hit))[^\n]{1,300}"
        ),
    ),
    (
        PauseKind.SERVICE_CAPACITY,
        re.compile(r"(?i)(?:overloaded|service unavailable|capacity|temporarily unavailable)"),
    ),
    (
        PauseKind.TRANSIENT_RATE_LIMIT,
        re.compile(
            r"(?i)(?:(?:rate[_ -]?limit).*?(?:reached|exceeded|hit)|"
            r"too many requests|status(?: code)? 429|\b429\b)"
        ),
    ),
    (
        PauseKind.AUTHENTICATION,
        re.compile(
            r"(?i)(?:not authenticated|authentication failed|login required|token expired|"
            r"invalid oauth|please log in|unauthorized|status(?: code)? 401|\b401\b)"
        ),
    ),
    (
        PauseKind.UNKNOWN_LIMIT,
        re.compile(
            r"(?i)(?:(?:usage|plan|session).*?(?:limit|cap).*?"
            r"(?:reached|exceeded|hit|resets?|available)|"
            r"(?:you(?:'ve|’ve| have)?|account).*?(?:hit|reached|exceeded).*?(?:limit|cap))"
        ),
    ),
)

@dataclass(frozen=True)
class FailureDisposition:
    kind: PauseKind
    message: str
    source: str
    resume_at: datetime

    def as_record(self, *, now: datetime | None = None) -> QuotaPauseRecord:
        detected = now or datetime.now(UTC)
        return QuotaPauseRecord(
            kind=self.kind,
            detected_at=detected,
            resume_at=self.resume_at,
            message=self.message,
            source=self.source,
        )


class QuotaLimitPause(RuntimeError):
    def __init__(self, record: QuotaPauseRecord, stage_result: StageResult | None = None) -> None:
        self.record = record
        self.stage_result = stage_result
        super().__init__(
            f"Claude usage paused ({record.kind.value}) until {record.resume_at.isoformat()}: "
            f"{record.message}"
        )


class AuthenticationPause(RuntimeError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def stage_failure_texts(result: StageResult, artifact_dir: Path) -> list[tuple[str, str]]:
    """Collect system-level failure evidence, not arbitrary model-authored prose.

    RateLimitEvent is handled authoritatively by the runners before this fallback is called.
    Never scan the transcript here: it contains allowed RateLimitEvent metadata and arbitrary
    model-authored prose, neither of which proves that Claude rejected the request.
    """
    texts: list[tuple[str, str]] = []
    if result.error:
        texts.append(("stage.error", result.error))
    if result.terminal_reason:
        texts.append(("stage.terminal_reason", result.terminal_reason))
    stderr_path = artifact_dir / "claude-stderr.log"
    if stderr_path.exists():
        texts.append(("claude-stderr.log", _safe_read(stderr_path)[-100_000:]))
    return texts


def _default_resume_at(
    kind: PauseKind,
    *,
    now: datetime,
    quota_fallback_wait_seconds: int,
    transient_retry_seconds: int,
) -> datetime:
    if kind in {
        PauseKind.FIVE_HOUR,
        PauseKind.WEEKLY,
        PauseKind.MODEL_LIMIT,
        PauseKind.UNKNOWN_LIMIT,
    }:
        # Do not guess when a subscription window resets. Probe once per configured interval;
        # a real rejection will create another durable pause, while an allowed request resumes.
        return now + timedelta(seconds=quota_fallback_wait_seconds)
    if kind == PauseKind.SERVICE_CAPACITY:
        return now + timedelta(minutes=10)
    if kind == PauseKind.TRANSIENT_RATE_LIMIT:
        return now + timedelta(seconds=transient_retry_seconds)
    return now + timedelta(seconds=quota_fallback_wait_seconds)


def disposition_from_rate_limit_info(
    info: object,
    *,
    now: datetime | None = None,
    quota_fallback_wait_seconds: int = 3_600,
    transient_retry_seconds: int = 3_600,
) -> FailureDisposition | None:
    """Convert an Agent SDK RateLimitInfo object/dict into a durable pause.

    Current Claude Agent SDK versions emit ``RateLimitEvent`` messages with a
    machine-readable status, limit type, and Unix reset timestamp. Duck typing keeps
    this helper testable without importing the SDK during local controller tests.
    """

    def field(name: str) -> object | None:
        if isinstance(info, dict):
            return cast(dict[str, object], info).get(name)
        return getattr(info, name, None)

    status = str(field("status") or "")
    rate_type = str(field("rate_limit_type") or "")
    overage_status = str(field("overage_status") or "")
    paid_overage_active = overage_status in {"allowed", "allowed_warning"} or (
        rate_type == "overage" and status in {"allowed", "allowed_warning"}
    )
    if paid_overage_active:
        current = now or datetime.now(UTC)
        return FailureDisposition(
            kind=PauseKind.AUTHENTICATION,
            message=(
                "Paid overage/usage credits appear enabled in the Agent SDK rate-limit "
                "state. Disable usage credits in Claude Settings -> Usage; the factory "
                "will not continue on paid overage."
            ),
            source="RateLimitEvent",
            resume_at=current,
        )
    if status != "rejected":
        return None
    kind_by_type = {
        "five_hour": PauseKind.FIVE_HOUR,
        "seven_day": PauseKind.WEEKLY,
        "seven_day_opus": PauseKind.MODEL_LIMIT,
        "seven_day_sonnet": PauseKind.MODEL_LIMIT,
        "seven_day_fable": PauseKind.MODEL_LIMIT,
        "overage": PauseKind.UNKNOWN_LIMIT,
    }
    kind = kind_by_type.get(rate_type)
    if kind is None and (
        rate_type.startswith("seven_day_")
        or any(model in rate_type for model in ("fable", "opus", "sonnet"))
    ):
        kind = PauseKind.MODEL_LIMIT
    if kind is None:
        kind = PauseKind.UNKNOWN_LIMIT
    current = now or datetime.now(UTC)
    resume_at = _default_resume_at(
        kind,
        now=current,
        quota_fallback_wait_seconds=quota_fallback_wait_seconds,
        transient_retry_seconds=transient_retry_seconds,
    )
    utilization = field("utilization")
    message = f"Agent SDK rate limit rejected: type={rate_type or 'unknown'}"
    if utilization is not None:
        message += f", utilization={utilization}"
    return FailureDisposition(
        kind=kind,
        message=message,
        source="RateLimitEvent",
        resume_at=resume_at,
    )


def classify_failure_texts(
    texts: Iterable[tuple[str, str]],
    *,
    now: datetime | None = None,
    quota_fallback_wait_seconds: int = 3_600,
    transient_retry_seconds: int = 3_600,
) -> FailureDisposition | None:
    current = now or datetime.now(UTC)
    for source, text in texts:
        if not text:
            continue
        for kind, marker in _LIMIT_MARKERS:
            match = marker.search(text)
            if not match:
                continue
            message = text[max(0, match.start() - 200) : min(len(text), match.end() + 500)].strip()
            if kind == PauseKind.AUTHENTICATION:
                return FailureDisposition(
                    kind=kind,
                    message=message,
                    source=source,
                    resume_at=current,
                )
            resume_at = _default_resume_at(
                kind,
                now=current,
                quota_fallback_wait_seconds=quota_fallback_wait_seconds,
                transient_retry_seconds=transient_retry_seconds,
            )
            return FailureDisposition(
                kind=kind,
                message=message,
                source=source,
                resume_at=resume_at,
            )
    return None


def classify_stage_failure(
    result: StageResult,
    artifact_dir: Path,
    *,
    quota_fallback_wait_seconds: int,
    transient_retry_seconds: int,
    now: datetime | None = None,
) -> FailureDisposition | None:
    return classify_failure_texts(
        stage_failure_texts(result, artifact_dir),
        now=now,
        quota_fallback_wait_seconds=quota_fallback_wait_seconds,
        transient_retry_seconds=transient_retry_seconds,
    )
