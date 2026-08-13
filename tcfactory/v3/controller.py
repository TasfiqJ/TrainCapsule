"""Executable V3 factory controller.

This is the only normal-operation dispatcher. Legacy T001--T124 artifacts are historical
inputs and are never loaded, scheduled, mutated, or resumed here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Protocol

from pydantic import Field

from tcfactory.backends.base import (
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    BackendTerminalDisposition,
    BashCommandRule,
    EngineeringAgentBackend,
    ExecutionEvidenceMode,
    Handoff,
    SessionState,
)
from tcfactory.checkpoints import CheckpointBudget, CheckpointStore, V3Checkpoint
from tcfactory.completion import CompletionProposal, evaluate_v3_milestone_completion
from tcfactory.config import load_roles
from tcfactory.context import (
    StaleCurrentFactError,
    V3ContextManifest,
    build_v3_context_manifest,
)
from tcfactory.github_sync import load_github_config
from tcfactory.gitops import Worktree, create_worktree, current_sha
from tcfactory.handoffs import read_v3_handoff, write_v3_handoff
from tcfactory.models import RoleName
from tcfactory.prompts import compose_system_prompt
from tcfactory.util import atomic_write_bytes, read_json, run_command, sha256_file, write_json
from tcfactory.v3.base import (
    DIGEST_PATTERN,
    SHA_PATTERN,
    V3Model,
    sha256_digest,
)
from tcfactory.v3.candidate_freeze import (
    CandidateFreezeError,
    assert_frozen_candidate,
    quarantine_tainted_evidence,
)
from tcfactory.v3.candidate_manifest import (
    CandidateManifest,
    ExecutorIdentity,
    ExternalEvidenceBinding,
    FindingBinding,
    GateBinding,
    StageArtifactBinding,
)
from tcfactory.v3.completion_artifacts import (
    SEMANTIC_OUTPUT_SPECS,
    DeliveryEconomicsEvidence,
    FrozenReleaseEvidenceAuthorization,
    ReductionBoundaryEvidence,
    SupportPolicyEvidence,
    ThirdSameFamilyCaseEvidence,
)
from tcfactory.v3.completion_policy import (
    CompletionEvidenceObservation,
    CorrelatedEvidenceFact,
    EvidenceAuthority,
    EvidenceGrade,
    SemanticEvidence,
    evaluate_milestone_exit_criteria,
    evaluate_work_item_evidence_contract,
    load_completion_evidence_policy,
    product_lineage_digest,
)
from tcfactory.v3.completion_verification import (
    CompletionVerificationError,
    DescriptorBoundArtifactReader,
    evaluate_installed_reduction_oracle,
    verify_delivery_economics,
)
from tcfactory.v3.configuration import (
    ExternalEvidenceConfig,
    FactoryV3Config,
    load_autonomy_v3,
    load_factory_v3,
    load_scheduler_v3,
    validate_v3_configuration,
)
from tcfactory.v3.contracts_v31 import GateResult
from tcfactory.v3.controller_lock import controller_process_lock
from tcfactory.v3.enums import (
    CommercialMaturity,
    EvidenceType,
    Lane,
    MilestoneStatus,
    ReleaseDecision,
    RiskTier,
    WorkKind,
    WorkStatus,
)
from tcfactory.v3.external_actions import (
    ExternalActionOutcome,
    ExternalActionStatus,
    ExternalResponseConsumption,
)
from tcfactory.v3.external_evidence import (
    ExternalEvidenceReceipt,
    ExternalEvidenceVerificationError,
    load_verified_external_evidence,
    load_verified_external_evidence_payload,
)
from tcfactory.v3.installed_runtime import (
    InstalledControllerRuntimeManifest,
    load_installed_controller_runtime,
)
from tcfactory.v3.machine_policy_runtime import (
    AuthorizedMachinePolicyReviewV31,
    MachinePolicyRuntimeError,
    load_authorized_machine_policy_review,
)
from tcfactory.v3.market_artifacts import ReachableAccountMap
from tcfactory.v3.maturity import (
    commercial_maturity_supported,
    derive_commercial_maturity_authorization,
)
from tcfactory.v3.milestone_runtime import (
    WorkItemCompletionEvidence,
    advance_milestone_state,
    initialize_milestone_state,
    load_work_item_completion_evidence,
    write_work_item_completion_evidence,
)
from tcfactory.v3.milestones import MilestoneRoadmap
from tcfactory.v3.native_value_runtime import (
    BENCHMARK_BINDING,
    BENCHMARK_FILE,
    POLICY_BINDING,
    POLICY_FILE,
    VALUE_RESULT_BINDING,
    VALUE_RESULT_FILE,
    ContentAddressedRuntimeArtifacts,
    ExternalPhase3NativeValueAuthority,
    NativeValueRuntimeError,
    RuntimeAuthorizedNativeValueV31,
    load_authorized_native_value_transition,
)
from tcfactory.v3.phase6_runtime import (
    Phase6ControllerRuntime,
    Phase6RuntimeError,
    ResearchAdvisoryBundle,
)
from tcfactory.v3.pipeline_services import assert_candidate_scope
from tcfactory.v3.planning import V3TaskPacket, compile_work_item_packet, write_packet
from tcfactory.v3.publication import (
    ExternalReceiptAuthorizer,
    PublicationError,
)
from tcfactory.v3.queue import V3Queue
from tcfactory.v3.recovery import (
    value_redesign_failure,
    write_value_redesign_proposal,
)
from tcfactory.v3.runtime_paths import ensure_v3_mutable_runtime, resolve_v3_runtime_paths
from tcfactory.v3.scheduler import (
    CORE_SCHEDULING_LANES,
    ActiveWork,
    SchedulerDecisionArtifact,
    schedule_cycle,
)
from tcfactory.v3.source_authority import (
    emit_stale_source_proposal,
    validate_active_source_generation,
)
from tcfactory.v3.task_compiler_v31 import (
    AgentExecutionReportV31,
    ExecutionVerdict,
    compile_task_contract_v31,
    execution_report_schema,
    lane_path_policy_v31,
    output_declarations_for_item_v31,
    tool_policy_for_request,
    validate_execution_report_v31,
)
from tcfactory.v3.traincheck_differential import (
    TrainCheckDifferentialRequest,
    TrainCheckDifferentialResult,
    VerifiedMachineReceiptTrainCheckOracle,
    authorize_traincheck_differential,
    replay_traincheck_differential,
)
from tcfactory.v3.verifier_submission import (
    VerifierSubmissionError,
    create_and_submit_verification_request,
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
        expected_candidate_tree_sha: str,
        expected_machine_policy_receipt_id: str | None = None,
        expected_machine_policy_receipt_digest: str | None = None,
        expected_release_authorization_envelope_digest: str | None = None,
        lease_guard: Callable[[], None] | None = None,
    ) -> Mapping[str, object]: ...


class ControllerState(V3Model):
    version: int = Field(default=3, ge=3, le=3)
    cycles: int = Field(default=0, ge=0)
    lane_cursor: Lane = Lane.PRODUCT
    last_decision_artifact: str | None = None
    last_work_item_id: str | None = None
    last_candidate_sha: str | None = None
    blocked_scopes: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    deployment_update_handoff: str | None = None
    deployment_update_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)


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
    return lane_path_policy_v31(item)


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
        outputs=[output.path for output in output_declarations_for_item_v31(item)],
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
        WorkKind.RESEARCH,
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
        phase6_runtime: Phase6ControllerRuntime | None = None,
        lease_renewal_interval_seconds: float = 10.0,
        installed_runtime_loader: Callable[[], InstalledControllerRuntimeManifest] | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.backend = backend
        self.publisher = publisher
        self.owner_id = owner_id
        self.phase6_runtime = phase6_runtime
        self.installed_runtime_loader = installed_runtime_loader
        if self.installed_runtime_loader is None and self.repo_root == Path(
            "/var/lib/traincapsule-verifier/repository-boundary"
        ):
            self.installed_runtime_loader = lambda: load_installed_controller_runtime()[0]
        if lease_renewal_interval_seconds <= 0:
            raise ValueError("lease renewal interval must be positive")
        self.lease_renewal_interval_seconds = lease_renewal_interval_seconds
        self.active_source = validate_active_source_generation(self.repo_root)
        self.factory: FactoryV3Config = load_factory_v3(self.repo_root / "config/factory.yaml")
        self.autonomy = load_autonomy_v3(self.repo_root / "config/autonomy.yaml")
        self.runtime_paths = resolve_v3_runtime_paths(self.repo_root, self.factory)
        ensure_v3_mutable_runtime(
            self.repo_root,
            self.runtime_paths,
            require_snapshot_alignment=False,
        )
        self.runtime_root = self.runtime_paths.state_root
        self.git_root = self.runtime_paths.git_root
        self.queue = V3Queue(self.runtime_paths.queue)
        self.checkpoints = CheckpointStore(self.runtime_paths.checkpoints)
        self.artifact_root = self.runtime_paths.artifact_root
        self.state_path = self.runtime_paths.controller_state
        self._active_lease_ids: dict[str, str] = {}

    def _renew_active_lease(self, work_item_id: str) -> None:
        lease_id = self._active_lease_ids.get(work_item_id)
        if lease_id is None:
            raise RuntimeError("publication boundary has no active work-item lease")
        try:
            self.queue.renew(
                work_item_id,
                lease_id=lease_id,
                now=datetime.now(UTC),
            )
        except BaseException as error:
            self._quarantine_lease_loss(work_item_id, error)
            raise RuntimeError(
                f"lease renewal failed for {work_item_id}; execution quarantined"
            ) from error

    def _quarantine_lease_loss(self, work_item_id: str, error: BaseException | None) -> None:
        item = self.queue.load(work_item_id)
        if item.status is WorkStatus.RUNNING:
            self.queue.transition(
                work_item_id,
                WorkStatus.BLOCKED_TECHNICAL,
                updated_at=datetime.now(UTC),
            )
        checkpoint = self.checkpoints.load_v3(work_item_id)
        if checkpoint is None:
            return
        checkpoint.active = False
        checkpoint.approval_state = "LEASE_LOST_QUARANTINED"
        checkpoint.circuit_breaker_reason = (
            "lease renewal failed; execution and candidate quarantined"
        )
        checkpoint.updated_at = datetime.now(UTC)
        self.checkpoints.save_v3(checkpoint)
        if checkpoint.artifact_root:
            artifact = Path(checkpoint.artifact_root).resolve()
            if artifact.is_relative_to(self.artifact_root.resolve()) and artifact.exists():
                evidence = {
                    str(path.relative_to(artifact)): path
                    for path in artifact.rglob("*")
                    if path.is_file()
                }
                quarantine_tainted_evidence(
                    evidence,
                    quarantine_root=(self.runtime_paths.quarantine / "lease-loss" / work_item_id),
                    reason=(
                        f"lease renewal failed: {type(error).__name__ if error else 'stopped'}"
                    ),
                )

    async def execute_claimed(
        self, item: WorkItem, *, lease_id: str, now: datetime
    ) -> dict[str, object]:
        """Execute one already-claimed item while binding all side effects to its lease."""

        if item.status is not WorkStatus.RUNNING:
            raise RuntimeError("direct execution requires an exact RUNNING queue claim")
        if item.work_item_id in self._active_lease_ids:
            raise RuntimeError("work item already has an active execution lease")
        self._active_lease_ids[item.work_item_id] = lease_id
        try:
            return await self._execute(item, now)
        finally:
            self._active_lease_ids.pop(item.work_item_id, None)

    def _load_state(self) -> ControllerState:
        if not self.state_path.exists():
            return ControllerState()
        return ControllerState.model_validate(read_json(self.state_path, {}))

    def _save_state(self, state: ControllerState) -> None:
        write_json(self.state_path, state.model_dump(mode="json", by_alias=True))

    def _require_installed_snapshot_alignment(self, *, state: ControllerState) -> None:
        """Stop before claims when installed authority/runtime trails verified main."""

        installed_main = current_sha(self.repo_root, "refs/heads/main")
        installed_tree = current_sha(self.repo_root, f"{installed_main}^{{tree}}")
        anchored_main = current_sha(self.git_root, "refs/heads/main")
        anchored_tree = current_sha(self.git_root, f"{anchored_main}^{{tree}}")
        handoff_root = self.runtime_root / "deployment-update-handoffs"
        runtime: InstalledControllerRuntimeManifest | None = None
        runtime_attested = self.installed_runtime_loader is None
        if self.installed_runtime_loader is not None:
            try:
                runtime = self.installed_runtime_loader()
                runtime_attested = (
                    runtime.repository_main_sha == installed_main == anchored_main
                    and runtime.repository_tree_sha == installed_tree == anchored_tree
                )
            except RuntimeError:
                runtime_attested = False
        if (installed_main, installed_tree) == (anchored_main, anchored_tree) and runtime_attested:
            if state.deployment_update_handoff is not None:
                state.deployment_update_handoff = None
                state.deployment_update_digest = None
                self._save_state(state)
            return
        payload = {
            "schemaVersion": "3.1",
            "disposition": "DEPLOYMENT_UPDATE_REQUIRED",
            "installedMainSha": installed_main,
            "installedMainTreeSha": installed_tree,
            "requiredMainSha": anchored_main,
            "requiredMainTreeSha": anchored_tree,
            "sourceGenerationId": self.active_source.generation_id,
            "sourceGenerationDigest": self.active_source.source_digest,
            "controllerRuntimeMayExecuteRequiredMain": False,
            "installedRuntimeAttested": runtime_attested,
            "installedRuntimeManifestDigest": (
                runtime.manifest_digest if runtime is not None else None
            ),
            "nextAction": "INSTALL_SIGNED_SNAPSHOT_RUNTIME_AT_REQUIRED_MAIN",
        }
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        digest = sha256_digest(encoded)
        handoff = handoff_root / f"{anchored_main}-{digest[7:23]}.json"
        if handoff.is_file():
            if handoff.read_bytes() != encoded:
                raise RuntimeError("deployment-update handoff identity conflicts")
        else:
            handoff_root.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(handoff, encoded)
        state.deployment_update_handoff = str(handoff.resolve(strict=True))
        state.deployment_update_digest = digest
        self._save_state(state)
        raise RuntimeError(
            "DEPLOYMENT_UPDATE_REQUIRED: mutable main is newer than the installed "
            "signed snapshot/runtime; no new work may be claimed"
        )

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

    def _controller_semantic_evidence(
        self,
        *,
        item: WorkItem,
        checkpoint: V3Checkpoint | None,
        base_sha: str,
        candidate_sha: str,
        candidate_manifest_path: Path | None,
    ) -> tuple[dict[SemanticEvidence, list[str]], dict[str, str]]:
        """Derive semantics only from strict controller-bound artifact bytes."""

        if checkpoint is None:
            return {}, {}
        semantic_refs: dict[SemanticEvidence, list[str]] = {}
        artifact_bindings: dict[str, str] = {}
        if item.work_item_id == "V3-MKT-001":
            key = "controller:research-typed-reachable-account-map"
            path_text = checkpoint.stage_artifact_paths.get(key)
            expected_digest = checkpoint.stage_artifact_digests.get(key)
            if path_text is None or expected_digest is None:
                raise RuntimeError("reachable-account evidence is not controller-bound")
            path = Path(path_text).resolve()
            try:
                path.relative_to(self.artifact_root.resolve())
            except ValueError as exc:
                raise RuntimeError("reachable-account evidence escaped the artifact root") from exc
            if path.is_symlink() or not path.is_file() or _digest_file(path) != expected_digest:
                raise RuntimeError("reachable-account evidence bytes changed")
            account_map = ReachableAccountMap.model_validate_json(path.read_bytes(), strict=True)
            if account_map.work_item_id != item.work_item_id or account_map.candidate_sha not in {
                base_sha,
                candidate_sha,
            }:
                raise RuntimeError("reachable-account evidence identity mismatch")
            qualified_accounts = [
                account
                for account in account_map.accounts
                if account.organization.verdict.value == "CLEAR"
                and account.relationship_path.verdict.value == "CLEAR"
                and account.organization.value is not None
                and account.relationship_path.value is not None
                and account.organization.source_artifact_digests
                and account.relationship_path.source_artifact_digests
            ]
            unique_names = {
                account.organization.value.casefold(): account
                for account in qualified_accounts
                if account.organization.value is not None
            }
            semantic_refs[SemanticEvidence.REACHABLE_ACCOUNT] = sorted(
                account.canonical_digest() for account in unique_names.values()
            )
            semantic_refs[SemanticEvidence.ATTRIBUTABLE_SOURCE] = sorted(
                {
                    digest
                    for account in unique_names.values()
                    for field in (account.organization, account.relationship_path)
                    for digest in field.source_artifact_digests
                }
            )
            artifact_bindings[str(path)] = expected_digest

        spec = SEMANTIC_OUTPUT_SPECS.get(item.work_item_id)
        if spec is not None:
            suffix = f":materialized-output:{spec.output_id}"
            keys = [key for key in checkpoint.stage_artifact_paths if key.endswith(suffix)]
            semantic_label = "/".join(spec.semantic_names)
            if len(keys) != 1:
                raise RuntimeError(f"{semantic_label} evidence has no unique validated output")
            key = keys[0]
            path = Path(checkpoint.stage_artifact_paths[key]).resolve()
            expected_digest = checkpoint.stage_artifact_digests.get(key)
            try:
                path.relative_to(self.artifact_root.resolve())
            except ValueError as exc:
                raise RuntimeError(f"{semantic_label} evidence escaped the artifact root") from exc
            if (
                expected_digest is None
                or path.is_symlink()
                or not path.is_file()
                or _digest_file(path) != expected_digest
            ):
                raise RuntimeError(f"{semantic_label} evidence bytes changed")
            record = spec.model.model_validate_json(path.read_bytes(), strict=True)
            if (
                getattr(record, "work_item_id", None) != item.work_item_id
                or getattr(record, "evidence_basis_sha", None) != base_sha
                or getattr(record, "source_authority_digest", None)
                != self.active_source.canonical_digest()
            ):
                raise RuntimeError(f"{semantic_label} evidence identity mismatch")
            artifact_paths_by_digest = {
                digest: Path(checkpoint.stage_artifact_paths[stage_key]).resolve()
                for stage_key, digest in checkpoint.stage_artifact_digests.items()
                if stage_key in checkpoint.stage_artifact_paths
            }
            artifact_reader = DescriptorBoundArtifactReader(
                self.artifact_root, artifact_paths_by_digest
            )
            if isinstance(record, ReductionBoundaryEvidence):
                installed_runtime_loader = getattr(self, "installed_runtime_loader", None)
                if installed_runtime_loader is None or candidate_manifest_path is None:
                    raise RuntimeError("reduction oracle installation is unavailable")
                try:
                    installed_runtime = installed_runtime_loader()
                except RuntimeError as exc:
                    raise RuntimeError("reduction oracle installation is unavailable") from exc
                tree = run_command(
                    ["git", "rev-parse", f"{candidate_sha}^{{tree}}"],
                    cwd=self.git_root,
                    check=False,
                )
                if tree.returncode != 0 or SHA_PATTERN.fullmatch(tree.stdout.strip()) is None:
                    raise RuntimeError("reduction oracle candidate tree is unavailable")
                try:
                    authorized, receipt_raw = evaluate_installed_reduction_oracle(
                        record,
                        installed_runtime=installed_runtime,
                        candidate_manifest_path=candidate_manifest_path,
                        candidate_sha=candidate_sha,
                        candidate_tree_sha=tree.stdout.strip(),
                        base_sha=base_sha,
                        source_generation_id=self.active_source.generation_id,
                        source_generation_digest=self.active_source.canonical_digest(),
                        artifacts=artifact_reader,
                        now=datetime.now(UTC),
                    )
                except CompletionVerificationError as exc:
                    raise RuntimeError(str(exc)) from exc
                receipt_path = path.parent / "reduction-oracle-receipt.json"
                atomic_write_bytes(receipt_path, receipt_raw)
                receipt_digest = _digest_file(receipt_path)
                if authorized.decision.oracle_result_digest != record.oracle_result_digest:
                    raise RuntimeError("reduction oracle result does not match evidence")
                installation = installed_runtime.reduction_oracle
                assert installation is not None
                machine_receipt_path = (
                    Path(installation.public_receipt_root)
                    / "machine-policy"
                    / item.work_item_id
                    / f"{candidate_sha}.json"
                )
                artifact_bindings[str(receipt_path.resolve())] = receipt_digest
                authority_snapshots = {
                    "oracle-executable.bin": (
                        Path(installation.executable.path),
                        installation.executable.digest,
                    ),
                    "oracle-public-key.bin": (
                        Path(installation.public_key.path),
                        installation.public_key.digest,
                    ),
                    "oracle-machine-policy-receipt.json": (
                        machine_receipt_path,
                        authorized.machine_policy_receipt_digest,
                    ),
                    "oracle-live-activation.json": (
                        Path(installation.activation_receipt_path),
                        authorized.activation_receipt_digest,
                    ),
                }
                for name, (authority_path, authority_digest) in authority_snapshots.items():
                    authority_raw = authority_path.read_bytes()
                    if sha256_digest(authority_raw) != authority_digest:
                        raise RuntimeError("reduction authority changed after verification")
                    snapshot_path = path.parent / name
                    atomic_write_bytes(snapshot_path, authority_raw)
                    artifact_bindings[str(snapshot_path.resolve())] = authority_digest
                for digest in record.raw_artifact_digests:
                    raw_path = artifact_paths_by_digest.get(digest)
                    if raw_path is None:
                        raise RuntimeError("reduction raw artifact is not checkpoint-bound")
                    artifact_bindings[str(raw_path)] = digest
            if isinstance(record, DeliveryEconomicsEvidence):
                external = ExternalEvidenceConfig.model_validate(
                    load_yaml(self.repo_root / "config/external_evidence.yaml")
                )
                try:
                    trusted = load_verified_external_evidence(
                        repo_root=self.repo_root,
                        subject_id=item.work_item_id,
                        trusted_root_environment_variable=(
                            external.trusted_root_environment_variable
                        ),
                        trusted_public_key_environment_variable=(
                            external.trusted_public_key_environment_variable
                        ),
                    )
                    receipt = trusted.require_commercial_trust()
                    verify_delivery_economics(record, artifacts=artifact_reader, receipt=receipt)
                except (ExternalEvidenceVerificationError, CompletionVerificationError) as exc:
                    raise RuntimeError(str(exc)) from exc
                for digest in record.source_record_digests:
                    raw_path = artifact_paths_by_digest.get(digest)
                    if raw_path is None:
                        raise RuntimeError("delivery measurement is not checkpoint-bound")
                    artifact_bindings[str(raw_path)] = digest
            if isinstance(record, ThirdSameFamilyCaseEvidence):
                external_paths = [
                    Path(value).resolve()
                    for key, value in checkpoint.stage_artifact_paths.items()
                    if key.startswith("external_evidence:")
                ]
                if len(external_paths) != 1:
                    raise RuntimeError("third same-family evidence lacks one authoritative receipt")
                external_receipt = ExternalEvidenceReceipt.model_validate_json(
                    external_paths[0].read_bytes(), strict=True
                )
                if external_receipt.evidence_type is not EvidenceType.SAME_FAMILY_CASE:
                    raise RuntimeError("third same-family receipt has the wrong type")
                correlation = external_receipt.correlation_identity
                if (
                    correlation is None
                    or correlation.candidate_sha != candidate_sha
                    or correlation.customer_identity_digest != record.customer_identity_digest
                    or correlation.family_identity_digest != record.family_identity_digest
                    or correlation.pack_identity_digest != record.reusable_pack_digest
                ):
                    raise RuntimeError("third same-family receipt correlation identity mismatch")
                artifact_digests = {artifact.digest for artifact in external_receipt.artifacts}
                if set(record.case_evidence_artifact_digests) - artifact_digests:
                    raise RuntimeError(
                        "third same-family cases are absent from the trusted receipt"
                    )
            for semantic_name in spec.semantic_names:
                semantic_refs[SemanticEvidence(semantic_name)] = [expected_digest]
            artifact_bindings[str(path)] = expected_digest
        return semantic_refs, artifact_bindings

    @staticmethod
    def _external_receipt_semantic_evidence(
        receipt: ExternalEvidenceReceipt,
    ) -> dict[SemanticEvidence, int]:
        attestation = receipt.customer_decision_value
        if receipt.evidence_type is not EvidenceType.DECISION_CHANGED or attestation is None:
            return {}
        observed: dict[SemanticEvidence, int] = {}
        if attestation.decision_changed_or_materially_strengthened:
            observed[SemanticEvidence.CUSTOMER_DECISION_CHANGED] = 1
        if attestation.value_exceeds_price_and_retained_effort:
            observed[SemanticEvidence.CUSTOMER_VALUE_EXCEEDS_PRICE_RETAINED_EFFORT] = 1
        return observed

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
        additional_evidence_refs: Sequence[str] = (),
        semantic_evidence_refs: Mapping[SemanticEvidence, Sequence[str]] | None = None,
    ) -> Path:
        tree = run_command(
            ["git", "rev-parse", f"{candidate_sha}^{{tree}}"],
            cwd=self.git_root,
            check=False,
        )
        candidate_tree_sha = tree.stdout.strip()
        if tree.returncode != 0 or SHA_PATTERN.fullmatch(candidate_tree_sha) is None:
            raise RuntimeError("completion evidence candidate tree is unavailable")
        checkpoint_path: Path | None = None
        current_checkpoint = self.checkpoints.path_for(item.work_item_id)
        artifact_candidates = [
            current_checkpoint,
            *sorted((self.artifact_root / item.work_item_id).rglob("checkpoint-generation-*.json")),
        ]
        for candidate in artifact_candidates:
            if candidate.is_file() and _digest_file(candidate) == checkpoint_digest:
                checkpoint_path = candidate.resolve()
                break
        manifest_path: Path | None = None
        base_sha = candidate_sha
        if manifest_digest is not None:
            for candidate in sorted(
                (self.artifact_root / item.work_item_id).rglob("candidate-manifest.json")
            ):
                if candidate.is_file() and _digest_file(candidate) == manifest_digest:
                    manifest_path = candidate.resolve()
                    manifest = CandidateManifest.model_validate(read_json(candidate, {}))
                    if (
                        manifest.work_item_id != item.work_item_id
                        or manifest.candidate_sha != candidate_sha
                    ):
                        raise RuntimeError("completion candidate manifest identity mismatch")
                    base_sha = manifest.base_sha
                    break
            if manifest_path is None:
                raise RuntimeError("completion candidate manifest bytes are unavailable")
        independent_review_artifacts: dict[str, str] = {}
        checkpoint = self.checkpoints.load_v3(item.work_item_id)
        if checkpoint is not None:
            for key, path_text in sorted(checkpoint.stage_artifact_paths.items()):
                role = key.split(":", 1)[0]
                if role not in {"audit", "adversary", "security"}:
                    continue
                path = Path(path_text).resolve()
                if not path.is_file():
                    raise RuntimeError("independent review artifact is missing")
                digest = checkpoint.stage_artifact_digests.get(key)
                observed_digest = (
                    V3ContextManifest.model_validate(read_json(path, {})).canonical_digest()
                    if key.endswith(":context-manifest")
                    else _digest_file(path)
                )
                if digest is None or observed_digest != digest:
                    raise RuntimeError("independent review artifact digest mismatch")
                independent_review_artifacts[str(path)] = digest
        if independent_reviewed and not independent_review_artifacts:
            raise RuntimeError("independent review claim lacks byte-bound review artifacts")
        machine_policy_receipt_path: Path | None = None
        bound_machine_policy_receipt_digest: str | None = None
        if machine_policy_receipt_digest is not None:
            github = load_github_config(self.repo_root / "config/github.yaml")
            machine_policy_receipt_path = (
                Path(github.independent_receipt_root)
                / "machine-policy"
                / item.work_item_id
                / f"{candidate_sha}.json"
            ).resolve()
            if machine_policy_receipt_path.is_file():
                bound_machine_policy_receipt_digest = machine_policy_receipt_digest
            else:
                machine_policy_receipt_path = None
        semantic_refs: dict[SemanticEvidence, list[str]] = {
            SemanticEvidence.DETERMINISTIC_ARTIFACT: [checkpoint_digest]
        }
        trusted_additional_refs = list(additional_evidence_refs)
        derived_semantics, semantic_artifact_bindings = self._controller_semantic_evidence(
            item=item,
            checkpoint=checkpoint,
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            candidate_manifest_path=manifest_path,
        )
        for semantic, digests in derived_semantics.items():
            semantic_refs.setdefault(semantic, []).extend(digests)
        if manifest_digest is not None:
            semantic_refs[SemanticEvidence.CANDIDATE_MANIFEST] = [manifest_digest]
        if independent_review_artifacts:
            semantic_refs[SemanticEvidence.INDEPENDENT_REVIEW] = sorted(
                set(independent_review_artifacts.values())
            )
        if bound_machine_policy_receipt_digest is not None:
            semantic_refs[SemanticEvidence.MACHINE_POLICY_DECISION] = [
                bound_machine_policy_receipt_digest
            ]
        release_envelope_path: Path | None = None
        release_envelope_digest: str | None = None
        if checkpoint is not None and (
            checkpoint.publication_authorization_envelope_path is not None
            or checkpoint.publication_authorization_envelope_digest is not None
        ):
            if (
                checkpoint.publication_authorization_envelope_path is None
                or checkpoint.publication_authorization_envelope_digest is None
            ):
                raise RuntimeError("release authorization envelope binding is incomplete")
            release_envelope_path = Path(
                checkpoint.publication_authorization_envelope_path
            ).resolve()
            release_envelope_digest = checkpoint.publication_authorization_envelope_digest
            if (
                release_envelope_path.is_symlink()
                or not release_envelope_path.is_file()
                or _digest_file(release_envelope_path) != release_envelope_digest
            ):
                raise RuntimeError("release authorization envelope bytes changed")
            semantic_artifact_bindings[str(release_envelope_path)] = release_envelope_digest
        prefix_semantics = {
            "native-value-authorization": SemanticEvidence.NATIVE_VALUE_AUTHORIZATION,
            "traincheck-differential": SemanticEvidence.TRAINCHECK_INCIDENT_DIFFERENTIAL,
            "support-policy": SemanticEvidence.SUPPORT_POLICY,
            "delivery-economics": SemanticEvidence.DELIVERY_ECONOMICS,
            "third-same-family-case": SemanticEvidence.THIRD_SAME_FAMILY_CASE,
            "reachable-account": SemanticEvidence.REACHABLE_ACCOUNT,
            "attributable-source": SemanticEvidence.ATTRIBUTABLE_SOURCE,
        }
        for reference in additional_evidence_refs:
            prefix, separator, digest = reference.partition(":")
            semantic = prefix_semantics.get(prefix)
            if separator and semantic is not None and DIGEST_PATTERN.fullmatch(digest):
                semantic_refs.setdefault(semantic, []).append(digest)
        for semantic, digests in (semantic_evidence_refs or {}).items():
            semantic_refs.setdefault(semantic, []).extend(digests)
        semantic_refs = {
            semantic: sorted(set(digests)) for semantic, digests in semantic_refs.items()
        }
        evidence = WorkItemCompletionEvidence(
            work_item_id=item.work_item_id,
            milestone_id=item.milestone,
            candidate_sha=candidate_sha,
            base_sha=base_sha,
            candidate_tree_sha=candidate_tree_sha,
            source_authority_digest=self.active_source.canonical_digest(),
            evidence_mode=(
                ExecutionEvidenceMode.EXTERNAL_VALIDATION
                if item.external_receipt_required
                or any(
                    reference.startswith("external-receipt:")
                    for reference in trusted_additional_refs
                )
                else checkpoint.execution_evidence_mode
                if checkpoint is not None and checkpoint.execution_evidence_mode is not None
                else ExecutionEvidenceMode.SIMULATION
            ),
            checkpoint_digest=checkpoint_digest,
            checkpoint_path=checkpoint_path,
            candidate_manifest_digest=manifest_digest,
            candidate_manifest_path=manifest_path,
            independent_review_artifacts=independent_review_artifacts,
            machine_policy_receipt_digest=bound_machine_policy_receipt_digest,
            machine_policy_receipt_path=machine_policy_receipt_path,
            release_authorization_envelope_digest=release_envelope_digest,
            release_authorization_envelope_path=release_envelope_path,
            external_receipt_refs=[*item.external_evidence_refs, *trusted_additional_refs],
            semantic_evidence_refs=semantic_refs,
            semantic_artifact_bindings=semantic_artifact_bindings,
            created_at=now,
        )
        return write_work_item_completion_evidence(self.runtime_paths.milestone_evidence, evidence)

    def _advance_completed_milestone(self, collection: WorkItemCollection) -> str | None:
        active_source = validate_active_source_generation(self.repo_root)
        active = [
            item for item in collection.work_items if item.milestone == collection.active_milestone
        ]
        if not active or any(
            item.status not in {WorkStatus.PASSED_ENGINEERING, WorkStatus.COMPLETED}
            for item in active
        ):
            return None
        evidence_digests: dict[str, str] = {}
        deterministic_evidence: dict[str, list[str]] = {}
        independent_review_refs: list[str] = []
        machine_policy_receipt_refs: list[str] = []
        trusted_external_receipt_refs: list[str] = []
        contract_failures: list[str] = []
        milestone_external_counts: dict[EvidenceType, int] = {}
        milestone_external_names: set[str] = set()
        milestone_external_digests: set[str] = set()
        milestone_external_identities: set[tuple[str, str, str]] = set()
        milestone_semantic_counts: dict[SemanticEvidence, int] = {}
        milestone_correlated_facts: list[CorrelatedEvidenceFact] = []
        milestone_verified_receipt_digests: set[str] = set()
        expected_product_lineage = product_lineage_digest(active_source.canonical_digest())
        completion_policy = load_completion_evidence_policy(self.repo_root)
        milestone_contract = completion_policy.milestone(collection.active_milestone)
        required_evidence_item_ids = {
            item.work_item_id for item in active
        } | {
            work_item_id
            for criterion in milestone_contract.exit_criteria
            for work_item_id in criterion.required_work_item_ids
        }
        if collection.active_milestone == "M6_COMMERCIALLY_SUPPORTED_PACK":
            required_evidence_item_ids.update(
                {
                    "V3-PILOT-003",
                    "V3-PILOT-011",
                    "V3-REPEAT-001",
                    "V3-REPEAT-005",
                    "V3-REPEAT-006",
                    "V3-PACK-002",
                    "V3-PROD-029",
                    "V3-MKT-011",
                }
            )
        evidence_items = [
            collection.item(work_item_id)
            for work_item_id in sorted(required_evidence_item_ids)
        ]
        external = ExternalEvidenceConfig.model_validate(
            load_yaml(self.repo_root / "config/external_evidence.yaml")
        )
        github = load_github_config(self.repo_root / "config/github.yaml")
        for item in evidence_items:
            item_contract = completion_policy.work_item(item.work_item_id)
            loaded = load_work_item_completion_evidence(
                self.runtime_paths.milestone_evidence, item.work_item_id
            )
            if loaded is None:
                continue
            evidence, digest = loaded
            if (
                evidence.work_item_id != item.work_item_id
                or evidence.milestone_id != item.milestone
                or evidence.source_authority_digest != active_source.canonical_digest()
            ):
                raise RuntimeError("milestone evidence identity mismatch")
            minimum_mode = (
                ExecutionEvidenceMode.EXTERNAL_VALIDATION
                if item.external_receipt_required
                else ExecutionEvidenceMode.CONTROLLED_VALIDATION
            )
            evidence_rank = {
                ExecutionEvidenceMode.SIMULATION: 0,
                ExecutionEvidenceMode.CONTROLLED_VALIDATION: 1,
                ExecutionEvidenceMode.LIVE_VALIDATION: 2,
                ExecutionEvidenceMode.EXTERNAL_VALIDATION: 3,
            }
            if evidence_rank[evidence.evidence_mode] < evidence_rank[minimum_mode]:
                continue
            bound_digests = [digest]
            observed_authorities = {EvidenceAuthority.CONTROLLER}
            checkpoint_record: V3Checkpoint | None = None
            semantic_counts = {
                semantic: len(digests)
                for semantic, digests in evidence.semantic_evidence_refs.items()
            }
            for semantic, count in semantic_counts.items():
                milestone_semantic_counts[semantic] = (
                    milestone_semantic_counts.get(semantic, 0) + count
                )
            external_type_counts: dict[EvidenceType, int] = {}
            prior_evidence: dict[str, list[SemanticEvidence]] = {}
            item_correlated_facts: list[CorrelatedEvidenceFact] = []
            item_verified_receipt_digests: set[str] = set()
            pending_semantic_facts: list[
                tuple[
                    SemanticEvidence,
                    str,
                    str | None,
                    str | None,
                    str | None,
                    str | None,
                ]
            ] = []
            if evidence.checkpoint_path is not None:
                checkpoint_path = evidence.checkpoint_path.resolve()
                try:
                    checkpoint_path.relative_to(self.runtime_root.resolve())
                except ValueError:
                    try:
                        checkpoint_path.relative_to(self.artifact_root.resolve())
                    except ValueError as exc:
                        raise RuntimeError(
                            "milestone checkpoint evidence escaped bounded runtime roots"
                        ) from exc
                if (
                    checkpoint_path.is_symlink()
                    or not checkpoint_path.is_file()
                    or _digest_file(checkpoint_path) != evidence.checkpoint_digest
                ):
                    raise RuntimeError("milestone checkpoint bytes changed")
                checkpoint_record = V3Checkpoint.model_validate(read_json(checkpoint_path, {}))
                bound_digests.append(evidence.checkpoint_digest)
            elif not item.external_receipt_required:
                raise RuntimeError("milestone evidence omitted its checkpoint bytes")
            semantic_paths = {
                SemanticEvidence.NATIVE_VALUE_AUTHORIZATION: "authorization-envelope",
                SemanticEvidence.TRAINCHECK_INCIDENT_DIFFERENTIAL: "traincheck:result",
            }
            for semantic, stage_name in semantic_paths.items():
                if semantic not in semantic_counts:
                    continue
                if checkpoint_record is None:
                    raise RuntimeError(f"{semantic.value} evidence lacks its checkpoint")
                stage_key = f"machine_policy:{stage_name}"
                stage_path_text = checkpoint_record.stage_artifact_paths.get(stage_key)
                stage_digest = checkpoint_record.stage_artifact_digests.get(stage_key)
                if stage_path_text is None or stage_digest is None:
                    raise RuntimeError(f"{semantic.value} evidence lacks bound bytes")
                stage_path = Path(stage_path_text).resolve()
                if stage_path.is_symlink() or not stage_path.is_file():
                    raise RuntimeError(f"{semantic.value} evidence bytes are missing")
                if (
                    _digest_file(stage_path) != stage_digest
                    or stage_digest not in (evidence.semantic_evidence_refs[semantic])
                ):
                    raise RuntimeError(f"{semantic.value} evidence bytes changed")
            for path_text, expected_digest in sorted(evidence.semantic_artifact_bindings.items()):
                path = Path(path_text).resolve()
                try:
                    path.relative_to(self.artifact_root.resolve())
                except ValueError as exc:
                    raise RuntimeError(
                        "semantic completion artifact escaped the artifact root"
                    ) from exc
                if path.is_symlink() or not path.is_file() or _digest_file(path) != expected_digest:
                    raise RuntimeError("semantic completion artifact bytes changed")
                bound_digests.append(expected_digest)
                try:
                    raw_semantic = path.read_bytes()
                    if SemanticEvidence.SUPPORT_POLICY in semantic_counts:
                        support = SupportPolicyEvidence.model_validate_json(
                            raw_semantic, strict=True
                        )
                        if support.product_lineage_digest != expected_product_lineage:
                            raise RuntimeError("support policy product lineage mismatch")
                        pending_semantic_facts.append(
                            (
                                SemanticEvidence.SUPPORT_POLICY,
                                expected_digest,
                                None,
                                support.family_identity_digest,
                                None,
                                support.pack_identity_digest,
                            )
                        )
                    if SemanticEvidence.DELIVERY_ECONOMICS in semantic_counts:
                        economics = DeliveryEconomicsEvidence.model_validate_json(
                            raw_semantic, strict=True
                        )
                        if economics.product_lineage_digest != expected_product_lineage:
                            raise RuntimeError("delivery economics product lineage mismatch")
                        pending_semantic_facts.append(
                            (
                                SemanticEvidence.DELIVERY_ECONOMICS,
                                expected_digest,
                                economics.customer_identity_digest,
                                None,
                                economics.offer_identity_digest,
                                None,
                            )
                        )
                    if SemanticEvidence.THIRD_SAME_FAMILY_CASE in semantic_counts:
                        family_case = ThirdSameFamilyCaseEvidence.model_validate_json(
                            raw_semantic, strict=True
                        )
                        if family_case.product_lineage_digest != expected_product_lineage:
                            raise RuntimeError("same-family case product lineage mismatch")
                        pending_semantic_facts.append(
                            (
                                SemanticEvidence.THIRD_SAME_FAMILY_CASE,
                                expected_digest,
                                family_case.customer_identity_digest,
                                family_case.family_identity_digest,
                                None,
                                family_case.reusable_pack_digest,
                            )
                        )
                except ValueError:
                    # Only the path corresponding to a semantic model can parse as it.
                    pass
            if evidence.candidate_manifest_path is not None:
                manifest_path = evidence.candidate_manifest_path.resolve()
                try:
                    manifest_path.relative_to(self.artifact_root.resolve())
                except ValueError as exc:
                    raise RuntimeError("milestone manifest escaped the artifact root") from exc
                if (
                    manifest_path.is_symlink()
                    or not manifest_path.is_file()
                    or _digest_file(manifest_path) != evidence.candidate_manifest_digest
                ):
                    raise RuntimeError("milestone candidate manifest bytes changed")
                assert evidence.candidate_manifest_digest is not None
                manifest = CandidateManifest.model_validate(read_json(manifest_path, {}))
                if (
                    manifest.work_item_id != item.work_item_id
                    or manifest.candidate_sha != evidence.candidate_sha
                    or manifest.base_sha != evidence.base_sha
                ):
                    raise RuntimeError("milestone candidate manifest identity mismatch")
                if checkpoint_record is not None:
                    self._reverify_traincheck_evidence(checkpoint_record, manifest_path)
                    self._reverify_release_evidence_authorization(checkpoint_record, manifest_path)
                tree = run_command(
                    ["git", "rev-parse", f"{evidence.candidate_sha}^{{tree}}"],
                    cwd=self.git_root,
                    check=False,
                )
                if tree.returncode != 0 or tree.stdout.strip() != evidence.candidate_tree_sha:
                    raise RuntimeError("milestone candidate tree identity changed")
                bound_digests.append(evidence.candidate_manifest_digest)
            for path_text, expected_digest in sorted(evidence.independent_review_artifacts.items()):
                path = Path(path_text).resolve()
                try:
                    path.relative_to(self.artifact_root.resolve())
                except ValueError as exc:
                    raise RuntimeError("independent review escaped the artifact root") from exc
                if path.is_symlink() or not path.is_file():
                    raise RuntimeError("independent review artifact is missing")
                observed = (
                    V3ContextManifest.model_validate(read_json(path, {})).canonical_digest()
                    if path.name.startswith("context-")
                    else _digest_file(path)
                )
                if observed != expected_digest:
                    raise RuntimeError("independent review artifact digest mismatch")
                independent_review_refs.append(f"{path}:{expected_digest}")
                bound_digests.append(expected_digest)
            if evidence.independent_review_artifacts:
                observed_authorities.add(EvidenceAuthority.INDEPENDENT_REVIEWER)
            if item.risk_tier in {RiskTier.INTEGRATION, RiskTier.TRUST_CORE} and not (
                evidence.independent_review_artifacts
            ):
                raise RuntimeError("integration/trust evidence lacks independent review bytes")
            for prior_item_id, required_semantics in item_contract.required_prior_evidence.items():
                prior_loaded = load_work_item_completion_evidence(
                    self.runtime_paths.milestone_evidence, prior_item_id
                )
                if prior_loaded is None:
                    continue
                prior, prior_digest = prior_loaded
                if prior.source_authority_digest != active_source.canonical_digest():
                    raise RuntimeError("prior completion authority is stale")
                observed_semantics = set(prior.semantic_evidence_refs)
                if not set(required_semantics).issubset(observed_semantics):
                    continue
                for path_text, expected_digest in prior.semantic_artifact_bindings.items():
                    prior_path = Path(path_text).resolve()
                    try:
                        prior_path.relative_to(self.artifact_root.resolve())
                    except ValueError as exc:
                        raise RuntimeError("prior authority artifact escaped its root") from exc
                    if (
                        prior_path.is_symlink()
                        or not prior_path.is_file()
                        or _digest_file(prior_path) != expected_digest
                    ):
                        raise RuntimeError("prior authority artifact bytes changed")
                if SemanticEvidence.NATIVE_VALUE_AUTHORIZATION in required_semantics:
                    if (
                        prior.checkpoint_path is None
                        or prior.candidate_manifest_path is None
                        or prior.machine_policy_receipt_digest is None
                    ):
                        raise RuntimeError("prior native authority lacks frozen provenance")
                    prior_checkpoint = V3Checkpoint.model_validate(
                        read_json(prior.checkpoint_path, {})
                    )
                    self._reverify_traincheck_evidence(
                        prior_checkpoint, prior.candidate_manifest_path
                    )
                    self._reverify_release_evidence_authorization(
                        prior_checkpoint, prior.candidate_manifest_path
                    )
                    observed_authorities.add(EvidenceAuthority.INDEPENDENT_MACHINE_POLICY)
                    native_digests = prior.semantic_evidence_refs.get(
                        SemanticEvidence.NATIVE_VALUE_AUTHORIZATION, []
                    )
                    if len(native_digests) != 1:
                        raise RuntimeError("prior native authority has an inexact fact roster")
                    native_fact = CorrelatedEvidenceFact(
                        product_lineage_digest=expected_product_lineage,
                        candidate_sha=prior.candidate_sha,
                        source_work_item_id=prior.work_item_id,
                        evidence_digest=native_digests[0],
                        authority_receipt_digest=prior.machine_policy_receipt_digest,
                        semantic=SemanticEvidence.NATIVE_VALUE_AUTHORIZATION,
                    )
                    item_correlated_facts.append(native_fact)
                    milestone_correlated_facts.append(native_fact)
                    item_verified_receipt_digests.add(prior.machine_policy_receipt_digest)
                    milestone_verified_receipt_digests.add(
                        prior.machine_policy_receipt_digest
                    )
                prior_evidence[prior_item_id] = sorted(
                    required_semantics, key=lambda value: value.value
                )
                bound_digests.append(prior_digest)
            if evidence.machine_policy_receipt_path is not None:
                if (
                    evidence.candidate_manifest_digest is None
                    or evidence.candidate_manifest_path is None
                    or evidence.machine_policy_receipt_digest is None
                ):
                    raise RuntimeError("machine-policy evidence lacks its candidate basis")
                try:
                    authorized = ExternalReceiptAuthorizer(
                        Path(github.receipt_verifier_executable)
                    ).authorize(
                        evidence.machine_policy_receipt_path,
                        candidate_sha=evidence.candidate_sha,
                        candidate_tree_sha=evidence.candidate_tree_sha,
                        base_sha=evidence.base_sha,
                        work_item_id=item.work_item_id,
                        candidate_manifest_digest=evidence.candidate_manifest_digest,
                    )
                except (OSError, PublicationError):
                    continue
                if authorized.receipt.canonical_digest() != evidence.machine_policy_receipt_digest:
                    raise RuntimeError("machine-policy receipt digest changed")
                machine_policy_receipt_refs.append(
                    f"{evidence.machine_policy_receipt_path}:"
                    f"{evidence.machine_policy_receipt_digest}"
                )
                bound_digests.append(evidence.machine_policy_receipt_digest)
                observed_authorities.add(EvidenceAuthority.INDEPENDENT_MACHINE_POLICY)
                item_verified_receipt_digests.add(evidence.machine_policy_receipt_digest)
                milestone_verified_receipt_digests.add(evidence.machine_policy_receipt_digest)
                native_digests = evidence.semantic_evidence_refs.get(
                    SemanticEvidence.NATIVE_VALUE_AUTHORIZATION, []
                )
                if native_digests:
                    if len(native_digests) != 1:
                        raise RuntimeError("native authority has an inexact fact roster")
                    native_fact = CorrelatedEvidenceFact(
                        product_lineage_digest=expected_product_lineage,
                        candidate_sha=evidence.candidate_sha,
                        source_work_item_id=evidence.work_item_id,
                        evidence_digest=native_digests[0],
                        authority_receipt_digest=evidence.machine_policy_receipt_digest,
                        semantic=SemanticEvidence.NATIVE_VALUE_AUTHORIZATION,
                    )
                    item_correlated_facts.append(native_fact)
                    milestone_correlated_facts.append(native_fact)
            if (
                item.machine_policy_receipt_required or item.kind is WorkKind.MACHINE_POLICY_REVIEW
            ) and evidence.machine_policy_receipt_path is None:
                raise RuntimeError("required independent machine-policy receipt is absent")
            if item.external_receipt_required or item_contract.allowed_external_evidence_types:
                record = load_verified_external_evidence(
                    repo_root=self.repo_root,
                    subject_id=item.work_item_id,
                    trusted_root_environment_variable=(external.trusted_root_environment_variable),
                    trusted_public_key_environment_variable=(
                        external.trusted_public_key_environment_variable
                    ),
                )
                receipt = record.require_commercial_trust()
                receipt_digest = receipt.canonical_digest()
                expected_external_reference = (
                    f"external-receipt:{receipt.receipt_id}@{receipt.canonical_digest()}"
                )
                if receipt.receipt_id not in evidence.external_receipt_refs and (
                    expected_external_reference not in evidence.external_receipt_refs
                ):
                    raise RuntimeError("verified external receipt is not completion-bound")
                if (
                    evidence.checkpoint_path is None
                    and evidence.checkpoint_digest != receipt.canonical_digest()
                ):
                    raise RuntimeError("external completion evidence digest mismatch")
                reference = f"{receipt.receipt_id}:{receipt_digest}"
                trusted_external_receipt_refs.append(reference)
                bound_digests.append(receipt_digest)
                observed_authorities.add(EvidenceAuthority.TRUSTED_EXTERNAL)
                item_verified_receipt_digests.add(receipt_digest)
                milestone_verified_receipt_digests.add(receipt_digest)
                unique_external_artifacts = {
                    (artifact.name, artifact.digest, artifact.location_class.value)
                    for artifact in receipt.artifacts
                }
                if len(unique_external_artifacts) != len(receipt.artifacts):
                    raise RuntimeError("trusted external receipt repeats an artifact")
                names = {artifact.name for artifact in receipt.artifacts}
                digests = {artifact.digest for artifact in receipt.artifacts}
                if (
                    milestone_external_names.intersection(names)
                    or milestone_external_digests.intersection(digests)
                    or milestone_external_identities.intersection(unique_external_artifacts)
                ):
                    raise RuntimeError("milestone external evidence repeats an artifact identity")
                milestone_external_names.update(names)
                milestone_external_digests.update(digests)
                milestone_external_identities.update(unique_external_artifacts)
                artifact_count = len(unique_external_artifacts)
                external_type_counts[receipt.evidence_type] = artifact_count
                milestone_external_counts[receipt.evidence_type] = (
                    milestone_external_counts.get(receipt.evidence_type, 0) + artifact_count
                )
                for semantic, count in self._external_receipt_semantic_evidence(receipt).items():
                    semantic_counts[semantic] = semantic_counts.get(semantic, 0) + count
                    milestone_semantic_counts[semantic] = (
                        milestone_semantic_counts.get(semantic, 0) + count
                    )
                correlation = receipt.correlation_identity
                if correlation is not None:
                    if correlation.candidate_sha != evidence.candidate_sha:
                        raise RuntimeError("external correlation candidate mismatch")
                    if correlation.product_lineage_digest != expected_product_lineage:
                        raise RuntimeError("external correlation product lineage mismatch")
                    external_fact = CorrelatedEvidenceFact(
                        product_lineage_digest=correlation.product_lineage_digest,
                        candidate_sha=correlation.candidate_sha,
                        source_work_item_id=evidence.work_item_id,
                        evidence_digest=receipt_digest,
                        authority_receipt_digest=receipt_digest,
                        customer_identity_digest=correlation.customer_identity_digest,
                        family_identity_digest=correlation.family_identity_digest,
                        offer_identity_digest=correlation.offer_identity_digest,
                        pack_identity_digest=correlation.pack_identity_digest,
                        external_evidence_type=receipt.evidence_type,
                    )
                    item_correlated_facts.append(external_fact)
                    milestone_correlated_facts.append(external_fact)
                    for semantic in self._external_receipt_semantic_evidence(receipt):
                        semantic_fact = CorrelatedEvidenceFact(
                            product_lineage_digest=correlation.product_lineage_digest,
                            candidate_sha=correlation.candidate_sha,
                            source_work_item_id=evidence.work_item_id,
                            evidence_digest=receipt_digest,
                            authority_receipt_digest=receipt_digest,
                            customer_identity_digest=correlation.customer_identity_digest,
                            family_identity_digest=correlation.family_identity_digest,
                            offer_identity_digest=correlation.offer_identity_digest,
                            pack_identity_digest=correlation.pack_identity_digest,
                            semantic=semantic,
                        )
                        item_correlated_facts.append(semantic_fact)
                        milestone_correlated_facts.append(semantic_fact)
                    for (
                        semantic,
                        semantic_digest,
                        customer_digest,
                        family_digest,
                        offer_digest,
                        pack_digest,
                    ) in pending_semantic_facts:
                        if (
                            semantic is SemanticEvidence.SUPPORT_POLICY
                            and semantic_digest not in digests
                        ):
                            raise RuntimeError(
                                "support policy bytes are absent from the signed receipt"
                            )
                        if any(
                            (
                                customer_digest is not None
                                and customer_digest != correlation.customer_identity_digest,
                                family_digest is not None
                                and family_digest != correlation.family_identity_digest,
                                offer_digest is not None
                                and offer_digest != correlation.offer_identity_digest,
                                pack_digest is not None
                                and pack_digest != correlation.pack_identity_digest,
                            )
                        ):
                            raise RuntimeError("semantic artifact correlation identity mismatch")
                        semantic_fact = CorrelatedEvidenceFact(
                            product_lineage_digest=correlation.product_lineage_digest,
                            candidate_sha=evidence.candidate_sha,
                            source_work_item_id=evidence.work_item_id,
                            evidence_digest=semantic_digest,
                            authority_receipt_digest=receipt_digest,
                            customer_identity_digest=customer_digest,
                            family_identity_digest=family_digest,
                            offer_identity_digest=offer_digest,
                            pack_identity_digest=pack_digest,
                            semantic=semantic,
                        )
                        item_correlated_facts.append(semantic_fact)
                        milestone_correlated_facts.append(semantic_fact)
                elif pending_semantic_facts:
                    raise RuntimeError("commercial semantic artifact lacks signed correlation")
            grade = {
                ExecutionEvidenceMode.SIMULATION: EvidenceGrade.DETERMINISTIC,
                ExecutionEvidenceMode.CONTROLLED_VALIDATION: EvidenceGrade.CONTROLLED,
                ExecutionEvidenceMode.LIVE_VALIDATION: EvidenceGrade.LIVE,
                ExecutionEvidenceMode.EXTERNAL_VALIDATION: EvidenceGrade.EXTERNAL,
            }[evidence.evidence_mode]
            contract_failures.extend(
                evaluate_work_item_evidence_contract(
                    item_contract,
                    CompletionEvidenceObservation(
                        grade=grade,
                        authorities=sorted(observed_authorities, key=lambda value: value.value),
                        semantic_counts=semantic_counts,
                        external_type_counts=external_type_counts,
                        prior_evidence=prior_evidence,
                    ),
                )
            )
            if (
                item.maturity_target.commercial is CommercialMaturity.EXTERNAL_VALUE_DEMONSTRATED
            ):
                try:
                    maturity_authorization = derive_commercial_maturity_authorization(
                        item_correlated_facts,
                        sorted(item_verified_receipt_digests),
                    )
                except ValueError:
                    maturity_authorization = None
                if commercial_maturity_supported(
                    item.maturity_target.commercial, maturity_authorization
                ):
                    pass
                else:
                    contract_failures.append(
                        f"{item.work_item_id} commercial maturity "
                        f"{item.maturity_target.commercial.value} exceeds exact trusted evidence"
                    )
            if (
                item.maturity_target.commercial is CommercialMaturity.NATIVE_ADVANTAGE_DEMONSTRATED
                and semantic_counts.get(SemanticEvidence.NATIVE_VALUE_AUTHORIZATION, 0) < 1
            ):
                contract_failures.append(
                    f"{item.work_item_id} native advantage lacks independent authorization"
                )
            evidence_digests[item.work_item_id] = digest
            deterministic_evidence[item.work_item_id] = bound_digests
        for evidence_type in milestone_contract.required_external_evidence_types:
            if milestone_external_counts.get(evidence_type, 0) < 1:
                contract_failures.append(
                    f"{collection.active_milestone} lacks {evidence_type.value} evidence"
                )
        for semantic, minimum in milestone_contract.required_semantic_counts.items():
            if milestone_semantic_counts.get(semantic, 0) < minimum:
                contract_failures.append(
                    f"{collection.active_milestone} lacks {minimum} {semantic.value} evidence"
                )
        if milestone_contract.machine_policy_required and not machine_policy_receipt_refs:
            contract_failures.append(
                f"{collection.active_milestone} lacks machine-policy authorization"
            )
        exit_failures = evaluate_milestone_exit_criteria(
            milestone_contract,
            completed_work_item_ids=set(evidence_digests),
            semantic_counts=milestone_semantic_counts,
            external_type_counts=milestone_external_counts,
            machine_policy_available=bool(machine_policy_receipt_refs),
            correlated_facts=milestone_correlated_facts,
        )
        contract_failures.extend(exit_failures)
        milestone_maturity_authorization = None
        if any(
            item.maturity_target.commercial is CommercialMaturity.COMMERCIALLY_SUPPORTED
            for item in active
        ):
            try:
                milestone_maturity_authorization = derive_commercial_maturity_authorization(
                    milestone_correlated_facts,
                    sorted(milestone_verified_receipt_digests),
                )
            except ValueError:
                milestone_maturity_authorization = None
            if not commercial_maturity_supported(
                CommercialMaturity.COMMERCIALLY_SUPPORTED,
                milestone_maturity_authorization,
            ):
                contract_failures.append(
                    f"{collection.active_milestone} commercially-supported maturity "
                    "lacks its exact correlated authorization envelope"
                )
        milestones = MilestoneRoadmap.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.milestones)
        )
        milestone = next(
            value
            for value in milestones.milestones
            if value.milestone_id == collection.active_milestone
        )
        decision = evaluate_v3_milestone_completion(
            milestone=milestone,
            work_items=collection,
            deterministic_evidence=deterministic_evidence,
            independent_review_refs=independent_review_refs,
            machine_policy_receipt_refs=machine_policy_receipt_refs,
            trusted_external_receipt_refs=trusted_external_receipt_refs,
            proposals=[],
            expansion_round=0,
            controlled_fixture_only=False,
        )
        completion_failures = list(decision.deterministic_failures)
        completion_failures.extend(contract_failures)
        if not machine_policy_receipt_refs:
            completion_failures.append(
                "milestone lacks independently verified machine-policy authorization"
            )
        if decision.decision is not MilestoneStatus.COMPLETED or completion_failures:
            if completion_failures:
                proposal = CompletionProposal(
                    proposal_id=(
                        "CPROP-"
                        f"{collection.active_milestone.replace('-', '_')}-"
                        f"{sha256_digest('|'.join(completion_failures).encode())[7:19].upper()}"
                    ),
                    milestone_id=collection.active_milestone,
                    summary="Bounded milestone completion gaps require separate work proposals.",
                    proposed_work=completion_failures[:5],
                    reviewer_artifact_digest=(
                        next(iter(evidence_digests.values()), active_source.canonical_digest())
                    ),
                    accepted=False,
                )
                proposal_path = (
                    self.runtime_paths.milestone_decisions
                    / "proposals"
                    / f"{proposal.proposal_id}.json"
                )
                proposal_envelope = {
                    "record": proposal.model_dump(mode="json", by_alias=True),
                    "contentDigest": proposal.canonical_digest(),
                }
                if proposal_path.exists():
                    if read_json(proposal_path, {}) != proposal_envelope:
                        raise RuntimeError("completion proposal is immutable and digest-bound")
                else:
                    write_json(proposal_path, proposal_envelope)
            return None
        receipt_path = (
            self.runtime_paths.milestone_decisions / f"{collection.active_milestone}.json"
        )
        commercial_authorization_digest: str | None = None
        if milestone_maturity_authorization is not None:
            authorization_path = (
                self.runtime_paths.milestone_decisions
                / f"{collection.active_milestone}-commercial-authorization.json"
            )
            authorization_raw = milestone_maturity_authorization.canonical_json_bytes()
            if (
                authorization_path.is_file()
                and authorization_path.read_bytes() != authorization_raw
            ):
                raise RuntimeError("commercial maturity authorization is immutable")
            if not authorization_path.is_file():
                atomic_write_bytes(authorization_path, authorization_raw)
            commercial_authorization_digest = milestone_maturity_authorization.canonical_digest()
        state = advance_milestone_state(
            roadmap=milestones,
            state_path=self.runtime_paths.milestone_state,
            receipt_path=receipt_path,
            evidence_digests=evidence_digests,
            expected_evidence_ids={item.work_item_id for item in evidence_items},
            source_authority_digest=active_source.canonical_digest(),
            commercial_authorization_digest=commercial_authorization_digest,
            proposals=[],
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
                base_sha=current_sha(self.git_root, "main"),
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

    def _authorize_machine_policy_review(
        self, item: WorkItem, now: datetime
    ) -> tuple[AuthorizedMachinePolicyReviewV31, Path, Path, str]:
        """Assemble dependency evidence, then consume only an external Phase 3 decision."""

        main_sha = current_sha(self.git_root, "main")
        tree_result = run_command(
            ["git", "rev-parse", f"{main_sha}^{{tree}}"],
            cwd=self.git_root,
            check=False,
        )
        tree_sha = tree_result.stdout.strip()
        if tree_result.returncode != 0 or SHA_PATTERN.fullmatch(tree_sha) is None:
            raise MachinePolicyRuntimeError("machine-policy review tree is unavailable")
        evidence_paths: dict[str, Path] = {}
        evidence_digests: dict[str, str] = {}
        for dependency in sorted(item.depends_on):
            loaded = load_work_item_completion_evidence(
                self.runtime_paths.milestone_evidence, dependency
            )
            path = self.runtime_paths.milestone_evidence / f"{dependency}.json"
            if loaded is None or not path.is_file() or path.is_symlink():
                raise MachinePolicyRuntimeError(
                    f"machine-policy dependency evidence is unavailable: {dependency}"
                )
            evidence_paths[dependency] = path.resolve()
            evidence_digests[dependency] = _digest_file(path)
        if not evidence_paths:
            raise MachinePolicyRuntimeError("machine-policy review has no dependency evidence")
        root = self.artifact_root / item.work_item_id / f"machine-policy-review-{main_sha}"
        root.mkdir(parents=True, exist_ok=True)
        checkpoint_path = root / "checkpoint-generation-0001.json"
        write_json(
            checkpoint_path,
            {
                "schemaVersion": "3.1",
                "workItemId": item.work_item_id,
                "milestoneId": item.milestone,
                "lane": item.lane.value,
                "riskTier": item.risk_tier.value,
                "candidateSha": main_sha,
                "candidateTreeSha": tree_sha,
                "dependencyEvidence": evidence_digests,
            },
        )
        context_digest = _digest_file(checkpoint_path)
        stage_outputs = [
            StageArtifactBinding(
                stage="dependency", name=dependency, digest=evidence_digests[dependency]
            )
            for dependency in sorted(evidence_paths)
        ]
        gate_bindings = [
            GateBinding(
                name=dependency,
                version="3.1",
                result=GateResult.PASS.value,
                evidence_digest=evidence_digests[dependency],
            )
            for dependency in sorted(evidence_paths)
        ]
        manifest = CandidateManifest(
            base_sha=main_sha,
            candidate_sha=main_sha,
            candidate_tree_sha=tree_sha,
            work_item_id=item.work_item_id,
            packet_digest=context_digest,
            context_digest=context_digest,
            executor=ExecutorIdentity(
                backend="controller-evidence-assembler",
                adapter="tcfactory.v3.machine_policy_runtime",
                capability_digest=_digest_file(self.repo_root / "tcfactory/v3/controller.py"),
            ),
            stage_outputs=stage_outputs,
            gates=gate_bindings,
            findings=[],
            external_evidence=[],
            checkpoint_digest=context_digest,
            release_decision=ReleaseDecision.HOLD,
            created_at=now,
        )
        bound_artifacts: dict[str, bytes] = {}
        for dependency, path in evidence_paths.items():
            raw = path.read_bytes()
            bound_artifacts[f"stage:dependency:{dependency}"] = raw
            bound_artifacts[f"gate:{dependency}"] = raw
        manifest.verify_artifacts(bound_artifacts)
        manifest_path = root / "candidate-manifest.json"
        write_json(manifest_path, manifest.model_dump(mode="json", by_alias=True))
        manifest_digest = _digest_file(manifest_path)
        github = load_github_config(self.repo_root / "config/github.yaml")
        receipt_path = (
            Path(github.independent_receipt_root)
            / "machine-policy"
            / item.work_item_id
            / f"{main_sha}.json"
        )
        active = validate_active_source_generation(self.repo_root)
        if not receipt_path.is_file():
            try:
                create_and_submit_verification_request(
                    profile_path=(
                        Path("/etc/traincapsule-verifier/request-profiles")
                        / f"{item.kind.value.lower()}.json"
                    ),
                    work_item_id=item.work_item_id,
                    milestone_id=item.milestone,
                    lane=item.lane.value,
                    candidate_sha=main_sha,
                    candidate_tree_sha=tree_sha,
                    base_sha=main_sha,
                    source_generation_id=active.generation_id,
                    source_generation_digest=f"sha256:{active.manifest_digest}",
                    context_manifest_digest=context_digest,
                    task_packet_digest=context_digest,
                    candidate_manifest_digest=manifest_digest,
                    checkpoint_digest=context_digest,
                    gate_evidence=evidence_paths,
                    evidence_root=root / "verifier-request-evidence",
                    now=now,
                )
            except (OSError, ValueError, VerifierSubmissionError) as exc:
                raise MachinePolicyRuntimeError(
                    f"independent verification request submission is unavailable: {exc}"
                ) from exc
        authorization = load_authorized_machine_policy_review(
            receipt_path=receipt_path,
            activation_path=Path(github.activation_receipt_path),
            authority=ExternalPhase3NativeValueAuthority(Path(github.receipt_verifier_executable)),
            work_item_id=item.work_item_id,
            milestone_id=item.milestone,
            lane=item.lane,
            risk_tier=item.risk_tier,
            candidate_sha=main_sha,
            candidate_tree_sha=tree_sha,
            base_sha=main_sha,
            candidate_manifest_digest=manifest_digest,
            review_context_digest=context_digest,
            dependency_evidence_digests=list(evidence_digests.values()),
            required_gate_results={
                dependency: GateResult.PASS for dependency in sorted(evidence_paths)
            },
            expected_main_sha=main_sha,
            source_generation_id=active.generation_id,
            source_generation_digest=f"sha256:{active.manifest_digest}",
            controller_binary_digest=_digest_file(self.repo_root / "tcfactory/v3/controller.py"),
            controller_config_digest=_digest_file(self.repo_root / "config/factory.yaml"),
            now=now,
        )
        authorization_path = root / "machine-policy-authorization.json"
        write_json(
            authorization_path,
            authorization.model_dump(mode="json", by_alias=True),
        )
        return authorization, checkpoint_path, manifest_path, manifest_digest

    def _future_lane_milestones(self, collection: WorkItemCollection) -> dict[Lane, frozenset[str]]:
        active_items = [
            item for item in collection.work_items if item.milestone == collection.active_milestone
        ]
        if not active_items or not any(
            item.status is WorkStatus.WAITING_EXTERNAL for item in active_items
        ):
            return {}
        if any(
            item.status
            not in {
                WorkStatus.WAITING_EXTERNAL,
                WorkStatus.PASSED_ENGINEERING,
                WorkStatus.COMPLETED,
                WorkStatus.NATIVE_SUFFICIENT,
                WorkStatus.REJECTED_VALUE,
            }
            for item in active_items
        ):
            return {}
        policy = load_completion_evidence_policy(self.repo_root)
        allowed_lanes = policy.milestone(
            collection.active_milestone
        ).allow_unrelated_future_lanes_while_external_wait
        if not allowed_lanes:
            return {}
        milestones = MilestoneRoadmap.model_validate(
            load_yaml(self.repo_root / self.factory.roadmap.milestones)
        )
        ordered = [milestone.milestone_id for milestone in milestones.milestones]
        index = ordered.index(collection.active_milestone)
        if index + 1 >= len(ordered):
            return {}
        next_milestone = ordered[index + 1]
        return {Lane(value): frozenset({next_milestone}) for value in allowed_lanes}

    def _promote_ready(
        self,
        collection: WorkItemCollection,
        now: datetime,
        *,
        future_lane_milestones: Mapping[Lane, frozenset[str]] | None = None,
    ) -> None:
        satisfied = {
            item.work_item_id
            for item in collection.work_items
            if item.status in {WorkStatus.PASSED_ENGINEERING, WorkStatus.COMPLETED}
        }
        future = future_lane_milestones or {}
        for item in collection.work_items:
            if item.milestone != collection.active_milestone and item.milestone not in future.get(
                item.lane, frozenset()
            ):
                continue
            if item.status not in {WorkStatus.PROPOSED, WorkStatus.WAITING_EXTERNAL}:
                continue
            if set(item.depends_on).issubset(satisfied):
                if item.kind is WorkKind.MACHINE_POLICY_REVIEW:
                    try:
                        authorization, checkpoint_path, manifest_path, manifest_digest = (
                            self._authorize_machine_policy_review(item, now)
                        )
                    except (MachinePolicyRuntimeError, FileNotFoundError, OSError):
                        self.queue.transition(
                            item.work_item_id,
                            WorkStatus.BLOCKED_POLICY,
                            updated_at=now,
                        )
                        continue
                    self.queue.transition(
                        item.work_item_id,
                        authorization.resulting_status,
                        updated_at=now,
                    )
                    verified_item = self.queue.load(item.work_item_id)
                    if authorization.resulting_status in {
                        WorkStatus.PASSED_ENGINEERING,
                        WorkStatus.NATIVE_SUFFICIENT,
                        WorkStatus.REJECTED_VALUE,
                    }:
                        self._record_completion_evidence(
                            item=verified_item,
                            candidate_sha=authorization.candidate_sha,
                            checkpoint_digest=_digest_file(checkpoint_path),
                            manifest_digest=manifest_digest,
                            machine_policy_receipt_digest=(authorization.machine_receipt_digest),
                            independent_reviewed=False,
                            additional_evidence_refs=(
                                *authorization.completion_evidence_refs(),
                                "machine-policy-authorization:"
                                f"{
                                    _digest_file(
                                        manifest_path.parent / 'machine-policy-authorization.json'
                                    )
                                }",
                            ),
                            now=now,
                        )
                    continue
                action_outcome: ExternalActionOutcome | None = None
                if self.phase6_runtime is not None and self.phase6_runtime.handles_external_action(
                    item
                ):
                    try:
                        action_outcome = self.phase6_runtime.execute_commercial_action(
                            item=item,
                            candidate_sha=current_sha(self.git_root, "main"),
                            now=now,
                        )
                    except Phase6RuntimeError:
                        if item.status is not WorkStatus.WAITING_EXTERNAL:
                            self.queue.transition(
                                item.work_item_id,
                                WorkStatus.WAITING_EXTERNAL,
                                updated_at=now,
                            )
                        continue
                    if action_outcome.status is not ExternalActionStatus.SENT:
                        if item.status is not WorkStatus.WAITING_EXTERNAL:
                            self.queue.transition(
                                item.work_item_id,
                                WorkStatus.WAITING_EXTERNAL,
                                updated_at=now,
                            )
                        continue
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
                    response_consumption: ExternalResponseConsumption | None = None
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
                        receipt = record.require_commercial_trust()
                        if action_outcome is not None:
                            receipt.require_exact_action_response(action_outcome, now=now)
                            if self.phase6_runtime is None:
                                raise Phase6RuntimeError("external response runtime is unavailable")
                            response_consumption = (
                                self.phase6_runtime.reserve_external_response_consumption(
                                    outcome=action_outcome,
                                    receipt=receipt,
                                )
                            )
                    except (
                        ExternalEvidenceVerificationError,
                        Phase6RuntimeError,
                        ValueError,
                    ):
                        continue
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
                        candidate_sha=current_sha(self.git_root, "main"),
                        checkpoint_digest=sha256_digest(receipt.canonical_json_bytes()),
                        manifest_digest=None,
                        machine_policy_receipt_digest=None,
                        independent_reviewed=False,
                        now=now,
                        additional_evidence_refs=(
                            (
                                "external-action-generation:"
                                f"{response_consumption.delivery_generation_id}"
                            ),
                            (
                                "external-response-consumption:"
                                f"{response_consumption.response_digest}"
                            ),
                        )
                        if response_consumption is not None
                        else (),
                    )
                    if response_consumption is not None and action_outcome is not None:
                        assert self.phase6_runtime is not None
                        self.phase6_runtime.commit_external_response_consumption(
                            outcome=action_outcome,
                            consumption=response_consumption,
                        )
                    continue
                if (
                    item.kind is WorkKind.RESEARCH
                    and item.lane in {Lane.MARKET, Lane.COMPETITOR}
                    and item.status is WorkStatus.WAITING_EXTERNAL
                ):
                    continue
                target = WorkStatus.READY if item.automatable else WorkStatus.BLOCKED_POLICY
                self.queue.transition(item.work_item_id, target, updated_at=now)

    def _promote_backend_pauses(self, collection: WorkItemCollection, now: datetime) -> None:
        """Requeue only due, durable backend/publication waits.

        The pause remains scoped to one work item.  A missing/corrupt checkpoint or an
        exhausted recheck budget fails closed instead of consuming engineering repair
        cycles or requesting operator intervention.
        """

        for item in collection.work_items:
            if item.status is not WorkStatus.PAUSED_BACKEND:
                continue
            checkpoint = self.checkpoints.load_v3(item.work_item_id)
            if (
                checkpoint is None
                or not checkpoint.active
                or checkpoint.backend_wait_state is None
                or checkpoint.backend_resume_at is None
            ):
                if checkpoint is not None:
                    checkpoint.active = False
                    checkpoint.circuit_breaker_reason = (
                        "backend pause lacks a complete durable resume contract"
                    )
                    self.checkpoints.save_v3(checkpoint)
                self.queue.transition(
                    item.work_item_id,
                    WorkStatus.BLOCKED_TECHNICAL,
                    updated_at=now,
                )
                continue
            if checkpoint.backend_resume_at > now:
                continue
            checkpoint.approval_state = "BACKEND_RECHECK_READY"
            checkpoint.backend_wait_state = None
            checkpoint.backend_resume_at = None
            checkpoint.updated_at = now
            self.checkpoints.save_v3(checkpoint)
            self.queue.transition(item.work_item_id, WorkStatus.READY, updated_at=now)

    def _roles(self, item: WorkItem) -> tuple[str, ...]:
        if item.lane is Lane.FACTORY:
            return ("factory_repair", "audit")
        roles = ROLE_POLICY[item.risk_tier]
        if item.kind is WorkKind.RESEARCH:
            return tuple("research" if role == "builder" else role for role in roles)
        if item.kind is WorkKind.SPECIFICATION:
            return tuple("specification" if role == "builder" else role for role in roles)
        return roles

    def _pause_publication(
        self,
        *,
        item: WorkItem,
        checkpoint: V3Checkpoint,
        release: Mapping[str, object],
    ) -> dict[str, object]:
        transaction_id = release.get("transactionId")
        if not isinstance(transaction_id, str) or not transaction_id:
            raise RuntimeError("pending publication omitted its durable transaction identity")
        if (
            checkpoint.publication_transaction_id is not None
            and checkpoint.publication_transaction_id != transaction_id
        ):
            raise RuntimeError("publication transaction identity changed across a recheck")
        poll_seconds = load_github_config(
            self.repo_root / "config/github.yaml"
        ).remote_ci.poll_seconds
        resume_at = datetime.now(UTC) + timedelta(seconds=poll_seconds)
        checkpoint.publication_transaction_id = transaction_id
        checkpoint.backend_wait_state = "PUBLICATION_PENDING"
        checkpoint.backend_resume_at = resume_at
        checkpoint.approval_state = "PUBLICATION_CHECKS_PENDING"
        checkpoint.circuit_breaker_reason = None
        checkpoint.active = True
        checkpoint.updated_at = datetime.now(UTC)
        self.checkpoints.save_v3(checkpoint)
        self.queue.transition(
            item.work_item_id,
            WorkStatus.PAUSED_BACKEND,
            updated_at=datetime.now(UTC),
        )
        return {
            "status": WorkStatus.PAUSED_BACKEND.value,
            "workItemId": item.work_item_id,
            "publicationStatus": "PENDING_REQUIRED_CHECKS",
            "publicationTransactionId": transaction_id,
            "resumeAt": resume_at.isoformat(),
            "release": dict(release),
        }

    def _reverify_research_advisory(
        self,
        advisory: ResearchAdvisoryBundle | None,
        checkpoint: V3Checkpoint,
    ) -> None:
        if advisory is None:
            return
        if self.phase6_runtime is None:
            raise RuntimeError("research evidence lost its installed verifier")
        self.phase6_runtime.verify_research_advisory(advisory)
        expected_paths = {
            "controller:research-advisory-bundle": Path(advisory.bundle_path),
            "controller:research-report": Path(advisory.report_path),
            **{
                f"controller:research-raw-{artifact.source_id}": Path(artifact.raw_cas_path)
                for artifact in advisory.artifacts
            },
            **{
                f"controller:research-receipt-{artifact.source_id}": Path(artifact.receipt_path)
                for artifact in advisory.artifacts
            },
            **{
                f"controller:research-typed-{name}": Path(path)
                for name, path in advisory.typed_market_artifact_paths.items()
            },
        }
        for key, path in expected_paths.items():
            if checkpoint.stage_artifact_paths.get(key) != str(
                path.resolve()
            ) or checkpoint.stage_artifact_digests.get(key) != _digest_file(path):
                raise RuntimeError("research evidence changed after controller verification")

    def _checkpoint_research_advisory(
        self, checkpoint: V3Checkpoint
    ) -> ResearchAdvisoryBundle | None:
        path_text = checkpoint.stage_artifact_paths.get("controller:research-advisory-bundle")
        if path_text is None:
            return None
        try:
            advisory = ResearchAdvisoryBundle.model_validate_json(
                Path(path_text).read_bytes(), strict=True
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError("persisted research advisory is invalid") from exc
        self._reverify_research_advisory(advisory, checkpoint)
        return advisory

    def _reverify_traincheck_evidence(self, checkpoint: V3Checkpoint, manifest_path: Path) -> None:
        """Reopen every frozen TrainCheck byte and match manifest bindings."""

        bindings = {
            key: value
            for key, value in checkpoint.stage_artifact_digests.items()
            if key.startswith("machine_policy:traincheck:")
            or key == "machine_policy:traincheck-receipt"
        }
        if not bindings:
            return
        manifest = CandidateManifest.model_validate(read_json(manifest_path, {}))
        manifest_bindings = {
            f"machine_policy:{binding.name}": binding.digest
            for binding in manifest.stage_outputs
            if binding.stage == "controller" and binding.name.startswith("traincheck:")
        }
        for key, expected_digest in sorted(bindings.items()):
            path_text = checkpoint.stage_artifact_paths.get(key)
            if path_text is None:
                raise RuntimeError("TrainCheck evidence omitted its bound path")
            path = Path(path_text).resolve()
            try:
                path.relative_to(self.artifact_root.resolve())
            except ValueError as exc:
                raise RuntimeError("TrainCheck evidence escaped the artifact root") from exc
            if path.is_symlink() or not path.is_file() or _digest_file(path) != expected_digest:
                raise RuntimeError("TrainCheck evidence changed after authorization")
            if key != "machine_policy:traincheck-receipt" and (
                manifest_bindings.get(key) != expected_digest
            ):
                raise RuntimeError("TrainCheck evidence is absent from the candidate manifest")
        result_key = "machine_policy:traincheck:result"
        result_path_text = checkpoint.stage_artifact_paths.get(result_key)
        if result_path_text is None:
            raise RuntimeError("TrainCheck result is missing")
        result = TrainCheckDifferentialResult.model_validate_json(
            Path(result_path_text).read_bytes(), strict=True
        )
        if (
            result.work_item_id != checkpoint.work_item_id
            or result.candidate_sha != checkpoint.candidate_sha
            or result.candidate_tree_sha != manifest.candidate_tree_sha
        ):
            raise RuntimeError("TrainCheck result identity changed")
        github = load_github_config(self.repo_root / "config/github.yaml")
        trusted_receipt_path = (
            Path(github.independent_receipt_root)
            / "machine-policy"
            / checkpoint.work_item_id
            / f"{checkpoint.candidate_sha}.json"
        )
        authorized = ExternalReceiptAuthorizer(Path(github.receipt_verifier_executable)).authorize(
            trusted_receipt_path,
            candidate_sha=checkpoint.candidate_sha,
            candidate_tree_sha=manifest.candidate_tree_sha,
            base_sha=manifest.base_sha,
            work_item_id=checkpoint.work_item_id,
            candidate_manifest_digest=_digest_file(manifest_path),
        )
        receipt_copy_path = Path(
            checkpoint.stage_artifact_paths["machine_policy:traincheck-receipt"]
        )
        if (
            receipt_copy_path.read_bytes() != trusted_receipt_path.read_bytes()
            or result.canonical_digest() not in authorized.receipt.raw_evidence_artifact_hashes
        ):
            raise RuntimeError("TrainCheck receipt/result binding changed")
        authorize_traincheck_differential(
            result,
            receipt_verifier=VerifiedMachineReceiptTrainCheckOracle(authorized.receipt),
        )

    def _reverify_release_evidence_authorization(
        self, checkpoint: V3Checkpoint, manifest_path: Path
    ) -> None:
        path_text = checkpoint.publication_authorization_envelope_path
        expected_digest = checkpoint.publication_authorization_envelope_digest
        if path_text is None and expected_digest is None:
            return
        if path_text is None or expected_digest is None:
            raise RuntimeError("release authorization envelope binding is incomplete")
        path = Path(path_text).resolve()
        try:
            path.relative_to(self.artifact_root.resolve())
        except ValueError as exc:
            raise RuntimeError("release authorization envelope escaped artifact root") from exc
        if path.is_symlink() or not path.is_file() or _digest_file(path) != expected_digest:
            raise RuntimeError("release authorization envelope bytes changed")
        envelope = FrozenReleaseEvidenceAuthorization.model_validate_json(
            path.read_bytes(), strict=True
        )
        if (
            envelope.work_item_id != checkpoint.work_item_id
            or envelope.candidate_sha != checkpoint.candidate_sha
            or envelope.candidate_tree_sha != checkpoint.publication_candidate_tree_sha
            or envelope.candidate_manifest_digest != _digest_file(manifest_path)
            or envelope.machine_policy_receipt_id
            != checkpoint.publication_expected_machine_policy_receipt_id
            or envelope.machine_policy_receipt_digest
            != checkpoint.publication_expected_machine_policy_receipt_digest
            or envelope.native_value_authorization_digest
            != checkpoint.stage_artifact_digests.get("machine_policy:authorization-envelope")
            or envelope.activation_receipt_digest
            != checkpoint.stage_artifact_digests.get("machine_policy:activation-receipt")
        ):
            raise RuntimeError("release authorization envelope identity mismatch")
        expected_frozen = {
            name.removeprefix("machine_policy:traincheck:"): digest
            for name, digest in checkpoint.stage_artifact_digests.items()
            if name.startswith("machine_policy:traincheck:")
        }
        receipt_digest = checkpoint.stage_artifact_digests.get("machine_policy:traincheck-receipt")
        if receipt_digest is not None:
            expected_frozen["machine-policy-receipt"] = receipt_digest
        if envelope.frozen_artifact_digests != expected_frozen:
            raise RuntimeError("release authorization envelope frozen roster mismatch")
        self._reverify_traincheck_evidence(checkpoint, manifest_path)

    def _reverify_external_evidence(
        self,
        *,
        item: WorkItem,
        candidate_sha: str,
        checkpoint: V3Checkpoint,
        now: datetime,
    ) -> None:
        expected = {
            key: digest
            for key, digest in checkpoint.stage_artifact_digests.items()
            if key.startswith("external_authority:")
        }
        if not expected:
            return
        config = ExternalEvidenceConfig.model_validate(
            load_yaml(self.repo_root / "config/external_evidence.yaml")
        )
        payload = load_verified_external_evidence_payload(
            repo_root=self.repo_root,
            subject_id=item.work_item_id,
            trusted_root_environment_variable=config.trusted_root_environment_variable,
            trusted_public_key_environment_variable=(
                config.trusted_public_key_environment_variable
            ),
            now=now,
        )
        receipt = payload.record.require_commercial_trust()
        if receipt.candidate_or_offer_identity != candidate_sha:
            raise ExternalEvidenceVerificationError(
                "external receipt candidate changed at the final publication boundary"
            )
        observed = {
            f"external_authority:{receipt.receipt_id}:{name}": digest
            for name, digest in payload.authority_digests.items()
        }
        if observed != expected:
            raise ExternalEvidenceVerificationError(
                "external authority snapshot changed before publication"
            )

    @staticmethod
    def _validated_publication_success(
        release: Mapping[str, object],
    ) -> tuple[str, str, int, str]:
        merged_main_sha = release.get("mergedMainSha")
        receipt_digest = release.get("machinePolicyReceiptDigest")
        pull_request_number = release.get("pullRequestNumber")
        pull_request_url = release.get("pullRequestUrl")
        if (
            not isinstance(merged_main_sha, str)
            or SHA_PATTERN.fullmatch(merged_main_sha) is None
            or not isinstance(receipt_digest, str)
            or DIGEST_PATTERN.fullmatch(receipt_digest) is None
            or not isinstance(pull_request_number, int)
            or pull_request_number < 1
            or not isinstance(pull_request_url, str)
            or not pull_request_url.startswith("https://github.com/")
        ):
            raise RuntimeError(
                "publisher claimed success without exact merged-main, PR, and policy bindings"
            )
        return merged_main_sha, receipt_digest, pull_request_number, pull_request_url

    @staticmethod
    def _value_failure_reasons(
        role: str,
        structured_output: Mapping[str, object] | None,
    ) -> tuple[list[str], bool]:
        if role not in {"audit", "adversary"} or structured_output is None:
            return [], False
        reasons: list[str] = []
        value_disposition = structured_output.get("valueDisposition")
        native_disposition = structured_output.get("nativeDisposition")
        native_sufficient = (
            structured_output.get("nativeWorkflowSufficient") is True
            or native_disposition == "NATIVE_WORKFLOW_SUFFICIENT"
        )
        if native_sufficient:
            reasons.append("native workflow is sufficient")
        if (
            structured_output.get("incrementalDecisionValue") is False
            or value_disposition == "NO_INCREMENTAL_DECISION_VALUE"
        ):
            reasons.append("no incremental decision value")
        if (
            structured_output.get("economicallyViable") is False
            or structured_output.get("technicallyValidButUneconomic") is True
            or value_disposition == "TECHNICALLY_VALID_BUT_UNECONOMIC"
        ):
            reasons.append("technically valid but uneconomic")
        return reasons, native_sufficient

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
                trusted_root_environment_variable=(external.trusted_root_environment_variable),
                trusted_public_key_environment_variable=(
                    external.trusted_public_key_environment_variable
                ),
            )
            verified[group] = record.require_commercial_trust().observed_at
        return verified

    def _bound_resume_handoff(
        self,
        *,
        checkpoint: V3Checkpoint,
        item: WorkItem,
        role: str,
    ) -> tuple[AgentSession, Handoff] | None:
        """Load an exact digest-bound backend handoff for one interrupted stage."""

        if not self.backend.capabilities().resume:
            return None
        if (
            checkpoint.backend_session is None
            or checkpoint.active_role != role
            or checkpoint.handoff_path is None
            or checkpoint.handoff_digest is None
        ):
            return None
        path = Path(checkpoint.handoff_path).resolve()
        try:
            path.relative_to(self.artifact_root.resolve())
        except ValueError as exc:
            raise RuntimeError("checkpoint handoff escaped the V3 artifact root") from exc
        if not path.is_file() or _digest_file(path) != checkpoint.handoff_digest:
            raise RuntimeError("checkpoint handoff is missing or substituted")
        bound = read_v3_handoff(path)
        payload = bound.payload
        if (
            payload.work_item_id != item.work_item_id
            or payload.source_digest != checkpoint.source_digest
            or payload.context_digest != checkpoint.context_digest
            or payload.candidate_sha != checkpoint.candidate_sha
            or payload.backend_session_ref != checkpoint.backend_session.session_ref
        ):
            raise RuntimeError("checkpoint handoff does not match the resumable stage")
        return checkpoint.backend_session, Handoff(
            work_item_id=payload.work_item_id,
            lane=payload.lane,
            milestone=payload.milestone,
            task_kind=payload.task_type.value,
            disposition=payload.disposition.value,
            decision_contribution=payload.decision_contribution,
            source_digest=payload.source_digest,
            context_digest=payload.context_digest,
            candidate_sha=payload.candidate_sha,
            candidate_manifest_digest=payload.candidate_manifest_digest,
            next_authorized_transition=payload.next_authorized_transition,
            artifact_digests=payload.artifact_digests,
            findings=payload.findings,
            attempts_remaining=payload.attempts_remaining,
            circuit_breaker_state=payload.circuit_breaker_state,
            external_evidence_required=payload.external_evidence_required,
        )

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
        base_sha = current_sha(self.git_root, "main")
        research_advisory: ResearchAdvisoryBundle | None = None
        if item.kind is WorkKind.RESEARCH and item.lane in {Lane.MARKET, Lane.COMPETITOR}:
            if self.phase6_runtime is None:
                self.queue.transition(
                    item.work_item_id,
                    WorkStatus.WAITING_EXTERNAL,
                    updated_at=datetime.now(UTC),
                )
                return {
                    "status": WorkStatus.WAITING_EXTERNAL.value,
                    "workItemId": item.work_item_id,
                    "reason": "controlled source acquisition runtime is unavailable",
                    "unrelatedLanesMayContinue": True,
                }
            try:
                research_advisory = self.phase6_runtime.prepare_research_advisory(
                    item=item,
                    candidate_sha=base_sha,
                    artifact_root=(
                        self.artifact_root / item.work_item_id / f"research-{base_sha[:12]}"
                    ),
                    now=now,
                )
            except Phase6RuntimeError as exc:
                self.queue.transition(
                    item.work_item_id,
                    WorkStatus.WAITING_EXTERNAL,
                    updated_at=datetime.now(UTC),
                )
                return {
                    "status": WorkStatus.WAITING_EXTERNAL.value,
                    "workItemId": item.work_item_id,
                    "reason": str(exc),
                    "unrelatedLanesMayContinue": True,
                }
        run_id = f"{item.work_item_id.lower()}-{now.strftime('%Y%m%dT%H%M%S%fZ')}"
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
                cwd=self.git_root,
                check=False,
            )
            if ancestor.returncode != 0:
                raise RuntimeError("recovery checkpoint candidate is not based on current main")
            worktree_base = recovered_checkpoint.candidate_sha
        if recovered_checkpoint is not None and recovered_checkpoint.publication_transaction_id:
            if (
                not recovered_checkpoint.active
                or recovered_checkpoint.candidate_worktree is None
                or recovered_checkpoint.publication_manifest_path is None
                or recovered_checkpoint.publication_manifest_digest is None
                or recovered_checkpoint.publication_checkpoint_digest is None
                or recovered_checkpoint.publication_packet_digest is None
                or recovered_checkpoint.publication_candidate_tree_sha is None
                or not recovered_checkpoint.publication_gate_digests
            ):
                raise RuntimeError("pending publication checkpoint is incomplete")
            publication_worktree = Path(recovered_checkpoint.candidate_worktree).resolve()
            publication_manifest = Path(recovered_checkpoint.publication_manifest_path).resolve()
            try:
                publication_worktree.relative_to(self.runtime_paths.worktree_root.resolve())
                publication_manifest.relative_to(self.artifact_root.resolve())
            except ValueError as exc:
                raise RuntimeError("pending publication paths escaped their bounded roots") from exc
            try:
                assert_frozen_candidate(
                    publication_worktree,
                    expected_candidate_sha=recovered_checkpoint.candidate_sha,
                    expected_candidate_tree_sha=(
                        recovered_checkpoint.publication_candidate_tree_sha
                    ),
                )
            except CandidateFreezeError as exc:
                raise RuntimeError("pending publication candidate is not frozen") from exc
            if (
                not publication_manifest.is_file()
                or _digest_file(publication_manifest)
                != recovered_checkpoint.publication_manifest_digest
            ):
                raise RuntimeError("pending publication candidate or manifest was substituted")
            self._checkpoint_research_advisory(recovered_checkpoint)
            try:
                self._reverify_external_evidence(
                    item=item,
                    candidate_sha=recovered_checkpoint.candidate_sha,
                    checkpoint=recovered_checkpoint,
                    now=now,
                )
            except ExternalEvidenceVerificationError as exc:
                recovered_checkpoint.active = False
                recovered_checkpoint.approval_state = "TRUSTED_EXTERNAL_EVIDENCE_TAINTED"
                recovered_checkpoint.circuit_breaker_reason = str(exc)
                recovered_checkpoint.updated_at = now
                self.checkpoints.save_v3(recovered_checkpoint)
                self.queue.transition(item.work_item_id, WorkStatus.BLOCKED_POLICY, updated_at=now)
                return {
                    "status": WorkStatus.BLOCKED_POLICY.value,
                    "workItemId": item.work_item_id,
                    "reason": "external authority changed before publication recovery",
                }
            self._reverify_traincheck_evidence(recovered_checkpoint, publication_manifest)
            self._reverify_release_evidence_authorization(
                recovered_checkpoint, publication_manifest
            )
            release = dict(
                self.publisher.publish(
                    item=item,
                    candidate_ref="recovered-publication",
                    candidate_sha=recovered_checkpoint.candidate_sha,
                    candidate_worktree=publication_worktree,
                    candidate_manifest_path=publication_manifest,
                    packet_digest=recovered_checkpoint.publication_packet_digest,
                    source_digest=recovered_checkpoint.source_digest,
                    context_digest=recovered_checkpoint.context_digest,
                    checkpoint_digest=recovered_checkpoint.publication_checkpoint_digest,
                    gate_digests=dict(recovered_checkpoint.publication_gate_digests),
                    expected_candidate_tree_sha=(
                        recovered_checkpoint.publication_candidate_tree_sha
                    ),
                    expected_machine_policy_receipt_id=(
                        recovered_checkpoint.publication_expected_machine_policy_receipt_id
                    ),
                    expected_machine_policy_receipt_digest=(
                        recovered_checkpoint.publication_expected_machine_policy_receipt_digest
                    ),
                    expected_release_authorization_envelope_digest=(
                        recovered_checkpoint.publication_authorization_envelope_digest
                    ),
                    lease_guard=lambda: self._renew_active_lease(item.work_item_id),
                )
            )
            if release.get("status") == "PENDING_REQUIRED_CHECKS":
                return self._pause_publication(
                    item=item,
                    checkpoint=recovered_checkpoint,
                    release=release,
                )
            if release.get("status") != "MERGED_MAIN_VERIFIED":
                recovered_checkpoint.active = False
                recovered_checkpoint.circuit_breaker_reason = (
                    "publication transaction reached a terminal non-success state"
                )
                self.checkpoints.save_v3(recovered_checkpoint)
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
            _, receipt_digest, _, _ = self._validated_publication_success(release)
            recovered_checkpoint.active = False
            recovered_checkpoint.backend_wait_state = None
            recovered_checkpoint.backend_resume_at = None
            recovered_checkpoint.approval_state = "INDEPENDENT_RELEASE_VERIFIED"
            recovered_checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(recovered_checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.PASSED_ENGINEERING,
                updated_at=datetime.now(UTC),
            )
            self._record_completion_evidence(
                item=item,
                candidate_sha=recovered_checkpoint.candidate_sha,
                checkpoint_digest=recovered_checkpoint.publication_checkpoint_digest,
                manifest_digest=recovered_checkpoint.publication_manifest_digest,
                machine_policy_receipt_digest=receipt_digest,
                independent_reviewed=any(
                    role in {"audit", "adversary", "security"} for role in self._roles(item)
                ),
                now=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.PASSED_ENGINEERING.value,
                "workItemId": item.work_item_id,
                "release": release,
                "resumedPublication": True,
            }
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
        backend_recheck_resume = (
            recovered_checkpoint is not None
            and recovered_checkpoint.approval_state == "BACKEND_RECHECK_READY"
        )
        if budget.plan_attempts_remaining <= 0 and not backend_recheck_resume:
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
        if not backend_recheck_resume:
            budget.plan_attempts_remaining -= 1
        resumable_candidate = (
            recovered_checkpoint is not None
            and recovered_checkpoint.active
            and recovered_checkpoint.candidate_worktree is not None
            and recovered_checkpoint.artifact_root is not None
        )
        if resumable_candidate:
            assert recovered_checkpoint is not None
            assert recovered_checkpoint.candidate_worktree is not None
            assert recovered_checkpoint.artifact_root is not None
            candidate_path = Path(recovered_checkpoint.candidate_worktree).resolve()
            artifact_path = Path(recovered_checkpoint.artifact_root).resolve()
            try:
                candidate_path.relative_to(self.runtime_paths.worktree_root.resolve())
                artifact_path.relative_to(self.artifact_root.resolve())
            except ValueError as exc:
                raise RuntimeError("resumable candidate escaped its bounded roots") from exc
            if (
                not candidate_path.is_dir()
                or current_sha(candidate_path) != recovered_checkpoint.candidate_sha
                or not artifact_path.is_dir()
            ):
                recovered_checkpoint.active = False
                recovered_checkpoint.approval_state = "CANDIDATE_SALVAGE_TRANSPLANTED"
                recovered_checkpoint.circuit_breaker_reason = (
                    "resumable worktree/artifacts unavailable; candidate commit transplanted "
                    "into a clean bounded worktree and all stages require revalidation"
                )
                recovered_checkpoint.completed_roles = []
                recovered_checkpoint.stage_artifact_digests = {}
                recovered_checkpoint.stage_artifact_paths = {}
                recovered_checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(recovered_checkpoint)
                resumable_candidate = False
                worktree = create_worktree(
                    self.git_root,
                    self.runtime_paths.worktree_root,
                    task_id=item.work_item_id,
                    run_id=f"{run_id}-salvage",
                    role="owner",
                    attempt=1,
                    base_sha=worktree_base,
                )
                root = self.artifact_root / item.work_item_id / f"{run_id}-salvage"
                root.mkdir(parents=True, exist_ok=True)
                write_json(
                    root / "SALVAGE_RECEIPT.json",
                    {
                        "schemaVersion": "3.1",
                        "workItemId": item.work_item_id,
                        "sourceCandidateSha": recovered_checkpoint.candidate_sha,
                        "sourceCheckpointGeneration": recovered_checkpoint.generation,
                        "allStagesRequireRevalidation": True,
                    },
                )
            else:
                worktree = Worktree(
                    path=candidate_path,
                    branch="recovered-bound-candidate",
                    base_sha=worktree_base,
                )
                root = artifact_path
        else:
            worktree = create_worktree(
                self.git_root,
                self.runtime_paths.worktree_root,
                task_id=item.work_item_id,
                run_id=run_id,
                role="owner",
                attempt=1,
                base_sha=worktree_base,
            )
            root = self.artifact_root / item.work_item_id / run_id
            root.mkdir(parents=True, exist_ok=True)
        generation = recovered_checkpoint.generation + 1 if recovered_checkpoint else 1
        if research_advisory is not None:
            if self.phase6_runtime is None:
                raise RuntimeError("research advisory lost its controller runtime")
            research_advisory = self.phase6_runtime.materialize_research_advisory(
                research_advisory,
                evidence_root=(root / "research-evidence" / f"generation-{generation:04d}"),
            )
        checkpoint = V3Checkpoint(
            generation=generation,
            work_item_id=item.work_item_id,
            lane=item.lane,
            milestone=item.milestone,
            backend_session_ref=(
                recovered_checkpoint.backend_session_ref
                if recovered_checkpoint is not None and resumable_candidate
                else None
            ),
            backend_session=(
                recovered_checkpoint.backend_session
                if recovered_checkpoint is not None and resumable_candidate
                else None
            ),
            active_role=(
                recovered_checkpoint.active_role
                if recovered_checkpoint is not None and resumable_candidate
                else None
            ),
            stage_attempt=(
                recovered_checkpoint.stage_attempt
                if recovered_checkpoint is not None and resumable_candidate
                else 0
            ),
            handoff_path=(
                recovered_checkpoint.handoff_path
                if recovered_checkpoint is not None and resumable_candidate
                else None
            ),
            handoff_digest=(
                recovered_checkpoint.handoff_digest
                if recovered_checkpoint is not None and resumable_candidate
                else None
            ),
            candidate_worktree=str(worktree.path.resolve()),
            artifact_root=str(root.resolve()),
            completed_roles=(
                list(recovered_checkpoint.completed_roles)
                if recovered_checkpoint is not None and resumable_candidate
                else []
            ),
            stage_artifact_digests=(
                dict(recovered_checkpoint.stage_artifact_digests)
                if recovered_checkpoint is not None and resumable_candidate
                else {}
            ),
            stage_artifact_paths=(
                dict(recovered_checkpoint.stage_artifact_paths)
                if recovered_checkpoint is not None and resumable_candidate
                else {}
            ),
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
            value_failure_count=(
                recovered_checkpoint.value_failure_count if recovered_checkpoint is not None else 0
            ),
            value_redesigns_remaining=(
                recovered_checkpoint.value_redesigns_remaining
                if recovered_checkpoint is not None
                else self.autonomy.value.max_value_redesigns
            ),
            backend_wait_state=None,
            backend_resume_at=None,
            backend_rechecks_remaining=(
                recovered_checkpoint.backend_rechecks_remaining
                if recovered_checkpoint is not None
                else 3
            ),
            backend_recheck_attempts=(
                recovered_checkpoint.backend_recheck_attempts
                if recovered_checkpoint is not None
                else 0
            ),
            backend_terminal_record_digest=(
                recovered_checkpoint.backend_terminal_record_digest
                if recovered_checkpoint is not None
                else None
            ),
            execution_evidence_mode=(
                recovered_checkpoint.execution_evidence_mode
                if recovered_checkpoint is not None
                else None
            ),
            publication_transaction_id=(
                recovered_checkpoint.publication_transaction_id
                if recovered_checkpoint is not None
                else None
            ),
            publication_manifest_path=(
                recovered_checkpoint.publication_manifest_path
                if recovered_checkpoint is not None
                else None
            ),
            publication_manifest_digest=(
                recovered_checkpoint.publication_manifest_digest
                if recovered_checkpoint is not None
                else None
            ),
            publication_candidate_tree_sha=(
                recovered_checkpoint.publication_candidate_tree_sha
                if recovered_checkpoint is not None
                else None
            ),
            publication_checkpoint_digest=(
                recovered_checkpoint.publication_checkpoint_digest
                if recovered_checkpoint is not None
                else None
            ),
            publication_packet_digest=(
                recovered_checkpoint.publication_packet_digest
                if recovered_checkpoint is not None
                else None
            ),
            publication_gate_digests=(
                dict(recovered_checkpoint.publication_gate_digests)
                if recovered_checkpoint is not None
                else {}
            ),
            publication_expected_machine_policy_receipt_id=(
                recovered_checkpoint.publication_expected_machine_policy_receipt_id
                if recovered_checkpoint is not None
                else None
            ),
            publication_expected_machine_policy_receipt_digest=(
                recovered_checkpoint.publication_expected_machine_policy_receipt_digest
                if recovered_checkpoint is not None
                else None
            ),
            publication_authorization_envelope_path=(
                recovered_checkpoint.publication_authorization_envelope_path
                if recovered_checkpoint is not None
                else None
            ),
            publication_authorization_envelope_digest=(
                recovered_checkpoint.publication_authorization_envelope_digest
                if recovered_checkpoint is not None
                else None
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
        task_contract = compile_task_contract_v31(
            item,
            task_packet_digest=packet.canonical_digest(),
            source_generation_id=self.active_source.generation_id,
            source_digest=packet.source_digest,
            context_digest=packet.context_digest,
        )
        task_contract_path = root / "task-contract.json"
        write_json(
            task_contract_path,
            task_contract.model_dump(mode="json", by_alias=True),
        )
        report_schema = execution_report_schema()
        report_schema_bytes = (
            json.dumps(report_schema, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        )
        checkpoint.context_digest = packet.context_digest
        checkpoint.source_digest = packet.source_digest
        checkpoint.candidate_sha = worktree_base
        checkpoint.updated_at = datetime.now(UTC)
        self.checkpoints.save_v3(checkpoint)
        stage_bindings: list[StageArtifactBinding] = [
            StageArtifactBinding(
                stage="controller",
                name="task-contract",
                digest=task_contract.canonical_digest(),
            ),
            StageArtifactBinding(
                stage="controller",
                name="agent-execution-report-schema",
                digest=sha256_digest(report_schema_bytes),
            ),
        ]
        bound_artifacts: dict[str, bytes] = {
            "packet": packet.canonical_json_bytes(),
            "context": planning_context.canonical_json_bytes(),
            "stage:controller:task-contract": task_contract.canonical_json_bytes(),
            "stage:controller:agent-execution-report-schema": report_schema_bytes,
        }
        if research_advisory is not None:
            assert self.phase6_runtime is not None
            research_payloads = self.phase6_runtime.verify_research_advisory(research_advisory)
            research_paths: dict[str, Path] = {
                "research-advisory-bundle": Path(research_advisory.bundle_path),
                "research-report": Path(research_advisory.report_path),
                **{
                    f"research-raw-{artifact.source_id}": Path(artifact.raw_cas_path)
                    for artifact in research_advisory.artifacts
                },
                **{
                    f"research-receipt-{artifact.source_id}": Path(artifact.receipt_path)
                    for artifact in research_advisory.artifacts
                },
                **{
                    f"research-typed-{name}": Path(path)
                    for name, path in research_advisory.typed_market_artifact_paths.items()
                },
            }
            research_bytes: dict[str, bytes] = {
                "research-advisory-bundle": Path(research_advisory.bundle_path).read_bytes(),
                "research-report": research_payloads["report"],
                **{
                    f"research-raw-{artifact.source_id}": research_payloads[
                        f"raw:{artifact.source_id}"
                    ]
                    for artifact in research_advisory.artifacts
                },
                **{
                    f"research-receipt-{artifact.source_id}": research_payloads[
                        f"receipt:{artifact.source_id}"
                    ]
                    for artifact in research_advisory.artifacts
                },
                **{
                    f"research-typed-{name}": research_payloads[f"typed:{name}"]
                    for name in research_advisory.typed_market_artifacts
                },
            }
            for name, path in sorted(research_paths.items()):
                raw = research_bytes[name]
                digest = sha256_digest(raw)
                stage_bindings.append(
                    StageArtifactBinding(stage="controller", name=name, digest=digest)
                )
                bound_artifacts[f"stage:controller:{name}"] = raw
                checkpoint.stage_artifact_digests[f"controller:{name}"] = digest
                checkpoint.stage_artifact_paths[f"controller:{name}"] = str(path.resolve())
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)
        materialized_output_copies: dict[str, Path] = {}
        for key, digest in sorted(checkpoint.stage_artifact_digests.items()):
            if key not in checkpoint.stage_artifact_paths or ":" not in key:
                raise RuntimeError("checkpoint stage artifact binding is incomplete")
            stage, name = key.split(":", 1)
            if stage not in checkpoint.completed_roles:
                continue
            artifact_path = Path(checkpoint.stage_artifact_paths[key]).resolve()
            try:
                artifact_path.relative_to(root.resolve())
            except ValueError as exc:
                raise RuntimeError("checkpoint stage artifact escaped its artifact root") from exc
            if not artifact_path.is_file():
                raise RuntimeError("checkpoint stage artifact is missing or substituted")
            if name == "context-manifest":
                artifact_bytes = V3ContextManifest.model_validate(
                    read_json(artifact_path, {})
                ).canonical_json_bytes()
                observed_digest = sha256_digest(artifact_bytes)
            else:
                artifact_bytes = artifact_path.read_bytes()
                observed_digest = _digest_file(artifact_path)
            if observed_digest != digest:
                raise RuntimeError("checkpoint stage artifact is missing or substituted")
            stage_bindings.append(StageArtifactBinding(stage=stage, name=name, digest=digest))
            bound_artifacts[f"stage:{stage}:{name}"] = artifact_bytes
        backend_session_ref: str | None = None
        candidate_sha = base_sha
        for index, role in enumerate(self._roles(item), start=1):
            if role in checkpoint.completed_roles:
                candidate_sha = current_sha(worktree.path)
                continue
            stage_base_sha = current_sha(worktree.path)
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
                    "taskContract": task_contract.model_dump(mode="json", by_alias=True),
                    "sourceContextManifest": role_context.model_dump(mode="json", by_alias=True),
                    "controllerAdvisoryEvidence": (
                        research_advisory.agent_context() if research_advisory is not None else None
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
            context_key = f"{role}:context-manifest"
            checkpoint.stage_artifact_digests[context_key] = role_context_digest
            checkpoint.stage_artifact_paths[context_key] = str(role_context_path.resolve())
            tool_policy = tool_policy_for_request(
                task_contract,
                mutating_owner=index == 1 and task_contract.mutating_work_item,
            )
            request_task_packet = packet.model_dump(mode="json", by_alias=True)
            request_task_packet["taskContract"] = task_contract.model_dump(
                mode="json", by_alias=True
            )
            if research_advisory is not None:
                request_task_packet["controllerAdvisoryEvidence"] = (
                    research_advisory.agent_context()
                )
            request = AgentTaskRequest(
                request_id=f"AREQ-{run_id.upper().replace('-', '_')}-{role.upper()}",
                work_item_id=item.work_item_id,
                role=role,
                task_packet=request_task_packet,
                source_context_manifest={
                    **role_context.model_dump(mode="json", by_alias=True),
                    "sourceDigest": packet.source_digest,
                    "contextDigest": role_context_digest,
                    "packetDigest": packet.canonical_digest(),
                    "controllerAdvisoryEvidence": (
                        research_advisory.agent_context() if research_advisory is not None else None
                    ),
                },
                allowed_paths=packet.allowed_paths,
                forbidden_paths=packet.forbidden_paths,
                tools=tool_policy.allowed_tools,
                network_policy="DENY",
                output_schema=report_schema,
                controller_repo_root=str(self.repo_root),
                candidate_worktree=str(worktree.path),
                artifact_root=str(root),
                prompt=task_prompt,
                system_prompt=system_prompt,
                schema_digest=sha256_digest(report_schema_bytes),
                context_digest=role_context_digest,
                source_digest=packet.source_digest,
                max_turns=64,
                max_tokens=96_000,
                max_cost_usd_equivalent=12.0,
                max_wall_time_seconds=14_400,
                bash_allowlist=[
                    BashCommandRule(
                        executable=rule.executable,
                        argumentPrefix=rule.argument_prefix,
                    )
                    for rule in tool_policy.bash_rules
                ],
                network_allowed=False,
            )
            resumable = self._bound_resume_handoff(
                checkpoint=checkpoint,
                item=item,
                role=role,
            )
            stage_attempt = checkpoint.stage_attempt if resumable is not None else 0
            while True:
                stage_attempt += 1
                request = request.model_copy(
                    update={"request_id": f"{request.request_id}-A{stage_attempt:02d}"}
                )
                expected_report_request_id = request.request_id
                if resumable is None:
                    result = await self.backend.execute(request)
                else:
                    resume_session, resume_handoff = resumable
                    expected_report_request_id = resume_session.request_id
                    result = await asyncio.to_thread(
                        self.backend.resume,
                        resume_session,
                        resume_handoff,
                    )
                    resumable = None
                backend_session_ref = result.session.session_ref
                mode_rank = {
                    ExecutionEvidenceMode.SIMULATION: 0,
                    ExecutionEvidenceMode.CONTROLLED_VALIDATION: 1,
                    ExecutionEvidenceMode.LIVE_VALIDATION: 2,
                    ExecutionEvidenceMode.EXTERNAL_VALIDATION: 3,
                }
                if (
                    checkpoint.execution_evidence_mode is None
                    or mode_rank[result.evidence_mode]
                    < mode_rank[checkpoint.execution_evidence_mode]
                ):
                    checkpoint.execution_evidence_mode = result.evidence_mode
                if result.state is SessionState.COMPLETED and result.verdict.lower() == "pass":
                    break
                retryable_dispositions = {
                    BackendTerminalDisposition.AUTH_EXPIRED,
                    BackendTerminalDisposition.QUOTA_WAIT,
                    BackendTerminalDisposition.INFRASTRUCTURE,
                    BackendTerminalDisposition.TIMEOUT,
                }
                if result.terminal_disposition in retryable_dispositions:
                    backend_state = result.error_state
                    if (
                        backend_state
                        not in {
                            BackendRouteState.AUTH_EXPIRED,
                            BackendRouteState.QUOTA_WAIT,
                            BackendRouteState.INFRASTRUCTURE,
                            BackendRouteState.TIMEOUT,
                        }
                        or result.terminal_record_digest is None
                    ):
                        raise RuntimeError(
                            "retryable backend result omitted its typed durable binding"
                        )
                    assert backend_state is not None
                    terminal_names = [
                        name
                        for name, digest in result.artifact_digests.items()
                        if digest == result.terminal_record_digest
                    ]
                    if len(terminal_names) != 1:
                        raise RuntimeError(
                            "retryable backend result omitted its unique terminal artifact"
                        )
                    terminal_path = (root / terminal_names[0]).resolve()
                    try:
                        terminal_path.relative_to(root.resolve())
                    except ValueError as exc:
                        raise RuntimeError("backend terminal artifact escaped its root") from exc
                    if (
                        terminal_path.is_symlink()
                        or not terminal_path.is_file()
                        or _digest_file(terminal_path) != result.terminal_record_digest
                    ):
                        raise RuntimeError("backend terminal artifact is missing or substituted")
                    if checkpoint.backend_rechecks_remaining <= 0:
                        checkpoint.active = False
                        checkpoint.backend_wait_state = backend_state
                        checkpoint.backend_resume_at = None
                        checkpoint.backend_terminal_record_digest = result.terminal_record_digest
                        checkpoint.circuit_breaker_reason = (
                            f"{backend_state.value} backend recheck budget exhausted"
                        )
                        checkpoint.updated_at = datetime.now(UTC)
                        self.checkpoints.save_v3(checkpoint)
                        self.queue.transition(
                            item.work_item_id,
                            WorkStatus.BLOCKED_TECHNICAL,
                            updated_at=datetime.now(UTC),
                        )
                        return {
                            "status": WorkStatus.BLOCKED_TECHNICAL.value,
                            "workItemId": item.work_item_id,
                            "backendState": backend_state.value,
                            "backendRechecksRemaining": 0,
                            "reason": "finite backend recheck budget exhausted",
                        }
                    retry_at: datetime
                    try:
                        retry_at = datetime.fromisoformat(result.usage.retry_at or "")
                        if retry_at.tzinfo is None:
                            retry_at = retry_at.replace(tzinfo=UTC)
                    except ValueError:
                        retry_at = datetime.now(UTC) + timedelta(
                            minutes=min(30, 2**checkpoint.backend_recheck_attempts)
                        )
                    if retry_at <= datetime.now(UTC):
                        retry_at = datetime.now(UTC) + timedelta(minutes=1)
                    checkpoint.backend_rechecks_remaining -= 1
                    checkpoint.backend_recheck_attempts += 1
                    checkpoint.backend_wait_state = backend_state
                    checkpoint.backend_resume_at = retry_at
                    checkpoint.backend_terminal_record_digest = result.terminal_record_digest
                    checkpoint.backend_session_ref = backend_session_ref
                    checkpoint.backend_session = result.session
                    checkpoint.active_role = role
                    checkpoint.stage_attempt = stage_attempt
                    checkpoint.candidate_sha = current_sha(worktree.path)
                    checkpoint.approval_state = "BACKEND_RECHECK_PENDING"
                    checkpoint.circuit_breaker_reason = (
                        f"scoped backend wait: {backend_state.value}"
                    )
                    checkpoint.updated_at = datetime.now(UTC)
                    handoff_path = write_v3_handoff(
                        artifact_root=root,
                        relative_path=f"backend-wait-{role}-{stage_attempt:02d}.json",
                        work_item=item,
                        disposition=item.disposition,
                        attempt=stage_attempt,
                        attempts_remaining=checkpoint.backend_rechecks_remaining,
                        base_sha=base_sha,
                        candidate_sha=checkpoint.candidate_sha,
                        next_action="RECHECK_BACKEND_ROUTE",
                        findings=[
                            {
                                "backendState": backend_state.value,
                                "terminalRecordDigest": result.terminal_record_digest,
                                "resumeAt": retry_at.isoformat(),
                            }
                        ],
                        artifacts={},
                        source_digest=checkpoint.source_digest,
                        context_digest=checkpoint.context_digest,
                        circuit_breaker_state="BOUNDED_RECHECK",
                        backend_session_ref=backend_session_ref,
                    )
                    checkpoint.handoff_path = str(handoff_path.resolve())
                    checkpoint.handoff_digest = _digest_file(handoff_path)
                    self.checkpoints.save_v3(checkpoint)
                    self.queue.transition(
                        item.work_item_id,
                        WorkStatus.PAUSED_BACKEND,
                        updated_at=datetime.now(UTC),
                    )
                    return {
                        "status": WorkStatus.PAUSED_BACKEND.value,
                        "workItemId": item.work_item_id,
                        "backendState": backend_state.value,
                        "resumeAt": retry_at.isoformat(),
                        "backendRechecksRemaining": checkpoint.backend_rechecks_remaining,
                    }
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
                checkpoint.backend_session = result.session
                checkpoint.active_role = role
                checkpoint.stage_attempt = stage_attempt
                checkpoint.candidate_sha = current_sha(worktree.path)
                handoff_path = write_v3_handoff(
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
                    circuit_breaker_state=("OPEN" if repeated or exhausted else "RETRYING"),
                    backend_session_ref=backend_session_ref,
                )
                checkpoint.handoff_path = str(handoff_path.resolve())
                checkpoint.handoff_digest = _digest_file(handoff_path)
                self.checkpoints.save_v3(checkpoint)
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
                resumable = self._bound_resume_handoff(
                    checkpoint=checkpoint,
                    item=item,
                    role=role,
                )
            candidate_sha = current_sha(worktree.path)
            if result.structured_output is None:
                raise RuntimeError("backend PASS omitted the strict agent execution report")
            execution_report = AgentExecutionReportV31.model_validate_json(
                json.dumps(result.structured_output)
            )
            actual_stage_changed_files = _changed_paths(
                self.git_root, stage_base_sha, candidate_sha
            )
            validate_execution_report_v31(
                execution_report,
                task_contract,
                candidate_root=worktree.path,
                tool_policy=tool_policy,
                expected_request_id=expected_report_request_id,
                expected_role=role,
                expected_base_sha=base_sha,
                expected_candidate_sha=candidate_sha,
                expected_context_digest=role_context_digest,
                actual_changed_files=actual_stage_changed_files,
            )
            report_path = root / f"validated-report-{index:02d}-{role}.json"
            write_json(
                report_path,
                execution_report.model_dump(mode="json", by_alias=True),
            )
            report_digest = _digest_file(report_path)
            report_name = "validated-agent-execution-report"
            stage_bindings.append(
                StageArtifactBinding(stage=role, name=report_name, digest=report_digest)
            )
            bound_artifacts[f"stage:{role}:{report_name}"] = report_path.read_bytes()
            report_key = f"{role}:{report_name}"
            checkpoint.stage_artifact_digests[report_key] = report_digest
            checkpoint.stage_artifact_paths[report_key] = str(report_path.resolve())
            for output in execution_report.outputs:
                output_name = f"materialized-output:{output.output_id}"
                output_path = worktree.path / output.path
                output_copy = root / (
                    f"materialized-output-{index:02d}-"
                    f"{hashlib.sha256(output_name.encode()).hexdigest()[:16]}.json"
                )
                shutil.copy2(output_path, output_copy)
                materialized_output_copies[f"{role}:{output.output_id}"] = output_copy
                stage_bindings.append(
                    StageArtifactBinding(
                        stage=role,
                        name=output_name,
                        digest=output.content_digest,
                    )
                )
                bound_artifacts[f"stage:{role}:{output_name}"] = output_path.read_bytes()
                output_key = f"{role}:{output_name}"
                checkpoint.stage_artifact_digests[output_key] = output.content_digest
                checkpoint.stage_artifact_paths[output_key] = str(output_copy.resolve())
            if index == 1 and item.kind is WorkKind.CONTROLLED_EXPERIMENT:
                logical_bindings = {
                    BENCHMARK_FILE: BENCHMARK_BINDING,
                    VALUE_RESULT_FILE: VALUE_RESULT_BINDING,
                    POLICY_FILE: POLICY_BINDING,
                }
                by_filename = {
                    PurePosixPath(output.path).name: output for output in execution_report.outputs
                }
                if set(logical_bindings) - set(by_filename):
                    raise RuntimeError("controlled experiment report omitted native/value outputs")
                for filename, binding_name in logical_bindings.items():
                    output = by_filename[filename]
                    stage_bindings.append(
                        StageArtifactBinding(
                            stage=role,
                            name=binding_name,
                            digest=output.content_digest,
                        )
                    )
                    native_output_path = worktree.path / output.path
                    bound_artifacts[f"stage:{role}:{binding_name}"] = (
                        native_output_path.read_bytes()
                    )
                    native_key = f"{role}:{binding_name}"
                    checkpoint.stage_artifact_digests[native_key] = output.content_digest
                    checkpoint.stage_artifact_paths[native_key] = str(
                        materialized_output_copies[f"{role}:{output.output_id}"].resolve()
                    )
            if execution_report.verdict is not ExecutionVerdict.PASS:
                checkpoint.active = False
                checkpoint.approval_state = "VALIDATED_NON_PASS_REPORT"
                checkpoint.circuit_breaker_reason = (
                    f"validated {role} report returned {execution_report.verdict.value}"
                )
                checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(checkpoint)
                target = (
                    WorkStatus.BLOCKED_POLICY
                    if execution_report.verdict is ExecutionVerdict.BLOCKED
                    else WorkStatus.BLOCKED_TECHNICAL
                )
                self.queue.transition(item.work_item_id, target, updated_at=datetime.now(UTC))
                write_v3_handoff(
                    artifact_root=root,
                    relative_path=f"validated-non-pass-{role}.json",
                    work_item=item,
                    disposition=item.disposition,
                    attempt=stage_attempt,
                    attempts_remaining=checkpoint.budget.repair_cycles_remaining,
                    base_sha=base_sha,
                    candidate_sha=candidate_sha,
                    next_action=target.value,
                    findings=[
                        {
                            "fingerprint": finding.fingerprint,
                            "severity": finding.severity.value,
                            "observed": finding.observed,
                        }
                        for finding in execution_report.findings
                    ],
                    artifacts={"validatedReport": report_path},
                    source_digest=checkpoint.source_digest,
                    context_digest=checkpoint.context_digest,
                    backend_session_ref=backend_session_ref,
                )
                return {
                    "status": target.value,
                    "workItemId": item.work_item_id,
                    "reportVerdict": execution_report.verdict.value,
                    "validatedReportDigest": report_digest,
                }
            actual_changed_files = _changed_paths(self.git_root, base_sha, candidate_sha)
            assert_candidate_scope(
                actual_changed_files,
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
                artifact_key = f"{role}:{name}"
                checkpoint.stage_artifact_digests[artifact_key] = digest
                checkpoint.stage_artifact_paths[artifact_key] = str(artifact_path)
            checkpoint.generation += 1
            checkpoint.candidate_sha = candidate_sha
            checkpoint.backend_session_ref = backend_session_ref
            checkpoint.backend_session = None
            checkpoint.active_role = None
            checkpoint.stage_attempt = 0
            checkpoint.handoff_path = None
            checkpoint.handoff_digest = None
            checkpoint.completed_roles.append(role)
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)
            value_reasons, native_sufficient = self._value_failure_reasons(
                role,
                result.structured_output,
            )
            if value_reasons and item.kind is not WorkKind.CONTROLLED_EXPERIMENT:
                checkpoint.value_failure_count += 1
                value_decision = value_redesign_failure(
                    checkpoint.value_failure_count,
                    max_value_redesigns=self.autonomy.value.max_value_redesigns,
                    native_workflow_sufficient=native_sufficient,
                )
                checkpoint.value_redesigns_remaining = value_decision.redesigns_remaining
                checkpoint.circuit_breaker_reason = "; ".join(value_reasons)
                proposed_status = value_decision.status
                transition_status = (
                    WorkStatus.READY
                    if proposed_status is WorkStatus.READY
                    else WorkStatus.BLOCKED_POLICY
                )
                checkpoint.active = transition_status is WorkStatus.READY
                if transition_status is WorkStatus.READY:
                    # A redesign is a new candidate-validation attempt.  No report,
                    # reviewer, gate, or materialized-output binding from the failed
                    # value attempt may be carried forward to the next candidate.
                    checkpoint.completed_roles = []
                    checkpoint.stage_artifact_digests = {}
                    checkpoint.stage_artifact_paths = {}
                checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(checkpoint)
                proposal_path = write_value_redesign_proposal(
                    proposal_root=self.runtime_paths.value_redesign_proposals,
                    work_item_id=item.work_item_id,
                    decision=value_decision,
                    reasons=value_reasons,
                    candidate_sha=candidate_sha,
                    source_digest=checkpoint.source_digest,
                    context_digest=checkpoint.context_digest,
                    created_at=datetime.now(UTC),
                )
                self.queue.transition(
                    item.work_item_id,
                    transition_status,
                    updated_at=datetime.now(UTC),
                )
                return {
                    "status": transition_status.value,
                    "workItemId": item.work_item_id,
                    "redesignProposed": True,
                    "proposalPath": str(proposal_path),
                    "proposedTerminalStatus": (
                        proposed_status.value if proposed_status is not WorkStatus.READY else None
                    ),
                    "reason": (
                        "terminal value disposition requires the Phase 11 independent "
                        "native-value receipt adapter"
                        if transition_status is WorkStatus.BLOCKED_POLICY
                        else "bounded value redesign remains available"
                    ),
                    "redesignsRemaining": value_decision.redesigns_remaining,
                }

        self._reverify_research_advisory(research_advisory, checkpoint)
        checkpoint_snapshot = root / f"checkpoint-generation-{checkpoint.generation:04d}.json"
        write_json(
            checkpoint_snapshot,
            checkpoint.model_dump(mode="json", by_alias=True),
        )
        checkpoint_digest = _digest_file(checkpoint_snapshot)
        try:
            frozen_candidate = assert_frozen_candidate(
                worktree.path, expected_candidate_sha=candidate_sha
            )
        except CandidateFreezeError as exc:
            raise RuntimeError("candidate must be frozen before gates") from exc
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
            cwd=self.git_root,
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
        self._renew_active_lease(item.work_item_id)
        gate_paths = dict(
            self.publisher.prepare_candidate(
                item=item,
                candidate_sha=candidate_sha,
                candidate_worktree=worktree.path,
            )
        )
        self._renew_active_lease(item.work_item_id)
        try:
            assert_frozen_candidate(
                worktree.path,
                expected_candidate_sha=candidate_sha,
                expected_candidate_tree_sha=frozen_candidate.candidate_tree_sha,
            )
        except CandidateFreezeError as exc:
            quarantine_tainted_evidence(
                gate_paths,
                quarantine_root=root / "quarantine" / "post-gate-candidate-mutation",
                reason=str(exc),
            )
            raise RuntimeError("pre-publication gate tainted the frozen candidate") from exc
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
        gate_handoff_paths: dict[str, Path] = {}
        for index, (name, path) in enumerate(sorted(gate_paths.items()), start=1):
            gate_copy = root / f"publication-gate-{index:02d}.evidence"
            shutil.copy2(path, gate_copy)
            gate_handoff_paths[name] = gate_copy
        if (
            validate_active_source_generation(worktree.path).canonical_digest()
            != active_now.canonical_digest()
        ):
            raise RuntimeError("pre-publication gate mutated active source authority")
        assert_frozen_candidate(
            worktree.path,
            expected_candidate_sha=candidate_sha,
            expected_candidate_tree_sha=frozen_candidate.candidate_tree_sha,
        )
        self._reverify_research_advisory(research_advisory, checkpoint)
        bound_artifacts["checkpoint"] = checkpoint_snapshot.read_bytes()
        for binding in gate_bindings:
            bound_artifacts[f"gate:{binding.name}"] = gate_paths[binding.name].read_bytes()
        validated_reports: list[tuple[AgentExecutionReportV31, str, Path]] = []
        for key, path_text in sorted(checkpoint.stage_artifact_paths.items()):
            stage, separator, name = key.partition(":")
            if separator != ":" or name != "validated-agent-execution-report":
                continue
            path = Path(path_text)
            report = AgentExecutionReportV31.model_validate_json(
                path.read_text(encoding="utf-8"), strict=True
            )
            if report.candidate_sha != candidate_sha:
                raise RuntimeError(
                    f"validated {stage} report was not revalidated at the final candidate SHA"
                )
            validated_reports.append((report, _digest_file(path), path))
        expected_report_roles = set(self._roles(item))
        if {report.role for report, _, _ in validated_reports} != expected_report_roles:
            raise RuntimeError("candidate is missing a final-SHA validated role report")
        finding_bindings: list[FindingBinding] = []
        external_bindings: list[ExternalEvidenceBinding] = []
        seen_findings: set[str] = set()
        seen_receipts: set[str] = set()
        verified_external_evidence_refs: list[str] = []
        handoff_findings: list[dict[str, str]] = []
        report_handoff_artifacts: dict[str, Path] = {}
        for report, report_digest, report_path in validated_reports:
            report_handoff_artifacts[f"validatedReport:{report.role}"] = report_path
            for finding in report.findings:
                if finding.fingerprint not in seen_findings:
                    finding_bindings.append(
                        FindingBinding(
                            fingerprint=finding.fingerprint,
                            disposition=(
                                f"{finding.severity.value}:"
                                f"{'BLOCKING' if finding.blocking else 'NON_BLOCKING'}"
                            ),
                            artifact_digest=report_digest,
                        )
                    )
                    seen_findings.add(finding.fingerprint)
                handoff_findings.append(
                    {
                        "fingerprint": finding.fingerprint,
                        "severity": finding.severity.value,
                        "observed": finding.observed,
                    }
                )
            handoff_findings.extend(
                {"role": report.role, "limitation": limitation} for limitation in report.limitations
            )
            for reference in report.external_receipt_refs:
                receipt_id, digest = reference.split("@", 1)
                handoff_findings.append({"role": report.role, "externalReceiptRef": reference})
                if receipt_id not in seen_receipts:
                    try:
                        external_config = ExternalEvidenceConfig.model_validate(
                            load_yaml(self.repo_root / "config/external_evidence.yaml")
                        )
                        payload = load_verified_external_evidence_payload(
                            repo_root=self.repo_root,
                            subject_id=item.work_item_id,
                            trusted_root_environment_variable=(
                                external_config.trusted_root_environment_variable
                            ),
                            trusted_public_key_environment_variable=(
                                external_config.trusted_public_key_environment_variable
                            ),
                        )
                        verified_receipt = payload.record.require_commercial_trust()
                        verified_receipt.require_current(now=datetime.now(UTC))
                        if (
                            verified_receipt.receipt_id != receipt_id
                            or payload.canonical_digest != digest
                            or verified_receipt.subject_id != item.work_item_id
                            or verified_receipt.candidate_or_offer_identity != candidate_sha
                            or verified_receipt.evidence_type
                            not in external_config.allowed_evidence_types
                        ):
                            raise ExternalEvidenceVerificationError(
                                "proposed external receipt binding is not authoritative"
                            )
                    except (ExternalEvidenceVerificationError, OSError, ValueError) as exc:
                        checkpoint.active = False
                        checkpoint.approval_state = "TRUSTED_EXTERNAL_EVIDENCE_REQUIRED"
                        checkpoint.circuit_breaker_reason = str(exc)
                        checkpoint.updated_at = datetime.now(UTC)
                        self.checkpoints.save_v3(checkpoint)
                        self.queue.transition(
                            item.work_item_id,
                            WorkStatus.BLOCKED_POLICY,
                            updated_at=datetime.now(UTC),
                        )
                        return {
                            "status": WorkStatus.BLOCKED_POLICY.value,
                            "workItemId": item.work_item_id,
                            "reason": "trusted external receipt verification failed closed",
                        }
                    external_copy = root / f"external-receipt-{receipt_id}.json"
                    external_copy.write_bytes(payload.canonical_bytes)
                    if _digest_file(external_copy) != payload.canonical_digest:
                        raise RuntimeError("materialized external receipt was substituted")
                    external_bindings.append(
                        ExternalEvidenceBinding(
                            receipt_id=receipt_id,
                            record_digest=payload.canonical_digest,
                        )
                    )
                    bound_artifacts[f"external:{receipt_id}"] = payload.canonical_bytes
                    report_handoff_artifacts[f"externalReceipt:{receipt_id}"] = external_copy
                    checkpoint.stage_artifact_digests[f"external_evidence:{receipt_id}"] = (
                        payload.canonical_digest
                    )
                    checkpoint.stage_artifact_paths[f"external_evidence:{receipt_id}"] = str(
                        external_copy.resolve()
                    )
                    for authority_name, authority_bytes in sorted(
                        payload.authority_payloads.items()
                    ):
                        authority_digest = payload.authority_digests[authority_name]
                        authority_copy = root / (
                            f"external-receipt-{receipt_id}-{authority_name}.evidence"
                        )
                        authority_copy.write_bytes(authority_bytes)
                        if _digest_file(authority_copy) != authority_digest:
                            raise RuntimeError(
                                "materialized external authority evidence was substituted"
                            )
                        binding_name = f"external-evidence:{receipt_id}:{authority_name}"
                        stage_bindings.append(
                            StageArtifactBinding(
                                stage="controller",
                                name=binding_name,
                                digest=authority_digest,
                            )
                        )
                        bound_artifacts[f"stage:controller:{binding_name}"] = authority_bytes
                        report_handoff_artifacts[
                            f"externalAuthority:{receipt_id}:{authority_name}"
                        ] = authority_copy
                        checkpoint.stage_artifact_digests[
                            f"external_authority:{receipt_id}:{authority_name}"
                        ] = authority_digest
                        checkpoint.stage_artifact_paths[
                            f"external_authority:{receipt_id}:{authority_name}"
                        ] = str(authority_copy.resolve())
                        verified_external_evidence_refs.append(
                            f"external-authority:{receipt_id}:{authority_name}@{authority_digest}"
                        )
                    verified_external_evidence_refs.append(
                        f"external-receipt:{receipt_id}@{payload.canonical_digest}"
                    )
                    seen_receipts.add(receipt_id)
        traincheck_request: TrainCheckDifferentialRequest | None = None
        traincheck_result: TrainCheckDifferentialResult | None = None
        traincheck_result_path: Path | None = None
        traincheck_raw_store: ContentAddressedRuntimeArtifacts | None = None
        if item.work_item_id == "V3-COMP-005":
            github = load_github_config(self.repo_root / "config/github.yaml")
            requests = [
                output
                for report, _, _ in validated_reports
                if report.owner_class == "CANDIDATE_AGENT"
                for output in report.outputs
                if PurePosixPath(output.path).name == "traincheck-differential-request.json"
            ]
            if len(requests) != 1:
                raise RuntimeError("TrainCheck work has no unique differential request")
            request_path = worktree.path / requests[0].path
            traincheck_request = TrainCheckDifferentialRequest.model_validate_json(
                request_path.read_bytes(), strict=True
            )
            traincheck_raw_store = ContentAddressedRuntimeArtifacts(
                Path(github.independent_receipt_root).parent / "native-value-artifacts"
            )
            traincheck_result = replay_traincheck_differential(
                traincheck_request,
                candidate_sha=candidate_sha,
                candidate_tree_sha=frozen_candidate.candidate_tree_sha,
                artifacts=traincheck_raw_store,
            )
            traincheck_root = root / "traincheck-evidence"
            traincheck_root.mkdir(parents=True, exist_ok=True)
            traincheck_artifacts = {
                "request": traincheck_request.canonical_json_bytes(),
                "tool": traincheck_raw_store.read_exact(traincheck_request.traincheck_tool_digest),
                "incident-contract": traincheck_raw_store.read_exact(
                    traincheck_request.incident_contract_digest
                ),
                "baseline-observation": traincheck_raw_store.read_exact(
                    traincheck_request.baseline_observation_digest
                ),
                "candidate-observation": traincheck_raw_store.read_exact(
                    traincheck_request.candidate_observation_digest
                ),
                "result": traincheck_result.canonical_json_bytes(),
            }
            for name, raw in traincheck_artifacts.items():
                path = traincheck_root / f"{name}.evidence"
                path.write_bytes(raw)
                digest = sha256_digest(raw)
                binding_name = f"traincheck:{name}"
                stage_bindings.append(
                    StageArtifactBinding(
                        stage="controller",
                        name=binding_name,
                        digest=digest,
                    )
                )
                bound_artifacts[f"stage:controller:{binding_name}"] = raw
                checkpoint.stage_artifact_digests[f"machine_policy:{binding_name}"] = digest
                checkpoint.stage_artifact_paths[f"machine_policy:{binding_name}"] = str(
                    path.resolve()
                )
                if name == "result":
                    traincheck_result_path = path
        manifest = CandidateManifest(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            candidate_tree_sha=frozen_candidate.candidate_tree_sha,
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
            findings=finding_bindings,
            external_evidence=external_bindings,
            checkpoint_digest=checkpoint_digest,
            release_decision=ReleaseDecision.APPROVED_FOR_AUTOMATED_PULL_REQUEST,
            created_at=datetime.now(UTC),
        )
        manifest.verify_artifacts(bound_artifacts)
        manifest_path = root / "candidate-manifest.json"
        write_json(manifest_path, manifest.model_dump(mode="json", by_alias=True))
        native_value_authorization: RuntimeAuthorizedNativeValueV31 | None = None
        native_value_authorization_path: Path | None = None
        native_value_evidence_refs: Sequence[str] = ()
        traincheck_evidence_refs: Sequence[str] = ()
        native_value_handoff_artifacts = {
            "candidateManifest": manifest_path,
            **report_handoff_artifacts,
            **{f"gate:{name}": path for name, path in sorted(gate_handoff_paths.items())},
            **{
                f"materialized:{key}": Path(path_text)
                for key, path_text in sorted(checkpoint.stage_artifact_paths.items())
                if ":materialized-output:" in key
            },
            **(
                {
                    "researchAdvisoryBundle": Path(research_advisory.bundle_path),
                    "researchReport": Path(research_advisory.report_path),
                    **{
                        f"researchRaw:{artifact.source_id}": Path(artifact.raw_cas_path)
                        for artifact in research_advisory.artifacts
                    },
                    **{
                        f"researchReceipt:{artifact.source_id}": Path(artifact.receipt_path)
                        for artifact in research_advisory.artifacts
                    },
                    **{
                        f"researchTyped:{name}": Path(path)
                        for name, path in research_advisory.typed_market_artifact_paths.items()
                    },
                }
                if research_advisory is not None
                else {}
            ),
        }
        if item.kind is WorkKind.CONTROLLED_EXPERIMENT:
            github = load_github_config(self.repo_root / "config/github.yaml")
            candidate_tree_sha = frozen_candidate.candidate_tree_sha
            try:
                benchmark_outputs = [
                    output
                    for report, _, _ in validated_reports
                    if report.owner_class == "CANDIDATE_AGENT"
                    for output in report.outputs
                    if PurePosixPath(output.path).name == BENCHMARK_FILE
                ]
                if len(benchmark_outputs) != 1:
                    raise NativeValueRuntimeError(
                        "controlled experiment has no unique native benchmark output"
                    )
                native_runtime_source = (
                    worktree.path / PurePosixPath(benchmark_outputs[0].path).parent
                )
                native_value_authorization = load_authorized_native_value_transition(
                    artifact_directory=native_runtime_source,
                    candidate_manifest_path=manifest_path,
                    raw_artifacts=ContentAddressedRuntimeArtifacts(
                        Path(github.independent_receipt_root).parent / "native-value-artifacts"
                    ),
                    receipt_root=Path(github.independent_receipt_root),
                    activation_path=Path(github.activation_receipt_path),
                    authority=ExternalPhase3NativeValueAuthority(
                        Path(github.receipt_verifier_executable)
                    ),
                    work_item_id=item.work_item_id,
                    candidate_sha=candidate_sha,
                    candidate_tree_sha=candidate_tree_sha,
                    base_sha=base_sha,
                    expected_main_sha=base_sha,
                    source_generation_id=active_now.generation_id,
                    source_generation_digest=f"sha256:{active_now.manifest_digest}",
                    controller_binary_digest=_digest_file(
                        self.repo_root / "tcfactory/v3/controller.py"
                    ),
                    controller_config_digest=_digest_file(self.repo_root / "config/factory.yaml"),
                    now=datetime.now(UTC),
                )
                if item.work_item_id == "V3-COMP-005":
                    if (
                        traincheck_request is None
                        or traincheck_result is None
                        or traincheck_result_path is None
                        or traincheck_raw_store is None
                    ):
                        raise NativeValueRuntimeError(
                            "TrainCheck replay was not frozen before the candidate manifest"
                        )
                    receipt_path = (
                        Path(github.independent_receipt_root)
                        / "machine-policy"
                        / item.work_item_id
                        / f"{candidate_sha}.json"
                    )
                    authorized_receipt = ExternalReceiptAuthorizer(
                        Path(github.receipt_verifier_executable)
                    ).authorize(
                        receipt_path,
                        candidate_sha=candidate_sha,
                        candidate_tree_sha=candidate_tree_sha,
                        base_sha=base_sha,
                        work_item_id=item.work_item_id,
                        candidate_manifest_digest=_digest_file(manifest_path),
                    )
                    authorize_traincheck_differential(
                        traincheck_result,
                        receipt_verifier=VerifiedMachineReceiptTrainCheckOracle(
                            authorized_receipt.receipt
                        ),
                    )
                    traincheck_result_digest = _digest_file(traincheck_result_path)
                    traincheck_receipt_copy = root / "traincheck-machine-policy-receipt.json"
                    traincheck_receipt_copy.write_bytes(receipt_path.read_bytes())
                    traincheck_receipt_digest = _digest_file(traincheck_receipt_copy)
                    checkpoint.stage_artifact_digests["machine_policy:traincheck-receipt"] = (
                        traincheck_receipt_digest
                    )
                    checkpoint.stage_artifact_paths["machine_policy:traincheck-receipt"] = str(
                        traincheck_receipt_copy.resolve()
                    )
                    traincheck_evidence_refs = (
                        f"traincheck-differential:{traincheck_result_digest}",
                        f"machine-policy-receipt:{traincheck_receipt_digest}",
                    )
                    native_value_handoff_artifacts["trainCheckDifferential"] = (
                        traincheck_result_path
                    )
                    native_value_handoff_artifacts["trainCheckMachinePolicyReceipt"] = (
                        traincheck_receipt_copy
                    )
                assert_frozen_candidate(
                    worktree.path,
                    expected_candidate_sha=candidate_sha,
                    expected_candidate_tree_sha=frozen_candidate.candidate_tree_sha,
                )
            except (
                CandidateFreezeError,
                FileNotFoundError,
                NativeValueRuntimeError,
                OSError,
                ValueError,
            ) as exc:
                if isinstance(exc, CandidateFreezeError):
                    quarantine_tainted_evidence(
                        gate_handoff_paths,
                        quarantine_root=root / "quarantine" / "native-value-candidate-mutation",
                        reason=str(exc),
                    )
                checkpoint.active = False
                checkpoint.approval_state = "INDEPENDENT_NATIVE_VALUE_REQUIRED"
                checkpoint.circuit_breaker_reason = (
                    "Phase 11 native/value bundle, receipt, or activation is unavailable"
                )
                checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(checkpoint)
                self.queue.transition(
                    item.work_item_id,
                    WorkStatus.BLOCKED_POLICY,
                    updated_at=datetime.now(UTC),
                )
                return {
                    "status": WorkStatus.BLOCKED_POLICY.value,
                    "workItemId": item.work_item_id,
                    "reason": "independent Phase 11 native/value authorization failed closed",
                    "failureType": type(exc).__name__,
                }
            transition = native_value_authorization.transition
            native_runtime_copy = root / "native-value-runtime"
            shutil.copytree(
                native_runtime_source,
                native_runtime_copy,
                dirs_exist_ok=True,
            )
            # The signed receipt binds the immutable candidate-manifest basis.  A
            # separate post-authorization envelope avoids an impossible digest
            # cycle while durably binding that manifest to the receipt, activation,
            # deterministic native replay, and value decision.
            native_value_authorization_path = root / "native-value-authorization.json"
            write_json(
                native_value_authorization_path,
                native_value_authorization.model_dump(mode="json", by_alias=True),
            )
            native_value_evidence_refs = (
                *native_value_authorization.completion_evidence_refs(),
                f"native-value-authorization:{_digest_file(native_value_authorization_path)}",
            )
            native_value_handoff_artifacts.update(
                {
                    "nativeValueAuthorization": native_value_authorization_path,
                    "nativeSubstituteBenchmark": (
                        root / "native-value-runtime" / "native-substitute-benchmark.json"
                    ),
                    "decisionValueResult": (
                        root / "native-value-runtime" / "decision-value-result.json"
                    ),
                    "nativeValuePolicy": (
                        root / "native-value-runtime" / "native-value-gate-policy.json"
                    ),
                }
            )
            receipt_path = (
                Path(github.independent_receipt_root)
                / "machine-policy"
                / item.work_item_id
                / f"{candidate_sha}.json"
            )
            authorization_paths = {
                "authorization-envelope": native_value_authorization_path,
                "native-substitute-benchmark": (
                    root / "native-value-runtime" / "native-substitute-benchmark.json"
                ),
                "decision-value-result": (
                    root / "native-value-runtime" / "decision-value-result.json"
                ),
                "native-value-policy": (
                    root / "native-value-runtime" / "native-value-gate-policy.json"
                ),
                "machine-policy-receipt": receipt_path,
                "activation-receipt": Path(github.activation_receipt_path),
            }
            authorization_digests = {
                "authorization-envelope": _digest_file(native_value_authorization_path),
                "native-substitute-benchmark": transition.benchmark_digest,
                "decision-value-result": transition.value_result_digest,
                "native-value-policy": native_value_authorization.policy_digest,
                "machine-policy-receipt": transition.machine_receipt_digest,
                "activation-receipt": native_value_authorization.activation_receipt_digest,
                "candidate-manifest": native_value_authorization.candidate_manifest_digest,
            }
            for name, digest in sorted(authorization_digests.items()):
                key = f"machine_policy:{name}"
                checkpoint.stage_artifact_digests[key] = digest
                checkpoint.stage_artifact_paths[key] = str(
                    authorization_paths.get(name, manifest_path).resolve()
                )
            if item.work_item_id == "V3-COMP-005":
                frozen_traincheck_digests = {
                    name.removeprefix("machine_policy:traincheck:"): digest
                    for name, digest in checkpoint.stage_artifact_digests.items()
                    if name.startswith("machine_policy:traincheck:")
                }
                receipt_file_digest = checkpoint.stage_artifact_digests.get(
                    "machine_policy:traincheck-receipt"
                )
                if receipt_file_digest is None:
                    raise RuntimeError("TrainCheck release envelope lacks receipt bytes")
                frozen_traincheck_digests["machine-policy-receipt"] = receipt_file_digest
                result_digest = frozen_traincheck_digests.get("result")
                if result_digest is None:
                    raise RuntimeError("TrainCheck release envelope lacks result bytes")
                release_authorization = FrozenReleaseEvidenceAuthorization(
                    authorization_id=f"FREA-V3-COMP-005-{candidate_sha[:12].upper()}",
                    work_item_id="V3-COMP-005",
                    candidate_sha=candidate_sha,
                    candidate_tree_sha=frozen_candidate.candidate_tree_sha,
                    candidate_manifest_digest=_digest_file(manifest_path),
                    native_value_authorization_digest=_digest_file(native_value_authorization_path),
                    machine_policy_receipt_id=(native_value_authorization.machine_receipt_id),
                    machine_policy_receipt_digest=transition.machine_receipt_digest,
                    activation_receipt_digest=(
                        native_value_authorization.activation_receipt_digest
                    ),
                    traincheck_result_digest=result_digest,
                    traincheck_receipt_file_digest=receipt_file_digest,
                    frozen_artifact_digests=frozen_traincheck_digests,
                    authorized_at=datetime.now(UTC),
                )
                release_authorization_path = root / "frozen-release-evidence-authorization.json"
                release_authorization_path.write_bytes(release_authorization.canonical_json_bytes())
                release_authorization_digest = _digest_file(release_authorization_path)
                checkpoint.publication_authorization_envelope_path = str(
                    release_authorization_path.resolve()
                )
                checkpoint.publication_authorization_envelope_digest = release_authorization_digest
                checkpoint.stage_artifact_paths["machine_policy:frozen-release-authorization"] = (
                    str(release_authorization_path.resolve())
                )
                checkpoint.stage_artifact_digests["machine_policy:frozen-release-authorization"] = (
                    release_authorization_digest
                )
                native_value_handoff_artifacts["frozenReleaseEvidenceAuthorization"] = (
                    release_authorization_path
                )
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)
            if transition.resulting_status is not WorkStatus.PASSED_ENGINEERING:
                checkpoint.active = False
                checkpoint.approval_state = "INDEPENDENT_NATIVE_VALUE_VERIFIED"
                checkpoint.updated_at = datetime.now(UTC)
                self.checkpoints.save_v3(checkpoint)
                self.queue.transition(
                    item.work_item_id,
                    transition.resulting_status,
                    updated_at=datetime.now(UTC),
                )
                write_v3_handoff(
                    artifact_root=root,
                    relative_path="handoff.json",
                    work_item=item,
                    disposition=item.disposition,
                    attempt=1,
                    attempts_remaining=checkpoint.budget.repair_cycles_remaining,
                    base_sha=base_sha,
                    candidate_sha=candidate_sha,
                    next_action=transition.resulting_status.value,
                    findings=handoff_findings,
                    artifacts=native_value_handoff_artifacts,
                    source_digest=packet.source_digest,
                    context_digest=packet.context_digest,
                    candidate_manifest_digest=_digest_file(manifest_path),
                    backend_session_ref=backend_session_ref,
                )
                self._record_completion_evidence(
                    item=item,
                    candidate_sha=candidate_sha,
                    checkpoint_digest=_digest_file(self.checkpoints.path_for(item.work_item_id)),
                    manifest_digest=_digest_file(manifest_path),
                    machine_policy_receipt_digest=transition.machine_receipt_digest,
                    independent_reviewed=True,
                    now=datetime.now(UTC),
                    additional_evidence_refs=(
                        *native_value_evidence_refs,
                        *traincheck_evidence_refs,
                        *verified_external_evidence_refs,
                    ),
                )
                return {
                    "status": transition.resulting_status.value,
                    "workItemId": item.work_item_id,
                    "technicalCeiling": transition.technical_ceiling.value,
                    "commercialCeiling": transition.commercial_ceiling.value,
                    "nativeValueEvidence": native_value_evidence_refs,
                }
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
            findings=handoff_findings,
            artifacts=native_value_handoff_artifacts,
            source_digest=packet.source_digest,
            context_digest=packet.context_digest,
            candidate_manifest_digest=_digest_file(manifest_path),
            backend_session_ref=backend_session_ref,
        )
        checkpoint.publication_transaction_id = (
            f"PRPUB-{item.work_item_id.replace('-', '_')}-{candidate_sha[:12].upper()}"
        )
        checkpoint.publication_manifest_path = str(manifest_path.resolve())
        checkpoint.publication_manifest_digest = _digest_file(manifest_path)
        checkpoint.publication_candidate_tree_sha = frozen_candidate.candidate_tree_sha
        checkpoint.publication_checkpoint_digest = checkpoint_digest
        checkpoint.publication_packet_digest = packet.canonical_digest()
        checkpoint.publication_gate_digests = {
            binding.name: binding.evidence_digest for binding in gate_bindings
        }
        checkpoint.publication_expected_machine_policy_receipt_id = (
            native_value_authorization.machine_receipt_id
            if native_value_authorization is not None
            else None
        )
        checkpoint.publication_expected_machine_policy_receipt_digest = (
            native_value_authorization.transition.machine_receipt_digest
            if native_value_authorization is not None
            else None
        )
        checkpoint.approval_state = "PUBLICATION_PREPARED"
        checkpoint.updated_at = datetime.now(UTC)
        self.checkpoints.save_v3(checkpoint)
        try:
            self._reverify_external_evidence(
                item=item,
                candidate_sha=candidate_sha,
                checkpoint=checkpoint,
                now=datetime.now(UTC),
            )
        except ExternalEvidenceVerificationError as exc:
            checkpoint.active = False
            checkpoint.approval_state = "TRUSTED_EXTERNAL_EVIDENCE_TAINTED"
            checkpoint.circuit_breaker_reason = str(exc)
            checkpoint.updated_at = datetime.now(UTC)
            self.checkpoints.save_v3(checkpoint)
            self.queue.transition(
                item.work_item_id,
                WorkStatus.BLOCKED_POLICY,
                updated_at=datetime.now(UTC),
            )
            return {
                "status": WorkStatus.BLOCKED_POLICY.value,
                "workItemId": item.work_item_id,
                "reason": "verified external authority changed before publication",
            }
        try:
            self._reverify_research_advisory(research_advisory, checkpoint)
            self._reverify_traincheck_evidence(checkpoint, manifest_path)
            self._reverify_release_evidence_authorization(checkpoint, manifest_path)
            assert_frozen_candidate(
                worktree.path,
                expected_candidate_sha=candidate_sha,
                expected_candidate_tree_sha=frozen_candidate.candidate_tree_sha,
            )
        except CandidateFreezeError as exc:
            quarantine_tainted_evidence(
                gate_handoff_paths,
                quarantine_root=root / "quarantine" / "pre-publication-candidate-mutation",
                reason=str(exc),
            )
            raise RuntimeError("candidate mutated before publisher side effects") from exc
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
                gate_digests=dict(checkpoint.publication_gate_digests),
                expected_candidate_tree_sha=frozen_candidate.candidate_tree_sha,
                expected_machine_policy_receipt_id=(
                    checkpoint.publication_expected_machine_policy_receipt_id
                ),
                expected_machine_policy_receipt_digest=(
                    checkpoint.publication_expected_machine_policy_receipt_digest
                ),
                expected_release_authorization_envelope_digest=(
                    checkpoint.publication_authorization_envelope_digest
                ),
                lease_guard=lambda: self._renew_active_lease(item.work_item_id),
            )
        )
        if release.get("status") == "PENDING_REQUIRED_CHECKS":
            return self._pause_publication(
                item=item,
                checkpoint=checkpoint,
                release=release,
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
        merged_main_sha, receipt_digest, _, _ = self._validated_publication_success(release)
        if current_sha(self.git_root, "refs/heads/main") != merged_main_sha:
            raise RuntimeError(
                "verified publication is not present in the independent mutable Git anchor"
            )
        if (
            native_value_authorization is not None
            and receipt_digest != native_value_authorization.transition.machine_receipt_digest
        ):
            raise RuntimeError(
                "publication receipt differs from the Phase 11 native/value authorization"
            )
        checkpoint.active = False
        checkpoint.approval_state = "INDEPENDENT_RELEASE_VERIFIED"
        self.checkpoints.save_v3(checkpoint)
        target = (
            WorkStatus.WAITING_EXTERNAL
            if item.external_receipt_required
            else (
                native_value_authorization.transition.resulting_status
                if native_value_authorization is not None
                else WorkStatus.PASSED_ENGINEERING
            )
        )
        self.queue.transition(item.work_item_id, target, updated_at=datetime.now(UTC))
        if target is WorkStatus.PASSED_ENGINEERING:
            self._record_completion_evidence(
                item=item,
                candidate_sha=candidate_sha,
                checkpoint_digest=(
                    _digest_file(self.checkpoints.path_for(item.work_item_id))
                    if native_value_authorization is not None
                    else checkpoint_digest
                ),
                manifest_digest=_digest_file(manifest_path),
                machine_policy_receipt_digest=receipt_digest,
                independent_reviewed=any(
                    role in {"audit", "adversary", "security"} for role in self._roles(item)
                ),
                now=datetime.now(UTC),
                additional_evidence_refs=(
                    *native_value_evidence_refs,
                    *traincheck_evidence_refs,
                    *verified_external_evidence_refs,
                ),
            )
        return {
            "status": target.value,
            "workItemId": item.work_item_id,
            "release": release,
            "nativeValue": (
                native_value_authorization.model_dump(mode="json", by_alias=True)
                if native_value_authorization is not None
                else None
            ),
        }

    async def run_cycle(self) -> dict[str, object]:
        """Run one complete cycle under exclusive process-wide ownership."""

        with controller_process_lock(self.runtime_paths.controller_lock):
            return await self._run_cycle_owned()

    async def _run_cycle_owned(self) -> dict[str, object]:
        self.initialize()
        now = datetime.now(UTC)
        state = self._load_state()
        self._require_installed_snapshot_alignment(state=state)
        collection = self._runtime_collection()
        self._promote_backend_pauses(collection, now)
        collection = self._runtime_collection()
        future_lane_milestones = self._future_lane_milestones(collection)
        self._promote_ready(
            collection,
            now,
            future_lane_milestones=future_lane_milestones,
        )
        collection = self._runtime_collection()
        advanced = self._advance_completed_milestone(collection)
        if advanced is not None:
            collection = self._runtime_collection()
            future_lane_milestones = {}
            self._promote_ready(collection, now)
            collection = self._runtime_collection()
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
            eligible_future_milestones=future_lane_milestones,
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
        state.last_decision_artifact = str(decision_path.resolve(strict=True))
        cursor = state.lane_cursor if state.lane_cursor in CORE_SCHEDULING_LANES else Lane.PRODUCT
        state.lane_cursor = CORE_SCHEDULING_LANES[
            (CORE_SCHEDULING_LANES.index(cursor) + 1) % len(CORE_SCHEDULING_LANES)
        ]
        if not decision.selected_work_item_ids:
            self._save_state(state)
            return {
                "status": "IDLE",
                "scopedBlockers": state.blocked_scopes,
                "interventionMode": "NONE",
            }

        async def execute_selected(identifier: str) -> dict[str, object]:
            self.queue.transition(identifier, WorkStatus.QUEUED, updated_at=datetime.now(UTC))
            lease = self.queue.claim(
                identifier,
                owner_id=self.owner_id,
                now=datetime.now(UTC),
            )

            async def renew_lease() -> None:
                while True:
                    await asyncio.sleep(self.lease_renewal_interval_seconds)
                    self.queue.renew(
                        identifier,
                        lease_id=lease.lease_id,
                        now=datetime.now(UTC),
                    )

            heartbeat = asyncio.create_task(renew_lease())
            execution = asyncio.create_task(
                self.execute_claimed(
                    self.queue.load(identifier),
                    lease_id=lease.lease_id,
                    now=datetime.now(UTC),
                )
            )
            lease_failure_consumed = False
            try:
                done, _ = await asyncio.wait(
                    {execution, heartbeat}, return_when=asyncio.FIRST_COMPLETED
                )
                if heartbeat in done:
                    lease_error = heartbeat.exception()
                    lease_failure_consumed = True
                    execution.cancel()
                    with suppress(asyncio.CancelledError):
                        await execution
                    self._quarantine_lease_loss(identifier, lease_error)
                    if lease_error is None:
                        raise RuntimeError("lease renewal stopped before work completed")
                    raise RuntimeError(
                        f"lease renewal failed for {identifier}; execution aborted"
                    ) from lease_error
                return await execution
            finally:
                if not heartbeat.done():
                    heartbeat.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat
                elif not lease_failure_consumed:
                    heartbeat.exception()

        completed = await asyncio.gather(
            *(execute_selected(identifier) for identifier in decision.selected_work_item_ids),
            return_exceptions=True,
        )
        for result in completed:
            if isinstance(result, BaseException):
                raise result
        results = [result for result in completed if isinstance(result, dict)]
        self._require_installed_snapshot_alignment(state=state)
        advanced = self._advance_completed_milestone(self._runtime_collection())
        if advanced is not None:
            self._promote_ready(self._runtime_collection(), datetime.now(UTC))
        state.last_work_item_id = decision.selected_work_item_ids[-1]
        state.last_candidate_sha = current_sha(self.git_root, "main")
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
            cwd=self.git_root,
            check=False,
        )
        if exists.returncode != 0:
            raise ValueError("checkpoint candidate SHA is not locally recoverable")
        observed_candidate = current_sha(self.git_root, checkpoint.candidate_sha)
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
