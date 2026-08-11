import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from tcfactory import autopilot
from tcfactory.github_sync import GitHubSyncState, save_github_state
from tcfactory.models import AutonomyConfig, AutonomyState, FactoryConfig


def test_controller_restart_preserves_a_future_quota_wake() -> None:
    now = datetime.now(UTC)
    wake_at = now + timedelta(hours=1)
    state = AutonomyState(
        status="paused",
        current_action="waiting for included Claude allowance",
        next_wake_at=wake_at,
        updated_at=now,
    )

    preserved = autopilot._prepare_restart_state(  # pyright: ignore[reportPrivateUsage]
        state
    )

    assert preserved is True
    assert state.status == "paused"
    assert state.next_wake_at == wake_at
    assert "preserving scheduled wait" in (state.last_event or "")


def test_timed_wait_is_interrupted_by_dashboard_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    state = AutonomyState(
        status="paused",
        current_action="waiting for included Claude allowance",
        next_wake_at=now + timedelta(hours=1),
        updated_at=now,
        blocker_reason="stale controller repair",
        repair_status="attempt 4/5",
        repair_attempts=4,
        blocked_tasks=["FACTORY_REPAIR"],
        last_repair_artifact="factory/old-repair.json",
    )
    requested = state.model_copy(
        update={
            "status": "restarting",
            "next_wake_at": None,
            "blocker_reason": None,
            "repair_status": None,
            "repair_attempts": 0,
            "blocked_tasks": [],
            "last_repair_artifact": None,
        }
    )
    saved: list[AutonomyState] = []

    def load_requested(_root: Path, _factory: FactoryConfig) -> AutonomyState:
        return requested

    def capture_state(_root: Path, _factory: FactoryConfig, value: AutonomyState) -> None:
        saved.append(value)

    monkeypatch.setattr(autopilot, "load_state", load_requested)
    monkeypatch.setattr(autopilot, "save_state", capture_state)

    async def unexpected_sleep(_seconds: float) -> None:
        raise AssertionError("an explicit retry must not remain asleep")

    monkeypatch.setattr(autopilot.asyncio, "sleep", unexpected_sleep)
    result = asyncio.run(
        autopilot._wait_until(  # pyright: ignore[reportPrivateUsage]
            repo_root=tmp_path,
            factory=cast(FactoryConfig, object()),
            autonomy=cast(AutonomyConfig, SimpleNamespace(stop_file="STOP", pause_file="PAUSE")),
            state=state,
            wake_at=now + timedelta(hours=1),
        )
    )

    assert result == "retry"
    assert state.status == "restarting"
    assert state.next_wake_at is None
    assert state.current_action == "retry requested; restarting now"
    assert state.blocker_reason is None
    assert state.repair_status is None
    assert state.repair_attempts == 0
    assert state.blocked_tasks == []
    assert state.last_repair_artifact is None
    assert saved


def test_begin_ready_task_clears_stale_repair_ui_state() -> None:
    state = AutonomyState(
        status="restarting",
        current_action="retry requested",
        blocker_reason="old protected-path blocker",
        required_action="repair controller",
        blocked_tasks=["FACTORY_REPAIR"],
        repair_attempts=5,
        repair_status="attempt 5/5",
        last_repair_artifact="factory/repair.json",
        consecutive_failures=12,
        updated_at=datetime.now(UTC),
    )

    autopilot._begin_ready_task(  # pyright: ignore[reportPrivateUsage]
        state, task_id="T002", has_packet=False
    )

    assert state.status == "running"
    assert state.active_task_id == "T002"
    assert state.current_action == "create task packet"
    assert state.blocker_reason is None
    assert state.required_action is None
    assert state.blocked_tasks == []
    assert state.repair_attempts == 0
    assert state.repair_status is None
    assert state.last_repair_artifact is None
    assert state.consecutive_failures == 0


def test_timed_wait_refreshes_visible_state_while_sleeping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    wake_at = now + timedelta(seconds=1)
    state = AutonomyState(
        status="paused",
        current_action="waiting for included Claude allowance",
        next_wake_at=wake_at,
        updated_at=now,
    )
    clock = iter([now, wake_at + timedelta(seconds=1)])
    saved: list[AutonomyState] = []
    monkeypatch.setattr(autopilot, "_now", lambda: next(clock))

    def load_waiting(_root: Path, _factory: FactoryConfig) -> AutonomyState:
        return state.model_copy()

    def capture_state(_root: Path, _factory: FactoryConfig, value: AutonomyState) -> None:
        saved.append(value)

    monkeypatch.setattr(autopilot, "load_state", load_waiting)
    monkeypatch.setattr(autopilot, "save_state", capture_state)

    async def complete_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(autopilot.asyncio, "sleep", complete_sleep)
    result = asyncio.run(
        autopilot._wait_until(  # pyright: ignore[reportPrivateUsage]
            repo_root=tmp_path,
            factory=cast(FactoryConfig, object()),
            autonomy=cast(AutonomyConfig, SimpleNamespace(stop_file="STOP", pause_file="PAUSE")),
            state=state,
            wake_at=wake_at,
            poll_seconds=1,
        )
    )

    assert result == "elapsed"
    assert saved
    assert saved[0].next_wake_at == wake_at


def test_completion_marker_is_not_final_while_main_ci_is_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = FactoryConfig()
    sha = "a" * 40

    def fake_current_sha(_repo_root: Path, _ref: str = "HEAD") -> str:
        return sha

    monkeypatch.setattr(autopilot, "current_sha", fake_current_sha)
    marker = tmp_path / "factory/state/PRODUCT_BUILD_COMPLETE.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        f'{{"main_sha": "{sha}", "audited_sha": "{sha}"}}\n', encoding="utf-8"
    )
    github_state = factory.resolve(tmp_path, factory.github_state_path)
    save_github_state(
        github_state,
        GitHubSyncState(pending=True, last_pushed_sha=sha),
    )

    assert (
        autopilot._completion_marker_is_final(  # pyright: ignore[reportPrivateUsage]
            tmp_path, factory
        )
        is False
    )

    save_github_state(
        github_state,
        GitHubSyncState(pending=False, last_pushed_sha=sha),
    )
    assert autopilot._completion_marker_is_final(  # pyright: ignore[reportPrivateUsage]
        tmp_path, factory
    )

    save_github_state(
        github_state,
        GitHubSyncState(pending=False, last_pushed_sha="b" * 40),
    )
    assert (
        autopilot._completion_marker_is_final(  # pyright: ignore[reportPrivateUsage]
            tmp_path, factory
        )
        is False
    )


def test_completion_marker_rejects_a_different_audited_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = FactoryConfig()
    sha = "a" * 40
    def fixed_sha(_repo_root: Path, _ref: str = "HEAD") -> str:
        return sha

    monkeypatch.setattr(autopilot, "current_sha", fixed_sha)
    marker = tmp_path / "factory/state/PRODUCT_BUILD_COMPLETE.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        f'{{"main_sha": "{sha}", "audited_sha": "{"b" * 40}"}}\n',
        encoding="utf-8",
    )
    save_github_state(
        factory.resolve(tmp_path, factory.github_state_path),
        GitHubSyncState(pending=False, last_pushed_sha=sha),
    )

    assert not autopilot._completion_marker_is_final(  # pyright: ignore[reportPrivateUsage]
        tmp_path, factory
    )
