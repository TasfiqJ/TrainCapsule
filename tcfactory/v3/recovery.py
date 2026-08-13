"""Bounded repeated-finding, value, and controller restart escalation."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from tcfactory.v3.base import V3Model
from tcfactory.v3.enums import Disposition, WorkStatus
from tcfactory.v3.retry_policy import RetryPolicy


class FindingEscalation(V3Model):
    fingerprint: str = Field(min_length=1)
    count: int = Field(ge=1)
    blocked: bool
    status: WorkStatus
    candidate_preserved: bool = True
    proposed_dispositions: list[Disposition]
    machine_policy_review_proposed: bool


class FindingCounter(V3Model):
    counts: dict[str, int] = Field(default_factory=dict[str, int])

    def record(self, fingerprint: str, policy: RetryPolicy) -> FindingEscalation:
        if not fingerprint.strip():
            raise ValueError("finding fingerprint cannot be empty")
        count = self.counts.get(fingerprint, 0) + 1
        self.counts[fingerprint] = count
        exhausted = policy.repeated_finding_exhausted(count)
        return FindingEscalation(
            fingerprint=fingerprint,
            count=count,
            blocked=exhausted,
            status=(WorkStatus.BLOCKED_TECHNICAL if exhausted else WorkStatus.RUNNING),
            proposed_dispositions=([Disposition.NARROW, Disposition.REPLACE] if exhausted else []),
            machine_policy_review_proposed=exhausted,
        )


class ValueRedesignDecision(V3Model):
    failure_count: int = Field(ge=1)
    redesigns_remaining: int = Field(ge=0)
    status: WorkStatus
    append_implementation_tasks: bool = False


class ValueRedesignProposal(V3Model):
    proposal_id: str = Field(pattern=r"^VRP-[A-F0-9]{24}$")
    work_item_id: str = Field(pattern=r"^V3-[A-Z]+-[0-9]{3}$")
    failure_count: int = Field(ge=1)
    redesigns_remaining: int = Field(ge=0)
    target_status: WorkStatus
    reasons: list[str] = Field(min_length=1)
    candidate_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime
    roadmap_mutation_authorized: bool = False


def write_value_redesign_proposal(
    *,
    proposal_root: Path,
    work_item_id: str,
    decision: ValueRedesignDecision,
    reasons: list[str],
    candidate_sha: str,
    source_digest: str,
    context_digest: str,
    created_at: datetime,
) -> Path:
    """Persist a content-bound proposal; it never mutates the active roadmap."""

    identity = hashlib.sha256(
        (
            f"{work_item_id}\n{decision.failure_count}\n{candidate_sha}\n"
            f"{source_digest}\n{context_digest}\n{'|'.join(sorted(reasons))}\n"
        ).encode()
    ).hexdigest()[:24].upper()
    proposal = ValueRedesignProposal(
        proposal_id=f"VRP-{identity}",
        work_item_id=work_item_id,
        failure_count=decision.failure_count,
        redesigns_remaining=decision.redesigns_remaining,
        target_status=decision.status,
        reasons=reasons,
        candidate_sha=candidate_sha,
        source_digest=source_digest,
        context_digest=context_digest,
        created_at=created_at,
    )
    path = proposal_root / work_item_id / f"{proposal.proposal_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(
        proposal.model_dump(mode="json", by_alias=True),
        indent=2,
        sort_keys=True,
    ) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError("value redesign proposal identity collision")
        return path
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def value_redesign_failure(
    failure_count: int,
    *,
    max_value_redesigns: int,
    native_workflow_sufficient: bool,
) -> ValueRedesignDecision:
    if failure_count <= 0:
        raise ValueError("value failure count must be positive")
    if max_value_redesigns <= 0:
        raise ValueError("maxValueRedesigns must be positive")
    redesigns_used = max(0, failure_count - 1)
    terminal = redesigns_used >= max_value_redesigns
    if terminal:
        status = (
            WorkStatus.NATIVE_SUFFICIENT
            if native_workflow_sufficient
            else WorkStatus.REJECTED_VALUE
        )
    else:
        status = WorkStatus.READY
    return ValueRedesignDecision(
        failure_count=failure_count,
        redesigns_remaining=max(0, max_value_redesigns - redesigns_used),
        status=status,
    )


class HardStuckRecord(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    incident_id: str = Field(min_length=1)
    restart_count: int = Field(ge=1)
    max_controller_restarts: int = Field(ge=1)
    detected_at: datetime
    reason: str = Field(min_length=1)
    recovery_instructions: list[str] = Field(min_length=1)
    launcher_must_stop: bool = True


def _atomic_json(path: Path, record: HardStuckRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(record.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def enforce_controller_restart_budget(
    *,
    incident_id: str,
    restart_count: int,
    max_controller_restarts: int,
    detected_at: datetime,
    hard_stuck_path: Path,
    stop_path: Path,
) -> HardStuckRecord | None:
    """Write durable stop evidence after the finite restart budget is exceeded."""

    if max_controller_restarts <= 0:
        raise ValueError("maxControllerRestarts must be positive")
    if restart_count <= max_controller_restarts:
        return None
    record = HardStuckRecord(
        incident_id=incident_id,
        restart_count=restart_count,
        max_controller_restarts=max_controller_restarts,
        detected_at=detected_at,
        reason="controller restart budget exceeded",
        recovery_instructions=[
            "keep the launcher disabled",
            "preserve the bound incident and last healthy checkpoint",
            "do not clear or resume this irrecoverable controller incident",
            "a later autonomous run requires a new incident identity and must pass "
            "the complete startup machine policy independently",
        ],
    )
    _atomic_json(hard_stuck_path, record)
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text(
        f"V3 hard stuck: {incident_id}\n",
        encoding="utf-8",
        newline="\n",
    )
    return record
