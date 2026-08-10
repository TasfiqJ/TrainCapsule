from datetime import UTC, datetime, timedelta
from pathlib import Path

from tcfactory.observability import append_event, heartbeat_health, tail_events, write_heartbeat
from tcfactory.util import write_json


def test_event_log_and_heartbeat(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    heartbeat_path = tmp_path / "heartbeat.json"
    append_event(event_path, event="started", component="test", task_id="T001")
    write_heartbeat(heartbeat_path, component="test", status="running", task_id="T001")
    assert tail_events(event_path, limit=1)[0]["event"] == "started"
    assert heartbeat_health(heartbeat_path, stale_after_seconds=60)["status"] == "healthy"


def test_stale_heartbeat_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.json"
    write_json(
        path,
        {
            "at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            "component": "test",
            "status": "running",
        },
    )
    assert heartbeat_health(path, stale_after_seconds=10)["stale"] is True
