from pathlib import Path

import pytest

from tcfactory.gates import PrivateGateError, run_private_gate
from tcfactory.models import PrivateGate


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
