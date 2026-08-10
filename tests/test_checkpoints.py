from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tcfactory.checkpoints import CheckpointStore, new_checkpoint
from tcfactory.models import PipelineState


def test_checkpoint_round_trip(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "pipelines")
    checkpoint = new_checkpoint(task_id="T001", run_id="run1", starting_sha="abc")
    checkpoint.state = PipelineState.PAUSED
    checkpoint.candidate_sha = "def"
    store.save(checkpoint)

    loaded = store.load("T001")
    assert loaded is not None
    assert loaded.state == PipelineState.PAUSED
    assert loaded.candidate_sha == "def"
    assert loaded.updated_at <= datetime.now(UTC)


def test_checkpoint_archive(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "pipelines")
    checkpoint = new_checkpoint(task_id="T001", run_id="run1", starting_sha="abc")
    store.save(checkpoint)
    archived = store.archive(checkpoint)
    assert archived.exists()
    assert store.load("T001") is None
