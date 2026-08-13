"""Digest-bound runtime milestone evidence and atomic progression state."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import Field, model_validator

from tcfactory.backends.base import ExecutionEvidenceMode
from tcfactory.util import read_json, write_json

from .base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .completion_policy import SemanticEvidence
from .enums import MilestoneStatus
from .milestones import MilestoneRoadmap


class WorkItemCompletionEvidence(V3Model):
    work_item_id: str
    milestone_id: str
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    base_sha: str = Field(pattern=SHA_PATTERN.pattern)
    candidate_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_authority_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    evidence_mode: ExecutionEvidenceMode
    checkpoint_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    checkpoint_path: Path | None = None
    candidate_manifest_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    candidate_manifest_path: Path | None = None
    independent_review_artifacts: dict[str, str] = Field(
        default_factory=dict[str, str]
    )
    machine_policy_receipt_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    machine_policy_receipt_path: Path | None = None
    release_authorization_envelope_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    release_authorization_envelope_path: Path | None = None
    external_receipt_refs: list[str]
    semantic_evidence_refs: dict[SemanticEvidence, list[str]] = Field(
        default_factory=dict[SemanticEvidence, list[str]]
    )
    semantic_artifact_bindings: dict[str, str] = Field(
        default_factory=dict[str, str]
    )
    created_at: datetime

    @model_validator(mode="after")
    def complete_bindings(self) -> WorkItemCompletionEvidence:
        if (self.candidate_manifest_path is None) != (
            self.candidate_manifest_digest is None
        ):
            raise ValueError("candidate manifest path/digest binding is incomplete")
        if (self.machine_policy_receipt_path is None) != (
            self.machine_policy_receipt_digest is None
        ):
            raise ValueError("machine-policy receipt path/digest binding is incomplete")
        if (self.release_authorization_envelope_path is None) != (
            self.release_authorization_envelope_digest is None
        ):
            raise ValueError("release authorization envelope binding is incomplete")
        for semantic, digests in self.semantic_evidence_refs.items():
            if not digests or len(digests) != len(set(digests)):
                raise ValueError(f"{semantic.value} evidence digests must be nonempty and unique")
            if any(DIGEST_PATTERN.fullmatch(digest) is None for digest in digests):
                raise ValueError(f"{semantic.value} evidence contains an invalid digest")
        if any(
            DIGEST_PATTERN.fullmatch(digest) is None
            for digest in self.semantic_artifact_bindings.values()
        ):
            raise ValueError("semantic artifact binding contains an invalid digest")
        return self


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


def write_work_item_completion_evidence(root: Path, evidence: WorkItemCompletionEvidence) -> Path:
    path = root / f"{evidence.work_item_id}.json"
    envelope = _envelope(evidence)
    if path.is_file():
        observed = read_json(path, {})
        if observed != envelope:
            raise ValueError(
                f"work-item completion evidence is immutable: {evidence.work_item_id}"
            )
        return path
    write_json(path, envelope)
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
    expected_evidence_ids: set[str],
    source_authority_digest: str,
    proposals: list[str] | None = None,
    now: datetime,
) -> MilestoneRuntimeState:
    if not evidence_digests:
        raise ValueError("milestone cannot advance without work-item evidence")
    if any(not digest.startswith("sha256:") for digest in evidence_digests.values()):
        raise ValueError("milestone evidence digest is invalid")
    if set(evidence_digests) != expected_evidence_ids:
        raise ValueError("milestone evidence must bind exactly every active work item")
    state = initialize_milestone_state(roadmap, state_path, now=now)
    if state.statuses.get(state.active_milestone) is not MilestoneStatus.ACTIVE:
        raise ValueError("milestone runtime state has no active completion target")
    active_statuses = [
        identifier
        for identifier, status in state.statuses.items()
        if status is MilestoneStatus.ACTIVE
    ]
    if active_statuses != [state.active_milestone]:
        raise ValueError("milestone runtime state must have exactly one ACTIVE milestone")
    ordered = [m.milestone_id for m in roadmap.milestones]
    index = ordered.index(state.active_milestone)
    next_milestone = ordered[index + 1] if index + 1 < len(ordered) else None
    receipt = MilestoneCompletionReceipt(
        milestone_id=state.active_milestone,
        next_milestone_id=next_milestone,
        evidence_digests=evidence_digests,
        source_authority_digest=source_authority_digest,
        proposals=proposals or [],
        decision=MilestoneStatus.COMPLETED,
        decided_at=now,
    )
    receipt_digest = sha256_digest(receipt.canonical_json_bytes())
    statuses = dict(state.statuses)
    statuses[state.active_milestone] = MilestoneStatus.COMPLETED
    if next_milestone is not None:
        statuses[next_milestone] = MilestoneStatus.ACTIVE
    if sum(status is MilestoneStatus.ACTIVE for status in statuses.values()) != 1:
        raise ValueError("milestone advance must leave exactly one ACTIVE milestone")
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
    if receipt_path.exists():
        raise ValueError("milestone completion receipt is immutable")
    write_json(transaction_path, _envelope(transaction))
    write_json(receipt_path, receipt_envelope)
    write_json(state_path, state_envelope)
    transaction_path.unlink()
    return advanced
