from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from tcfactory.models import FactoryConfig, PauseKind, QueuePauseMetadata
from tcfactory.queue import promote_due_paused
from tcfactory.util import write_json


def test_due_paused_task_returns_to_pending(tmp_path: Path) -> None:
    config = FactoryConfig(queue_dir="queue")
    paused = tmp_path / "queue" / "paused"
    paused.mkdir(parents=True)
    task = paused / "T001.yaml"
    task.write_text(yaml.safe_dump({"task_id": "T001"}), encoding="utf-8")
    write_json(
        task.with_suffix(".pause.json"),
        QueuePauseMetadata(
            task_id="T001",
            kind=PauseKind.FIVE_HOUR,
            resume_at=datetime.now(UTC) - timedelta(seconds=1),
            message="reset",
        ).model_dump(mode="json"),
    )
    assert promote_due_paused(tmp_path, config) == 1
    assert (tmp_path / "queue" / "pending" / "T001.yaml").exists()
