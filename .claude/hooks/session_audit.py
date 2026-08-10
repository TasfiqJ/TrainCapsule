#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

payload = json.load(sys.stdin)
path = Path(os.environ.get("TCF_SESSION_AUDIT_PATH", "factory/logs/session-events.jsonl"))
path.parent.mkdir(parents=True, exist_ok=True)
record = {
    "at": datetime.now(UTC).isoformat(),
    "task_id": os.environ.get("TCF_TASK_ID"),
    "role": os.environ.get("TCF_ACTIVE_ROLE"),
    "session_name": os.environ.get("TCF_SESSION_NAME"),
    "event": payload.get("hook_event_name"),
    "session_id": payload.get("session_id"),
}
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
