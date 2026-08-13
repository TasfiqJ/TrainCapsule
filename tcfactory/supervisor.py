"""Finite V3 controller supervision and startup preflight."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from .backends.claude import ClaudeCredentialProvider
from .github_sync import (
    load_github_config,
    reconcile_publications,
    validate_controller_activation,
    validate_publication_installation,
    validate_repository_release_controls,
)
from .gitops import current_sha
from .util import read_json, resolve_within, sha256_file, write_json
from .v3.base import SHA_PATTERN, V3Model, sha256_digest
from .v3.configuration import (
    AutonomyV3Config,
    FactoryV3Config,
    load_factory_v3,
    validate_v3_configuration,
)
from .v3.enums import MilestoneStatus, WorkStatus
from .v3.migrations import (
    load_installed_legacy_migration,
    verify_legacy_queue_archive_receipt,
)
from .v3.milestones import MilestoneRoadmap
from .v3.private_gate import (
    validate_private_gate_installation,
    validate_private_gate_runtime_health,
)
from .v3.queue import V3Queue
from .v3.recovery import enforce_controller_restart_budget
from .v3.runtime_paths import V3RuntimePaths, resolve_v3_runtime_paths
from .v3.source_authority import validate_active_source_generation
from .v3.work_items import WorkItemCollection
from .yamlutil import load_yaml


class MigrationCompleteMarker(V3Model):
    version: Literal[3] = 3
    status: Literal["COMPLETE"] = "COMPLETE"
    completed_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_generation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    milestone: Literal["M0_FACTORY_MIGRATED"] = "M0_FACTORY_MIGRATED"
    acceptance_work_items: dict[str, str]
    acceptance_evidence_digests: dict[str, str]
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
    """Supervisor view of the shared V3 runtime paths (legacy constructor compatible)."""

    state_root: Path
    migration_marker: Path
    supervisor_state: Path
    supervisor_lock: Path
    hard_stuck: Path
    stop: Path

    @property
    def queue(self) -> Path:
        return self.state_root / "v3-queue"

    @property
    def checkpoints(self) -> Path:
        return self.state_root / "pipelines"


def _factory_config(repo_root: Path) -> FactoryV3Config:
    return load_factory_v3(repo_root / "config" / "factory.yaml")


def runtime_paths(repo_root: Path, config: FactoryV3Config | None = None) -> RuntimePaths:
    """Compatibility export for callers migrated to the shared V3 resolver."""

    paths: V3RuntimePaths = resolve_v3_runtime_paths(repo_root, config)
    return RuntimePaths(
        state_root=paths.state_root,
        migration_marker=paths.migration_marker,
        supervisor_state=paths.supervisor_state,
        supervisor_lock=paths.supervisor_lock,
        hard_stuck=paths.hard_stuck,
        stop=paths.stop,
    )


def load_supervisor_state(path: Path) -> SupervisorState:
    if not path.exists():
        return SupervisorState()
    return SupervisorState.model_validate(read_json(path, {}))


def save_supervisor_state(path: Path, state: SupervisorState) -> None:
    write_json(path, state.model_dump(mode="json", by_alias=True))


def _verify_source_integrity(repo_root: Path) -> None:
    validate_active_source_generation(repo_root)


def _verify_migration_marker(
    repo_root: Path, config: FactoryV3Config, marker_path: Path
) -> MigrationCompleteMarker:
    if not marker_path.is_file():
        raise RuntimeError("V3 migration-complete marker is missing")
    marker = MigrationCompleteMarker.model_validate(read_json(marker_path, {}))
    active_source = validate_active_source_generation(repo_root)
    manifest = repo_root / active_source.manifest_path
    if sha256_file(manifest) != marker.source_manifest_sha256:
        raise RuntimeError("migration marker source-manifest digest is stale")
    if active_source.config_digest != marker.active_generation_sha256:
        raise RuntimeError("migration marker active-generation digest is stale")
    head = current_sha(repo_root)
    if marker.completed_sha != head:
        raise RuntimeError("migration marker must match the exact current checkout SHA")
    roadmap = WorkItemCollection.model_validate(load_yaml(repo_root / config.roadmap.work_items))
    milestones = MilestoneRoadmap.model_validate(load_yaml(repo_root / config.roadmap.milestones))
    if milestones.milestone("M0_FACTORY_MIGRATED").status is not MilestoneStatus.COMPLETED:
        raise RuntimeError("migration marker requires completed M0 milestone")
    required = {f"V3-MIG-{number:03d}" for number in range(16, 21)}
    if set(marker.acceptance_work_items) != required:
        raise RuntimeError("migration marker acceptance work-item set is incomplete")
    for identifier in required:
        item = roadmap.item(identifier)
        if item.status is not WorkStatus.COMPLETED or not item.evidence_required:
            raise RuntimeError(f"migration acceptance item is incomplete: {identifier}")
        if marker.acceptance_work_items[identifier] != WorkStatus.COMPLETED.value:
            raise RuntimeError(f"migration marker status is stale: {identifier}")
        if identifier not in marker.acceptance_evidence_digests:
            raise RuntimeError(f"migration marker evidence digest is missing: {identifier}")
        referenced = [
            resolve_within(repo_root, reference, require_exists=True)
            for reference in item.evidence_required
        ]
        actual_digest = sha256_digest(
            b"\n".join(
                f"{path.relative_to(repo_root).as_posix()}:{sha256_file(path)}".encode()
                for path in sorted(referenced)
            )
        )
        if marker.acceptance_evidence_digests[identifier] != actual_digest:
            raise RuntimeError(f"migration marker evidence is stale: {identifier}")
    return marker


def run_startup_preflight(
    repo_root: Path, *, allow_stop_for_activation: bool = False
) -> dict[str, object]:
    """Fail closed before a controller process can start."""

    repo_root = repo_root.resolve()
    loaded = validate_v3_configuration(repo_root)
    config = _factory_config(repo_root)
    paths = runtime_paths(repo_root, config)
    _verify_source_integrity(repo_root)
    legacy_migration = load_installed_legacy_migration(repo_root)
    # Production executes from an immutable clean snapshot, where ignored legacy
    # queue copies are intentionally absent.  The tracked canonical archive
    # receipt remains authoritative and still revalidates live copies whenever
    # they are present.
    verify_legacy_queue_archive_receipt(repo_root, require_live=False)
    if paths.stop.exists() and not allow_stop_for_activation:
        raise RuntimeError("durable STOP is present")
    if paths.hard_stuck.exists():
        raise RuntimeError("HARD_STUCK is present")
    validate_private_gate_installation(repo_root)
    private_gate_health = validate_private_gate_runtime_health(repo_root, paths.state_root)
    github = load_github_config(repo_root / "config/github.yaml")
    validate_publication_installation(github)
    activation_digest = validate_controller_activation(repo_root=repo_root, config=github)
    if not allow_stop_for_activation:
        from .v3.activation import validate_activation_control_state

        validate_activation_control_state(
            paths=resolve_v3_runtime_paths(repo_root, config),
            exact_main_sha=current_sha(repo_root),
            activation_receipt_digest=activation_digest,
        )
    release_controls = validate_repository_release_controls(repo_root=repo_root, config=github)
    recovered = reconcile_publications(repo_root=repo_root, state_root=paths.state_root)
    publication_recovery: dict[str, object] = {
        "status": "RECONCILED",
        "transactions": len(recovered),
        "phases": [item.phase.value for item in recovered],
        "repositoryControls": release_controls,
        "activationReceiptDigest": activation_digest,
    }
    marker = _verify_migration_marker(repo_root, config, paths.migration_marker)
    queue = V3Queue(paths.queue)
    queue.initialize()
    pending_claim_recovery = len(queue.items(WorkStatus.RUNNING))
    corrupt = list(paths.checkpoints.glob("*.corrupt-*"))
    if corrupt:
        raise RuntimeError("corrupt checkpoints require explicit recovery before startup")
    route = ClaudeCredentialProvider(require_long_lived_token=True).state()
    return {
        "ready": True,
        "configVersion": 3,
        "validatedConfigs": sorted(loaded),
        "sourceIntegrity": "PASS",
        "legacyMigrationRecords": len(legacy_migration.records),
        "migrationCompletedSha": marker.completed_sha,
        "credentialRoute": route.value,
        "credentials": route.value,
        "runtimeState": "RECOVERY_PENDING" if pending_claim_recovery else "CLEAN",
        "pendingClaimRecovery": pending_claim_recovery,
        "publicationRecovery": publication_recovery,
        "privateGateHealth": private_gate_health.model_dump(mode="json", by_alias=True),
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
    run_startup_preflight(repo_root)
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
    migration_status = "MISSING"
    if paths.migration_marker.exists():
        try:
            _verify_migration_marker(repo_root, config, paths.migration_marker)
        except (RuntimeError, ValueError):
            migration_status = "STALE_OR_INVALID"
        else:
            migration_status = "VALID"
    return {
        "used": state.restart_attempts,
        "maximum": maximum,
        "remaining": maximum - state.restart_attempts,
        "backoffSeconds": autonomy.recovery.restart_backoff_seconds,
        "healthyResetSeconds": autonomy.recovery.require_healthy_seconds_to_reset_restart_budget,
        "hardStuck": paths.hard_stuck.exists(),
        "migrationComplete": migration_status == "VALID",
        "migrationMarkerStatus": migration_status,
        "state": state.model_dump(mode="json", by_alias=True),
    }


def create_migration_complete_marker(
    repo_root: Path, *, acknowledge: bool = False
) -> MigrationCompleteMarker:
    del acknowledge  # Retained only as a compatibility flag; V3 is zero-human.
    validate_v3_configuration(repo_root)
    _verify_source_integrity(repo_root)
    config = _factory_config(repo_root)
    paths = runtime_paths(repo_root, config)
    roadmap = WorkItemCollection.model_validate(load_yaml(repo_root / config.roadmap.work_items))
    milestones = MilestoneRoadmap.model_validate(load_yaml(repo_root / config.roadmap.milestones))
    if milestones.milestone("M0_FACTORY_MIGRATED").status is not MilestoneStatus.COMPLETED:
        raise RuntimeError("cannot create migration marker before M0 is completed")
    required = [f"V3-MIG-{number:03d}" for number in range(16, 21)]
    evidence: dict[str, str] = {}
    for identifier in required:
        item = roadmap.item(identifier)
        if item.status is not WorkStatus.COMPLETED or not item.evidence_required:
            raise RuntimeError(f"cannot create marker before {identifier} evidence is complete")
        referenced = [
            resolve_within(repo_root, reference, require_exists=True)
            for reference in item.evidence_required
        ]
        evidence[identifier] = sha256_digest(
            b"\n".join(
                f"{path.relative_to(repo_root).as_posix()}:{sha256_file(path)}".encode()
                for path in sorted(referenced)
            )
        )
    marker = MigrationCompleteMarker(
        completed_sha=current_sha(repo_root),
        source_manifest_sha256=validate_active_source_generation(repo_root).manifest_digest,
        active_generation_sha256=validate_active_source_generation(repo_root).config_digest,
        acceptance_work_items={identifier: "COMPLETED" for identifier in required},
        acceptance_evidence_digests=evidence,
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
    parser.add_argument("--acknowledge", action="store_true", help=argparse.SUPPRESS)
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
