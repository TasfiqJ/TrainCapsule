from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .util import read_json, write_json


def _now() -> datetime:
    return datetime.now(UTC)


def append_event(
    path: Path,
    *,
    event: str,
    component: str,
    task_id: str | None = None,
    run_id: str | None = None,
    role: str | None = None,
    detail: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append one compact controller-owned event.

    Event records intentionally contain no prompt text, credentials, source contents, or private
    gate details. They are operational metadata for status, recovery, and audit commands.
    """

    payload: dict[str, Any] = {
        "at": _now().isoformat(),
        "event": event,
        "component": component,
        "pid": os.getpid(),
    }
    if task_id:
        payload["task_id"] = task_id
    if run_id:
        payload["run_id"] = run_id
    if role:
        payload["role"] = role
    if detail:
        payload["detail"] = detail[:2000]
    if data:
        payload["data"] = data
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def write_heartbeat(
    path: Path,
    *,
    component: str,
    status: str,
    task_id: str | None = None,
    run_id: str | None = None,
    role: str | None = None,
    detail: str | None = None,
    next_wake_at: datetime | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "at": _now().isoformat(),
        "component": component,
        "status": status,
        "pid": os.getpid(),
        "task_id": task_id,
        "run_id": run_id,
        "role": role,
        "detail": detail,
        "next_wake_at": next_wake_at.isoformat() if next_wake_at else None,
    }
    write_json(path, payload)
    return payload


def heartbeat_health(path: Path, *, stale_after_seconds: int = 300) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "missing", "path": str(path), "stale": True}
    payload = read_json(path, {})
    raw_at = cast(dict[str, object], payload).get("at") if isinstance(payload, dict) else None
    age_seconds: float | None = None
    if isinstance(raw_at, str):
        try:
            timestamp = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
            age_seconds = max(0.0, (_now() - timestamp.astimezone(UTC)).total_seconds())
        except ValueError:
            age_seconds = None
    stale = age_seconds is None or age_seconds > stale_after_seconds
    return {
        "status": "stale" if stale else "healthy",
        "path": str(path),
        "stale": stale,
        "age_seconds": age_seconds,
        "heartbeat": payload,
    }


def tail_events(path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    result: list[dict[str, Any]] = []
    for line in lines[-max(1, limit) :]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(cast(dict[str, Any], value))
    return result
