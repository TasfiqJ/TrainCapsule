from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .models import PipelineCheckpoint, PipelineState
from .util import read_json, write_json


class CheckpointError(RuntimeError):
    pass


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        return self.root / f"{task_id}.json"

    def load(self, task_id: str) -> PipelineCheckpoint | None:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        payload = read_json(path, None)
        if payload is None:
            return None
        return PipelineCheckpoint.model_validate(payload)

    def save(self, checkpoint: PipelineCheckpoint) -> Path:
        checkpoint.updated_at = datetime.now(UTC)
        path = self.path_for(checkpoint.task_id)
        temporary = path.with_suffix(".json.tmp")
        write_json(temporary, checkpoint.model_dump(mode="json"))
        os.replace(temporary, path)
        return path

    def archive(self, checkpoint: PipelineCheckpoint, *, suffix: str | None = None) -> Path:
        path = self.path_for(checkpoint.task_id)
        if not path.exists():
            raise CheckpointError(f"Checkpoint does not exist: {path}")
        archive_root = self.root / "archive"
        archive_root.mkdir(parents=True, exist_ok=True)
        label = suffix or checkpoint.run_id
        destination = archive_root / f"{checkpoint.task_id}-{label}.json"
        os.replace(path, destination)
        return destination

    def clear(self, task_id: str) -> None:
        self.path_for(task_id).unlink(missing_ok=True)

    def list_active(self) -> list[PipelineCheckpoint]:
        checkpoints: list[PipelineCheckpoint] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                checkpoints.append(PipelineCheckpoint.model_validate(read_json(path, {})))
            except Exception:  # noqa: BLE001
                continue
        return checkpoints


def new_checkpoint(
    *,
    task_id: str,
    run_id: str,
    starting_sha: str,
) -> PipelineCheckpoint:
    now = datetime.now(UTC)
    return PipelineCheckpoint(
        task_id=task_id,
        run_id=run_id,
        starting_sha=starting_sha,
        candidate_sha=starting_sha,
        state=PipelineState.NEW,
        started_at=now,
        updated_at=now,
    )


def checkpoint_result_payload(result: object) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        return dict(result.model_dump(mode="json"))  # type: ignore[union-attr]
    if isinstance(result, dict):
        return dict(cast(dict[str, Any], result))
    raise TypeError(f"Cannot serialize checkpoint result of type {type(result).__name__}")
