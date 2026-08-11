"""Truthful read-only V3 runtime status aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from .checkpoints import CheckpointError, CheckpointStore, V3Checkpoint
from .github_sync import GitHubReleaseMetadata, load_github_config
from .supervisor import supervisor_status
from .util import read_json
from .v3.work_items import WorkItem, WorkItemCollection
from .yamlutil import load_yaml


def _current_item(roadmap: WorkItemCollection) -> WorkItem:
    active = [item for item in roadmap.work_items if item.milestone == roadmap.active_milestone]
    if not active:
        raise RuntimeError(f"active milestone {roadmap.active_milestone} has no work items")
    priority = {"RUNNING": 0, "QUEUED": 1, "READY": 2, "WAITING_HUMAN": 3}
    return min(active, key=lambda item: (priority.get(item.status.value, 9), item.work_item_id))


def _active_checkpoint(repo_root: Path, work_item_id: str) -> V3Checkpoint | None:
    try:
        active = CheckpointStore(repo_root / "factory" / "state" / "pipelines").list_active_v3()
    except CheckpointError:
        return None
    exact = [checkpoint for checkpoint in active if checkpoint.work_item_id == work_item_id]
    candidates = exact or active
    if not candidates:
        return None
    return max(candidates, key=lambda checkpoint: checkpoint.updated_at)


def _release_metadata(repo_root: Path) -> GitHubReleaseMetadata | None:
    config = load_github_config(repo_root / "config" / "github.yaml")
    path = Path(config.release_metadata_path)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        return None
    try:
        return GitHubReleaseMetadata.model_validate(read_json(path, {}))
    except ValueError:
        return None


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
    roadmap = WorkItemCollection.model_validate(
        load_yaml(repo_root / "factory" / "roadmap" / "work_items.yaml")
    )
    current = _current_item(roadmap)
    active = [item for item in roadmap.work_items if item.milestone == roadmap.active_milestone]
    checkpoint = _active_checkpoint(repo_root, current.work_item_id)
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
            "activeMilestone": roadmap.active_milestone,
            "currentWorkItem": {
                "workItemId": current.work_item_id,
                "lane": current.lane.value,
                "status": current.status.value,
            },
            "retryBudget": retry_budget,
            "restartBudget": supervisor_status(repo_root),
            "humanBlockers": [
                item.work_item_id for item in active if item.status.value == "WAITING_HUMAN"
            ],
            "externalBlockers": [
                item.work_item_id for item in active if item.status.value == "WAITING_EXTERNAL"
            ],
            "candidateSha": candidate_sha,
            "factoryCi": _ci_rollup(release, factory_names),
            "productCi": _ci_rollup(release, product_names),
            "lastReleasePr": release.pull_request_url if release is not None else None,
        },
    )
