from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from traincapsule_canary_runner import external_probes, mechanisms
from traincapsule_canary_runner.external_probes import run_probe
from traincapsule_canary_runner.mechanisms import EXTERNAL, LOCAL
from traincapsule_canary_runner.models import MandatoryCanaryId, RunnerPolicy
from traincapsule_canary_runner.runner import (
    distribution_digest,
    execute,
    sha256_digest,
    validate_disposable_roots,
)

SHA = "a" * 40
TREE = "b" * 40
RUN = "CANARY-20260812T180000Z-AAAAAAAAAAAA"


def _roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    parent = tmp_path / "run"
    repo, runtime, artifacts = (
        parent / "isolated-repo",
        parent / "isolated-runtime",
        parent / MandatoryCanaryId.MALFORMED_REPORT.value,
    )
    for root in (repo, runtime, artifacts):
        root.mkdir(parents=True, mode=0o700)
    (runtime / "STOP").write_text("isolated\n", encoding="utf-8")
    return repo, runtime, artifacts


def test_wire_roster_matches_factory_without_importing_signer() -> None:
    from tcfactory.v3.canaries import MandatoryCanaryId as FactoryCanaryId

    assert {item.value for item in MandatoryCanaryId} == {
        item.value for item in FactoryCanaryId
    }
    assert len(MandatoryCanaryId) == 20
    implemented = set(LOCAL) | set(EXTERNAL) | {MandatoryCanaryId.RUNTIME_ROOT_OUTSIDE_REPO}
    assert implemented == set(MandatoryCanaryId)
    assert not (set(LOCAL) & set(EXTERNAL))
    assert len(LOCAL) == 17
    assert len(EXTERNAL) == 2
    source = Path(__file__).resolve().parents[1] / "src"
    assert not any(
        token in path.read_text()
        for path in source.rglob("*.py")
        for token in (
            "traincapsule_verifier.crypto",
            "traincapsule_verifier.evaluator",
            "sign_model",
            "private-key.pem",
        )
    )


def test_policy_requires_exactly_20_digest_pinned_unique_mechanisms() -> None:
    mechanism = {
        "executable": "/usr/libexec/traincapsule-canary-mechanism",
        "executableDigest": "sha256:" + "1" * 64,
        "timeoutSeconds": 30,
        "networkAllowed": False,
    }
    mechanisms: dict[str, dict[str, str | int | bool]] = {
        item.value: dict(mechanism) for item in MandatoryCanaryId
    }
    payload: dict[str, object] = {
        "schemaVersion": "3.1",
        "runnerExecutableDigest": "sha256:" + "2" * 64,
        "distributionDigest": distribution_digest(),
        "mechanisms": mechanisms,
    }
    assert len(RunnerPolicy.model_validate_json(json.dumps(payload), strict=True).mechanisms) == 20
    mechanisms.pop(MandatoryCanaryId.MALFORMED_REPORT.value)
    with pytest.raises(ValueError, match="exactly all 20"):
        RunnerPolicy.model_validate_json(json.dumps(payload), strict=True)


def test_root_validation_rejects_symlink_alias_and_live_broad_roots(tmp_path: Path) -> None:
    repo, runtime, artifacts = _roots(tmp_path)
    validate_disposable_roots(repo, runtime, artifacts)
    alias = runtime.parent / "alias"
    alias.symlink_to(artifacts, target_is_directory=True)
    with pytest.raises(ValueError, match="untrusted directory"):
        validate_disposable_roots(repo, runtime, alias)
    with pytest.raises(ValueError, match="distinct"):
        validate_disposable_roots(repo, runtime, runtime)


def test_every_missing_real_mechanism_blocks_with_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = tmp_path / "runner"
    runner.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    runner.chmod(0o700)
    def git_identity(_repo: Path, *args: str) -> str:
        return SHA if args[-1] == "HEAD" else TREE

    def regular_file(path: Path, *, executable: bool = False) -> object:
        del executable
        return path.stat()

    monkeypatch.setattr("traincapsule_canary_runner.runner._git", git_identity)
    monkeypatch.setattr("traincapsule_canary_runner.runner._regular", regular_file)
    for item in MandatoryCanaryId:
        repo, runtime, initial = _roots(tmp_path / item.value)
        if item is MandatoryCanaryId.MALFORMED_REPORT:
            artifacts = initial
        else:
            initial.rmdir()
            artifacts = runtime.parent / item.value
            artifacts.mkdir(mode=0o700)
        result = execute(
            canary_id=item,
            run_id=RUN,
            repo=repo,
            runtime=runtime,
            artifacts=artifacts,
            main_sha=SHA,
            tree_sha=TREE,
            runner_executable=runner,
            policy_path=tmp_path / "absent-policy.json",
        )
        assert result.status.value == "BLOCKED_PREREQUISITE"
        assert result.failure_reason and "unavailable" in result.failure_reason
        assert result.evidence_artifacts == {
            "runner-blocked.json": sha256_digest(
                (artifacts / "runner-blocked.json").read_bytes()
            )
        }


def test_fake_pass_without_evidence_and_wrong_status_exit_are_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, runtime, artifacts = _roots(tmp_path)
    runner = tmp_path / "runner"
    driver = tmp_path / "traincapsule-canary-driver"
    for path in (runner, driver):
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o700)
    policy_path = tmp_path / "policy.json"
    policy = {
        "schemaVersion": "3.1",
        "runnerExecutableDigest": sha256_digest(runner.read_bytes()),
        "distributionDigest": distribution_digest(),
        "mechanisms": {
            item.value: {
                "executable": "/usr/libexec/traincapsule-canary-driver",
                "executableDigest": sha256_digest(driver.read_bytes()),
                "timeoutSeconds": 30,
                "networkAllowed": False,
            }
            for item in MandatoryCanaryId
        },
    }
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    def git_identity(_repo: Path, *args: str) -> str:
        return SHA if args[-1] == "HEAD" else TREE

    monkeypatch.setattr("traincapsule_canary_runner.runner._git", git_identity)
    def regular(path: Path, *, executable: bool = False) -> object:
        del executable
        return (driver if str(path).startswith("/usr/libexec") else path).stat()

    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if str(path).startswith("/usr/libexec"):
            return original_read_bytes(driver)
        return original_read_bytes(path)

    monkeypatch.setattr("traincapsule_canary_runner.runner._regular", regular)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    outcome: dict[str, object] = {
        "schemaVersion": "3.1",
        "canaryId": MandatoryCanaryId.MALFORMED_REPORT.value,
        "runId": RUN,
        "exactMainSha": SHA,
        "exactTreeSha": TREE,
        "status": "PASS",
        "evidenceArtifacts": {},
        "failureReason": None,
        "observedAt": "2026-08-12T18:00:00Z",
    }
    completed = subprocess.CompletedProcess([], 0, json.dumps(outcome).encode(), b"")
    commands: list[list[str]] = []

    def completed_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        assert isinstance(command, list)
        commands.append(cast(list[str], command))
        del kwargs
        return completed

    monkeypatch.setattr(subprocess, "run", completed_run)
    result = execute(
        canary_id=MandatoryCanaryId.MALFORMED_REPORT,
        run_id=RUN,
        repo=repo,
        runtime=runtime,
        artifacts=artifacts,
        main_sha=SHA,
        tree_sha=TREE,
        runner_executable=runner,
        policy_path=policy_path,
    )
    assert result.status.value == "BLOCKED_PREREQUISITE"
    assert result.failure_reason and "without evidence" in result.failure_reason
    assert commands[0][:5] == [
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--net",
        "--",
    ]


def test_wheel_has_only_runner_code_and_no_signing_authority() -> None:
    project = Path(__file__).resolve().parents[1]
    import tomllib

    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    assert metadata["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/traincapsule_canary_runner"
    ]
    assert set(metadata["project"]["dependencies"]) == {"pydantic>=2.8"}
    distribution = project / "dist"
    if distribution.exists():
        for wheel in distribution.glob("*.whl"):
            with zipfile.ZipFile(wheel) as archive:
                assert all(
                    name.startswith(
                        (
                            "traincapsule_canary_runner/",
                            "traincapsule_mandatory_canary_runner-3.1.0.dist-info/",
                        )
                    )
                    for name in archive.namelist()
                )


def test_quota_and_auth_use_real_typed_backend_contract_without_repair_spend(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[2]
    for canary, disposition in (
        (MandatoryCanaryId.QUOTA_PAUSE_AND_RESUME, "QUOTA_WAIT"),
        (MandatoryCanaryId.AUTHENTICATION_EXPIRY_AND_RECOVERY, "AUTH_EXPIRED"),
    ):
        root = tmp_path / canary.value
        root.mkdir()
        evidence = mechanisms._backend_wait(repo, root, disposition)  # pyright: ignore[reportPrivateUsage]
        assert mechanisms._local_proven(canary, evidence)  # pyright: ignore[reportPrivateUsage]
        persisted = json.loads((root / "backend-wait.json").read_text())
        assert persisted["repairBudget"] == 3
        assert persisted["backendRechecks"] == 1
        assert persisted["state"] == "AUTHENTICATED"


def test_live_probes_cannot_pass_without_root_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "traincapsule_canary_runner.external_probes.POLICY_PATH",
        tmp_path / "missing-live-policy.json",
    )
    args = argparse.Namespace(
        repo=tmp_path,
        runtime_root=tmp_path,
        artifact_root=tmp_path,
        run_id=RUN,
        main_sha=SHA,
        tree_sha=TREE,
    )
    with pytest.raises(OSError):
        run_probe(MandatoryCanaryId.REAL_CLAUDE_MECHANICAL_TASK.value, args)
    with pytest.raises(OSError):
        run_probe(
            MandatoryCanaryId.POST_MERGE_INVARIANT_FAILURE_AND_AUTOMATED_REVERT_PR.value,
            args,
        )


def test_github_live_probe_forces_read_only_method_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "gh"
    executable.write_bytes(b"gh")
    token = tmp_path / "token"
    token.write_text("test-token", encoding="utf-8")
    token.chmod(0o600)
    commands: list[list[str]] = []

    def policy() -> Any:
        return SimpleNamespace(
            github=SimpleNamespace(
                executable=str(executable),
                executable_digest=sha256_digest(executable.read_bytes()),
                repository="TasfiqJ/TrainCapsule-Canary",
                token_file=str(token),
                workflow="traincapsule-post-merge-revert-canary.yml",
            )
        )

    def trust(_path: Path, _expected_digest: str) -> None:
        return None

    def run(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            1 if "workflow" in command else 0,
            "{}",
            "",
        )

    monkeypatch.setattr(external_probes, "_load_policy", policy)
    monkeypatch.setattr(external_probes, "_trusted_executable", trust)
    monkeypatch.setattr(subprocess, "run", run)
    args = argparse.Namespace(
        repo=tmp_path,
        runtime_root=tmp_path,
        artifact_root=tmp_path,
        run_id=RUN,
        main_sha=SHA,
        tree_sha=TREE,
    )
    with pytest.raises(ValueError, match="dispatch was rejected"):
        external_probes._github_revert(args)  # pyright: ignore[reportPrivateUsage]
    assert commands[0][1:5] == [
        "api",
        "repos/TasfiqJ/TrainCapsule-Canary/actions/runs",
        "--method",
        "GET",
    ]
