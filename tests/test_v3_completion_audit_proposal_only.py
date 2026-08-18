from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import tcfactory.completion as completion_module
from tcfactory.completion import CompletionBlocked
from tcfactory.feature_ledger import FeatureItem, FeatureLedger
from tcfactory.models import (
    CompletionAuditReport,
    CompletionVerdict,
    CompletionWorkItem,
    FactoryConfig,
)

ROOT = Path(__file__).resolve().parents[1]


def _repo(tmp_path: Path) -> tuple[Path, Path, FeatureLedger]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    ledger_path = repo / "factory/feature_ledger.yaml"
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("immutable-ledger-bytes\n", encoding="utf-8")
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "candidate",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    ledger = FeatureLedger(
        source_of_truth="test",
        tasks=[
            FeatureItem(
                task_id="T001",
                outcome="existing build work",
                lead_role="Builder",
                phase="build",
                status="passed",
            )
        ],
    )
    return repo, ledger_path, ledger


def _sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _guard_mutators(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("completion audit called a roadmap or Git mutator")

    for name in ("_append_missing_items", "save_feature_ledger", "commit_all"):
        monkeypatch.setattr(completion_module, name, forbidden, raising=False)


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    report: CompletionAuditReport,
) -> None:
    def load_definition(*_: object) -> dict[str, object]:
        return {}

    def deterministic_check(*_: object) -> list[str]:
        return []

    monkeypatch.setattr(completion_module, "load_definition", load_definition)
    monkeypatch.setattr(completion_module, "deterministic_completion_check", deterministic_check)

    async def review(**_: object) -> CompletionAuditReport:
        return report

    monkeypatch.setattr(completion_module, "_one_review", review)
    _guard_mutators(monkeypatch)


def _run(repo: Path, ledger: FeatureLedger) -> tuple[str, list[str], str]:
    return asyncio.run(
        completion_module.audit_and_expand_or_complete(
            repo_root=repo,
            config=FactoryConfig(auth_mode="unrestricted"),
            ledger=ledger,
            audits_required=2,
        )
    )


def test_complete_audit_preserves_ledger_bytes_and_git_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, ledger_path, ledger = _repo(tmp_path)
    _configure(
        monkeypatch,
        CompletionAuditReport(
            verdict=CompletionVerdict.COMPLETE,
            summary="complete",
            completed_evidence=["evidence/passed.json"],
        ),
    )
    def private_gate(**_: object) -> dict[str, object]:
        return {"passed": True, "result": {}}

    monkeypatch.setattr(completion_module, "run_private_completion_gate", private_gate)
    before_bytes, before_sha = ledger_path.read_bytes(), _sha(repo)

    outcome, _, audited_sha = _run(repo, ledger)

    assert outcome == "complete"
    assert audited_sha == before_sha == _sha(repo)
    assert ledger_path.read_bytes() == before_bytes


def test_blocked_audit_preserves_ledger_bytes_and_git_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, ledger_path, ledger = _repo(tmp_path)
    _configure(
        monkeypatch,
        CompletionAuditReport(
            verdict=CompletionVerdict.BLOCKED,
            summary="blocked",
            blockers=["independent evidence unavailable"],
        ),
    )
    before_bytes, before_sha = ledger_path.read_bytes(), _sha(repo)

    with pytest.raises(CompletionBlocked, match="independent evidence unavailable"):
        _run(repo, ledger)

    assert _sha(repo) == before_sha
    assert ledger_path.read_bytes() == before_bytes


def test_missing_work_emits_candidate_bound_proposal_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, ledger_path, ledger = _repo(tmp_path)
    _configure(
        monkeypatch,
        CompletionAuditReport(
            verdict=CompletionVerdict.INCOMPLETE,
            summary="missing bounded work",
            missing_items=[
                CompletionWorkItem(
                    task_id="AUTO001",
                    outcome="Implement the missing production behavior",
                    phase="completion",
                    lead_role="Builder",
                    evidence_required=["deterministic test"],
                )
            ],
        ),
    )
    before_bytes, before_sha = ledger_path.read_bytes(), _sha(repo)

    outcome, proposal_refs, audited_sha = _run(repo, ledger)

    assert outcome == "proposed"
    assert audited_sha == before_sha == _sha(repo)
    assert ledger_path.read_bytes() == before_bytes
    proposal = json.loads((repo / proposal_refs[0]).read_text(encoding="utf-8"))
    assert proposal["record"]["candidateSha"] == before_sha
    assert proposal["record"]["accepted"] is False
    assert proposal["record"]["evidenceDigests"]
    assert proposal["proposedWorkItems"][0]["task_id"] == "AUTO001"


def test_v3_mig_010_engineering_evidence_is_digest_bound_and_non_authoritative() -> None:
    evidence = json.loads(
        (ROOT / "docs/migrations/evidence/V3-MIG-010.json").read_text(encoding="utf-8")
    )
    assert evidence["workItemId"] == "V3-MIG-010"
    assert evidence["authorityClaim"] == "NONE"
    assert evidence["machinePolicyAuthorized"] is False
    assert evidence["controllerAuthorized"] is False
    observed_base = str(evidence["observedCommit"])
    assert len(observed_base) == 40
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", observed_base, "HEAD"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ancestry.returncode == 0
    for binding in evidence["bindings"]:
        payload = (ROOT / binding["path"]).read_bytes()
        assert "sha256:" + hashlib.sha256(payload).hexdigest() == binding["digest"]
