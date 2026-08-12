from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

from tcfactory.backends.base import AgentRunResult, AgentTaskRequest
from tcfactory.backends.fake import FakeBackend
from tcfactory.util import sha256_file
from tcfactory.v3.controller import V3Controller
from tcfactory.v3.external_evidence import ExternalEvidenceReceipt, TrustedEvidenceRecord
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
) -> WorkItem:
    return WorkItem.model_validate(
        {
            "version": 3,
            "workItemId": identifier,
            "title": f"Simulation {identifier}",
            "lane": lane,
            "kind": kind,
            "milestone": "M1_NATIVE_PREFLIGHT",
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
            "ownerType": "EXTERNAL_PARTY" if external else "AI",
            "automatable": automatable,
            "evidenceRequired": ["deterministic disposable-repository simulation"],
            "externalReceiptRequired": external,
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
    shutil.copytree(
        ROOT / "docs/source-of-truth/v3-2026-08-11",
        repo / "docs/source-of-truth/v3-2026-08-11",
    )
    (repo / "docs").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs/CONTEXT_INDEX.yaml", repo / "docs/CONTEXT_INDEX.yaml")
    shutil.copytree(ROOT / "factory/policy", repo / "factory/policy")
    (repo / "factory/roadmap").mkdir(parents=True)
    (repo / "tcfactory/v3").mkdir(parents=True)
    shutil.copy2(ROOT / "tcfactory/v3/planning.py", repo / "tcfactory/v3/planning.py")
    (repo / "factory/feature_ledger.yaml").write_text(
        "version: 2\nlegacy: immutable\n", encoding="utf-8"
    )
    collection = WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
        work_items=[
            _item("V3-SIM-001", risk="MECHANICAL"),
            _item("V3-SIM-002", risk="STANDARD", depends=["V3-SIM-001"]),
            _item(
                "V3-SIM-003",
                risk="EXTERNAL",
                kind="EXTERNAL_EVIDENCE",
                lane="MARKET",
                automatable=False,
                external=True,
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


class _CommittingBackend(FakeBackend):
    async def execute(self, request: AgentTaskRequest) -> AgentRunResult:
        if request.role == "builder":
            worktree = Path(request.candidate_worktree)
            target = worktree / "packages/traincapsule-core/simulation"
            target.mkdir(parents=True, exist_ok=True)
            artifact = target / f"{request.work_item_id}.txt"
            artifact.write_text(f"{request.request_id}\n", encoding="utf-8")
            _git(worktree, "add", str(artifact.relative_to(worktree)))
            _git(worktree, "commit", "-m", f"simulate {request.work_item_id}")
        return await super().execute(request)


class _LocalMainPublisher:
    def __init__(self, repo: Path, gate_root: Path) -> None:
        self.repo = repo
        self.gate_root = gate_root

    def prepare_candidate(
        self, *, item: WorkItem, candidate_sha: str, candidate_worktree: Path
    ) -> dict[str, Path]:
        del candidate_worktree
        self.gate_root.mkdir(parents=True, exist_ok=True)
        path = self.gate_root / f"{item.work_item_id}-{candidate_sha}.gate"
        path.write_text("PASS\n", encoding="utf-8")
        return {"disposable-simulation": path}

    def publish(self, **arguments: object) -> dict[str, object]:
        candidate_sha = str(arguments["candidate_sha"])
        _git(self.repo, "merge", "--ff-only", candidate_sha)
        return {
            "status": "PUBLISHED_MAIN_VERIFIED",
            "candidateSha": candidate_sha,
            "branch": "main",
            "hostedChecks": {"mode": "DETERMINISTIC_FAKE_NO_NETWORK"},
        }


def test_disposable_controller_progresses_mechanical_and_standard_without_humans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _simulation_repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    legacy_digest = sha256_file(repo / "factory/feature_ledger.yaml")
    controller = V3Controller(
        repo_root=repo,
        backend=_CommittingBackend(),
        publisher=_LocalMainPublisher(repo, tmp_path / "gates"),
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
    assert _git(repo, "rev-list", "--count", "HEAD") == "3"


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
    )
    collection = WorkItemCollection(
        active_milestone="M1_NATIVE_PREFLIGHT",
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
        publisher=_LocalMainPublisher(repo, tmp_path / "gates"),
    )
    controller.initialize()
    receipt = ExternalEvidenceReceipt.model_validate(
        {
            "receiptId": "XREC-SIM-003",
            "evidenceType": "INCIDENT_ARCHIVE_ACCESS",
            "subjectId": "V3-SIM-003",
            "issuer": {"id": "archive-custodian", "authority": "lawful custodian"},
            "observedAt": "2026-08-11T22:00:00Z",
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

    monkeypatch.setattr(
        "tcfactory.v3.controller.load_verified_external_evidence", verified_loader
    )

    result = asyncio.run(controller.run_cycle())

    advanced = controller.queue.load("V3-SIM-003")
    assert result["status"] == "IDLE"
    assert advanced.status.value == "PASSED_ENGINEERING"
    assert advanced.external_evidence_refs == ["XREC-SIM-003"]
