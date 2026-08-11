import json
import subprocess
from pathlib import Path

import pytest

from tcfactory.gates import PrivateGateError, run_private_gate
from tcfactory.models import FactoryConfig, PrivateGate, TaskPacket
from tcfactory.pipeline import (
    PipelineFailure,
    _run_private_release_gate,  # pyright: ignore[reportPrivateUsage]
)
from tcfactory.yamlutil import load_yaml


def test_required_private_gate_needs_suite() -> None:
    with pytest.raises(ValueError):
        PrivateGate(required=True)


def test_private_gate_runner_must_be_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = repo / "runner.sh"
    runner.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    runner.chmod(0o700)
    with pytest.raises(PrivateGateError):
        run_private_gate(
            runner=runner,
            suite="hidden",
            cwd=repo,
            repo_root=repo,
            artifact_dir=tmp_path / "artifacts",
            timeout_seconds=30,
            task_id="T999",
            run_id="run",
            candidate_sha="abc",
        )


def test_external_private_gate_receives_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "private"
    outside.mkdir()
    runner = outside / "runner.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'test "$1" = trust-core\n'
        'test "$2" = "$TCF_CANDIDATE_WORKTREE"\n'
        'test "$TCF_TASK_ID" = T999\n'
        'test "$TCF_RUN_ID" = run-1\n'
        'test "$TCF_CANDIDATE_SHA" = deadbeef\n',
        encoding="utf-8",
    )
    runner.chmod(0o700)
    result = run_private_gate(
        runner=runner,
        suite="trust-core",
        cwd=repo,
        repo_root=repo,
        artifact_dir=tmp_path / "artifacts",
        timeout_seconds=30,
        task_id="T999",
        run_id="run-1",
        candidate_sha="deadbeef",
    )
    assert result.passed


def _private_release_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> tuple[Path, FactoryConfig, TaskPacket, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "README.md").write_text("baseline\n", encoding="utf-8")
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
            "baseline",
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
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
    candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    private = tmp_path / "private"
    private.mkdir()
    runner = private / "run.sh"
    runner.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{mutation}\n",
        encoding="utf-8",
    )
    runner.chmod(0o700)
    monkeypatch.setenv("TCF_PRIVATE_GATE_RUNNER", str(runner))
    task_payload = load_yaml(Path(__file__).resolve().parents[1] / "tasks/DEMO-001.yaml")
    task_payload["private_gate"] = {
        "required": True,
        "suite": "mutation-check",
        "timeout_seconds": 30,
    }
    task = TaskPacket.model_validate(task_payload)
    return repo, FactoryConfig(auth_mode="unrestricted"), task, candidate_sha


@pytest.mark.parametrize(
    ("mutation", "expected_path"),
    [
        ('printf "mutated\\n" > "$2/README.md"', "README.md"),
        ('printf "created\\n" > "$2/private-gate-created.txt"', "private-gate-created.txt"),
    ],
)
def test_task_private_gate_cannot_certify_a_mutated_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_path: str,
) -> None:
    repo, config, task, candidate_sha = _private_release_fixture(
        tmp_path, monkeypatch, mutation
    )

    with pytest.raises(PipelineFailure, match="modified the candidate worktree"):
        _run_private_release_gate(
            repo_root=repo,
            config=config,
            task=task,
            candidate_sha=candidate_sha,
            run_id="private-mutation-test",
        )

    result_path = (
        repo
        / "factory/artifacts/DEMO-001/private-mutation-test/private-gate/"
        "private-gate-result.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["candidate_sha"] == candidate_sha
    assert payload["runner_sha256"] and len(payload["runner_sha256"]) == 64
    assert expected_path in payload["candidate_mutations"]


def test_task_private_gate_cannot_certify_a_reset_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config, task, candidate_sha = _private_release_fixture(
        tmp_path,
        monkeypatch,
        'git -C "$2" reset --hard HEAD^',
    )

    with pytest.raises(PipelineFailure, match="changed the candidate worktree HEAD"):
        _run_private_release_gate(
            repo_root=repo,
            config=config,
            task=task,
            candidate_sha=candidate_sha,
            run_id="private-reset-test",
        )

    result_path = (
        repo
        / "factory/artifacts/DEMO-001/private-reset-test/private-gate/"
        "private-gate-result.json"
    )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["observed_head_before"] == candidate_sha
    assert payload["observed_head_after"] != candidate_sha
    assert payload["candidate_mutations"] == []
