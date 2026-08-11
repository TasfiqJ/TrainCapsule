"""Finite V3 controller supervision and startup preflight."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from .backends.base import BackendRouteState
from .backends.claude import ClaudeCredentialProvider
from .gitops import current_sha
from .util import read_json, run_command, sha256_file, write_json
from .v3.base import SHA_PATTERN, V3Model
from .v3.configuration import (
    AutonomyV3Config,
    FactoryV3Config,
    load_factory_v3,
    validate_v3_configuration,
)
from .v3.migrations import (
    load_installed_legacy_migration,
    verify_legacy_queue_archive_receipt,
)
from .v3.recovery import enforce_controller_restart_budget


class MigrationCompleteMarker(V3Model):
    version: Literal[3] = 3
    status: Literal["COMPLETE"] = "COMPLETE"
    completed_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: datetime


class SupervisorState(V3Model):
    version: Literal[3] = 3
    restart_attempts: int = Field(default=0, ge=0, le=3)
    last_started_at: datetime | None = None
    last_exit_at: datetime | None = None
    last_exit_code: int | None = None
    last_runtime_seconds: int | None = Field(default=None, ge=0)
    healthy_resets: int = Field(default=0, ge=0)
    last_decision: Literal["START", "RESTART", "HARD_STUCK", "STOPPED"] | None = None


class RestartDecision(V3Model):
    action: Literal["RESTART", "HARD_STUCK"]
    delay_seconds: int = Field(ge=0, le=300)
    restart_attempts: int = Field(ge=0, le=3)
    remaining_restarts: int = Field(ge=0, le=3)
    budget_reset: bool = False


class RuntimePaths(V3Model):
    state_root: Path
    migration_marker: Path
    supervisor_state: Path
    supervisor_lock: Path
    hard_stuck: Path
    stop: Path


def _factory_config(repo_root: Path) -> FactoryV3Config:
    return load_factory_v3(repo_root / "config" / "factory.yaml")


def runtime_paths(repo_root: Path, config: FactoryV3Config | None = None) -> RuntimePaths:
    factory = config or _factory_config(repo_root)
    raw_root = os.getenv(factory.runtime.local_state_root_environment_variable)
    if raw_root:
        state_root = Path(raw_root).expanduser()
        if not state_root.is_absolute():
            raise ValueError("configured runtime state root must be absolute")
        state_root = state_root.resolve()
    else:
        state_root = (repo_root / "factory" / "state").resolve()
    return RuntimePaths(
        state_root=state_root,
        migration_marker=state_root / factory.runtime.migration_complete_marker,
        supervisor_state=state_root / factory.runtime.supervisor_state_file,
        supervisor_lock=state_root / factory.runtime.supervisor_lock_file,
        hard_stuck=state_root / factory.runtime.hard_stuck_file,
        stop=state_root / factory.runtime.stop_file,
    )


def load_supervisor_state(path: Path) -> SupervisorState:
    if not path.exists():
        return SupervisorState()
    return SupervisorState.model_validate(read_json(path, {}))


def save_supervisor_state(path: Path, state: SupervisorState) -> None:
    write_json(path, state.model_dump(mode="json", by_alias=True))


def _verify_source_integrity(repo_root: Path) -> None:
    result = run_command(
        [sys.executable, str(repo_root / "scripts" / "gates" / "source_of_truth_integrity.py")],
        cwd=repo_root,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError("source-of-truth integrity preflight failed")


def _verify_migration_marker(
    repo_root: Path, config: FactoryV3Config, marker_path: Path
) -> MigrationCompleteMarker:
    if not marker_path.is_file():
        raise RuntimeError("V3 migration-complete marker is missing")
    marker = MigrationCompleteMarker.model_validate(read_json(marker_path, {}))
    manifest = repo_root / config.source_of_truth.manifest
    if sha256_file(manifest) != marker.source_manifest_sha256:
        raise RuntimeError("migration marker source-manifest digest is stale")
    head = current_sha(repo_root)
    ancestor = run_command(
        ["git", "merge-base", "--is-ancestor", marker.completed_sha, head],
        cwd=repo_root,
        check=False,
    )
    if ancestor.returncode != 0:
        raise RuntimeError("migration marker commit is not an ancestor of the current checkout")
    return marker


def run_startup_preflight(repo_root: Path) -> dict[str, object]:
    """Fail closed before a controller process can start."""

    repo_root = repo_root.resolve()
    loaded = validate_v3_configuration(repo_root)
    config = _factory_config(repo_root)
    paths = runtime_paths(repo_root, config)
    _verify_source_integrity(repo_root)
    legacy_migration = load_installed_legacy_migration(repo_root)
    verify_legacy_queue_archive_receipt(repo_root)
    marker = _verify_migration_marker(repo_root, config, paths.migration_marker)
    if paths.stop.exists():
        raise RuntimeError("durable STOP is present")
    if paths.hard_stuck.exists():
        raise RuntimeError("HARD_STUCK is present")
    running_dir = repo_root / "factory" / "queue" / "running"
    running_records = [
        path
        for path in running_dir.glob("*")
        if path.is_file() and not path.name.startswith(".")
    ]
    if running_records:
        raise RuntimeError("running queue records require explicit recovery before startup")
    corrupt = list((repo_root / "factory" / "state" / "pipelines").glob("*.corrupt-*"))
    if corrupt:
        raise RuntimeError("corrupt checkpoints require explicit recovery before startup")
    route = ClaudeCredentialProvider(require_long_lived_token=True).state()
    if route is not BackendRouteState.AUTHENTICATED:
        raise RuntimeError(f"credential preflight failed: {route.value}")
    return {
        "ready": True,
        "configVersion": 3,
        "validatedConfigs": sorted(loaded),
        "sourceIntegrity": "PASS",
        "legacyMigrationRecords": len(legacy_migration.records),
        "migrationCompletedSha": marker.completed_sha,
        "credentials": route.value,
        "runtimeState": "CLEAN",
    }


def record_controller_exit(
    *,
    repo_root: Path,
    runtime_seconds: int,
    exit_code: int,
    now: datetime | None = None,
) -> RestartDecision:
    """Persist one exit and return the only lawful finite restart decision."""

    if runtime_seconds < 0:
        raise ValueError("runtime_seconds cannot be negative")
    detected_at = now or datetime.now(UTC)
    config = _factory_config(repo_root)
    autonomy = validate_v3_configuration(repo_root)["autonomy"]
    if not isinstance(autonomy, AutonomyV3Config):
        raise RuntimeError("validated autonomy configuration has the wrong type")
    recovery = autonomy.recovery
    paths = runtime_paths(repo_root, config)
    state = load_supervisor_state(paths.supervisor_state)
    reset = runtime_seconds >= recovery.require_healthy_seconds_to_reset_restart_budget
    if reset:
        state.restart_attempts = 0
        state.healthy_resets += 1
    next_attempt = state.restart_attempts + 1
    state.last_exit_at = detected_at
    state.last_exit_code = exit_code
    state.last_runtime_seconds = runtime_seconds
    if next_attempt > recovery.max_controller_restarts:
        enforce_controller_restart_budget(
            incident_id=f"supervisor-{detected_at.strftime('%Y%m%dT%H%M%SZ')}",
            restart_count=next_attempt,
            max_controller_restarts=recovery.max_controller_restarts,
            detected_at=detected_at,
            hard_stuck_path=paths.hard_stuck,
            stop_path=paths.stop,
        )
        state.last_decision = "HARD_STUCK"
        save_supervisor_state(paths.supervisor_state, state)
        return RestartDecision(
            action="HARD_STUCK",
            delay_seconds=0,
            restart_attempts=state.restart_attempts,
            remaining_restarts=0,
            budget_reset=reset,
        )
    delay = recovery.restart_backoff_seconds[next_attempt - 1]
    state.restart_attempts = next_attempt
    state.last_decision = "RESTART"
    save_supervisor_state(paths.supervisor_state, state)
    return RestartDecision(
        action="RESTART",
        delay_seconds=delay,
        restart_attempts=next_attempt,
        remaining_restarts=recovery.max_controller_restarts - next_attempt,
        budget_reset=reset,
    )


def record_controller_start(repo_root: Path, now: datetime | None = None) -> SupervisorState:
    config = _factory_config(repo_root)
    paths = runtime_paths(repo_root, config)
    state = load_supervisor_state(paths.supervisor_state)
    state.last_started_at = now or datetime.now(UTC)
    state.last_decision = "START"
    save_supervisor_state(paths.supervisor_state, state)
    return state


def supervisor_status(repo_root: Path) -> dict[str, object]:
    config = _factory_config(repo_root)
    autonomy = validate_v3_configuration(repo_root)["autonomy"]
    if not isinstance(autonomy, AutonomyV3Config):
        raise RuntimeError("validated autonomy configuration has the wrong type")
    paths = runtime_paths(repo_root, config)
    state = load_supervisor_state(paths.supervisor_state)
    maximum = autonomy.recovery.max_controller_restarts
    return {
        "used": state.restart_attempts,
        "maximum": maximum,
        "remaining": maximum - state.restart_attempts,
        "backoffSeconds": autonomy.recovery.restart_backoff_seconds,
        "healthyResetSeconds": autonomy.recovery.require_healthy_seconds_to_reset_restart_budget,
        "hardStuck": paths.hard_stuck.exists(),
        "migrationComplete": paths.migration_marker.exists(),
        "state": state.model_dump(mode="json", by_alias=True),
    }


def create_migration_complete_marker(
    repo_root: Path, *, acknowledge: bool
) -> MigrationCompleteMarker:
    if not acknowledge:
        raise RuntimeError("explicit migration-complete acknowledgement is required")
    validate_v3_configuration(repo_root)
    _verify_source_integrity(repo_root)
    config = _factory_config(repo_root)
    paths = runtime_paths(repo_root, config)
    marker = MigrationCompleteMarker(
        completed_sha=current_sha(repo_root),
        source_manifest_sha256=sha256_file(repo_root / config.source_of_truth.manifest),
        completed_at=datetime.now(UTC),
    )
    write_json(paths.migration_marker, marker.model_dump(mode="json", by_alias=True))
    return marker


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TrainCapsule finite controller supervisor")
    parser.add_argument(
        "action", choices=["preflight", "start", "record-exit", "status", "mark-complete"]
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--runtime-seconds", type=int, default=0)
    parser.add_argument("--exit-code", type=int, default=1)
    parser.add_argument("--acknowledge", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = args.repo.expanduser().resolve()
    if args.action == "preflight":
        print(json.dumps(run_startup_preflight(repo_root), sort_keys=True))
    elif args.action == "start":
        state = record_controller_start(repo_root)
        print(json.dumps(state.model_dump(mode="json", by_alias=True), sort_keys=True))
    elif args.action == "record-exit":
        decision = record_controller_exit(
            repo_root=repo_root,
            runtime_seconds=args.runtime_seconds,
            exit_code=args.exit_code,
        )
        print(f"{decision.action} {decision.delay_seconds}")
    elif args.action == "status":
        print(json.dumps(supervisor_status(repo_root), sort_keys=True))
    else:
        marker = create_migration_complete_marker(repo_root, acknowledge=args.acknowledge)
        print(json.dumps(marker.model_dump(mode="json", by_alias=True), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
