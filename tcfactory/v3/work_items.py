"""Strict V3 work items, dependency graphs, and status transitions."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import Field, model_validator

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import (
    CommercialMaturity,
    Disposition,
    EvidenceType,
    Lane,
    OwnerType,
    RiskTier,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.external_evidence import TrustedEvidenceRecord
from tcfactory.v3.maturity import MaturityTarget, commercial_maturity_supported
from tcfactory.v3.retry_policy import RetryPolicy

ALLOWED_TRANSITIONS: dict[WorkStatus, frozenset[WorkStatus]] = {
    WorkStatus.PROPOSED: frozenset(
        {
            WorkStatus.READY,
            WorkStatus.WAITING_EXTERNAL,
            WorkStatus.WAITING_HUMAN,
            WorkStatus.REJECTED_VALUE,
            WorkStatus.NATIVE_SUFFICIENT,
            WorkStatus.DEFERRED,
            WorkStatus.SUPERSEDED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.READY: frozenset(
        {
            WorkStatus.QUEUED,
            WorkStatus.WAITING_EXTERNAL,
            WorkStatus.WAITING_HUMAN,
            WorkStatus.BLOCKED_TECHNICAL,
            WorkStatus.BLOCKED_POLICY,
            WorkStatus.DEFERRED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.QUEUED: frozenset(
        {
            WorkStatus.RUNNING,
            WorkStatus.PAUSED_QUOTA,
            WorkStatus.BLOCKED_TECHNICAL,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.RUNNING: frozenset(
        {
            WorkStatus.PAUSED_QUOTA,
            WorkStatus.WAITING_EXTERNAL,
            WorkStatus.WAITING_HUMAN,
            WorkStatus.BLOCKED_TECHNICAL,
            WorkStatus.BLOCKED_POLICY,
            WorkStatus.PASSED_ENGINEERING,
            WorkStatus.REJECTED_VALUE,
            WorkStatus.NATIVE_SUFFICIENT,
            WorkStatus.DEFERRED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.PAUSED_QUOTA: frozenset({WorkStatus.QUEUED, WorkStatus.CANCELLED}),
    WorkStatus.WAITING_EXTERNAL: frozenset(
        {
            WorkStatus.READY,
            WorkStatus.REJECTED_VALUE,
            WorkStatus.NATIVE_SUFFICIENT,
            WorkStatus.DEFERRED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.WAITING_HUMAN: frozenset(
        {
            WorkStatus.READY,
            WorkStatus.BLOCKED_POLICY,
            WorkStatus.DEFERRED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.BLOCKED_TECHNICAL: frozenset(
        {WorkStatus.READY, WorkStatus.DEFERRED, WorkStatus.CANCELLED}
    ),
    WorkStatus.BLOCKED_POLICY: frozenset(
        {
            WorkStatus.READY,
            WorkStatus.WAITING_HUMAN,
            WorkStatus.DEFERRED,
            WorkStatus.CANCELLED,
        }
    ),
    WorkStatus.PASSED_ENGINEERING: frozenset(
        {
            WorkStatus.COMPLETED,
            WorkStatus.WAITING_EXTERNAL,
            WorkStatus.WAITING_HUMAN,
            WorkStatus.REJECTED_VALUE,
            WorkStatus.NATIVE_SUFFICIENT,
            WorkStatus.DEFERRED,
        }
    ),
    WorkStatus.REJECTED_VALUE: frozenset(),
    WorkStatus.NATIVE_SUFFICIENT: frozenset(),
    WorkStatus.DEFERRED: frozenset({WorkStatus.PROPOSED, WorkStatus.CANCELLED}),
    WorkStatus.SUPERSEDED: frozenset(),
    WorkStatus.CANCELLED: frozenset(),
    WorkStatus.COMPLETED: frozenset(),
}


def assert_status_transition(current: WorkStatus, target: WorkStatus) -> None:
    """Reject implicit, same-state, and terminal-state transitions."""

    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid work status transition: {current} -> {target}")


class WorkItem(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    title: str = Field(min_length=1)
    lane: Lane
    kind: WorkKind
    milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    decision_contribution: str = Field(min_length=1)
    customer_outcome: str
    depends_on: list[str]
    soft_depends_on: list[str]
    blocks_commercial_release: bool
    priority: int = Field(ge=0, le=100)
    risk_tier: RiskTier
    maturity_target: MaturityTarget
    disposition: Disposition
    status: WorkStatus
    owner_type: OwnerType
    automatable: bool
    packet_path: str | None = None
    evidence_required: list[str]
    external_receipt_required: bool
    human_approval_required: bool
    retry_policy: RetryPolicy
    external_evidence_refs: list[str] = Field(default_factory=list[str])
    human_approval_refs: list[str] = Field(default_factory=list[str])
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_work_item(self) -> WorkItem:
        if self.work_item_id in {*self.depends_on, *self.soft_depends_on}:
            raise ValueError("work item cannot depend on itself")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("hard dependencies must be unique")
        if len(self.soft_depends_on) != len(set(self.soft_depends_on)):
            raise ValueError("soft dependencies must be unique")
        overlap = set(self.depends_on) & set(self.soft_depends_on)
        if overlap:
            raise ValueError(f"hard and soft dependencies overlap: {sorted(overlap)}")
        human_or_external = self.kind in {
            WorkKind.EXTERNAL_EVIDENCE,
            WorkKind.HUMAN_REVIEW,
        }
        if human_or_external and self.automatable:
            raise ValueError("external evidence and human review are not automatable")
        if human_or_external and self.owner_type is OwnerType.AI:
            raise ValueError("AI cannot own external evidence or human review")
        if self.kind is WorkKind.EXTERNAL_EVIDENCE and not self.external_receipt_required:
            raise ValueError("external evidence work requires an external receipt")
        if self.kind is WorkKind.COMMERCIAL_EXPERIMENT and not self.external_receipt_required:
            raise ValueError("commercial experiment work requires an external receipt")
        if self.kind is WorkKind.HUMAN_REVIEW and not self.human_approval_required:
            raise ValueError("human review work requires human approval")
        if self.status is WorkStatus.COMPLETED:
            if self.external_receipt_required and not self.external_evidence_refs:
                raise ValueError("completed work lacks required external receipt references")
            if self.human_approval_required and not self.human_approval_refs:
                raise ValueError("completed work lacks required human approval references")
            if (
                self.maturity_target.commercial
                not in {
                    CommercialMaturity.NOT_EVALUATED,
                    CommercialMaturity.NATIVE_ADVANTAGE_UNPROVEN,
                    CommercialMaturity.WITHDRAWN,
                }
                and not self.external_evidence_refs
            ):
                raise ValueError("completed commercial maturity lacks external evidence")
        if self.created_at and self.updated_at and self.updated_at < self.created_at:
            raise ValueError("updatedAt cannot precede createdAt")
        return self


class WorkItemCollection(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    active_milestone: str = Field(pattern=r"^M[0-9]+_[A-Z0-9_]+$")
    work_items: list[WorkItem]

    @model_validator(mode="after")
    def validate_graph(self) -> WorkItemCollection:
        identifiers = [item.work_item_id for item in self.work_items]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("work item IDs must be unique")
        known = set(identifiers)
        for item in self.work_items:
            missing = ({*item.depends_on, *item.soft_depends_on}) - known
            if missing:
                raise ValueError(
                    f"work item {item.work_item_id} has missing dependencies: "
                    f"{sorted(missing)}"
                )
        self._require_acyclic()
        return self

    def _require_acyclic(self) -> None:
        graph = {item.work_item_id: set(item.depends_on) for item in self.work_items}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                raise ValueError(f"hard dependency cycle includes {identifier}")
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in graph[identifier]:
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)

        for identifier in sorted(graph):
            visit(identifier)

    def item(self, work_item_id: str) -> WorkItem:
        for item in self.work_items:
            if item.work_item_id == work_item_id:
                return item
        raise KeyError(work_item_id)

    def validate_completion_evidence(
        self,
        receipts: Mapping[str, TrustedEvidenceRecord],
    ) -> None:
        """Validate trusted receipts and maturity ceilings for completed work."""

        for item in self.work_items:
            if item.status is not WorkStatus.COMPLETED:
                continue
            trusted_types: list[EvidenceType] = []
            for receipt_id in item.external_evidence_refs:
                record = receipts.get(receipt_id)
                if record is None:
                    raise ValueError(
                        f"completed work {item.work_item_id} has unknown receipt {receipt_id}"
                    )
                trusted_types.append(record.require_commercial_trust().evidence_type)
            if not commercial_maturity_supported(
                item.maturity_target.commercial,
                trusted_types,
            ):
                raise ValueError(
                    f"commercial maturity for {item.work_item_id} exceeds trusted evidence"
                )
