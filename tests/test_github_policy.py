from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tcfactory.github_sync import (
    GitHubConfig,
    GitHubSyncState,
    record_verified_task,
    should_push,
)
from tcfactory.models import RiskTier


def test_periodic_push_threshold() -> None:
    config = GitHubConfig(enabled=True, push_after_verified_tasks=3)
    state = GitHubSyncState(tasks_since_push=3)
    assert should_push(
        config=config,
        state=state,
        task=None,
        force=False,
        now=datetime.now(UTC),
    )


def test_interval_push() -> None:
    config = GitHubConfig(enabled=True, push_interval_seconds=60)
    state = GitHubSyncState(
        tasks_since_push=1,
        pending=True,
        last_push_at=datetime.now(UTC) - timedelta(seconds=61),
    )
    assert should_push(
        config=config,
        state=state,
        task=None,
        force=False,
        now=datetime.now(UTC),
    )


def test_record_verified_task_persists_risk(tmp_path: Path) -> None:
    from tcfactory.models import RoleName, SecurityPolicy, Stage, TaskPacket

    task = TaskPacket(
        task_id="T900",
        title="test",
        phase="test",
        goal="test",
        source_of_truth=["README.md"],
        acceptance_criteria=["works"],
        outputs=["x"],
        stop_conditions=["blocked"],
        security=SecurityPolicy(),
        pipeline=[Stage(role=RoleName.BUILDER, allowed_paths=["x"])],
        risk_tier=RiskTier.INTEGRATION,
    )
    state = record_verified_task(tmp_path / "state.json", task=task)
    assert state.tasks_since_push == 1
    assert state.last_task_risk == RiskTier.INTEGRATION
    assert state.pending
