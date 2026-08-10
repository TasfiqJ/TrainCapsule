from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as date_parser

from .models import PauseKind, QuotaPauseRecord, StageResult

_LIMIT_MARKERS: tuple[tuple[PauseKind, re.Pattern[str]], ...] = (
    (
        PauseKind.FIVE_HOUR,
        re.compile(
            r"(?i)(?:(?:5[- ]hour|five[- ]hour|session).*?(?:limit|cap)|"
            r"(?:limit|cap).*?(?:5[- ]hour|five[- ]hour|session)).*?"
            r"(?:reached|exceeded|hit|resets?|available)"
        ),
    ),
    (
        PauseKind.WEEKLY,
        re.compile(
            r"(?i)(?:weekly|week).*?(?:limit|cap).*?"
            r"(?:reached|exceeded|hit|resets?|available)"
        ),
    ),
    (
        PauseKind.MODEL_LIMIT,
        re.compile(
            r"(?i)(?:opus|sonnet|fable|model).*?(?:limit|cap).*?"
            r"(?:reached|exceeded|hit|resets?|available)"
        ),
    ),
    (
        PauseKind.SERVICE_CAPACITY,
        re.compile(r"(?i)(?:overloaded|service unavailable|capacity|temporarily unavailable)"),
    ),
    (
        PauseKind.TRANSIENT_RATE_LIMIT,
        re.compile(r"(?i)(?:rate[_ -]?limit|too many requests|status(?: code)? 429|\b429\b)"),
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

_RESET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)resets?(?:\s+again)?(?:\s+at|\s+on|\s+in)?\s+"
        r"(?P<value>[^\n.;]+)"
    ),
    re.compile(r"(?i)available(?:\s+again)?(?:\s+at|\s+on|\s+in)\s+(?P<value>[^\n.;]+)"),
    re.compile(r"(?i)retry(?:\s+after|\s+at|\s+in)\s+(?P<value>[^\n.;]+)"),
)


_IANA_ZONE_PATTERN = re.compile(r"\((?P<zone>[A-Za-z_+-]+/[A-Za-z0-9_+./-]+)\)")

_DURATION_PATTERN = re.compile(
    r"(?i)(?:(?P<hours>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h))?\s*"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m))?"
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

    RateLimitEvent is authoritative when present. This text fallback exists for older CLI/SDK
    failure paths and intentionally excludes report findings to avoid treating a code example
    containing words such as "limit reached" as a real quota event.
    """
    texts: list[tuple[str, str]] = []
    if result.error:
        texts.append(("stage.error", result.error))
    if result.terminal_reason:
        texts.append(("stage.terminal_reason", result.terminal_reason))
    stderr_path = artifact_dir / "claude-stderr.log"
    if stderr_path.exists():
        texts.append(("claude-stderr.log", _safe_read(stderr_path)[-100_000:]))
    transcript_path = artifact_dir / "transcript.jsonl"
    if transcript_path.exists():
        transcript = _safe_read(transcript_path)[-100_000:]
        if "RateLimitEvent" in transcript or '"error"' in transcript:
            texts.append(("transcript.jsonl", transcript))
    return texts


def _parse_duration(value: str, *, now: datetime) -> datetime | None:
    match = _DURATION_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    if hours <= 0 and minutes <= 0:
        return None
    return now + timedelta(hours=hours, minutes=minutes)


def _parse_reset_value(value: str, *, now: datetime) -> datetime | None:
    cleaned = value.strip().strip("`'\"")
    if not cleaned:
        return None
    duration = _parse_duration(cleaned, now=now)
    if duration:
        return duration
    zone = None
    zone_match = _IANA_ZONE_PATTERN.search(cleaned)
    if zone_match:
        try:
            zone = ZoneInfo(zone_match.group("zone"))
        except ZoneInfoNotFoundError:
            zone = None
        cleaned = _IANA_ZONE_PATTERN.sub("", cleaned).strip()
    try:
        default = now.astimezone(zone).replace(tzinfo=None) if zone else now.replace(tzinfo=None)
        parsed = date_parser.parse(cleaned, fuzzy=True, default=default)
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone or now.tzinfo or UTC)
    parsed = parsed.astimezone(UTC)
    # A time-only expression may parse to earlier today. Move it to tomorrow.
    if parsed <= now - timedelta(minutes=2):
        parsed += timedelta(days=1)
    # Reject implausibly distant values caused by fuzzy parsing.
    if parsed > now + timedelta(days=8):
        return None
    return parsed


def _extract_reset_at(text: str, *, now: datetime) -> datetime | None:
    for pattern in _RESET_PATTERNS:
        for match in pattern.finditer(text):
            parsed = _parse_reset_value(match.group("value"), now=now)
            if parsed:
                return parsed
    return None


def _default_resume_at(
    kind: PauseKind,
    *,
    now: datetime,
    quota_fallback_wait_seconds: int,
    transient_retry_seconds: int,
) -> datetime:
    if kind == PauseKind.FIVE_HOUR:
        return now + timedelta(seconds=max(quota_fallback_wait_seconds, 5 * 3600 + 300))
    if kind in {PauseKind.WEEKLY, PauseKind.MODEL_LIMIT}:
        # The next retry reclassifies the message. A 24-hour probe interval avoids tight loops
        # if an exact weekly reset timestamp was absent from the SDK output.
        return now + timedelta(hours=24)
    if kind == PauseKind.SERVICE_CAPACITY:
        return now + timedelta(minutes=10)
    if kind == PauseKind.TRANSIENT_RATE_LIMIT:
        return now + timedelta(seconds=transient_retry_seconds)
    return now + timedelta(seconds=quota_fallback_wait_seconds)


def disposition_from_rate_limit_info(
    info: object,
    *,
    now: datetime | None = None,
    quota_fallback_wait_seconds: int = 19_800,
    transient_retry_seconds: int = 900,
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
        "overage": PauseKind.UNKNOWN_LIMIT,
    }
    kind = kind_by_type.get(rate_type, PauseKind.UNKNOWN_LIMIT)
    current = now or datetime.now(UTC)
    raw_reset = field("resets_at")
    reset_at: datetime | None = None
    if isinstance(raw_reset, (int, float)) and raw_reset > 0:
        try:
            reset_at = datetime.fromtimestamp(float(raw_reset), tz=UTC)
        except (OverflowError, OSError, ValueError):
            reset_at = None
    if reset_at is None or reset_at <= current:
        reset_at = _default_resume_at(
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
        resume_at=reset_at,
    )


def classify_failure_texts(
    texts: Iterable[tuple[str, str]],
    *,
    now: datetime | None = None,
    quota_fallback_wait_seconds: int = 19_800,
    transient_retry_seconds: int = 900,
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
            reset_at = _extract_reset_at(text, now=current) or _default_resume_at(
                kind,
                now=current,
                quota_fallback_wait_seconds=quota_fallback_wait_seconds,
                transient_retry_seconds=transient_retry_seconds,
            )
            return FailureDisposition(
                kind=kind,
                message=message,
                source=source,
                resume_at=reset_at,
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
