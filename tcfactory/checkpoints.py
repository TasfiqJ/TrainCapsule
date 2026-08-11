from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import Field

from .models import PipelineCheckpoint, PipelineState
from .util import atomic_write_text, read_json
from .v3.base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .v3.enums import Lane


class CheckpointError(RuntimeError):
    pass


class CheckpointBudget(V3Model):
    max_turns: int = Field(ge=1, le=200)
    max_wall_time_seconds: int = Field(ge=1, le=14_400)
    plan_attempts_remaining: int = Field(ge=0, le=5)
    repair_cycles_remaining: int = Field(ge=0, le=10)
    restarts_remaining: int = Field(ge=0, le=3)


class V3Checkpoint(V3Model):
    schema_version: int = Field(default=3, ge=3, le=3)
    generation: int = Field(ge=1)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    lane: Lane
    milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    backend_session_ref: str | None = None
    budget: CheckpointBudget
    context_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    source_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    approval_state: str
    circuit_breaker_reason: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime


def _envelope(payload: dict[str, Any], record_kind: str) -> dict[str, object]:
    canonical = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()
    return {
        "schemaVersion": 3,
        "recordKind": record_kind,
        "contentDigest": sha256_digest(canonical),
        "checkpoint": payload,
    }


def _validate_envelope(raw: object, *, expected_kind: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CheckpointError("checkpoint envelope is not an object")
    typed = cast(dict[str, Any], raw)
    if typed.get("schemaVersion") != 3:
        raise CheckpointError("checkpoint schema version is incompatible")
    if typed.get("recordKind") != expected_kind:
        raise CheckpointError("checkpoint record kind is incompatible")
    payload = typed.get("checkpoint")
    if not isinstance(payload, dict):
        raise CheckpointError("checkpoint payload is missing")
    typed_payload = cast(dict[str, Any], payload)
    expected = _envelope(typed_payload, expected_kind)["contentDigest"]
    if typed.get("contentDigest") != expected:
        raise CheckpointError("checkpoint content digest mismatch")
    return typed_payload


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
        try:
            raw: object = read_json(path, None)
            payload: object
            if isinstance(raw, dict) and cast(dict[str, Any], raw).get("schemaVersion") == 3:
                payload = _validate_envelope(
                    cast(dict[str, Any], raw), expected_kind="legacy-pipeline"
                )
            else:
                payload = cast(object, raw)
            return PipelineCheckpoint.model_validate(payload)
        except Exception as exc:
            quarantined = self._quarantine(path, "corrupt-or-incompatible")
            raise CheckpointError(
                f"active checkpoint is corrupt/incompatible and blocks recovery; "
                f"quarantined={quarantined}"
            ) from exc

    def save(self, checkpoint: PipelineCheckpoint) -> Path:
        checkpoint.updated_at = datetime.now(UTC)
        path = self.path_for(checkpoint.task_id)
        payload = checkpoint.model_dump(mode="json")
        rendered = (
            json.dumps(_envelope(payload, "legacy-pipeline"), indent=2, sort_keys=True)
            + "\n"
        )
        atomic_write_text(path, rendered, keep_previous=True)
        return path

    def _quarantine(self, path: Path, reason: str) -> Path:
        root = self.root / "quarantine"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = root / f"{path.stem}-{stamp}-{reason}.json"
        os.replace(path, destination)
        return destination

    def recover_previous(self, task_id: str) -> Path:
        path = self.path_for(task_id)
        previous = path.with_suffix(path.suffix + ".previous")
        if path.exists():
            raise CheckpointError("active checkpoint still exists; recovery must be explicit")
        if not previous.is_file():
            raise CheckpointError("no previous valid checkpoint generation exists")
        atomic_write_text(path, previous.read_text(encoding="utf-8"))
        raw: object = read_json(path, None)
        is_v3 = (
            isinstance(raw, dict)
            and cast(dict[str, Any], raw).get("recordKind") == "v3-work-item"
        )
        loaded = self.load_v3(task_id) if is_v3 else self.load(task_id)
        if loaded is None:
            raise CheckpointError("previous checkpoint recovery produced no active checkpoint")
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
            loaded = self.load(path.stem)
            if loaded is not None:
                checkpoints.append(loaded)
        task_ids = [checkpoint.task_id for checkpoint in checkpoints]
        if len(task_ids) != len(set(task_ids)):
            raise CheckpointError("duplicate active work checkpoints detected")
        return checkpoints

    def save_v3(self, checkpoint: V3Checkpoint) -> Path:
        checkpoint.updated_at = datetime.now(UTC)
        path = self.path_for(checkpoint.work_item_id)
        payload = checkpoint.model_dump(mode="json", by_alias=True)
        rendered = json.dumps(_envelope(payload, "v3-work-item"), indent=2, sort_keys=True) + "\n"
        atomic_write_text(path, rendered, keep_previous=True)
        return path

    def load_v3(
        self,
        work_item_id: str,
        *,
        observed_candidate_sha: str | None = None,
    ) -> V3Checkpoint | None:
        path = self.path_for(work_item_id)
        if not path.exists():
            return None
        try:
            payload = _validate_envelope(read_json(path, None), expected_kind="v3-work-item")
            checkpoint = V3Checkpoint.model_validate(payload)
            if observed_candidate_sha and checkpoint.candidate_sha != observed_candidate_sha:
                raise CheckpointError("checkpoint candidate SHA is stale")
            return checkpoint
        except Exception as exc:
            quarantined = self._quarantine(path, "corrupt-or-incompatible")
            raise CheckpointError(
                f"active V3 checkpoint blocks recovery; quarantined={quarantined}"
            ) from exc

    def list_active_v3(self) -> list[V3Checkpoint]:
        records: list[V3Checkpoint] = []
        for path in sorted(self.root.glob("V3-*.json")):
            loaded = self.load_v3(path.stem)
            if loaded is not None and loaded.active:
                records.append(loaded)
        identifiers = [record.work_item_id for record in records]
        if len(identifiers) != len(set(identifiers)):
            raise CheckpointError("duplicate active V3 work detected")
        return records


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
