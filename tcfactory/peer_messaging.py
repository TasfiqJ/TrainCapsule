from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .util import write_json

_MESSAGE_RE = re.compile(
    r"^RPMSG/1\s+task=(?P<task>[A-Z][A-Z0-9_-]{1,63})\s+"
    r"type=(?P<kind>[a-z_]+)\s+sha=(?P<sha>[0-9a-f]{7,64}|none)\s+"
    r"artifact=(?P<artifact>\S+)\s+summary=(?P<summary>.+)$"
)


class PeerMessageError(RuntimeError):
    pass


class PeerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: Literal["RPMSG/1"] = "RPMSG/1"
    task_id: str
    kind: Literal["finding", "blocker", "decision", "status", "challenge", "response"]
    candidate_sha: str | None = None
    artifact_path: str
    summary: str
    sender: str | None = None
    recipient: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PeerSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    run_id: str
    session_name: str
    role: str
    session_id: str | None = None
    status: Literal["starting", "running", "finished", "failed"] = "starting"
    candidate_sha: str
    artifact_dir: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


def format_peer_message(message: PeerMessage) -> str:
    sha = message.candidate_sha or "none"
    summary = " ".join(message.summary.split())
    if len(summary) > 500:
        summary = summary[:497] + "..."
    if any(char.isspace() for char in message.artifact_path):
        raise PeerMessageError("artifact_path may not contain whitespace")
    return (
        f"RPMSG/1 task={message.task_id} type={message.kind} sha={sha} "
        f"artifact={message.artifact_path} summary={summary}"
    )


def parse_peer_message(raw: str) -> PeerMessage:
    match = _MESSAGE_RE.fullmatch(raw.strip())
    if not match:
        raise PeerMessageError("Peer message does not match RPMSG/1")
    values = match.groupdict()
    return PeerMessage(
        task_id=values["task"],
        kind=values["kind"],  # type: ignore[arg-type]
        candidate_sha=None if values["sha"] == "none" else values["sha"],
        artifact_path=values["artifact"],
        summary=values["summary"],
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def register_peer_session(message_dir: Path, record: PeerSessionRecord) -> Path:
    path = message_dir / record.task_id / record.run_id / "sessions" / f"{record.session_name}.json"
    write_json(path, record.model_dump(mode="json"))
    _append_jsonl(
        message_dir / record.task_id / record.run_id / "events.jsonl",
        {"event": "session_registered", **record.model_dump(mode="json")},
    )
    return path


def update_peer_session(message_dir: Path, record: PeerSessionRecord) -> Path:
    return register_peer_session(message_dir, record)


def journal_peer_message(
    message_dir: Path, message: PeerMessage, *, delivered: bool | None = None
) -> None:
    payload = message.model_dump(mode="json")
    payload["wire"] = format_peer_message(message)
    payload["delivered"] = delivered
    _append_jsonl(message_dir / message.task_id / "messages.jsonl", payload)


def peer_status(message_dir: Path, task_id: str | None = None) -> dict[str, Any]:
    roots = (
        [message_dir / task_id]
        if task_id
        else sorted(path for path in message_dir.glob("*") if path.is_dir())
    )
    tasks: dict[str, Any] = {}
    for root in roots:
        if not root.exists():
            continue
        sessions: list[dict[str, Any]] = []
        for path in sorted(root.glob("*/sessions/*.json")):
            try:
                sessions.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        messages = 0
        msg_file = root / "messages.jsonl"
        if msg_file.is_file():
            messages = sum(
                1 for line in msg_file.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        tasks[root.name] = {"sessions": sessions, "message_count": messages}
    return {"tasks": tasks}
