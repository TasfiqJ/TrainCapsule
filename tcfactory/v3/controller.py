"""Executable V3 factory controller.

This is the only normal-operation dispatcher. Legacy T001--T124 artifacts are historical
inputs and are never loaded, scheduled, mutated, or resumed here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import Field

from tcfactory.backends.base import AgentTaskRequest, EngineeringAgentBackend, SessionState
from tcfactory.checkpoints import CheckpointBudget, CheckpointStore, V3Checkpoint
from tcfactory.config import load_roles
from tcfactory.context import (
    StaleCurrentFactError,
    V3ContextManifest,
    build_v3_context_manifest,
)
from tcfactory.gitops import create_worktree, current_sha
from tcfactory.handoffs import write_v3_handoff
from tcfactory.models import RoleName
from tcfactory.prompts import compose_system_prompt
from tcfactory.util import read_json, run_command, sha256_file, write_json
from tcfactory.v3.base import V3Model, sha256_digest
from tcfactory.v3.candidate_manifest import (
    CandidateManifest,
    ExecutorIdentity,
    GateBinding,
    StageArtifactBinding,
)
from tcfactory.v3.configuration import (
    ExternalEvidenceConfig,
    FactoryV3Config,
    load_factory_v3,
    load_scheduler_v3,
    validate_v3_configuration,
)
from tcfactory.v3.enums import (
    Lane,
    ReleaseDecision,
    RiskTier,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.external_evidence import (
    ExternalEvidenceVerificationError,
    load_verified_external_evidence,
)
from tcfactory.v3.milestone_runtime import (
    WorkItemCompletionEvidence,
    advance_milestone_state,
    initialize_milestone_state,
    load_work_item_completion_evidence,
    write_work_item_completion_evidence,
)
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.pipeline_services import assert_candidate_scope
from tcfactory.v3.planning import V3TaskPacket, compile_work_item_packet, write_packet
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.runtime_paths import resolve_v3_runtime_paths
from tcfactory.v3.scheduler import ActiveWork, SchedulerDecisionArtifact, schedule_cycle
from tcfactory.v3.source_authority import (
    emit_stale_source_proposal,
    validate_active_source_generation,
)
from tcfactory.v3.work_items import WorkItem, WorkItemCollection
from tcfactory.yamlutil import load_yaml


class CandidatePublisher(Protocol):
    def prepare_candidate(
        self, *, item: WorkItem, candidate_sha: str, candidate_worktree: Path
    ) -> Mapping[str, Path]: ...

    def publish(
        self,
        *,
        item: WorkItem,
        candidate_ref: str,
        candidate_sha: str,
        candidate_worktree: Path,
        candidate_manifest_path: Path,
        packet_digest: str,
        source_digest: str,
        context_digest: str,
        checkpoint_digest: str,
        gate_digests: dict[str, str],
    ) -> Mapping[str, object]: ...


class ControllerState(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    cycles: int = Field(default=0, ge=0)
    lane_cursor: Lane = Lane.PRODUCT
    last_decision_artifact: str | None = None
    last_work_item_id: str | None = None
    last_candidate_sha: str | None = None
    blocked_scopes: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])


ROLE_POLICY: dict[RiskTier, tuple[str, ...]] = {
    RiskTier.MECHANICAL: ("builder",),
    RiskTier.STANDARD: ("builder", "audit"),
    RiskTier.INTEGRATION: ("builder", "integration_scout", "adversary"),
    RiskTier.TRUST_CORE: ("builder", "audit", "security", "adversary"),
    RiskTier.EXTERNAL: ("research", "audit"),
}


def _digest_file(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def _lane_paths(item: WorkItem) -> tuple[list[str], list[str]]:
    if item.lane is Lane.PRODUCT:
        return (
            ["packages/traincapsule-*/**", "tests/product/**", "examples/product/**"],
            ["tcfactory/**", "factory/**", "config/**", "scripts/**", "prompts/**"],
        )
    return (
        ["tcfactory/**", "factory/**", "config/**", "scripts/**", "prompts/**", "tests/**"],
        ["packages/traincapsule-*/**", "tests/product/**", "examples/product/**"],
    )


def _packet_for(
    repo_root: Path,
    item: WorkItem,
    *,
    base_sha: str,
    artifact_root: Path,
    context_digest: str,
    context_manifest_path: Path,
) -> V3TaskPacket:
    allowed, forbidden = _lane_paths(item)
    active_source = validate_active_source_generation(repo_root)
    criteria = item.evidence_required or [
        "The bounded work-item outcome is executable and deterministically verified."
    ]
    packet = compile_work_item_packet(
        item,
        source_documents=[
            active_source.config_path,
            active_source.manifest_path,
            "docs/CONTEXT_INDEX.yaml",
            str(context_manifest_path),
        ],
        allowed_paths=allowed,
        outputs=[],
        acceptance_criteria=criteria[:12],
        non_goals=["Do not broaden the active milestone or fabricate external/customer evidence."],
        oracle="Deterministic gates and candidate-SHA-bound machine evidence.",
        rollback="Preserve the candidate branch and revert only its bounded delta.",
        stop_conditions=[
            "Stop on finite budget exhaustion, repeated finding, native sufficiency, "
            "or UNKNOWN external truth."
        ],
        stop_disposition="BLOCKED_TECHNICAL or WAITING_EXTERNAL for this work item only.",
        source_digest=active_source.source_digest,
        context_digest=context_digest,
        compiler_digest=_digest_file(Path(__file__).with_name("planning.py")),
        base_sha=base_sha,
    )
    # The WorkItem-level split is the only writer of scope; forbidden paths are
    # controller-derived and then included in the immutable packet.
    packet = packet.model_copy(update={"forbidden_paths": forbidden})
    packet_path = artifact_root / "task-packet.yaml"
    write_packet(packet_path, packet)
    return packet


def _context_groups(item: WorkItem, role: str) -> list[str]:
    if item.lane is Lane.FACTORY:
        return ["factory_control", "roadmap"]
    if item.lane in {Lane.MARKET, Lane.COMPETITOR}:
        if role in {"planner", "research", "value_validator", "value_adversary"}:
            return ["commercial", "current_facts", "market_evidence"]
        return ["current_facts"]
    if role in {"security"}:
        return ["technical_architecture", "trust_core"]
    if role in {"integration_scout", "performance"}:
        return ["technical_architecture"]
    groups = ["product_normative", "technical_architecture", "trust_core"]
    if role in {"audit", "adversary"}:
        groups.append("roadmap")
    return groups


def _changed_paths(repo_root: Path, base_sha: str, candidate_sha: str) -> list[str]:
    result = run_command(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", base_sha, candidate_sha],
        cwd=repo_root,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("candidate changed-path inspection failed")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _mutating(item: WorkItem) -> bool:
    return item.kind in {
        WorkKind.CODE,
        WorkKind.SPECIFICATION,
        WorkKind.CONTROLLED_EXPERIMENT,
        WorkKind.MAINTENANCE,
        WorkKind.MIGRATION,
    }


class V3Controller:
    def __init__(
        self,
        *,
        repo_root: Path,
        backend: EngineeringAgentBackend,
        publisher: CandidatePublisher,
        owner_id: str = "v3-controller",
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.backend = backend
        self.publisher = publisher
        self.owner_id = owner_id
        self.active_source = validate_active_source_generation(self.repo_root)
        self.factory: FactoryV3Config = load_factory_v3(self.repo_root / "config/factory.yaml")
        self.runtime_paths = resolve_v3_runtime_paths(self.repo_root, self.factory)
        self.runtime_root = self.runtime_paths.state_root
        self.queue = V3Queue(self.runtime_paths.queue)
        self.checkpoints = CheckpointStore(self.runtime_paths.checkpoints)
        self.artifact_root = self.repo_root / "factory/artifacts/v3"
        self.state_path = self.runtime_paths.controller_state

    def _load_state(self) -> ControllerState:
        if not self.state_path.exists():
            return ControllerState()
        return ControllerState.model_validate(read_json(self.state_path, {}))

    def _save_state(self, state: ControllerState) -> None:
        write_json(self.state_path, state.model_dump(mode="json", by_alias=True))

    def _roadmap(self) -> WorkItemCollection:
        roadmap = WorkItemCollection.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.work_items)
        )
        milestones = MilestoneRoadmap.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.milestones)
        )
        state = initialize_milestone_state(
            milestones, self.runtime_paths.milestone_state, now=datetime.now(UTC)
        )
        return roadmap.model_copy(update={"active_milestone": state.active_milestone})

    def _record_completion_evidence(
        self,
        *,
        item: WorkItem,
        candidate_sha: str,
        checkpoint_digest: str,
        manifest_digest: str | None,
        machine_policy_receipt_digest: str | None,
        independent_reviewed: bool,
        now: datetime,
    ) -> Path:
        evidence = WorkItemCompletionEvidence(
            work_item_id=item.work_item_id,
            milestone_id=item.milestone,
            candidate_sha=candidate_sha,
            checkpoint_digest=checkpoint_digest,
            candidate_manifest_digest=manifest_digest,
            independent_reviewed=independent_reviewed,
            machine_policy_receipt_digest=machine_policy_receipt_digest,
            external_receipt_refs=item.external_evidence_refs,
            created_at=now,
        )
        return write_work_item_completion_evidence(
            self.runtime_paths.milestone_evidence, evidence
        )

    def _advance_completed_milestone(self, collection: WorkItemCollection) -> str | None:
        validate_active_source_generation(self.repo_root)
        active = [
            item
            for item in collection.work_items
            if item.milestone == collection.active_milestone
        ]
        if not active or any(
            item.status not in {WorkStatus.PASSED_ENGINEERING, WorkStatus.COMPLETED}
            for item in active
        ):
            return None
        evidence_digests: dict[str, str] = {}
        for item in active:
            loaded = load_work_item_completion_evidence(
                self.runtime_paths.milestone_evidence, item.work_item_id
            )
            if loaded is None:
                return None
            evidence, digest = loaded
            if evidence.milestone_id != collection.active_milestone:
                return None
            if item.risk_tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE} and not (
                evidence.independent_reviewed
            ):
                return None
            if (
                item.kind is WorkKind.MACHINE_POLICY_REVIEW
                and evidence.machine_policy_receipt_digest is None
            ):
                return None
            if item.external_receipt_required and not evidence.external_receipt_refs:
                return None
            evidence_digests[item.work_item_id] = digest
        milestones = MilestoneRoadmap.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.milestones)
        )
        receipt_path = (
            self.runtime_paths.milestone_decisions
            / f"{collection.active_milestone}.json"
        )
        state = advance_milestone_state(
            roadmap=milestones,
            state_path=self.runtime_paths.milestone_state,
            receipt_path=receipt_path,
            evidence_digests=evidence_digests,
            source_authority_digest=self.active_source.canonical_digest(),
            now=datetime.now(UTC),
        )
        return state.active_milestone

    def initialize(self) -> None:
        validate_v3_configuration(self.repo_root)
        self.queue.initialize()
        self.queue.reconcile_transactions()
        now = datetime.now(UTC)
        interrupted = self.queue.recover_interrupted(updated_at=now)
        for identifier in interrupted:
            checkpoint = self.checkpoints.load_v3(identifier)
            if checkpoint is None or not checkpoint.active:
                continue
            if checkpoint.budget.restarts_remaining <= 0:
                checkpoint.active = False
                checkpoint.circuit_breaker_reason = "candidate restart budget exhausted after crash"
                self.checkpoints.save_v3(checkpoint)
                continue
            checkpoint.generation += 1
            checkpoint.budget.restarts_remaining -= 1
            checkpoint.circuit_breaker_reason = "interrupted controller session recovered"
            checkpoint.updated_at = now
            self.checkpoints.save_v3(checkpoint)
            item = self.queue.load(identifier)
            recovery_root = (
                self.artifact_root / identifier / f"recovery-{checkpoint.generation:04d}"
            )
            write_v3_handoff(
                artifact_root=recovery_root,
                relative_path="handoff.json",
                work_item=item,
                disposition=item.disposition,
                attempt=checkpoint.generation,
                attempts_remaining=checkpoint.budget.restarts_remaining,
                base_sha=current_sha(self.repo_root, "main"),
                candidate_sha=checkpoint.candidate_sha,
                next_action="RESTART_FROM_BOUND_CHECKPOINT",
                findings=[{"summary": "controller session interrupted"}],
                artifacts={},
                source_digest=checkpoint.source_digest,
                context_digest=checkpoint.context_digest,
                circuit_breaker_state="RECOVERED_INTERRUPTION",
                backend_session_ref=checkpoint.backend_session_ref,
            )
            self.queue.transition(identifier, WorkStatus.READY, updated_at=now)
        self.queue.recover_expired_claims(now=now)
        roadmap = self._roadmap()
        existing = {item.work_item_id for item in self.queue.items()}
        for item in roadmap.work_items:
            if item.work_item_id in existing or item.status in {
                WorkStatus.COMPLETED,
                WorkStatus.CANCELLED,
                WorkStatus.SUPERSEDED,
                WorkStatus.REJECTED_VALUE,
                WorkStatus.NATIVE_SUFFICIENT,
            }:
                continue
            self.queue.put(item)

    def _runtime_collection(self) -> WorkItemCollection:
        roadmap = self._roadmap()
        runtime = {item.work_item_id: item for item in self.queue.items()}
        return roadmap.model_copy(
            update={
                "work_items": [runtime.get(item.work_item_id, item) for item in roadmap.work_items]
            }
        )

    def _promote_ready(self, collection: WorkItemCollection, now: datetime) -> None:
        satisfied = {
            item.work_item_id
            for item in collection.work_items
            if item.status in {WorkStatus.PASSED_ENGINEERING, WorkStatus.COMPLETED}
        }
        for item in collection.work_items:
            if item.milestone != collection.active_milestone:
                continue
            if item.status not in {WorkStatus.PROPOSED, WorkStatus.WAITING_EXTERNAL}:
                continue
            if set(item.depends_on).issubset(satisfied):
                if item.external_receipt_required:
                    if item.status is WorkStatus.PROPOSED:
                        self.queue.transition(
                            item.work_item_id,
                            WorkStatus.WAITING_EXTERNAL,
                            updated_at=now,
                        )
                    external = ExternalEvidenceConfig.model_validate(
                        load_yaml(self.repo_root / "config/external_evidence.yaml")
                    )
                    try:
                        record = load_verified_external_evidence(
                            repo_root=self.repo_root,
                            subject_id=item.work_item_id,
                            trusted_root_environment_variable=(
                                external.trusted_root_environment_variable
                            ),
                            trusted_public_key_environment_variable=(
                                external.trusted_public_key_environment_variable
                            ),
                        )
                    except ExternalEvidenceVerificationError:
                        continue
                    receipt = record.require_commercial_trust()
                    self.queue.bind_external_evidence(
                        item.work_item_id,
                        receipt_id=receipt.receipt_id,
                        updated_at=now,
                    )
                    self.queue.transition(
                        item.work_item_id,
                        WorkStatus.PASSED_ENGINEERING,
                        updated_at=now,
                    )
                    verified_item = self.queue.load(item.work_item_id)
                    self._record_completion_evidence(
                        item=verified_item,
                        candidate_sha=current_sha(self.repo_root, "main"),
                        checkpoint_digest=sha256_digest(receipt.canonical_json_bytes()),
                        manifest_digest=None,
                        machine_policy_receipt_digest=None,
                        independent_reviewed=False,
                        now=now,
                    )
                    continue
                target = (
                    WorkStatus.READY
                    if item.automatable
                    else WorkStatus.BLOCKED_POLICY
                )
                self.queue.transition(item.work_item_id, target, updated_at=now)

    def _roles(self, item: WorkItem) -> tuple[str, ...]:
        if item.lane is Lane.FACTORY:
            return ("factory_repair", "audit")
        roles = ROLE_POLICY[item.risk_tier]
        if item.kind is WorkKind.RESEARCH:
            return tuple("research" if role == "builder" else role for role in roles)
        if item.kind is WorkKind.SPECIFICATION:
            return tuple("specification" if role == "builder" else role for role in roles)
        return roles

    def _freshness_receipts(self, item: WorkItem) -> dict[str, datetime]:
        if item.lane not in {Lane.MARKET, Lane.COMPETITOR}:
            return {}
        external = ExternalEvidenceConfig.model_validate(
            load_yaml(self.repo_root / "config/external_evidence.yaml")
        )
        verified: dict[str, datetime] = {}
        for group in ("current_facts", "market_evidence"):
            subject_id = f"CONTEXT-{group.replace('_', '-').upper()}"
            record = load_verified_external_evidence(
                repo_root=self.repo_root,
                subject_id=subject_id,
                trusted_root_environment_variable=(
                    external.trusted_root_environment_variable
                ),
                trusted_public_key_environment_variable=(
                    external.trusted_public_key_environment_variable
                ),
            )
            verified[group] = record.require_commercial_trust().observed_at
        return verified

    async def _execute(self, item: WorkItem, now: datetime) -> dict[str, object]:
        if item.machine_policy_receipt_required or item.kind is WorkKind.MACHINE_POLICY_REVIEW:
            self.queue.transition(
                item.work_item_id,
                WorkStatus.BLOCKED_POLICY,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.BLOCKED_POLICY.value,
                "workItemId": item.work_item_id,
                "reason": (
                    "independently signed Phase 3 machine-policy receipt is required; "
                    "the controller cannot issue or verify its own authorization"
                ),
            }
        if item.external_receipt_required:
            raise RuntimeError(
                "outside-fact work cannot execute; it advances only through a "
                "cryptographically verified external receipt"
            )
        try:
            freshness_receipts = self._freshness_receipts(item)
        except ExternalEvidenceVerificationError:
            group = "current_facts"
            proposal, proposal_path = emit_stale_source_proposal(
                proposal_root=self.runtime_paths.source_proposals,
                work_item_id=item.work_item_id,
                group=group,
                freshness_status="RECHECK_REQUIRED",
                now=datetime.now(UTC),
            )
            self.queue.transition(
                item.work_item_id,
                WorkStatus.WAITING_EXTERNAL,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": "WAITING_EXTERNAL",
                "workItemId": item.work_item_id,
                "reason": "signed current-fact freshness receipts are unavailable",
                "sourceProposal": str(proposal_path),
                "proposalId": proposal.proposal_id,
            }
        run_id = f"{item.work_item_id.lower()}-{now.strftime('%Y%m%dT%H%M%S%fZ')}"
        base_sha = current_sha(self.repo_root, "main")
        recovered_checkpoint = self.checkpoints.load_v3(item.work_item_id)
        worktree_base = base_sha
        if recovered_checkpoint is not None and recovered_checkpoint.active:
            ancestor = run_command(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    base_sha,
                    recovered_checkpoint.candidate_sha,
                ],
                cwd=self.repo_root,
                check=False,
            )
            if ancestor.returncode != 0:
                raise RuntimeError("recovery checkpoint candidate is not based on current main")
            worktree_base = recovered_checkpoint.candidate_sha
        budget = (
            recovered_checkpoint.budget
            if recovered_checkpoint is not None
            else CheckpointBudget(
                max_turns=64,
                max_wall_time_seconds=14_400,
                plan_attempts_remaining=item.retry_policy.max_plan_attempts,
                repair_cycles_remaining=item.retry_policy.max_candidate_repair_cycles,
                restarts_remaining=item.retry_policy.max_candidate_restarts,
            )
        )
        if budget.plan_attempts_remaining <= 0:
            if recovered_checkpoint is not None:
                recovered_checkpoint.active = False
                recovered_checkpoint.circuit_breaker_reason = "planning attempt budget exhausted"
                recovered_checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(recovered_checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.BLOCKED_TECHNICAL,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": "BLOCKED_TECHNICAL",
                "workItemId": item.work_item_id,
                "redesignProposed": True,
                "reason": "planning attempt budget exhausted",
            }
        budget.plan_attempts_remaining -= 1
        worktree = create_worktree(
            self.repo_root,
            self.repo_root / "factory/worktrees",
            task_id=item.work_item_id,
            run_id=run_id,
            role="owner",
            attempt=1,
            base_sha=worktree_base,
        )
        root = self.artifact_root / item.work_item_id / run_id
        root.mkdir(parents=True, exist_ok=True)
        checkpoint = V3Checkpoint(
            generation=(recovered_checkpoint.generation + 1 if recovered_checkpoint else 1),
            work_item_id=item.work_item_id,
            lane=item.lane,
            milestone=item.milestone,
            budget=budget,
            context_digest=sha256_digest(b"PLANNING_CONTEXT_PENDING\n"),
            source_digest=self.active_source.source_digest,
            candidate_sha=worktree_base,
            approval_state="MACHINE_POLICY_REQUIRED",
            finding_fingerprints=(
                dict(recovered_checkpoint.finding_fingerprints)
                if recovered_checkpoint is not None
                else {}
            ),
            active=True,
            created_at=(recovered_checkpoint.created_at if recovered_checkpoint else now),
            updated_at=now,
        )
        self.checkpoints.save_v3(checkpoint)
        planning_role = "factory_repair" if item.lane is Lane.FACTORY else "planner"
        try:
            planning_context = build_v3_context_manifest(
                repo_root=self.repo_root,
                work_item=item,
                role=planning_role,
                requested_groups=_context_groups(item, planning_role),
                max_context_chars=200_000,
                freshness_receipts=freshness_receipts,
                stale_proposal_root=self.runtime_paths.source_proposals,
            )
        except StaleCurrentFactError as exc:
            checkpoint.active = False
            checkpoint.circuit_breaker_reason = str(exc)
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.WAITING_EXTERNAL,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.WAITING_EXTERNAL.value,
                "workItemId": item.work_item_id,
                "reason": str(exc),
                "sourceProposal": str(exc.proposal_path) if exc.proposal_path else None,
            }
        planning_context_path = root / "context-planning.json"
        write_json(
            planning_context_path,
            planning_context.model_dump(mode="json", by_alias=True),
        )
        packet = _packet_for(
            self.repo_root,
            item,
            base_sha=base_sha,
            artifact_root=root,
            context_digest=planning_context.canonical_digest(),
            context_manifest_path=planning_context_path,
        )
        checkpoint.context_digest = packet.context_digest
        checkpoint.source_digest = packet.source_digest
        checkpoint.candidate_sha = worktree_base
        checkpoint.updated_at = datetime.now(UTC)
        self.checkpoints.save_v3(checkpoint)
        stage_bindings: list[StageArtifactBinding] = []
        bound_artifacts: dict[str, bytes] = {
            "packet": packet.canonical_json_bytes(),
            "context": planning_context.canonical_json_bytes(),
        }
        backend_session_ref: str | None = None
        candidate_sha = base_sha
        for index, role in enumerate(self._roles(item), start=1):
            role_context: V3ContextManifest = build_v3_context_manifest(
                repo_root=self.repo_root,
                work_item=item,
                role=role,
                requested_groups=_context_groups(item, role),
                max_context_chars=200_000,
                freshness_receipts=freshness_receipts,
                stale_proposal_root=self.runtime_paths.source_proposals,
            )
            role_context_path = root / f"context-{index:02d}-{role}.json"
            write_json(role_context_path, role_context.model_dump(mode="json", by_alias=True))
            role_context_digest = role_context.canonical_digest()
            role_config = load_roles(self.repo_root / "config/roles.yaml")[RoleName(role)]
            system_prompt = compose_system_prompt(
                repo_root=self.repo_root,
                global_prompt_path="prompts/global.md",
                role=role_config,
                role_name=role,
            )
            task_prompt = json.dumps(
                {
                    "taskPacket": packet.model_dump(mode="json", by_alias=True),
                    "sourceContextManifest": role_context.model_dump(
                        mode="json", by_alias=True
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            stage_bindings.append(
                StageArtifactBinding(
                    stage=role,
                    name="context-manifest",
                    digest=role_context_digest,
                )
            )
            bound_artifacts[f"stage:{role}:context-manifest"] = role_context.canonical_json_bytes()
            request = AgentTaskRequest(
                request_id=f"AREQ-{run_id.upper().replace('-', '_')}-{role.upper()}",
                work_item_id=item.work_item_id,
                role=role,
                task_packet=packet.model_dump(mode="json", by_alias=True),
                source_context_manifest={
                    **role_context.model_dump(mode="json", by_alias=True),
                    "sourceDigest": packet.source_digest,
                    "contextDigest": role_context_digest,
                    "packetDigest": packet.canonical_digest(),
                },
                allowed_paths=packet.allowed_paths,
                forbidden_paths=packet.forbidden_paths,
                tools=["Read", "Grep", "Glob", "Bash"]
                if role != "builder"
                else ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
                network_policy="DENY",
                output_schema={"type": "object"},
                controller_repo_root=str(self.repo_root),
                candidate_worktree=str(worktree.path),
                artifact_root=str(root),
                prompt=task_prompt,
                system_prompt=system_prompt,
                schema_digest=sha256_digest(b'{"type":"object"}\n'),
                context_digest=role_context_digest,
                source_digest=packet.source_digest,
                max_turns=64,
                max_tokens=96_000,
                max_cost_usd_equivalent=12.0,
                max_wall_time_seconds=14_400,
                bash_allowlist=[],
                network_allowed=False,
            )
            stage_attempt = 0
            while True:
                stage_attempt += 1
                request = request.model_copy(
                    update={"request_id": f"{request.request_id}-A{stage_attempt:02d}"}
                )
                result = await self.backend.execute(request)
                backend_session_ref = result.session.session_ref
                if result.state is SessionState.COMPLETED and result.verdict.lower() == "pass":
                    break
                fingerprint = hashlib.sha256(
                    f"{role}\n{result.verdict}\n{result.redacted_summary}\n"
                    f"{result.error_state or ''}".encode()
                ).hexdigest()
                finding_key = f"{role}:{fingerprint}"
                repeats = checkpoint.finding_fingerprints.get(finding_key, 0) + 1
                checkpoint.finding_fingerprints[finding_key] = repeats
                checkpoint.budget.repair_cycles_remaining = max(
                    0, checkpoint.budget.repair_cycles_remaining - 1
                )
                repeated = repeats >= item.retry_policy.max_same_finding_repeats
                exhausted = checkpoint.budget.repair_cycles_remaining <= 0
                checkpoint.circuit_breaker_reason = (
                    f"stage {role} finding {fingerprint[:16]} repeated {repeats} time(s)"
                )
                checkpoint.updated_at = datetime.now(UTC)
                checkpoint.backend_session_ref = backend_session_ref
                self.checkpoints.save_v3(checkpoint)
                write_v3_handoff(
                    artifact_root=root,
                    relative_path=f"recovery-handoff-{role}-{stage_attempt:02d}.json",
                    work_item=item,
                    disposition=item.disposition,
                    attempt=stage_attempt,
                    attempts_remaining=checkpoint.budget.repair_cycles_remaining,
                    base_sha=base_sha,
                    candidate_sha=current_sha(worktree.path),
                    next_action=(
                        "BOUNDED_REDESIGN_DECISION" if repeated or exhausted else "REPAIR_CANDIDATE"
                    ),
                    findings=[{"fingerprint": fingerprint, "summary": result.redacted_summary}],
                    artifacts={},
                    source_digest=checkpoint.source_digest,
                    context_digest=checkpoint.context_digest,
                    circuit_breaker_state=(
                        "OPEN" if repeated or exhausted else "RETRYING"
                    ),
                    backend_session_ref=backend_session_ref,
                )
                if repeated or exhausted:
                    checkpoint.active = False
                    self.checkpoints.save_v3(checkpoint)
                    self.queue.transition(
                        item.work_item_id,
                        WorkStatus.BLOCKED_TECHNICAL,
                        updated_at=datetime.now(UTC),
                    )
                    return {
                        "status": "BLOCKED_TECHNICAL",
                        "workItemId": item.work_item_id,
                        "findingFingerprint": fingerprint,
                        "redesignProposed": True,
                    }
            candidate_sha = current_sha(worktree.path)
            assert_candidate_scope(
                _changed_paths(self.repo_root, base_sha, candidate_sha),
                allowed_paths=packet.allowed_paths,
                forbidden_paths=packet.forbidden_paths,
            )
            for name, digest in sorted(result.artifact_digests.items()):
                artifact_path = (root / name).resolve()
                try:
                    artifact_path.relative_to(root.resolve())
                except ValueError as exc:
                    raise RuntimeError("backend artifact escaped its artifact root") from exc
                if not artifact_path.is_file() or _digest_file(artifact_path) != digest:
                    raise RuntimeError(f"backend artifact is missing or substituted: {name}")
                stage_bindings.append(StageArtifactBinding(stage=role, name=name, digest=digest))
                bound_artifacts[f"stage:{role}:{name}"] = artifact_path.read_bytes()
            checkpoint.generation += 1
            checkpoint.candidate_sha = candidate_sha
            checkpoint.backend_session_ref = backend_session_ref
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)

        checkpoint_snapshot = root / f"checkpoint-generation-{checkpoint.generation:04d}.json"
        write_json(
            checkpoint_snapshot,
            checkpoint.model_dump(mode="json", by_alias=True),
        )
        checkpoint_digest = _digest_file(checkpoint_snapshot)
        dirty = run_command(["git", "status", "--porcelain"], cwd=worktree.path, check=False)
        if dirty.returncode != 0 or dirty.stdout.strip():
            raise RuntimeError("candidate worktree must be clean and fully committed before gates")
        if not _mutating(item):
            if candidate_sha != base_sha:
                raise RuntimeError("read-only work produced a repository mutation")
            checkpoint.active = False
            checkpoint.approval_state = "READ_ONLY_EVIDENCE_RECORDED"
            self.checkpoints.save_v3(checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.PASSED_ENGINEERING,
                updated_at=datetime.now(UTC),
            )
            self._record_completion_evidence(
                item=item,
                candidate_sha=candidate_sha,
                checkpoint_digest=_digest_file(self.checkpoints.path_for(item.work_item_id)),
                manifest_digest=None,
                machine_policy_receipt_digest=None,
                independent_reviewed=any(
                    role in {"audit", "adversary", "security"} for role in self._roles(item)
                ),
                now=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.PASSED_ENGINEERING.value,
                "workItemId": item.work_item_id,
                "publication": "NOT_REQUIRED_READ_ONLY",
            }
        ancestor = run_command(
            ["git", "merge-base", "--is-ancestor", base_sha, candidate_sha],
            cwd=self.repo_root,
            check=False,
        )
        if ancestor.returncode != 0 or candidate_sha == base_sha:
            raise RuntimeError("candidate must be a non-empty descendant of its exact base")
        active_now = validate_active_source_generation(self.repo_root)
        candidate_source = validate_active_source_generation(worktree.path)
        if active_now.canonical_digest() != self.active_source.canonical_digest() or (
            candidate_source.canonical_digest() != active_now.canonical_digest()
        ):
            raise RuntimeError("candidate gate rejected changed or mixed source authority")
        gate_paths = dict(
            self.publisher.prepare_candidate(
                item=item,
                candidate_sha=candidate_sha,
                candidate_worktree=worktree.path,
            )
        )
        gate_bindings = [
            GateBinding(
                name=name,
                version="3",
                result="PASS",
                evidence_digest=_digest_file(path),
            )
            for name, path in sorted(gate_paths.items())
        ]
        if not gate_bindings:
            raise RuntimeError("release candidate has no deterministic gate evidence")
        if (
            validate_active_source_generation(worktree.path).canonical_digest()
            != active_now.canonical_digest()
        ):
            raise RuntimeError("pre-publication gate mutated active source authority")
        bound_artifacts["checkpoint"] = checkpoint_snapshot.read_bytes()
        for binding in gate_bindings:
            bound_artifacts[f"gate:{binding.name}"] = gate_paths[binding.name].read_bytes()
        manifest = CandidateManifest(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            work_item_id=item.work_item_id,
            packet_digest=packet.canonical_digest(),
            context_digest=packet.context_digest,
            executor=ExecutorIdentity(
                backend=self.backend.capabilities().backend,
                adapter=f"{type(self.backend).__module__}.{type(self.backend).__name__}",
                capability_digest=self.backend.capabilities().canonical_digest(),
                executor_session_ref=backend_session_ref,
            ),
            stage_outputs=stage_bindings,
            gates=gate_bindings,
            findings=[],
            external_evidence=[],
            checkpoint_digest=checkpoint_digest,
            release_decision=ReleaseDecision.APPROVED_FOR_AUTOMATED_PULL_REQUEST,
            created_at=datetime.now(UTC),
        )
        manifest.verify_artifacts(bound_artifacts)
        manifest_path = root / "candidate-manifest.json"
        write_json(manifest_path, manifest.model_dump(mode="json", by_alias=True))
        write_v3_handoff(
            artifact_root=root,
            relative_path="handoff.json",
            work_item=item,
            disposition=item.disposition,
            attempt=1,
            attempts_remaining=checkpoint.budget.repair_cycles_remaining,
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            next_action="OPEN_AUTOMATED_PULL_REQUEST",
            findings=[],
            artifacts={"candidateManifest": manifest_path},
            source_digest=packet.source_digest,
            context_digest=packet.context_digest,
            candidate_manifest_digest=_digest_file(manifest_path),
            backend_session_ref=backend_session_ref,
        )
        release = dict(
            # The source authority comparison above is the last fail-closed
            # publication boundary before the publisher receives the candidate.
            self.publisher.publish(
                item=item,
                candidate_ref=worktree.branch,
                candidate_sha=candidate_sha,
                candidate_worktree=worktree.path,
                candidate_manifest_path=manifest_path,
                packet_digest=packet.canonical_digest(),
                source_digest=packet.source_digest,
                context_digest=packet.context_digest,
                checkpoint_digest=checkpoint_digest,
                gate_digests={binding.name: binding.evidence_digest for binding in gate_bindings},
            )
        )
        if release.get("status") != "MERGED_MAIN_VERIFIED":
            checkpoint.active = False
            checkpoint.circuit_breaker_reason = "main publication failed hosted verification"
            self.checkpoints.save_v3(checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.BLOCKED_TECHNICAL,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.BLOCKED_TECHNICAL.value,
                "workItemId": item.work_item_id,
                "release": release,
            }
        checkpoint.active = False
        checkpoint.approval_state = "INDEPENDENT_RELEASE_VERIFIED"
        self.checkpoints.save_v3(checkpoint)
        target = (
            WorkStatus.WAITING_EXTERNAL
            if item.external_receipt_required
            else WorkStatus.PASSED_ENGINEERING
        )
        self.queue.transition(item.work_item_id, target, updated_at=datetime.now(UTC))
        if target is WorkStatus.PASSED_ENGINEERING:
            self._record_completion_evidence(
                item=item,
                candidate_sha=candidate_sha,
                checkpoint_digest=checkpoint_digest,
                manifest_digest=_digest_file(manifest_path),
                machine_policy_receipt_digest=None,
                independent_reviewed=any(
                    role in {"audit", "adversary", "security"} for role in self._roles(item)
                ),
                now=datetime.now(UTC),
            )
        return {"status": target.value, "workItemId": item.work_item_id, "release": release}

    async def run_cycle(self) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        collection = self._runtime_collection()
        self._promote_ready(collection, now)
        collection = self._runtime_collection()
        advanced = self._advance_completed_milestone(collection)
        if advanced is not None:
            collection = self._runtime_collection()
            self._promote_ready(collection, now)
            collection = self._runtime_collection()
        state = self._load_state()
        config = load_scheduler_v3(self.repo_root / "config/scheduler.yaml")
        config = config.model_copy(update={"active_milestone": collection.active_milestone})
        if collection.active_milestone != config.active_milestone:
            raise RuntimeError(
                "roadmap and scheduler active milestone mismatch: "
                f"{collection.active_milestone} != {config.active_milestone}"
            )
        active = [
            ActiveWork(
                work_item_id=item.work_item_id,
                lane=item.lane,
                mutating=_mutating(item),
            )
            for item in collection.work_items
            if item.status is WorkStatus.RUNNING
        ]
        decision: SchedulerDecisionArtifact = schedule_cycle(
            collection,
            config,
            cycle_id=f"cycle-{state.cycles + 1:08d}",
            decided_at=now,
            active_work=active,
            max_concurrent_mutating_sessions=self.factory.execution.max_concurrent_mutating_sessions,
            max_concurrent_read_only_sessions=self.factory.execution.max_concurrent_read_only_sessions,
            migration_bootstrap=collection.active_milestone == "M0_FACTORY_MIGRATED",
            lane_cursor=state.lane_cursor,
        )
        decision_path = self.runtime_paths.scheduler_decisions / f"{decision.cycle_id}.json"
        write_json(decision_path, decision.model_dump(mode="json", by_alias=True))
        waiting_external = [
            item.work_item_id
            for item in collection.work_items
            if item.status is WorkStatus.WAITING_EXTERNAL
        ]
        state.blocked_scopes = {"externalEvidence": waiting_external}
        state.cycles += 1
        state.last_decision_artifact = str(decision_path.relative_to(self.repo_root))
        lanes = list(Lane)
        state.lane_cursor = lanes[(lanes.index(state.lane_cursor) + 1) % len(lanes)]
        if not decision.selected_work_item_ids:
            self._save_state(state)
            return {
                "status": "IDLE",
                "scopedBlockers": state.blocked_scopes,
                "interventionMode": "NONE",
            }

        async def execute_selected(identifier: str) -> dict[str, object]:
            self.queue.transition(identifier, WorkStatus.QUEUED, updated_at=datetime.now(UTC))
            self.queue.claim(identifier, owner_id=self.owner_id, now=datetime.now(UTC))
            item = self.queue.load(identifier)
            return await self._execute(item, datetime.now(UTC))

        results = await asyncio.gather(
            *(execute_selected(identifier) for identifier in decision.selected_work_item_ids)
        )
        advanced = self._advance_completed_milestone(self._runtime_collection())
        if advanced is not None:
            self._promote_ready(self._runtime_collection(), datetime.now(UTC))
        state.last_work_item_id = decision.selected_work_item_ids[-1]
        state.last_candidate_sha = current_sha(self.repo_root, "main")
        self._save_state(state)
        return {
            "status": "CYCLE_COMPLETE",
            "results": results,
            "scopedBlockers": state.blocked_scopes,
            "interventionMode": "NONE",
            "activeMilestone": advanced or collection.active_milestone,
        }

    def salvage_candidate(self, work_item_id: str, destination: Path) -> Path:
        checkpoint = self.checkpoints.load_v3(work_item_id)
        if checkpoint is None:
            raise ValueError("no V3 checkpoint exists for candidate salvage")
        exists = run_command(
            ["git", "cat-file", "-e", f"{checkpoint.candidate_sha}^{{commit}}"],
            cwd=self.repo_root,
            check=False,
        )
        if exists.returncode != 0:
            raise ValueError("checkpoint candidate SHA is not locally recoverable")
        observed_candidate = current_sha(self.repo_root, checkpoint.candidate_sha)
        if observed_candidate != checkpoint.candidate_sha:
            raise ValueError("checkpoint candidate identity mismatch")
        salvage_root = (self.runtime_root / "candidate-salvage").resolve()
        destination = (
            destination.resolve()
            if destination.is_absolute()
            else (salvage_root / destination).resolve()
        )
        try:
            destination.relative_to(salvage_root)
        except ValueError as exc:
            raise ValueError(
                "candidate salvage destination escapes the bounded state root"
            ) from exc
        destination.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self.checkpoints.root / f"{work_item_id}.json"
        if not checkpoint_path.is_file():
            raise ValueError("candidate salvage checkpoint artifact is missing")
        payload = {
            "version": 3,
            "workItemId": work_item_id,
            "candidateSha": checkpoint.candidate_sha,
            "sourceDigest": checkpoint.source_digest,
            "contextDigest": checkpoint.context_digest,
            "checkpointGeneration": checkpoint.generation,
            "checkpointDigest": f"sha256:{sha256_file(checkpoint_path)}",
            "circuitBreakerReason": checkpoint.circuit_breaker_reason,
            "automaticResume": False,
            "evidenceAuthority": "LOCAL_RECOVERY_ONLY",
        }
        encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
        digest = sha256_digest(encoded).removeprefix("sha256:")
        receipt = destination / f"{work_item_id}-{checkpoint.candidate_sha[:12]}-{digest}.json"
        if receipt.exists():
            if receipt.read_bytes() != encoded:
                raise ValueError("existing salvage receipt content does not match its identity")
            return receipt
        with receipt.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        receipt.chmod(0o444)
        return receipt
