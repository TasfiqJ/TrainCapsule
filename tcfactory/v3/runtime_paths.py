"""Single source of truth for all mutable V3 runtime paths."""

from __future__ import annotations

import os
from pathlib import Path

from .base import V3Model
from .configuration import FactoryV3Config, load_factory_v3


class V3RuntimePaths(V3Model):
    state_root: Path
    queue: Path
    checkpoints: Path
    controller_state: Path
    scheduler_decisions: Path
    milestone_state: Path
    milestone_evidence: Path
    milestone_decisions: Path
    machine_policy_receipts: Path
    source_proposals: Path
    quarantine: Path
    migration_marker: Path
    supervisor_state: Path
    supervisor_lock: Path
    controller_lock: Path
    hard_stuck: Path
    stop: Path
    pause: Path


def resolve_v3_runtime_paths(
    repo_root: Path, config: FactoryV3Config | None = None
) -> V3RuntimePaths:
    """Resolve the configured V3 state root once for every runtime consumer."""

    root = repo_root.resolve()
    factory = config or load_factory_v3(root / "config" / "factory.yaml")
    raw_root = os.getenv(factory.runtime.local_state_root_environment_variable)
    if raw_root:
        state_root = Path(raw_root).expanduser()
        if not state_root.is_absolute():
            raise ValueError("configured runtime state root must be absolute")
        state_root = state_root.resolve()
    else:
        state_root = (root / "factory" / "state").resolve()
    return V3RuntimePaths(
        state_root=state_root,
        queue=state_root / "v3-queue",
        checkpoints=state_root / "pipelines",
        controller_state=state_root / "v3-controller.json",
        scheduler_decisions=state_root / "scheduler-decisions",
        milestone_state=state_root / "milestone-state.json",
        milestone_evidence=state_root / "milestone-evidence",
        milestone_decisions=state_root / "milestone-decisions",
        machine_policy_receipts=state_root / "machine-policy-receipts",
        source_proposals=state_root / "source-proposals",
        quarantine=state_root / "quarantine",
        migration_marker=state_root / factory.runtime.migration_complete_marker,
        supervisor_state=state_root / factory.runtime.supervisor_state_file,
        supervisor_lock=state_root / factory.runtime.supervisor_lock_file,
        controller_lock=state_root / "controller.lock",
        hard_stuck=state_root / factory.runtime.hard_stuck_file,
        stop=state_root / factory.runtime.stop_file,
        pause=state_root / "PAUSE",
    )
