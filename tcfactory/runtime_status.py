"""Truthful read-only V3 runtime status aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from .checkpoints import CheckpointError, CheckpointStore, V3Checkpoint
from .github_sync import GitHubReleaseMetadata, load_github_config
from .supervisor import supervisor_status
from .v3.configuration import load_factory_v3
from .v3.milestone_runtime import load_milestone_state
from .v3.queue import V3Queue
from .v3.runtime_paths import V3RuntimePaths, resolve_v3_runtime_paths
from .v3.work_items import WorkItem, WorkItemCollection
from .yamlutil import load_yaml


def _current_item(roadmap: WorkItemCollection) -> WorkItem:
    active = [item for item in roadmap.work_items if item.milestone == roadmap.active_milestone]
    if not active:
        raise RuntimeError(f"active milestone {roadmap.active_milestone} has no work items")
    priority = {"RUNNING": 0, "QUEUED": 1, "READY": 2, "WAITING_EXTERNAL": 3}
    return min(active, key=lambda item: (priority.get(item.status.value, 9), item.work_item_id))


def _checkpoint(paths: V3RuntimePaths, work_item_id: str) -> V3Checkpoint | None:
    try:
        store = CheckpointStore(paths.checkpoints)
        exact = store.load_v3(work_item_id)
        active = store.list_active_v3()
    except CheckpointError:
        return None
    candidates = ([exact] if exact is not None else []) or active
    if not candidates:
        return None
    return max(candidates, key=lambda checkpoint: checkpoint.updated_at)


def _release_metadata(repo_root: Path) -> GitHubReleaseMetadata | None:
    config = load_github_config(repo_root / "config" / "github.yaml")
    if config.publisher_capability == "PENDING_PHASE_4":
        return None
    raise RuntimeError("unknown V3.1 publication capability")


def _ci_rollup(
    release: GitHubReleaseMetadata | None, names: set[str]
) -> Literal["NOT_RUN", "PENDING", "PASS", "FAIL"]:
    if release is None:
        return "NOT_RUN"
    checks = [
        check for check in release.required_workflow_status.workflows if check.name in names
    ]
    if len(checks) != len(names):
        return "PENDING"
    if any(check.status == "completed" and check.conclusion != "success" for check in checks):
        return "FAIL"
    if all(check.status == "completed" and check.conclusion == "success" for check in checks):
        return "PASS"
    return "PENDING"


def build_runtime_status(repo_root: Path) -> dict[str, Any]:
    factory = load_factory_v3(repo_root / "config" / "factory.yaml")
    paths = resolve_v3_runtime_paths(repo_root, factory)
    roadmap = WorkItemCollection.model_validate(
        load_yaml(repo_root / "factory" / "roadmap" / "work_items.yaml")
    )
    milestone_state = load_milestone_state(paths.milestone_state)
    if milestone_state is not None:
        roadmap = roadmap.model_copy(
            update={"active_milestone": milestone_state.active_milestone}
        )
    queue = V3Queue(paths.queue)
    compatibility: list[dict[str, object]] = []
    if paths.queue.exists():
        authoritative = {item.work_item_id: item for item in roadmap.work_items}
        queue_items, migrations = queue.compatible_items(authoritative)
        runtime_items = {item.work_item_id: item for item in queue_items}
        compatibility = [
            cast(dict[str, object], item.model_dump(mode="json", by_alias=True))
            for item in migrations
        ]
    else:
        runtime_items = {}
    runtime_roadmap = roadmap.model_copy(
        update={
            "work_items": [
                runtime_items.get(item.work_item_id, item) for item in roadmap.work_items
            ]
        }
    )
    current = _current_item(runtime_roadmap)
    active = [
        item
        for item in runtime_roadmap.work_items
        if item.milestone == runtime_roadmap.active_milestone
    ]
    checkpoint = _checkpoint(paths, current.work_item_id)
    release = _release_metadata(repo_root)
    retry_budget: dict[str, int] = {
        "planAttemptsRemaining": current.retry_policy.max_plan_attempts,
        "repairCyclesRemaining": current.retry_policy.max_candidate_repair_cycles,
        "candidateRestartsRemaining": current.retry_policy.max_candidate_restarts,
    }
    if checkpoint is not None:
        retry_budget = {
            "planAttemptsRemaining": checkpoint.budget.plan_attempts_remaining,
            "repairCyclesRemaining": checkpoint.budget.repair_cycles_remaining,
            "candidateRestartsRemaining": checkpoint.budget.restarts_remaining,
        }
    factory_names = {
        "TrainCapsule / Factory quality",
        "TrainCapsule / Security",
        "TrainCapsule / Source-of-truth integrity",
    }
    product_names = {
        "TrainCapsule / Product unit",
        "TrainCapsule / Product contract",
    }
    candidate_sha = checkpoint.candidate_sha if checkpoint is not None else None
    if release is not None:
        candidate_sha = release.candidate_sha
    return cast(
        dict[str, Any],
        {
            "activeMilestone": runtime_roadmap.active_milestone,
            "queuePolicyCompatibility": compatibility,
            "currentWorkItem": {
                "workItemId": current.work_item_id,
                "lane": current.lane.value,
                "status": current.status.value,
            },
            "retryBudget": retry_budget,
            "restartBudget": supervisor_status(repo_root),
            "interventionMode": "NONE",
            "externalBlockers": [
                item.work_item_id for item in active if item.status.value == "WAITING_EXTERNAL"
            ],
            "queueRoot": str(paths.queue),
            "queueCounts": {
                status: sum(item.status.value == status for item in runtime_items.values())
                for status in sorted({item.status.value for item in runtime_items.values()})
            },
            "candidateSha": candidate_sha,
            "factoryCi": _ci_rollup(release, factory_names),
            "productCi": _ci_rollup(release, product_names),
            "lastMainPublication": (
                release.model_dump(mode="json", by_alias=True) if release is not None else None
            ),
        },
    )
