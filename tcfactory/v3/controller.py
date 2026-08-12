"""Executable V3 factory controller.

This is the only normal-operation dispatcher. Legacy T001--T124 artifacts are historical
inputs and are never loaded, scheduled, mutated, or resumed here.
"""

from __future__ import annotations

import asyncio
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
from tcfactory.context import V3ContextManifest, build_v3_context_manifest
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
from tcfactory.v3.pipeline_services import assert_candidate_scope
from tcfactory.v3.planning import V3TaskPacket, compile_work_item_packet, write_packet
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.scheduler import ActiveWork, SchedulerDecisionArtifact, schedule_cycle
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
    manifest = repo_root / "docs/source-of-truth/v3-2026-08-11/FINAL_MANIFEST_V3.json"
    criteria = item.evidence_required or [
        "The bounded work-item outcome is executable and deterministically verified."
    ]
    packet = compile_work_item_packet(
        item,
        source_documents=[
            "docs/source-of-truth/v3-2026-08-11/CODEX_MASTER_MIGRATION_PROMPT.md",
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
        source_digest=_digest_file(manifest),
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
        return ["commercial"]
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
        self.factory: FactoryV3Config = load_factory_v3(self.repo_root / "config/factory.yaml")
        runtime_root_value = os.getenv(self.factory.runtime.local_state_root_environment_variable)
        self.runtime_root = (
            Path(runtime_root_value).expanduser().resolve()
            if runtime_root_value
            else (self.repo_root / "factory/state").resolve()
        )
        self.queue = V3Queue(self.runtime_root / "v3-queue")
        self.checkpoints = CheckpointStore(self.runtime_root / "pipelines")
        self.artifact_root = self.repo_root / "factory/artifacts/v3"
        self.state_path = self.runtime_root / "v3-controller.json"

    def _load_state(self) -> ControllerState:
        if not self.state_path.exists():
            return ControllerState()
        return ControllerState.model_validate(read_json(self.state_path, {}))

    def _save_state(self, state: ControllerState) -> None:
        write_json(self.state_path, state.model_dump(mode="json", by_alias=True))

    def _roadmap(self) -> WorkItemCollection:
        return WorkItemCollection.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.work_items)
        )

    def initialize(self) -> None:
        validate_v3_configuration(self.repo_root)
        self.queue.initialize()
        self.queue.reconcile_transactions()
        self.queue.recover_expired_claims(now=datetime.now(UTC))
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

    async def _execute(self, item: WorkItem, now: datetime) -> dict[str, object]:
        if item.external_receipt_required:
            raise RuntimeError(
                "outside-fact work cannot execute; it advances only through a "
                "cryptographically verified external receipt"
            )
        run_id = f"{item.work_item_id.lower()}-{now.strftime('%Y%m%dT%H%M%SZ')}"
        base_sha = current_sha(self.repo_root, "main")
        worktree = create_worktree(
            self.repo_root,
            self.repo_root / "factory/worktrees",
            task_id=item.work_item_id,
            run_id=run_id,
            role="owner",
            attempt=1,
            base_sha=base_sha,
        )
        root = self.artifact_root / item.work_item_id / run_id
        root.mkdir(parents=True, exist_ok=True)
        planning_role = "factory_repair" if item.lane is Lane.FACTORY else "planner"
        planning_context = build_v3_context_manifest(
            repo_root=self.repo_root,
            work_item=item,
            role=planning_role,
            requested_groups=_context_groups(item, planning_role),
            max_context_chars=200_000,
        )
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
        checkpoint = V3Checkpoint(
            generation=1,
            work_item_id=item.work_item_id,
            lane=item.lane,
            milestone=item.milestone,
            budget=CheckpointBudget(
                max_turns=64,
                max_wall_time_seconds=14_400,
                plan_attempts_remaining=item.retry_policy.max_plan_attempts,
                repair_cycles_remaining=item.retry_policy.max_candidate_repair_cycles,
                restarts_remaining=item.retry_policy.max_candidate_restarts,
            ),
            context_digest=packet.context_digest,
            source_digest=packet.source_digest,
            candidate_sha=base_sha,
            approval_state="MACHINE_POLICY_REQUIRED",
            active=True,
            created_at=now,
            updated_at=now,
        )
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
            result = await self.backend.execute(request)
            backend_session_ref = result.session.session_ref
            if result.state is not SessionState.COMPLETED or result.verdict.lower() != "pass":
                checkpoint.active = False
                checkpoint.circuit_breaker_reason = f"stage {role} did not pass"
                checkpoint.budget.repair_cycles_remaining = max(
                    0, checkpoint.budget.repair_cycles_remaining - 1
                )
                self.checkpoints.save_v3(checkpoint)
                self.queue.transition(
                    item.work_item_id, WorkStatus.BLOCKED_TECHNICAL, updated_at=datetime.now(UTC)
                )
                return {"status": "BLOCKED_TECHNICAL", "workItemId": item.work_item_id}
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
            release_decision=ReleaseDecision.APPROVED_FOR_MAIN_PROMOTION,
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
            next_action="PUBLISH_MAIN_ONLY",
            findings=[],
            artifacts={"candidateManifest": manifest_path},
            source_digest=packet.source_digest,
            context_digest=packet.context_digest,
            candidate_manifest_digest=_digest_file(manifest_path),
            backend_session_ref=backend_session_ref,
        )
        release = dict(
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
        if release.get("status") != "PUBLISHED_MAIN_VERIFIED":
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
        checkpoint.approval_state = "OWNER_MACHINE_POLICY_SATISFIED"
        self.checkpoints.save_v3(checkpoint)
        target = (
            WorkStatus.WAITING_EXTERNAL
            if item.external_receipt_required
            else WorkStatus.PASSED_ENGINEERING
        )
        self.queue.transition(item.work_item_id, target, updated_at=datetime.now(UTC))
        return {"status": target.value, "workItemId": item.work_item_id, "release": release}

    async def run_cycle(self) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        collection = self._runtime_collection()
        self._promote_ready(collection, now)
        collection = self._runtime_collection()
        state = self._load_state()
        config = load_scheduler_v3(self.repo_root / "config/scheduler.yaml")
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
        decision_path = self.runtime_root / "scheduler-decisions" / f"{decision.cycle_id}.json"
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
        state.last_work_item_id = decision.selected_work_item_ids[-1]
        state.last_candidate_sha = current_sha(self.repo_root, "main")
        self._save_state(state)
        return {
            "status": "CYCLE_COMPLETE",
            "results": results,
            "scopedBlockers": state.blocked_scopes,
            "interventionMode": "NONE",
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
