from __future__ import annotations

from pathlib import Path

import pytest

from tcfactory.checkpoints import CheckpointStore, new_checkpoint
from tcfactory.config import load_factory_config, load_task
from tcfactory.models import PipelineState
from tcfactory.pipeline import (
    PipelineBlocked,
    _load_checkpoint,  # pyright: ignore[reportPrivateUsage]
)

ROOT = Path(__file__).resolve().parents[1]


def _paused_checkpoint(repo: Path, *, candidate_sha: str = "old-main") -> CheckpointStore:
    config = load_factory_config(ROOT / "config/factory.yaml")
    store = CheckpointStore(config.resolve(repo, config.pipeline_state_dir))
    checkpoint = new_checkpoint(
        task_id="T002",
        run_id="paused-run",
        starting_sha="old-main",
    )
    checkpoint.state = PipelineState.PAUSED
    checkpoint.candidate_sha = candidate_sha
    store.save(checkpoint)
    return store


def test_empty_quota_paused_checkpoint_restarts_from_verified_new_main(
    tmp_path: Path,
) -> None:
    config = load_factory_config(ROOT / "config/factory.yaml")
    task = load_task(ROOT / "tasks/T002.yaml")
    store = _paused_checkpoint(tmp_path)

    _, checkpoint = _load_checkpoint(
        repo_root=tmp_path,
        config=config,
        task=task,
        starting_sha="verified-new-main",
        resume=True,
    )

    assert checkpoint.starting_sha == "verified-new-main"
    assert checkpoint.candidate_sha == "verified-new-main"
    assert checkpoint.state == PipelineState.NEW
    assert not checkpoint.results
    assert list((store.root / "archive").glob("T002-stale-base-*.json"))


def test_empty_interrupted_running_checkpoint_restarts_from_verified_new_main(
    tmp_path: Path,
) -> None:
    config = load_factory_config(ROOT / "config/factory.yaml")
    task = load_task(ROOT / "tasks/T002.yaml")
    store = _paused_checkpoint(tmp_path)
    interrupted = store.load("T002")
    assert interrupted is not None
    interrupted.state = PipelineState.RUNNING
    store.save(interrupted)

    _, checkpoint = _load_checkpoint(
        repo_root=tmp_path,
        config=config,
        task=task,
        starting_sha="verified-new-main",
        resume=True,
    )

    assert checkpoint.starting_sha == "verified-new-main"
    assert checkpoint.candidate_sha == "verified-new-main"
    assert checkpoint.state == PipelineState.NEW
    assert not checkpoint.results
    assert list((store.root / "archive").glob("T002-stale-base-*.json"))


def test_paused_checkpoint_with_candidate_work_still_requires_explicit_reconciliation(
    tmp_path: Path,
) -> None:
    config = load_factory_config(ROOT / "config/factory.yaml")
    task = load_task(ROOT / "tasks/T002.yaml")
    _paused_checkpoint(tmp_path, candidate_sha="partial-candidate")

    with pytest.raises(PipelineBlocked, match="Reconcile the previous candidate explicitly"):
        _load_checkpoint(
            repo_root=tmp_path,
            config=config,
            task=task,
            starting_sha="verified-new-main",
            resume=True,
        )
