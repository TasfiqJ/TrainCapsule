from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .models import CommitType, RiskTier
from .yamlutil import load_yaml

LedgerStatus = Literal[
    "blocked",
    "ready",
    "packet_proposed",
    "packet_approved",
    "queued",
    "running",
    "paused",
    "passed",
    "failed",
    "respec_required",
    "deferred",
    "external_wait",
]
CompletionKind = Literal["build", "external_validation", "commercial_validation", "demand_driven"]


class FeatureItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    task_id: str
    outcome: str
    lead_role: str
    phase: str
    depends_on: list[str] = Field(default_factory=list)
    status: LedgerStatus = "blocked"
    packet_path: str | None = None
    trust_core: bool = False
    risk_tier: RiskTier = RiskTier.STANDARD
    context_keys: list[str] = Field(default_factory=list)
    remote_ci_required: bool = False
    allow_test_changes: bool = False
    commit_type: CommitType = CommitType.FEAT
    auto_enqueue_allowed: bool = True
    automatable: bool = True
    completion_kind: CompletionKind = "build"
    evidence_required: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    last_run_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    revisions: int = 0
    value_revisions: int = 0


class FeatureLedger(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    source_of_truth: str
    rules: dict[str, Any] = Field(default_factory=dict)
    tasks: list[FeatureItem]

    def item(self, task_id: str) -> FeatureItem:
        for item in self.tasks:
            if item.task_id == task_id:
                return item
        raise KeyError(task_id)

    def passed_ids(self) -> set[str]:
        return {item.task_id for item in self.tasks if item.status == "passed"}

    def refresh_readiness(self) -> None:
        passed = self.passed_ids()
        for item in self.tasks:
            if item.status in {
                "passed",
                "deferred",
                "external_wait",
                "running",
                "paused",
                "failed",
                "respec_required",
            }:
                continue
            if set(item.depends_on).issubset(passed):
                if item.packet_path and item.status == "blocked":
                    item.status = "packet_approved"
                elif not item.packet_path and item.status == "blocked":
                    item.status = "ready"
            elif item.status == "ready":
                item.status = "blocked"

    def next_ready(self) -> FeatureItem | None:
        self.refresh_readiness()
        for item in self.tasks:
            if item.automatable and item.status in {"ready", "packet_approved"}:
                return item
        return None

    def build_complete(self) -> bool:
        relevant = [
            item
            for item in self.tasks
            if item.automatable and item.completion_kind == "build" and item.status != "deferred"
        ]
        return bool(relevant) and all(item.status == "passed" for item in relevant)

    def all_automatable_complete(self) -> bool:
        relevant = [item for item in self.tasks if item.automatable and item.status != "deferred"]
        return bool(relevant) and all(
            item.status in {"passed", "external_wait"} for item in relevant
        )


def load_feature_ledger(path: Path) -> FeatureLedger:
    return FeatureLedger.model_validate(load_yaml(path))


def save_feature_ledger(path: Path, ledger: FeatureLedger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = ledger.model_dump(mode="json", exclude_none=False)
    payload["updated_at"] = datetime.now(UTC).isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    temporary.replace(path)
