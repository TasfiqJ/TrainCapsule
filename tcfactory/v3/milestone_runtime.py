"""Digest-bound runtime milestone evidence and atomic progression state."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import Field

from tcfactory.util import read_json, write_json

from .base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .enums import MilestoneStatus
from .milestones import MilestoneRoadmap


class WorkItemCompletionEvidence(V3Model):
    work_item_id: str
    milestone_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    checkpoint_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    candidate_manifest_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    independent_reviewed: bool
    machine_policy_receipt_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    external_receipt_refs: list[str]
    created_at: datetime


class MilestoneRuntimeState(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    active_milestone: str
    statuses: dict[str, MilestoneStatus]
    last_completion_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    updated_at: datetime


class MilestoneCompletionReceipt(V3Model):
    milestone_id: str
    next_milestone_id: str | None
    evidence_digests: dict[str, str]
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    proposals: list[str] = Field(default_factory=list[str], max_length=5)
    decision: MilestoneStatus
    decided_at: datetime


class MilestoneAdvanceTransaction(V3Model):
    state_path: Path
    receipt_path: Path
    state_envelope: dict[str, object]
    receipt_envelope: dict[str, object]
    created_at: datetime


def _envelope(record: V3Model) -> dict[str, object]:
    payload = record.model_dump(mode="json", by_alias=True)
    return {"record": payload, "contentDigest": sha256_digest(record.canonical_json_bytes())}


def _transaction_path(state_path: Path) -> Path:
    return state_path.with_name(f".{state_path.name}.advance-transaction.json")


def reconcile_milestone_advance(state_path: Path) -> bool:
    transaction_path = _transaction_path(state_path)
    if not transaction_path.is_file():
        return False
    raw = read_json(transaction_path, {})
    transaction = MilestoneAdvanceTransaction.model_validate(raw.get("record"))
    if raw.get("contentDigest") != sha256_digest(transaction.canonical_json_bytes()):
        raise ValueError("milestone advance transaction digest mismatch")
    resolved_state = transaction.state_path.resolve()
    if resolved_state != state_path.resolve():
        raise ValueError("milestone advance transaction state path mismatch")
    try:
        transaction.receipt_path.resolve().relative_to(state_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("milestone advance receipt escapes runtime state root") from exc
    write_json(transaction.receipt_path, transaction.receipt_envelope)
    write_json(state_path, transaction.state_envelope)
    transaction_path.unlink()
    return True


def initialize_milestone_state(
    roadmap: MilestoneRoadmap, path: Path, *, now: datetime
) -> MilestoneRuntimeState:
    reconcile_milestone_advance(path)
    if path.is_file():
        raw = read_json(path, {})
        state = MilestoneRuntimeState.model_validate(raw.get("record"))
        if raw.get("contentDigest") != sha256_digest(state.canonical_json_bytes()):
            raise ValueError("milestone runtime state digest mismatch")
        return state
    active = [m.milestone_id for m in roadmap.milestones if m.status is MilestoneStatus.ACTIVE]
    if len(active) != 1:
        raise ValueError("milestone roadmap must have exactly one ACTIVE milestone")
    state = MilestoneRuntimeState(
        active_milestone=active[0],
        statuses={m.milestone_id: m.status for m in roadmap.milestones},
        updated_at=now,
    )
    write_json(path, _envelope(state))
    return state


def load_milestone_state(path: Path) -> MilestoneRuntimeState | None:
    if not path.is_file():
        return None
    raw = read_json(path, {})
    state = MilestoneRuntimeState.model_validate(raw.get("record"))
    if raw.get("contentDigest") != sha256_digest(state.canonical_json_bytes()):
        raise ValueError("milestone runtime state digest mismatch")
    return state


def write_work_item_completion_evidence(
    root: Path, evidence: WorkItemCompletionEvidence
) -> Path:
    path = root / f"{evidence.work_item_id}.json"
    write_json(path, _envelope(evidence))
    return path


def load_work_item_completion_evidence(
    root: Path, work_item_id: str
) -> tuple[WorkItemCompletionEvidence, str] | None:
    path = root / f"{work_item_id}.json"
    if not path.is_file():
        return None
    raw = read_json(path, {})
    evidence = WorkItemCompletionEvidence.model_validate(raw.get("record"))
    digest = sha256_digest(evidence.canonical_json_bytes())
    if raw.get("contentDigest") != digest:
        raise ValueError(f"work-item completion evidence digest mismatch: {work_item_id}")
    return evidence, digest


def advance_milestone_state(
    *,
    roadmap: MilestoneRoadmap,
    state_path: Path,
    receipt_path: Path,
    evidence_digests: dict[str, str],
    source_authority_digest: str,
    now: datetime,
) -> MilestoneRuntimeState:
    state = initialize_milestone_state(roadmap, state_path, now=now)
    ordered = [m.milestone_id for m in roadmap.milestones]
    index = ordered.index(state.active_milestone)
    next_milestone = ordered[index + 1] if index + 1 < len(ordered) else None
    receipt = MilestoneCompletionReceipt(
        milestone_id=state.active_milestone,
        next_milestone_id=next_milestone,
        evidence_digests=evidence_digests,
        source_authority_digest=source_authority_digest,
        decision=MilestoneStatus.COMPLETED,
        decided_at=now,
    )
    receipt_digest = sha256_digest(receipt.canonical_json_bytes())
    statuses = dict(state.statuses)
    statuses[state.active_milestone] = MilestoneStatus.COMPLETED
    if next_milestone is not None:
        statuses[next_milestone] = MilestoneStatus.ACTIVE
    advanced = MilestoneRuntimeState(
        active_milestone=next_milestone or state.active_milestone,
        statuses=statuses,
        last_completion_digest=receipt_digest,
        updated_at=now,
    )
    receipt_envelope = _envelope(receipt)
    state_envelope = _envelope(advanced)
    transaction = MilestoneAdvanceTransaction(
        state_path=state_path.resolve(),
        receipt_path=receipt_path.resolve(),
        state_envelope=state_envelope,
        receipt_envelope=receipt_envelope,
        created_at=now,
    )
    transaction_path = _transaction_path(state_path)
    write_json(transaction_path, _envelope(transaction))
    write_json(receipt_path, receipt_envelope)
    write_json(state_path, state_envelope)
    transaction_path.unlink()
    return advanced
