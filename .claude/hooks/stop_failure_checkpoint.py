#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

payload = json.load(sys.stdin)
path = Path(os.environ.get("TCF_STOP_FAILURE_PATH", "factory/logs/stop-failures.jsonl"))
path.parent.mkdir(parents=True, exist_ok=True)
record = {
    "at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - WSL hook Python is 3.10
    "task_id": os.environ.get("TCF_TASK_ID"),
    "role": os.environ.get("TCF_ACTIVE_ROLE"),
    "session_name": os.environ.get("TCF_SESSION_NAME"),
    "event": payload.get("hook_event_name"),
    "error": payload.get("error") or payload.get("message"),
}
with path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
