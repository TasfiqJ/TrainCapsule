from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tcfactory.backends.fake import FakeBackend
from tcfactory.checkpoints import CheckpointBudget, V3Checkpoint
from tcfactory.v3.controller import V3Controller
from tcfactory.v3.enums import Lane

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "sha256:" + "0" * 64


class _DisabledPublisher:
    def prepare_candidate(self, **_: object) -> dict[str, Path]:
        raise AssertionError("salvage must not prepare a publication")

    def publish(self, **_: object) -> dict[str, object]:
        raise AssertionError("salvage must not publish")


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    shutil.copy2(ROOT / "config/factory.yaml", repo / "config/factory.yaml")
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "candidate"], cwd=repo, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, sha


def _checkpoint(candidate_sha: str) -> V3Checkpoint:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
    return V3Checkpoint(
        generation=2,
        work_item_id="V3-MIG-001",
        lane=Lane.FACTORY,
        milestone="M0_FACTORY_MIGRATED",
        budget=CheckpointBudget(
            max_turns=8,
            max_wall_time_seconds=120,
            plan_attempts_remaining=1,
            repair_cycles_remaining=1,
            restarts_remaining=1,
        ),
        context_digest=DIGEST,
        source_digest=DIGEST,
        candidate_sha=candidate_sha,
        approval_state="MACHINE_POLICY_REQUIRED",
        active=False,
        created_at=now,
        updated_at=now,
    )


def test_candidate_salvage_is_bounded_content_addressed_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, sha = _repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_DisabledPublisher(),
    )
    controller.checkpoints.save_v3(_checkpoint(sha))

    receipt = controller.salvage_candidate("V3-MIG-001", Path("operator-copy"))
    assert receipt == controller.salvage_candidate("V3-MIG-001", Path("operator-copy"))
    assert receipt.parent == repo / "factory/state/candidate-salvage/operator-copy"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["candidateSha"] == sha
    assert payload["automaticResume"] is False
    assert payload["evidenceAuthority"] == "LOCAL_RECOVERY_ONLY"

    with pytest.raises(ValueError, match="escapes"):
        controller.salvage_candidate("V3-MIG-001", tmp_path / "outside")


def test_candidate_salvage_rejects_missing_checkpoint_and_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _ = _repo(tmp_path)
    monkeypatch.delenv("TCF_RUNTIME_ROOT", raising=False)
    controller = V3Controller(
        repo_root=repo,
        backend=FakeBackend(),
        publisher=_DisabledPublisher(),
    )
    with pytest.raises(ValueError, match="no V3 checkpoint"):
        controller.salvage_candidate("V3-MIG-999", Path("missing"))
    controller.checkpoints.save_v3(_checkpoint("f" * 40))
    with pytest.raises(ValueError, match="not locally recoverable"):
        controller.salvage_candidate("V3-MIG-001", Path("missing-candidate"))
