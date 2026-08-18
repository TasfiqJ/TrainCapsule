from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never, cast

import pytest
import yaml

from tcfactory.backends.base import (
    AgentCapabilityReport,
    AgentRunResult,
    AgentSession,
    AgentTaskRequest,
    BackendRouteState,
    BackendTerminalDisposition,
    Handoff,
    SessionState,
    UsageState,
)
from tcfactory.backends.fake import FakeBackend
from tcfactory.checkpoints import CheckpointBudget, V3Checkpoint
from tcfactory.context import V3ContextManifest
from tcfactory.util import sha256_file, write_json
from tcfactory.v3.candidate_freeze import CandidateFreezeError, assert_frozen_candidate
from tcfactory.v3.controller import V3Controller
from tcfactory.v3.controller_lock import ControllerLockError
from tcfactory.v3.enums import Lane, WorkKind, WorkStatus
from tcfactory.v3.external_actions import (
    ExternalActionChannel,
    ExternalActionOutcome,
    ExternalActionReason,
    ExternalActionRequest,
    ExternalActionStatus,
)
from tcfactory.v3.external_evidence import (
    ExternalEvidenceReceipt,
    ExternalEvidenceVerificationError,
    TrustedEvidenceRecord,
)
from tcfactory.v3.installed_runtime import InstalledControllerRuntimeManifest
from tcfactory.v3.milestone_runtime import (
    load_milestone_state,
)
from tcfactory.v3.phase6_runtime import (
    AdvisoryArtifact,
    Phase6ControllerRuntime,
    Phase6RuntimeError,
    ResearchAdvisoryBundle,
)
from tcfactory.v3.work_items import WorkItem, WorkItemCollection

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _item(
    identifier: str,
    *,
    risk: str,
    depends: list[str] | None = None,
    kind: str = "CODE",
    lane: str = "PRODUCT",
    automatable: bool = True,
    external: bool = False,
    milestone: str = "M1_NATIVE_PREFLIGHT",
) -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": identifier,
            "title": f"Simulation {identifier}",
            "lane": lane,
            "kind": kind,
            "milestone": milestone,
            "decisionContribution": "Prove one bounded unattended controller transition.",
            "customerOutcome": "No customer claim; deterministic controller evidence only.",
            "dependsOn": depends or [],
            "softDependsOn": [],
            "blocksCommercialRelease": external,
            "priority": 90,
            "riskTier": risk,
            "maturityTarget": {
                "engineering": "CONTROLLED_VALIDATED",
                "commercial": "NOT_EVALUATED",
            },
            "disposition": "KEEP",
            "status": "PROPOSED",
            "ownerType": (
                "EXTERNAL_PARTY"
                if external
                else "MACHINE_POLICY_AUTHORITY"
                if kind == "MACHINE_POLICY_REVIEW"
                else "AI"
            ),
            "automatable": automatable,
            "evidenceRequired": ["deterministic disposable-repository simulation"],
            "externalReceiptRequired": external,
            "machinePolicyReceiptRequired": kind == "MACHINE_POLICY_REVIEW",
            "retryPolicy": {
                "maxPlanAttempts": 2,
                "maxCandidateRepairCycles": 2,
                "maxSameFindingRepeats": 2,
                "maxCandidateRestarts": 1,
            },
        }
    )


def _simulation_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / "config", repo / "config")
    shutil.copytree(ROOT / "prompts", repo / "prompts")
    (repo / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/generate_v3_1_zh_source.py",
        repo / "scripts/generate_v3_1_zh_source.py",
    )
    shutil.copytree(
        ROOT / "docs/source-of-truth",
        repo / "docs/source-of-truth",
    )
    shutil.copytree(
        ROOT / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
        repo / "TrainCapsule_V3_Review_and_Migration_Bundle_2026-08-11",
    )
    (repo / "docs").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs/CONTEXT_INDEX.yaml", repo / "docs/CONTEXT_INDEX.yaml")
    shutil.copy2(ROOT / "SOURCE_PRECEDENCE.md", repo / "SOURCE_PRECEDENCE.md")
    shutil.copytree(ROOT / "factory/policy", repo / "factory/policy")
    (repo / "factory/roadmap").mkdir(parents=True)
    shutil.copy2(
        ROOT / "factory/roadmap/milestones.yaml",
        repo / "factory/roadmap/milestones.yaml",
    )
    (repo / "tcfactory/v3").mkdir(parents=True)
    shutil.copy2(ROOT / "tcfactory/v3/planning.py", repo / "tcfactory/v3/planning.py")
    (repo / "factory/feature_ledger.yaml").write_text(
        "version: 2\nlegacy: immutable\n", encoding="utf-8"
    )
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=[
            _item("V3-SIM-001", risk="MECHANICAL", milestone="M0_FACTORY_MIGRATED"),
            _item(
                "V3-SIM-002",
                risk="STANDARD",
                depends=["V3-SIM-001"],
                milestone="M0_FACTORY_MIGRATED",
            ),
            _item(
                "V3-SIM-003",
                risk="EXTERNAL",
                kind="EXTERNAL_EVIDENCE",
                lane="MARKET",
                automatable=False,
                external=True,
                milestone="M0_FACTORY_MIGRATED",
            ),
        ],
    )
    (repo / "factory/roadmap/work_items.yaml").write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Controller Simulation")
    _git(repo, "config", "user.email", "simulation@example.invalid")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "simulation baseline")
    return repo


def _make_first_item_standard(repo: Path) -> None:
    roadmap = repo / "factory/roadmap/work_items.yaml"
    raw = yaml.safe_load(roadmap.read_text(encoding="utf-8"))
    raw["workItems"][0]["riskTier"] = "STANDARD"
    roadmap.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    _git(repo, "add", str(roadmap.relative_to(repo)))
    _git(repo, "commit", "-m", "use standard restart fixture")


def _strict_simulation_report(
    request: AgentTaskRequest, *, before_sha: str, mutate: bool
) -> dict[str, object]:
    worktree = Path(request.candidate_worktree)
    task_contract = cast(dict[str, object], request.task_packet["taskContract"])
    outputs = cast(list[dict[str, object]], task_contract["outputs"])
    declaration = outputs[0]
    output_path = str(declaration["path"])
    output_file = worktree / output_path
    if mutate:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(
                {
                    "schemaVersion": "3.1",
                    "workItemId": request.work_item_id,
                    "requestId": request.request_id,
                    "verdict": "PASS",
                    "evidenceDigests": [request.source_digest],
                    "summary": "Controlled simulation result.",
                    "limitations": [],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _git(worktree, "add", output_path)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False
        )
        if staged.returncode != 0:
            _git(worktree, "commit", "-m", f"bind output {request.work_item_id}")
    payload = output_file.read_bytes()
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    after_sha = _git(worktree, "rev-parse", "HEAD")
    changed_files = (
        _git(worktree, "diff", "--name-only", before_sha, after_sha).splitlines()
        if before_sha != after_sha
        else []
    )
    source_manifest = request.source_context_manifest
    return {
        "schemaVersion": "3.1",
        "requestId": request.request_id,
        "workItemId": request.work_item_id,
        "role": request.role,
        "ownerClass": (
            "CANDIDATE_AGENT" if {"Write", "Edit"} <= set(request.allowed_tools)
            else "READ_ONLY_REVIEWER"
        ),
        "baseSha": str(request.task_packet["baseSha"]),
        "candidateSha": after_sha,
        "sourceGenerationId": str(task_contract["sourceGenerationId"]),
        "sourceDigest": str(source_manifest["sourceDigest"]),
        "contextDigest": str(source_manifest["contextDigest"]),
        "taskPacketDigest": str(source_manifest["packetDigest"]),
        "verdict": "PASS",
        "truthState": "CLEAR",
        "criterionResults": [
            {
                "schemaVersion": "3.1",
                "criterionId": "CRIT:SIMULATION:OUTPUT",
                "passed": True,
                "evidenceDigests": [digest],
                "explanation": "Controlled simulation output is present and digest-bound.",
            }
        ],
        "findings": [],
        "findingFingerprints": [],
        "changedFiles": changed_files,
        "commandsRun": [],
        "testsRun": [],
        "outputs": [
            {
                "schemaVersion": "3.1",
                "outputId": declaration["outputId"],
                "path": output_path,
                "schemaId": declaration["schemaId"],
                "contentDigest": digest,
                "sizeBytes": len(payload),
            }
        ],
        "artifactDigests": [digest],
        "externalReceiptRefs": [],
        "nativeDisposition": "NOT_APPLICABLE",
        "valueDisposition": "NOT_EVALUATED",
        "limitations": [],
        "resourceUsage": {
            "schemaVersion": "3.1",
            "wallTimeSeconds": 1,
            "turns": 1,
            "tokens": 1000,
            "costUsdEquivalent": 0,
        },
        "sessionRef": "SESSION:CONTROLLED:SIMULATION",
        "resumeState": "NOT_REQUIRED",
        "nextAuthorizedAction": "VERIFY",
    }


class _CommittingBackend(FakeBackend):
    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        worktree = Path(request.candidate_worktree)
        before_sha = _git(worktree, "rev-parse", "HEAD")
        mutating = {"Write", "Edit"} <= set(request.allowed_tools)
        if mutating:
            target = worktree / "packages/traincapsule-core/simulation"
            target.mkdir(parents=True, exist_ok=True)
            artifact = target / f"{request.work_item_id}.txt"
            artifact.write_text(f"{request.request_id}\n", encoding="utf-8")
            _git(worktree, "add", str(artifact.relative_to(worktree)))
            _git(worktree, "commit", "-m", f"simulate {request.work_item_id}")
        report = _strict_simulation_report(
            request,
            before_sha=before_sha,
            mutate=mutating,
        )
        result = await super().execute(request)
        original = result.structured_output or {}
        if original.get("nativeWorkflowSufficient") is True:
            report["nativeDisposition"] = "NATIVE_WORKFLOW_SUFFICIENT"
        if original.get("incrementalDecisionValue") is False:
            report["valueDisposition"] = "NO_INCREMENTAL_DECISION_VALUE"
        if (
            original.get("economicallyViable") is False
            or original.get("technicallyValidButUneconomic") is True
        ):
            report["valueDisposition"] = "TECHNICALLY_VALID_BUT_UNECONOMIC"
        return result.model_copy(update={"structured_output": report})


class _FailThenCommitBackend(_CommittingBackend):
    def __init__(self, *, always_fail: bool = False) -> None:
        super().__init__()
        self.calls = 0
        self.always_fail = always_fail

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.calls += 1
        if self.always_fail or self.calls == 1:
            result = await FakeBackend.execute(self, request)
            return result.model_copy(
                update={
                    "state": SessionState.FAILED,
                    "verdict": "fail",
                    "redacted_summary": "deterministic repeated simulation finding",
                }
            )
        return await super().execute(request)

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult:
        self.calls += 1
        result = FakeBackend.resume(self, session, handoff)
        if self.always_fail:
            return result.model_copy(
                update={
                    "state": SessionState.FAILED,
                    "verdict": "fail",
                    "redacted_summary": "deterministic repeated simulation finding",
                }
            )
        request = self._requests[session.session_ref]  # noqa: SLF001 - resume fixture
        if request.role == "builder":
            worktree = Path(request.candidate_worktree)
            target = worktree / "packages/traincapsule-core/simulation"
            target.mkdir(parents=True, exist_ok=True)
            artifact = target / f"{request.work_item_id}.txt"
            artifact.write_text(f"{request.request_id}-resumed\n", encoding="utf-8")
            _git(worktree, "add", str(artifact.relative_to(worktree)))
            _git(worktree, "commit", "-m", f"resume {request.work_item_id}")
        return result


class _CrashingBackend(FakeBackend):
    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        del request
        raise RuntimeError("simulated process crash after durable checkpoint")


class _CrashAfterBoundFailureBackend(_CommittingBackend):
    def capabilities(self) -> AgentCapabilityReport:
        return super().capabilities().model_copy(update={"resume": True})

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        result = await super().execute(request)
        if request.role != "audit":
            return result
        return result.model_copy(
            update={
                "state": SessionState.FAILED,
                "verdict": "fail",
                "redacted_summary": "audit finding bound before crash",
            }
        )

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult:
        del session, handoff
        raise RuntimeError("simulated crash after bound repair handoff")


class _ResumingBackend(FakeBackend):
    def __init__(self, candidate_worktree: Path) -> None:
        super().__init__()
        self.candidate_worktree = candidate_worktree
        self.resume_calls = 0

    def capabilities(self) -> AgentCapabilityReport:
        return super().capabilities().model_copy(update={"resume": True})

    def resume(self, session: AgentSession, handoff: Handoff) -> AgentRunResult:
        self.resume_calls += 1
        self._sessions[session.session_ref] = session  # noqa: SLF001 - restart fixture
        result = super().resume(session, handoff)
        artifact_root = (
            self.candidate_worktree.parent.parent / "artifacts/v3" / handoff.work_item_id
        )
        contract_path = next(artifact_root.rglob("task-contract.json"))
        context_path = next(artifact_root.rglob("context-*-audit.json"))
        contract = cast(dict[str, object], json.loads(contract_path.read_text(encoding="utf-8")))
        declaration = cast(list[dict[str, object]], contract["outputs"])[0]
        output_path = str(declaration["path"])
        payload = (self.candidate_worktree / output_path).read_bytes()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        context = V3ContextManifest.model_validate_json(context_path.read_text(encoding="utf-8"))
        report = {
            "schemaVersion": "3.1",
            "requestId": session.request_id,
            "workItemId": handoff.work_item_id,
            "role": "audit",
            "ownerClass": "READ_ONLY_REVIEWER",
            "baseSha": _git(self.candidate_worktree, "rev-parse", "main"),
            "candidateSha": _git(self.candidate_worktree, "rev-parse", "HEAD"),
            "sourceGenerationId": contract["sourceGenerationId"],
            "sourceDigest": handoff.source_digest,
            "contextDigest": context.canonical_digest(),
            "taskPacketDigest": contract["taskPacketDigest"],
            "verdict": "PASS",
            "truthState": "CLEAR",
            "criterionResults": [
                {
                    "schemaVersion": "3.1",
                    "criterionId": "CRIT:SIMULATION:OUTPUT",
                    "passed": True,
                    "evidenceDigests": [digest],
                    "explanation": "Resumed audit verified the bound output.",
                }
            ],
            "findings": [],
            "findingFingerprints": [],
            "changedFiles": [],
            "commandsRun": [],
            "testsRun": [],
            "outputs": [
                {
                    "schemaVersion": "3.1",
                    "outputId": declaration["outputId"],
                    "path": output_path,
                    "schemaId": declaration["schemaId"],
                    "contentDigest": digest,
                    "sizeBytes": len(payload),
                }
            ],
            "artifactDigests": [digest],
            "externalReceiptRefs": [],
            "nativeDisposition": "NOT_APPLICABLE",
            "valueDisposition": "NOT_EVALUATED",
            "limitations": [],
            "resourceUsage": {
                "schemaVersion": "3.1",
                "wallTimeSeconds": 1,
                "turns": 1,
                "tokens": 1000,
                "costUsdEquivalent": 0,
            },
            "sessionRef": session.session_ref,
            "resumeState": "NOT_REQUIRED",
            "nextAuthorizedAction": "VERIFY",
        }
        return result.model_copy(update={"structured_output": report})


class _PausingCommittingBackend(_CommittingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.started.set()
        await self.release.wait()
        return await super().execute(request)


class _AutomatedPRSimulationPublisher:
    def __init__(self, repo: Path, gate_root: Path) -> None:
        self.repo = repo
        self.gate_root = gate_root
        self.simulate_signed_deployment_update = True

    def prepare_candidate(
        self, *, item: WorkItem, candidate_sha: str, candidate_worktree: Path
    ) -> dict[str, Path]:
        del candidate_worktree
        self.gate_root.mkdir(parents=True, exist_ok=True)
        path = self.gate_root / f"{item.work_item_id}-{candidate_sha}.gate"
        path.write_text("PASS\n", encoding="utf-8")
        return {"disposable-simulation": path}

    def publish(self, **arguments: object) -> dict[str, object]:
        lease_guard = arguments.get("lease_guard")
        assert callable(lease_guard)
        lease_guard()
        candidate_sha = str(arguments["candidate_sha"])
        assert _git(self.repo, "rev-parse", "main") != candidate_sha
        candidate_worktree = Path(str(arguments["candidate_worktree"]))
        _git(candidate_worktree, "update-ref", "refs/heads/main", candidate_sha)
        if self.simulate_signed_deployment_update:
            _git(self.repo, "fetch", str(candidate_worktree), candidate_sha)
            _git(self.repo, "update-ref", "refs/heads/main", candidate_sha)
        return {
            "status": "MERGED_MAIN_VERIFIED",
            "candidateSha": candidate_sha,
            "pullRequestNumber": 1,
            "pullRequestUrl": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
            "machinePolicyReceiptDigest": "sha256:" + "a" * 64,
            "mergedMainSha": candidate_sha,
            "simulation": "DETERMINISTIC_FAKE_NO_NETWORK",
        }


class _MutatingGatePublisher(_AutomatedPRSimulationPublisher):
    def __init__(self, repo: Path, gate_root: Path, mutation: str) -> None:
        super().__init__(repo, gate_root)
        self.mutation = mutation
        self.publish_called = False

    def prepare_candidate(
        self, *, item: WorkItem, candidate_sha: str, candidate_worktree: Path
    ) -> dict[str, Path]:
        evidence = super().prepare_candidate(
            item=item,
            candidate_sha=candidate_sha,
            candidate_worktree=candidate_worktree,
        )
        if self.mutation == "untracked":
            target = candidate_worktree / "post-gate-untracked.txt"
            target.write_text("tainted\n", encoding="utf-8")
        elif self.mutation == "tracked":
            target = candidate_worktree / "factory/feature_ledger.yaml"
            target.write_text("version: 2\nlegacy: tainted\n", encoding="utf-8")
        elif self.mutation == "symlink":
            target = candidate_worktree / "post-gate-symlink"
            target.symlink_to(candidate_worktree / "factory/feature_ledger.yaml")
        else:  # pragma: no cover - test fixture contract
            raise AssertionError(self.mutation)
        return evidence

    def publish(self, **arguments: object) -> dict[str, object]:
        self.publish_called = True
        return super().publish(**arguments)


class _Phase6SimulationRuntime(Phase6ControllerRuntime):
    def __init__(self, *, research_failure: bool = False) -> None:
        self.research_failure = research_failure
        self.research_calls: list[str] = []
        self.action_calls: list[str] = []

    def handles_external_action(self, item: WorkItem) -> bool:
        return item.kind is WorkKind.COMMERCIAL_EXPERIMENT

    def prepare_research_advisory(
        self,
        *,
        item: WorkItem,
        candidate_sha: str,
        artifact_root: Path,
        now: datetime,
    ) -> ResearchAdvisoryBundle:
        del now
        self.research_calls.append(item.work_item_id)
        if self.research_failure:
            raise Phase6RuntimeError("trusted parser unavailable")
        artifact_root.mkdir(parents=True, exist_ok=True)
        raw = artifact_root / "source.raw"
        receipt = artifact_root / "source-receipt.json"
        report = artifact_root / "research-report.json"
        bundle_path = artifact_root / "research-advisory-bundle.json"
        raw.write_text("offline source\n", encoding="utf-8")
        receipt.write_text(
            '{"authorityEffect":"ADVISORY_ONLY_NEVER_NORMATIVE","signature":"signed"}\n',
            encoding="utf-8",
        )
        report.write_text('{"overallVerdict":"CLEAR"}\n', encoding="utf-8")
        bundle = ResearchAdvisoryBundle(
            work_item_id=item.work_item_id,
            candidate_sha=candidate_sha,
            lane=item.lane,
            plan_digest="sha256:" + "a" * 64,
            report_path=str(report.resolve()),
            report_digest="sha256:" + sha256_file(report),
            bundle_path=str(bundle_path.resolve()),
            artifacts=[
                AdvisoryArtifact(
                    source_id="SOURCE-001",
                    raw_cas_path=str(raw.resolve()),
                    raw_digest="sha256:" + sha256_file(raw),
                    receipt_path=str(receipt.resolve()),
                    receipt_digest="sha256:" + sha256_file(receipt),
                )
            ],
        )
        write_json(bundle_path, bundle.model_dump(mode="json", by_alias=True))
        return bundle

    def execute_commercial_action(
        self, *, item: WorkItem, candidate_sha: str, now: datetime
    ) -> ExternalActionOutcome:
        del now
        self.action_calls.append(item.work_item_id)
        return ExternalActionOutcome(
            schema_version="3.1",
            action_id="ACTION:SIMULATION:001",
            work_item_id=item.work_item_id,
            candidate_sha=candidate_sha,
            request=ExternalActionRequest(
                schema_version="3.1",
                action_id="ACTION:SIMULATION:001",
                work_item_id=item.work_item_id,
                candidate_sha=candidate_sha,
                channel=ExternalActionChannel.EMAIL,
                recipient="simulation@example.test",
                template_id="TEMPLATE:SIMULATION:001",
                variables={},
                machine_policy_receipt_id="MPR-SIMULATION",
                machine_policy_receipt_digest="sha256:" + "a" * 64,
                requested_at=datetime.now(UTC),
            ),
            request_digest="sha256:" + "b" * 64,
            status=ExternalActionStatus.WAITING_EXTERNAL_CHANNEL,
            reason=ExternalActionReason.CHANNEL_UNAVAILABLE,
        )

    def verify_research_advisory(
        self, bundle: ResearchAdvisoryBundle
    ) -> dict[str, bytes]:
        payloads = {"report": Path(bundle.report_path).read_bytes()}
        for artifact in bundle.artifacts:
            payloads[f"raw:{artifact.source_id}"] = Path(artifact.raw_cas_path).read_bytes()
            payloads[f"receipt:{artifact.source_id}"] = Path(
                artifact.receipt_path
            ).read_bytes()
        return payloads


class _CapturingMarketBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[AgentTaskRequest] = []

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.requests.append(request)
        before_sha = _git(Path(request.candidate_worktree), "rev-parse", "HEAD")
        report = _strict_simulation_report(request, before_sha=before_sha, mutate=True)
        result = await super().execute(request)
        return result.model_copy(update={"structured_output": report})


def _no_freshness(_item: WorkItem) -> dict[str, str]:
    return {}


def _no_context_groups(_item: WorkItem, _role: str) -> list[str]:
    return []


class _TypedWaitThenCommitBackend(_CommittingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.calls += 1
        if self.calls > 1:
            return await super().execute(request)
        result = await FakeBackend.execute(self, request)
        terminal = Path(request.artifact_root) / request.role / "backend-terminal.json"
        terminal.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            terminal,
            {
                "requestId": request.request_id,
                "state": "QUOTA_WAIT",
                "retryAt": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            },
        )
        digest = "sha256:" + sha256_file(terminal)
        retry_at = datetime.now(UTC) + timedelta(minutes=5)
        return result.model_copy(
            update={
                "state": SessionState.FAILED,
                "verdict": "blocked",
                "redacted_summary": "subscription quota temporarily unavailable",
                "terminal_disposition": BackendTerminalDisposition.QUOTA_WAIT,
                "terminal_record_digest": digest,
                "error_state": BackendRouteState.QUOTA_WAIT,
                "usage": UsageState(
                    route_state=BackendRouteState.QUOTA_WAIT,
                    subscription_capacity="unavailable",
                    retry_at=retry_at.isoformat(),
                ),
                "artifact_digests": {f"{request.role}/backend-terminal.json": digest},
            }
        )


class _AlwaysTypedWaitBackend(_TypedWaitThenCommitBackend):
    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.calls = 0
        return await super().execute(request)


class _CountingCommittingBackend(_CommittingBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        self.calls += 1
        return await super().execute(request)


class _BackendMustNotRun(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        del request
        self.calls += 1
        raise AssertionError("pending publication restart must not rerun the backend")


class _PendingThenVerifiedPublisher(_AutomatedPRSimulationPublisher):
    def __init__(self, repo: Path, gate_root: Path) -> None:
        super().__init__(repo, gate_root)
        self.simulate_signed_deployment_update = False
        self.calls = 0
        self._verified_result: dict[str, object] | None = None

    def publish(self, **arguments: object) -> dict[str, object]:
        self.calls += 1
        candidate_sha = str(arguments["candidate_sha"])
        if self.calls == 1:
            return {
                "status": "PENDING_REQUIRED_CHECKS",
                "transactionId": f"MAINPUB-V3_SIM_001-{candidate_sha[:12].upper()}",
                "candidateSha": candidate_sha,
                "pullRequestNumber": 1,
                "pullRequestUrl": "https://github.com/TasfiqJ/TrainCapsule/pull/1",
                "phase": "CHECKS_PENDING",
            }
        if self._verified_result is not None:
            lease_guard = arguments.get("lease_guard")
            assert callable(lease_guard)
            lease_guard()
            return dict(self._verified_result)
        result = super().publish(**arguments)
        result["transactionId"] = f"MAINPUB-V3_SIM_001-{candidate_sha[:12].upper()}"
        self._verified_result = dict(result)
        return result


def test_typed_backend_wait_is_durable_and_does_not_spend_repair_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _TypedWaitThenCommitBackend()
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    first = asyncio.run(controller.run_cycle())
    first_result = cast(list[dict[str, object]], first["results"])[0]
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert first_result["status"] == "PAUSED_BACKEND"
    assert first_result["backendState"] == "QUOTA_WAIT"
    assert checkpoint.backend_wait_state is BackendRouteState.QUOTA_WAIT
    assert checkpoint.backend_terminal_record_digest is not None
    assert checkpoint.backend_rechecks_remaining == 2
    assert checkpoint.budget.repair_cycles_remaining == 2
    assert checkpoint.active is True

    checkpoint.backend_resume_at = datetime.now(UTC) - timedelta(seconds=1)
    controller.checkpoints.save_v3(checkpoint)
    second = asyncio.run(controller.run_cycle())
    second_result = cast(list[dict[str, object]], second["results"])[0]
    assert second_result["status"] == "PASSED_ENGINEERING"
    assert backend.calls >= 2


def test_pending_publication_remains_active_and_resumes_same_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    publisher = _PendingThenVerifiedPublisher(repo, tmp_path / "gates")
    backend = _CountingCommittingBackend()
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=publisher,
    )

    first = asyncio.run(controller.run_cycle())
    first_result = cast(list[dict[str, object]], first["results"])[0]
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    transaction_id = checkpoint.publication_transaction_id
    assert first_result["publicationStatus"] == "PENDING_REQUIRED_CHECKS"
    assert checkpoint.active is True
    assert checkpoint.backend_wait_state == "PUBLICATION_PENDING"
    assert transaction_id == first_result["publicationTransactionId"]
    assert checkpoint.budget.repair_cycles_remaining == 2

    checkpoint.backend_resume_at = datetime.now(UTC) - timedelta(seconds=1)
    controller.checkpoints.save_v3(checkpoint)
    restarted_backend = _BackendMustNotRun()
    restarted = V3Controller(
        repo_root=repo,
        backend=restarted_backend,
        publisher=publisher,
    )
    with pytest.raises(RuntimeError, match="DEPLOYMENT_UPDATE_REQUIRED"):
        asyncio.run(restarted.run_cycle())
    assert publisher.calls == 2
    assert backend.calls == 1
    assert restarted_backend.calls == 0
    final_checkpoint = restarted.checkpoints.load_v3("V3-SIM-001")
    assert final_checkpoint is not None
    assert final_checkpoint.publication_transaction_id == transaction_id
    assert final_checkpoint.active is False
    restart_state = restarted._load_state()  # pyright: ignore[reportPrivateUsage]
    assert restart_state.deployment_update_handoff is not None
    assert Path(restart_state.deployment_update_handoff).is_file()

    merged_main = _git(restarted.git_root, "rev-parse", "main")
    installed_main = _git(repo, "rev-parse", "main")
    _git(repo, "fetch", str(restarted.git_root), "main")
    _git(repo, "update-ref", "refs/heads/main", merged_main, installed_main)

    updated_runtime = V3Controller(
        repo_root=repo,
        backend=restarted_backend,
        publisher=publisher,
    )
    updated_runtime._require_installed_snapshot_alignment(  # pyright: ignore[reportPrivateUsage]
        state=updated_runtime._load_state()  # pyright: ignore[reportPrivateUsage]
    )
    assert publisher.calls == 2
    assert backend.calls == 1
    assert restarted_backend.calls == 0
    completed_checkpoint = updated_runtime.checkpoints.load_v3("V3-SIM-001")
    assert completed_checkpoint is not None
    assert completed_checkpoint.publication_transaction_id == transaction_id
    assert completed_checkpoint.active is False
    completed_state = updated_runtime._load_state()  # pyright: ignore[reportPrivateUsage]
    assert completed_state.deployment_update_handoff is None


def test_advanced_anchor_requires_signed_deployment_update_before_next_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _BackendMustNotRun()
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    base = _git(controller.git_root, "rev-parse", "main")
    installed_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    installed_runtime = InstalledControllerRuntimeManifest.model_construct(
        manifest_digest="sha256:" + "0" * 64,
        repository_main_sha=base,
        repository_tree_sha=installed_tree,
    )
    controller.installed_runtime_loader = lambda: installed_runtime
    worktree = tmp_path / "verified-merged-main"
    _git(tmp_path, "clone", str(controller.git_root), str(worktree))
    _git(worktree, "config", "user.name", "Independent Updater")
    _git(worktree, "config", "user.email", "updater@example.invalid")
    (worktree / "verified-main.txt").write_text("verified\n", encoding="utf-8")
    _git(worktree, "add", "verified-main.txt")
    _git(worktree, "commit", "-m", "verified merged main")
    merged = _git(worktree, "rev-parse", "HEAD")
    _git(controller.git_root, "fetch", str(worktree), "main")
    _git(controller.git_root, "update-ref", "refs/heads/main", merged, base)

    with pytest.raises(RuntimeError, match="DEPLOYMENT_UPDATE_REQUIRED"):
        asyncio.run(controller.run_cycle())
    state = controller._load_state()  # pyright: ignore[reportPrivateUsage]
    assert state.deployment_update_handoff is not None
    handoff = Path(state.deployment_update_handoff)
    assert handoff.is_file()
    payload = json.loads(handoff.read_text(encoding="utf-8"))
    assert payload["installedMainSha"] == base
    assert payload["requiredMainSha"] == merged
    assert payload["controllerRuntimeMayExecuteRequiredMain"] is False
    assert payload["installedRuntimeManifestDigest"] == installed_runtime.canonical_digest()
    assert payload["installedRuntimeManifestDigest"] != installed_runtime.manifest_digest
    assert backend.calls == 0
    assert all(item.status is not WorkStatus.RUNNING for item in controller.queue.items())

    restarted = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates-restart"),
        installed_runtime_loader=lambda: installed_runtime,
    )
    with pytest.raises(RuntimeError, match="DEPLOYMENT_UPDATE_REQUIRED"):
        asyncio.run(restarted.run_cycle())
    restarted_handoff = (
        restarted._load_state().deployment_update_handoff  # pyright: ignore[reportPrivateUsage]
    )
    assert restarted_handoff is not None
    assert handoff.read_bytes() == Path(restarted_handoff).read_bytes()
    assert backend.calls == 0

    _git(repo, "fetch", str(controller.git_root), "main")
    _git(repo, "update-ref", "refs/heads/main", merged, base)
    aligned = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates-aligned"),
    )
    aligned_state = aligned._load_state()  # pyright: ignore[reportPrivateUsage]
    aligned._require_installed_snapshot_alignment(  # pyright: ignore[reportPrivateUsage]
        state=aligned_state
    )
    assert aligned._load_state().deployment_update_handoff is None  # pyright: ignore[reportPrivateUsage]
    assert backend.calls == 0

    def stale_installed_runtime() -> InstalledControllerRuntimeManifest:
        raise RuntimeError("installed runtime manifest is stale")

    stale_runtime = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates-stale-runtime"),
        installed_runtime_loader=stale_installed_runtime,
    )
    with pytest.raises(RuntimeError, match="DEPLOYMENT_UPDATE_REQUIRED"):
        stale_runtime._require_installed_snapshot_alignment(  # pyright: ignore[reportPrivateUsage]
            state=stale_runtime._load_state()  # pyright: ignore[reportPrivateUsage]
        )
    stale_handoff = stale_runtime._load_state().deployment_update_handoff  # pyright: ignore[reportPrivateUsage]
    assert stale_handoff is not None
    stale_payload = json.loads(Path(stale_handoff).read_text(encoding="utf-8"))
    assert stale_payload["installedMainSha"] == merged
    assert stale_payload["requiredMainSha"] == merged
    assert stale_payload["installedRuntimeAttested"] is False


def test_signed_installed_successor_may_recover_a_lagging_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=_BackendMustNotRun(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    anchored_main = _git(controller.git_root, "rev-parse", "main")
    (repo / "signed-install.txt").write_text("newer signed install\n", encoding="utf-8")
    _git(repo, "add", "signed-install.txt")
    _git(repo, "commit", "-m", "newer signed install")
    installed_main = _git(repo, "rev-parse", "main")
    installed_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    assert installed_main != anchored_main
    installed_runtime = InstalledControllerRuntimeManifest.model_construct(
        manifest_digest="sha256:" + "0" * 64,
        repository_main_sha=installed_main,
        repository_tree_sha=installed_tree,
    )
    controller.installed_runtime_loader = lambda: installed_runtime

    state = controller._load_state()  # pyright: ignore[reportPrivateUsage]
    controller._require_installed_snapshot_alignment(  # pyright: ignore[reportPrivateUsage]
        state=state
    )

    assert controller._load_state().deployment_update_handoff is None  # pyright: ignore[reportPrivateUsage]


def test_backend_wait_exhaustion_is_finite_without_product_repair_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=_AlwaysTypedWaitBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    first = asyncio.run(controller.run_cycle())
    assert cast(list[dict[str, object]], first["results"])[0]["status"] == (
        "PAUSED_BACKEND"
    )
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    checkpoint.backend_rechecks_remaining = 0
    checkpoint.backend_resume_at = datetime.now(UTC) - timedelta(seconds=1)
    repair_budget = checkpoint.budget.repair_cycles_remaining
    controller.checkpoints.save_v3(checkpoint)

    second = asyncio.run(controller.run_cycle())
    result = cast(list[dict[str, object]], second["results"])[0]
    exhausted = controller.checkpoints.load_v3("V3-SIM-001")
    assert exhausted is not None
    assert result["status"] == "BLOCKED_TECHNICAL"
    assert result["backendState"] == "QUOTA_WAIT"
    assert exhausted.active is False
    assert exhausted.budget.repair_cycles_remaining == repair_budget


def test_controller_cannot_self_issue_machine_policy_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    review = _item(
        "V3-DEC-001",
        risk="TRUST_CORE",
        kind="MACHINE_POLICY_REVIEW",
        lane="FACTORY",
        automatable=False,
        milestone="M0_FACTORY_MIGRATED",
    )
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=[review],
    )
    (repo / "factory/roadmap/work_items.yaml").write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(controller.run_cycle())

    assert result["status"] == "IDLE"
    assert controller.queue.load("V3-DEC-001").status.value == "BLOCKED_POLICY"
    assert not controller.runtime_paths.machine_policy_receipts.exists()


def test_disposable_controller_progresses_mechanical_and_standard_without_humans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    legacy_digest = sha256_file(repo / "factory/feature_ledger.yaml")
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    first = asyncio.run(controller.run_cycle())
    second = asyncio.run(controller.run_cycle())

    assert first["status"] == second["status"] == "CYCLE_COMPLETE"
    assert first["interventionMode"] == second["interventionMode"] == "NONE"
    first_results = cast(list[dict[str, object]], first["results"])
    second_results = cast(list[dict[str, object]], second["results"])
    assert first_results[0]["status"] == "PASSED_ENGINEERING"
    assert second_results[0]["status"] == "PASSED_ENGINEERING"
    assert controller.queue.load("V3-SIM-003").status.value == "WAITING_EXTERNAL"
    assert sha256_file(repo / "factory/feature_ledger.yaml") == legacy_digest
    assert _git(repo, "rev-list", "--count", "HEAD") == "5"
    packet_path = next(
        (controller.artifact_root / "V3-SIM-001").glob("*/task-packet.yaml")
    )
    packet = yaml.safe_load(packet_path.read_text(encoding="utf-8"))
    sources = cast(list[str], packet["sourceDocuments"])
    assert sources[:2] == [
        "config/active_generation.yaml",
        "docs/source-of-truth/v3.1-zh-2026-08-12/FINAL_MANIFEST_V3_1_ZH.json",
    ]
    assert not any("CODEX_MASTER_MIGRATION_PROMPT" in source for source in sources)
    assert all(
        (Path(source).is_file() if Path(source).is_absolute() else (repo / source).is_file())
        for source in sources
    )


def test_controller_consumes_bounded_repair_then_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _FailThenCommitBackend()
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(controller.run_cycle())

    assert cast(list[dict[str, object]], result["results"])[0]["status"] == ("PASSED_ENGINEERING")
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert checkpoint.budget.plan_attempts_remaining == 1
    assert checkpoint.budget.repair_cycles_remaining == 1
    handoffs = list(
        (controller.artifact_root / "V3-SIM-001").glob("*/recovery-handoff-builder-01.json")
    )
    assert len(handoffs) == 1


def test_repeated_finding_blocks_after_finite_attempts_and_proposes_redesign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _FailThenCommitBackend(always_fail=True)
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(controller.run_cycle())

    item_result = cast(list[dict[str, object]], result["results"])[0]
    assert item_result["status"] == "BLOCKED_TECHNICAL"
    assert item_result["redesignProposed"] is True
    assert backend.calls == 2
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None and checkpoint.active is False
    assert checkpoint.budget.repair_cycles_remaining == 0


def test_value_redesign_is_finite_durable_and_never_expands_the_roadmap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=[
            _item(
                "V3-SIM-001",
                risk="STANDARD",
                milestone="M0_FACTORY_MIGRATED",
            )
        ],
    )
    roadmap_path = repo / "factory/roadmap/work_items.yaml"
    roadmap_path.write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    roadmap_before = roadmap_path.read_bytes()
    backend = _CommittingBackend(
        results=[
            {},
            {"incrementalDecisionValue": False},
            {},
            {"incrementalDecisionValue": False},
        ]
    )
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    first = asyncio.run(controller.run_cycle())
    second = asyncio.run(controller.run_cycle())

    assert cast(list[dict[str, object]], first["results"])[0]["status"] == "READY"
    second_result = cast(list[dict[str, object]], second["results"])[0]
    assert second_result["status"] == "BLOCKED_POLICY"
    assert second_result["proposedTerminalStatus"] == "REJECTED_VALUE"
    assert controller.queue.load("V3-SIM-001").status.value == "BLOCKED_POLICY"
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert checkpoint.active is False
    assert checkpoint.value_failure_count == 2
    assert checkpoint.value_redesigns_remaining == 0
    assert (
        len(
            list(
                (controller.runtime_paths.value_redesign_proposals / "V3-SIM-001").glob(
                    "VRP-*.json"
                )
            )
        )
        == 2
    )
    assert roadmap_path.read_bytes() == roadmap_before


def test_interrupted_controller_resumes_candidate_with_finite_restart_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    crashing = V3Controller(
        repo_root=repo,
        backend=_CrashingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    with pytest.raises(RuntimeError, match="simulated process crash"):
        asyncio.run(crashing.run_cycle())
    interrupted = crashing.checkpoints.load_v3("V3-SIM-001")
    assert interrupted is not None
    assert interrupted.budget.plan_attempts_remaining == 1
    assert interrupted.budget.restarts_remaining == 1
    assert crashing.queue.load("V3-SIM-001").status.value == "RUNNING"

    lease_path = crashing.queue.lease_root / "V3-SIM-001.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["ownerProcessIdentity"] = "linux-proc:999999999:0"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")

    resumed = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    result = asyncio.run(resumed.run_cycle())

    assert "results" in result, result
    assert cast(list[dict[str, object]], result["results"])[0]["status"] == ("PASSED_ENGINEERING")
    checkpoint = resumed.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert checkpoint.budget.plan_attempts_remaining == 0
    assert checkpoint.budget.restarts_remaining == 0
    handoffs = list(
        (resumed.artifact_root / "V3-SIM-001").glob("recovery-*/handoff.json")
    )
    assert len(handoffs) == 1


def test_restart_resumes_exact_session_handoff_and_candidate_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    _make_first_item_standard(repo)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    crashing = V3Controller(
        repo_root=repo,
        backend=_CrashAfterBoundFailureBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    with pytest.raises(RuntimeError, match="crash after bound repair handoff"):
        asyncio.run(crashing.run_cycle())
    checkpoint = crashing.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert checkpoint.backend_session is not None
    assert checkpoint.handoff_path is not None
    assert checkpoint.handoff_digest is not None
    assert checkpoint.candidate_worktree is not None
    assert checkpoint.completed_roles == ["builder"]
    original_worktree = Path(checkpoint.candidate_worktree)

    lease_path = crashing.queue.lease_root / "V3-SIM-001.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["ownerProcessIdentity"] = "linux-proc:999999999:0"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    backend = _ResumingBackend(original_worktree)
    resumed = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(resumed.run_cycle())

    assert cast(list[dict[str, object]], result["results"])[0]["status"] == ("PASSED_ENGINEERING")
    assert backend.resume_calls == 1
    assert resumed.checkpoints.load_v3("V3-SIM-001") is not None
    assert original_worktree.is_dir()


def test_substituted_recovery_handoff_fails_closed_before_backend_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    _make_first_item_standard(repo)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    crashing = V3Controller(
        repo_root=repo,
        backend=_CrashAfterBoundFailureBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    with pytest.raises(RuntimeError, match="crash after bound repair handoff"):
        asyncio.run(crashing.run_cycle())
    checkpoint = crashing.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None and checkpoint.handoff_path is not None
    Path(checkpoint.handoff_path).write_text("{}\n", encoding="utf-8")
    lease_path = crashing.queue.lease_root / "V3-SIM-001.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["ownerProcessIdentity"] = "linux-proc:999999999:0"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    backend = _ResumingBackend(Path(checkpoint.candidate_worktree or "missing"))
    resumed = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    with pytest.raises(RuntimeError, match="missing or substituted"):
        asyncio.run(resumed.run_cycle())
    assert backend.resume_calls == 0


def test_missing_recovery_worktree_is_transplanted_and_fully_revalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    _make_first_item_standard(repo)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    crashing = V3Controller(
        repo_root=repo,
        backend=_CrashAfterBoundFailureBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    with pytest.raises(RuntimeError, match="crash after bound repair handoff"):
        asyncio.run(crashing.run_cycle())
    checkpoint = crashing.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None and checkpoint.candidate_worktree is not None
    missing = Path(checkpoint.candidate_worktree).resolve()
    assert missing.is_relative_to(crashing.runtime_paths.worktree_root.resolve())
    shutil.rmtree(missing)
    lease_path = crashing.queue.lease_root / "V3-SIM-001.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["ownerProcessIdentity"] = "linux-proc:999999999:0"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    resumed = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(resumed.run_cycle())

    assert cast(list[dict[str, object]], result["results"])[0]["status"] == (
        "PASSED_ENGINEERING"
    )
    receipts = list(
        (resumed.artifact_root / "V3-SIM-001").rglob("SALVAGE_RECEIPT.json")
    )
    assert len(receipts) == 1
    receipt = cast(dict[str, object], json.loads(receipts[0].read_bytes()))
    assert receipt["allStagesRequireRevalidation"] is True


def test_stale_main_checkpoint_is_invalidated_and_restarted_from_current_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    _make_first_item_standard(repo)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    crashing = V3Controller(
        repo_root=repo,
        backend=_CrashAfterBoundFailureBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    with pytest.raises(RuntimeError, match="crash after bound repair handoff"):
        asyncio.run(crashing.run_cycle())
    stale = crashing.checkpoints.load_v3("V3-SIM-001")
    assert stale is not None

    (repo / "main-advanced.txt").write_text("new protected main\n", encoding="utf-8")
    _git(repo, "add", "main-advanced.txt")
    _git(repo, "commit", "-m", "advance protected main")
    advanced_main = _git(repo, "rev-parse", "HEAD")
    _git(crashing.git_root, "fetch", str(repo), advanced_main)
    _git(crashing.git_root, "update-ref", "refs/heads/main", advanced_main)
    lease_path = crashing.queue.lease_root / "V3-SIM-001.json"
    lease = json.loads(lease_path.read_text(encoding="utf-8"))
    lease["ownerProcessIdentity"] = "linux-proc:999999999:0"
    lease_path.write_text(json.dumps(lease), encoding="utf-8")
    resumed = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    result = asyncio.run(resumed.run_cycle())

    assert cast(list[dict[str, object]], result["results"])[0]["status"] == (
        "PASSED_ENGINEERING"
    )
    checkpoint = resumed.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert (
        subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                advanced_main,
                checkpoint.candidate_sha,
            ],
            cwd=repo,
            check=False,
        ).returncode
        == 0
    )


def test_controller_process_lock_covers_the_entire_async_worker_lifetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _PausingCommittingBackend()
    first = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    second = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    async def exercise() -> None:
        running = asyncio.create_task(first.run_cycle())
        await backend.started.wait()
        with pytest.raises(ControllerLockError, match="already active"):
            await second.run_cycle()
        backend.release.set()
        assert (await running)["status"] == "CYCLE_COMPLETE"

    asyncio.run(exercise())


def test_lease_renewal_failure_cancels_backend_and_quarantines_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    backend = _PausingCommittingBackend()
    publisher = _AutomatedPRSimulationPublisher(repo, tmp_path / "gates")
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=publisher,
        lease_renewal_interval_seconds=0.001,
    )

    def lose_lease(*_args: object, **_kwargs: object) -> Never:
        raise RuntimeError("injected lease loss")

    monkeypatch.setattr(controller.queue, "renew", lose_lease)

    with pytest.raises(RuntimeError, match="lease renewal failed"):
        asyncio.run(controller.run_cycle())
    assert controller.queue.load("V3-SIM-001").status is WorkStatus.BLOCKED_TECHNICAL
    checkpoint = controller.checkpoints.load_v3("V3-SIM-001")
    assert checkpoint is not None
    assert checkpoint.active is False
    assert checkpoint.approval_state == "LEASE_LOST_QUARANTINED"
    assert not (tmp_path / "gates").exists()


def test_lease_loss_at_gate_boundary_blocks_every_publication_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
        lease_renewal_interval_seconds=60,
    )

    def lose_lease(*_args: object, **_kwargs: object) -> Never:
        raise RuntimeError("injected boundary lease loss")

    monkeypatch.setattr(controller.queue, "renew", lose_lease)

    with pytest.raises(RuntimeError, match="execution quarantined"):
        asyncio.run(controller.run_cycle())
    assert controller.queue.load("V3-SIM-001").status is WorkStatus.BLOCKED_TECHNICAL
    assert not (tmp_path / "gates").exists()


def test_scheduler_decision_path_supports_runtime_root_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    external_runtime = tmp_path / "external-runtime"
    monkeypatch.setenv("TCF_RUNTIME_ROOT", str(external_runtime))
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    def no_advance(_items: WorkItemCollection) -> None:
        return None

    monkeypatch.setattr(controller, "_advance_completed_milestone", no_advance)

    asyncio.run(controller.run_cycle())

    decision = controller._load_state().last_decision_artifact  # pyright: ignore[reportPrivateUsage]
    assert decision is not None
    assert Path(decision).is_absolute()
    assert Path(decision).is_relative_to(external_runtime.resolve())


def test_milestone_does_not_advance_on_self_asserted_publication_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=[
            _item(
                "V3-SIM-001",
                risk="MECHANICAL",
                milestone="M0_FACTORY_MIGRATED",
            )
        ],
    )
    roadmap_path = repo / "factory/roadmap/work_items.yaml"
    roadmap_path.write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    _git(repo, "add", str(roadmap_path.relative_to(repo)))
    _git(repo, "commit", "-m", "bounded milestone fixture")
    tracked_roadmap = roadmap_path.read_bytes()
    tracked_scheduler = (repo / "config/scheduler.yaml").read_bytes()
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )

    with pytest.raises(ValueError, match="completion evidence policy is stale"):
        asyncio.run(controller.run_cycle())

    state = load_milestone_state(controller.runtime_paths.milestone_state)
    assert state is not None and state.active_milestone == "M0_FACTORY_MIGRATED"
    assert roadmap_path.read_bytes() == tracked_roadmap
    assert (repo / "config/scheduler.yaml").read_bytes() == tracked_scheduler

def test_controller_binds_verified_outside_fact_receipt_before_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    outside_fact = _item(
        "V3-SIM-003",
        risk="EXTERNAL",
        kind="EXTERNAL_EVIDENCE",
        lane="MARKET",
        automatable=False,
        external=True,
        milestone="M0_FACTORY_MIGRATED",
    )
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=[outside_fact],
    )
    (repo / "factory/roadmap/work_items.yaml").write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    controller.initialize()
    receipt = ExternalEvidenceReceipt.model_validate(
        {
            "receiptId": "XREC-SIM-003",
            "evidenceType": "INCIDENT_ARCHIVE_ACCESS",
            "subjectId": "V3-SIM-003",
                "issuer": {"id": "archive-custodian", "authority": "lawful custodian"},
                "issuedAt": "2026-08-11T21:59:00Z",
                "observedAt": "2026-08-11T22:00:00Z",
                "expiresAt": "2027-08-11T22:00:00Z",
                "revocationEpoch": 1,
                "revoked": False,
                "nonce": "1" * 32,
            "outcome": "Lawful archive access granted.",
            "artifacts": [
                {
                    "name": "access-grant",
                    "digest": "sha256:" + "a" * 64,
                    "locationClass": "TRUSTED_EXTERNAL",
                }
            ],
            "limitations": ["Fixture receipt; no customer claim."],
            "signature": {
                "algorithm": "ed25519",
                "keyId": "custodian-key-1",
                "value": "detached-signature",
            },
            "syntheticTestOnly": False,
        }
    )
    verified = TrustedEvidenceRecord(
        receipt=receipt,
        signature_valid=True,
        source_agent_writable=False,
    )

    def verified_loader(
        *,
        repo_root: Path,
        subject_id: str,
        trusted_root_environment_variable: str,
        trusted_public_key_environment_variable: str,
    ) -> TrustedEvidenceRecord:
        del (
            repo_root,
            subject_id,
            trusted_root_environment_variable,
            trusted_public_key_environment_variable,
        )
        return verified

    monkeypatch.setattr("tcfactory.v3.controller.load_verified_external_evidence", verified_loader)

    def do_not_advance_fixture_milestone(_items: WorkItemCollection) -> None:
        return None

    monkeypatch.setattr(
        controller, "_advance_completed_milestone", do_not_advance_fixture_milestone
    )

    result = asyncio.run(controller.run_cycle())

    advanced = controller.queue.load("V3-SIM-003")
    assert result["status"] == "IDLE"
    assert advanced.status.value == "PASSED_ENGINEERING"
    assert advanced.external_evidence_refs == ["XREC-SIM-003"]


def test_final_external_evidence_revalidation_rejects_revoke_after_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    item = _item(
        "V3-SIM-003",
        risk="EXTERNAL",
        kind="EXTERNAL_EVIDENCE",
        lane="MARKET",
        automatable=False,
        external=True,
        milestone="M0_FACTORY_MIGRATED",
    )
    checkpoint = V3Checkpoint(
        generation=1,
        work_item_id=item.work_item_id,
        lane=Lane.MARKET,
        milestone=item.milestone,
        budget=CheckpointBudget(
            max_turns=1,
            max_wall_time_seconds=60,
            plan_attempts_remaining=0,
            repair_cycles_remaining=0,
            restarts_remaining=0,
        ),
        context_digest="sha256:" + "1" * 64,
        source_digest="sha256:" + "2" * 64,
        candidate_sha="a" * 40,
        approval_state="PUBLICATION_PREPARED",
        stage_artifact_digests={
            "external_authority:XREC-SIM-003:revocation-list": (
                "sha256:" + "3" * 64
            )
        },
        active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    def revoked(**_: object) -> object:
        raise ExternalEvidenceVerificationError("external evidence receipt is revoked")

    monkeypatch.setattr(
        "tcfactory.v3.controller.load_verified_external_evidence_payload", revoked
    )
    with pytest.raises(ExternalEvidenceVerificationError, match="revoked"):
        controller._reverify_external_evidence(  # pyright: ignore[reportPrivateUsage]
            item=item,
            candidate_sha=checkpoint.candidate_sha,
            checkpoint=checkpoint,
            now=datetime.now(UTC),
        )


def test_invalid_external_receipt_remains_scoped_waiting_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    outside_fact = _item(
        "V3-SIM-003",
        risk="EXTERNAL",
        kind="EXTERNAL_EVIDENCE",
        lane="MARKET",
        automatable=False,
        external=True,
        milestone="M0_FACTORY_MIGRATED",
    )
    (repo / "factory/roadmap/work_items.yaml").write_text(
        yaml.safe_dump(
            WorkItemCollection(
                active_milestone="M0_FACTORY_MIGRATED",
                work_items=[outside_fact],
            ).model_dump(mode="json", by_alias=True),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
    )
    controller.initialize()
    invalid_receipt = ExternalEvidenceReceipt.model_validate(
        {
            "receiptId": "XREC-SIM-003",
            "evidenceType": "INCIDENT_ARCHIVE_ACCESS",
            "subjectId": "V3-SIM-003",
                "issuer": {"id": "untrusted", "authority": "none"},
                "issuedAt": "2026-08-11T21:59:00Z",
                "observedAt": "2026-08-11T22:00:00Z",
                "expiresAt": "2027-08-11T22:00:00Z",
                "revocationEpoch": 1,
                "revoked": False,
                "nonce": "2" * 32,
            "outcome": "Unverified claim.",
            "artifacts": [
                {
                    "name": "claim",
                    "digest": "sha256:" + "a" * 64,
                    "locationClass": "TRUSTED_EXTERNAL",
                }
            ],
            "limitations": [],
            "signature": {
                "algorithm": "ed25519",
                "keyId": "invalid",
                "value": "invalid",
            },
            "syntheticTestOnly": False,
        }
    )
    def invalid_loader(**_: object) -> TrustedEvidenceRecord:
        return TrustedEvidenceRecord(
            receipt=invalid_receipt,
            signature_valid=False,
            source_agent_writable=False,
        )

    monkeypatch.setattr(
        "tcfactory.v3.controller.load_verified_external_evidence",
        invalid_loader,
    )

    result = asyncio.run(controller.run_cycle())

    assert result["status"] == "IDLE"
    blocked = controller.queue.load("V3-SIM-003")
    assert blocked.status.value == "WAITING_EXTERNAL"
    assert blocked.external_evidence_refs == []


@pytest.mark.parametrize("mutation", ["untracked", "tracked", "symlink"])
def test_post_gate_candidate_mutation_taints_evidence_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    publisher = _MutatingGatePublisher(repo, tmp_path / "gates", mutation)
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=publisher,
    )

    with pytest.raises(RuntimeError, match="gate tainted the frozen candidate"):
        asyncio.run(controller.run_cycle())

    assert publisher.publish_called is False
    quarantine = next(
            (controller.artifact_root / "V3-SIM-001").glob(
            "*/quarantine/post-gate-candidate-mutation/REASON.txt"
        )
    )
    assert "candidate worktree is not clean" in quarantine.read_text(encoding="utf-8")


def test_candidate_freeze_detects_mutation_racing_its_status_observations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "race-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Freeze Test")
    _git(repo, "config", "user.email", "freeze@example.invalid")
    tracked = repo / "tracked.txt"
    tracked.write_text("reviewed\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "reviewed candidate")
    candidate_sha = _git(repo, "rev-parse", "HEAD")
    candidate_tree = _git(repo, "rev-parse", "HEAD^{tree}")

    import tcfactory.v3.candidate_freeze as freeze_module

    original = freeze_module._git_value  # pyright: ignore[reportPrivateUsage]
    status_observations = 0

    def racing_value(worktree: Path, arguments: list[str], *, label: str) -> str:
        nonlocal status_observations
        if arguments[:2] == ["status", "--porcelain=v1"]:
            status_observations += 1
            if status_observations == 2:
                tracked.write_text("raced\n", encoding="utf-8")
        return original(worktree, arguments, label=label)

    monkeypatch.setattr(freeze_module, "_git_value", racing_value)

    with pytest.raises(CandidateFreezeError, match="not clean"):
        assert_frozen_candidate(
            repo,
            expected_candidate_sha=candidate_sha,
            expected_candidate_tree_sha=candidate_tree,
        )


def test_candidate_freeze_rejects_symlink_root_and_concurrent_directory_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "swap-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Freeze Test")
    _git(repo, "config", "user.email", "freeze@example.invalid")
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "reviewed candidate")
    candidate_sha = _git(repo, "rev-parse", "HEAD")
    candidate_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    linked = tmp_path / "linked-worktree"
    linked.symlink_to(repo, target_is_directory=True)

    with pytest.raises(CandidateFreezeError, match="non-symlink directory"):
        assert_frozen_candidate(
            linked,
            expected_candidate_sha=candidate_sha,
            expected_candidate_tree_sha=candidate_tree,
        )

    import tcfactory.v3.candidate_freeze as freeze_module

    original_identity = freeze_module._directory_identity  # pyright: ignore[reportPrivateUsage]
    identity_observations = 0

    def swapping_identity(path: Path) -> tuple[int, int]:
        nonlocal identity_observations
        identity_observations += 1
        if identity_observations == 2:
            moved = tmp_path / "swapped-out-worktree"
            repo.rename(moved)
            shutil.copytree(moved, repo, symlinks=True)
        return original_identity(path)

    monkeypatch.setattr(freeze_module, "_directory_identity", swapping_identity)

    with pytest.raises(CandidateFreezeError, match="directory identity changed"):
        assert_frozen_candidate(
            repo,
            expected_candidate_sha=candidate_sha,
            expected_candidate_tree_sha=candidate_tree,
        )


def _replace_simulation_items(repo: Path, items: list[WorkItem]) -> None:
    collection = WorkItemCollection(
        active_milestone="M0_FACTORY_MIGRATED",
        work_items=items,
    )
    (repo / "factory/roadmap/work_items.yaml").write_text(
        yaml.safe_dump(collection.model_dump(mode="json", by_alias=True), sort_keys=False),
        encoding="utf-8",
    )
    _git(repo, "add", "factory/roadmap/work_items.yaml")
    _git(repo, "commit", "-m", "phase6 simulation roadmap")


def test_phase6_research_agent_receives_only_advisory_offline_network_denied_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    item = _item(
        "V3-MKT-002",
        risk="MECHANICAL",
        kind="RESEARCH",
        lane="MARKET",
        milestone="M0_FACTORY_MIGRATED",
    )
    _replace_simulation_items(repo, [item])
    backend = _CapturingMarketBackend()
    runtime = _Phase6SimulationRuntime()
    controller = V3Controller(
        repo_root=repo,
        backend=backend,
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
        phase6_runtime=runtime,
    )
    monkeypatch.setattr(controller, "_freshness_receipts", _no_freshness)
    monkeypatch.setattr("tcfactory.v3.controller._context_groups", _no_context_groups)

    controller.initialize()
    controller.queue.transition(
        "V3-MKT-002", WorkStatus.READY, updated_at=datetime.now(UTC)
    )
    controller.queue.transition(
        "V3-MKT-002", WorkStatus.QUEUED, updated_at=datetime.now(UTC)
    )
    lease = controller.queue.claim(
        "V3-MKT-002", owner_id="phase6-test", now=datetime.now(UTC)
    )
    result = asyncio.run(
        controller.execute_claimed(
            controller.queue.load("V3-MKT-002"),
            lease_id=lease.lease_id,
            now=datetime.now(UTC),
        )
    )

    assert result["status"] == "PASSED_ENGINEERING", result
    assert runtime.research_calls == ["V3-MKT-002"]
    assert backend.requests
    request = backend.requests[0]
    assert request.network_policy == "DENY"
    assert request.network_allowed is False
    advisory = cast(dict[str, object], request.task_packet["controllerAdvisoryEvidence"])
    assert advisory["authorityEffect"] == "ADVISORY_ONLY_NEVER_NORMATIVE"
    assert advisory["networkPolicy"] == "DENY"


def test_phase6_research_and_external_channel_waits_are_item_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    research = _item(
        "V3-MKT-001",
        risk="MECHANICAL",
        kind="RESEARCH",
        lane="MARKET",
        milestone="M0_FACTORY_MIGRATED",
    )
    commercial = _item(
        "V3-MKT-002",
        risk="EXTERNAL",
        kind="COMMERCIAL_EXPERIMENT",
        lane="MARKET",
        automatable=False,
        external=True,
        milestone="M0_FACTORY_MIGRATED",
    )
    product = _item(
        "V3-SIM-001",
        risk="MECHANICAL",
        lane="PRODUCT",
        milestone="M0_FACTORY_MIGRATED",
    )
    _replace_simulation_items(repo, [research, commercial, product])
    runtime = _Phase6SimulationRuntime(research_failure=True)
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_AutomatedPRSimulationPublisher(repo, tmp_path / "gates"),
        phase6_runtime=runtime,
    )
    monkeypatch.setattr(controller, "_freshness_receipts", _no_freshness)
    monkeypatch.setattr("tcfactory.v3.controller._context_groups", _no_context_groups)

    controller.initialize()
    controller._promote_ready(  # pyright: ignore[reportPrivateUsage]
        controller._runtime_collection(),  # pyright: ignore[reportPrivateUsage]
        datetime.now(UTC),
    )
    if controller.queue.load("V3-MKT-001").status is not WorkStatus.READY:
        controller.queue.transition(
            "V3-MKT-001", WorkStatus.READY, updated_at=datetime.now(UTC)
        )
    controller.queue.transition(
        "V3-MKT-001", WorkStatus.QUEUED, updated_at=datetime.now(UTC)
    )
    research_lease = controller.queue.claim(
        "V3-MKT-001", owner_id="phase6-test", now=datetime.now(UTC)
    )
    research_result = asyncio.run(
        controller.execute_claimed(
            controller.queue.load("V3-MKT-001"),
            lease_id=research_lease.lease_id,
            now=datetime.now(UTC),
        )
    )
    if controller.queue.load("V3-SIM-001").status is not WorkStatus.READY:
        controller.queue.transition(
            "V3-SIM-001", WorkStatus.READY, updated_at=datetime.now(UTC)
        )
    controller.queue.transition(
        "V3-SIM-001", WorkStatus.QUEUED, updated_at=datetime.now(UTC)
    )
    product_lease = controller.queue.claim(
        "V3-SIM-001", owner_id="phase6-test", now=datetime.now(UTC)
    )
    product_result = asyncio.run(
        controller.execute_claimed(
            controller.queue.load("V3-SIM-001"),
            lease_id=product_lease.lease_id,
            now=datetime.now(UTC),
        )
    )

    assert research_result["status"] == "WAITING_EXTERNAL"
    assert product_result["status"] == "PASSED_ENGINEERING"
    assert controller.queue.load("V3-MKT-001").status.value == "WAITING_EXTERNAL"
    assert controller.queue.load("V3-MKT-002").status.value == "WAITING_EXTERNAL"
    assert controller.queue.load("V3-SIM-001").status.value == "PASSED_ENGINEERING"
    assert runtime.research_calls
    assert runtime.action_calls
