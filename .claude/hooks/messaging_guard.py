#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import NoReturn, cast


def deny(reason: str) -> NoReturn:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    raise SystemExit(0)


def object_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        deny(f"{label} must be an object")
    return cast(dict[str, object], value)


def allowed_peers() -> set[str]:
    value: object = json.loads(os.environ.get("TCF_ALLOWED_PEERS_JSON", "[]"))
    if not isinstance(value, list):
        deny("TCF_ALLOWED_PEERS_JSON must contain a JSON string array")
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        deny("TCF_ALLOWED_PEERS_JSON must contain a JSON string array")
    return set(cast(list[str], items))


def main() -> None:
    payload = object_dict(json.load(sys.stdin), "Hook payload")
    tool = str(payload.get("tool_name", ""))
    if tool not in {"ListAgents", "SendMessage"}:
        return
    if os.environ.get("TCF_PEER_MESSAGING") != "1":
        deny("Cross-session messaging is not enabled for this bounded role")
    if tool == "ListAgents":
        return

    tool_input = object_dict(payload.get("tool_input") or {}, "Tool input")
    message = str(tool_input.get("message") or tool_input.get("content") or "")
    recipient = str(
        tool_input.get("recipient")
        or tool_input.get("agent")
        or tool_input.get("name")
        or tool_input.get("target")
        or ""
    )
    allowed = allowed_peers()
    if not recipient or recipient not in allowed:
        deny(f"Message recipient {recipient!r} is outside this task's peer allowlist")
    max_chars = int(os.environ.get("TCF_MAX_MESSAGE_CHARS", "1200"))
    if len(message) > max_chars:
        deny(f"Cross-session message exceeds {max_chars} characters")
    if re.search(r"(?:change|disable|bypass).*(?:permission|sandbox|config|hook)", message, re.I):
        deny(
            "Cross-session messages may not request permission, sandbox, hook, or "
            "configuration changes"
        )

    audit_path = Path(os.environ.get("TCF_MESSAGE_AUDIT_PATH", "factory/messages/audit.jsonl"))
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if audit_path.exists():
        count = sum(1 for _ in audit_path.open("r", encoding="utf-8"))
    maximum = int(os.environ.get("TCF_MAX_MESSAGES", "4"))
    if count >= maximum:
        deny(f"Cross-session message limit of {maximum} reached")
    record = {
        "task_id": os.environ.get("TCF_TASK_ID"),
        "role": os.environ.get("TCF_ACTIVE_ROLE"),
        "sender": os.environ.get("TCF_SESSION_NAME"),
        "recipient": recipient,
        "message_chars": len(message),
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
