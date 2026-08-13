"""Isolated dispatcher for digest-pinned root-owned canary mechanisms."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    CanaryStatus,
    MandatoryCanaryId,
    MandatoryCanaryResult,
    MechanismOutcome,
    RunnerPolicy,
)

POLICY_PATH = Path("/etc/traincapsule-canary-runner/policy.json")
MAX_OUTPUT = 65_536


def sha256_digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def distribution_digest() -> str:
    """Bind all imported runner implementation bytes, not only console-script stubs."""

    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    sources = sorted(path for path in root.rglob("*.py") if path.is_file())
    if not sources:
        raise ValueError("canary runner distribution has no implementation sources")
    for path in sources:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def _write_evidence(root: Path, name: str, payload: bytes) -> str:
    root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=root_descriptor,
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    return sha256_digest(payload)


def _regular(path: Path, *, executable: bool = False) -> os.stat_result:
    observed = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
        raise ValueError(f"untrusted regular file: {path}")
    if observed.st_uid != 0 or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"file is not root-owned and immutable: {path}")
    if executable and not observed.st_mode & stat.S_IXUSR:
        raise ValueError(f"mechanism is not root executable: {path}")
    return observed


def _directory(path: Path) -> os.stat_result:
    observed = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        raise ValueError(f"untrusted directory: {path}")
    if observed.st_uid != os.geteuid() or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"directory has unsafe ownership or mode: {path}")
    return observed


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=False, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise ValueError("disposable repository identity is unavailable")
    return result.stdout.strip()


def validate_disposable_roots(repo: Path, runtime: Path, artifacts: Path) -> None:
    identities: list[tuple[int, int]] = []
    for root in (repo, runtime, artifacts):
        observed = _directory(root)
        identities.append((observed.st_dev, observed.st_ino))
    if len(set(identities)) != 3:
        raise ValueError("canary roots must be distinct")
    if repo.name != "isolated-repo" or runtime.name != "isolated-runtime":
        raise ValueError("canary repository/runtime must use the isolated orchestrator layout")
    if artifacts.parent != repo.parent:
        raise ValueError("canary artifacts must remain beneath the isolated run result root")
    common = Path(os.path.commonpath([repo, runtime, artifacts]))
    if common in {Path("/"), Path("/home"), Path("/var"), Path("/tmp")}:
        raise ValueError("canary roots do not share a bounded disposable parent")
    if not (runtime / "STOP").is_file() or (runtime / "STOP").is_symlink():
        raise ValueError("disposable runtime lacks immutable STOP control")


def _load_policy(path: Path, runner_executable: Path) -> RunnerPolicy:
    _regular(path)
    policy = RunnerPolicy.model_validate_json(path.read_bytes(), strict=True)
    _regular(runner_executable, executable=True)
    if sha256_digest(runner_executable.read_bytes()) != policy.runner_executable_digest:
        raise ValueError("runner executable digest differs from root policy")
    if distribution_digest() != policy.distribution_digest:
        raise ValueError("runner implementation distribution differs from root policy")
    return policy


def _evidence(outcome: MechanismOutcome, artifact_root: Path) -> dict[str, str]:
    verified: dict[str, str] = {}
    for relative, expected in outcome.evidence_artifacts.items():
        if relative.startswith("/") or any(part in {"", ".", ".."} for part in relative.split("/")):
            raise ValueError("mechanism evidence path escaped its root")
        path = artifact_root / relative
        observed = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ValueError("mechanism evidence is not a single-link regular file")
        digest = sha256_digest(path.read_bytes())
        if digest != expected:
            raise ValueError("mechanism evidence digest mismatch")
        verified[relative] = digest
    if outcome.status is CanaryStatus.PASS and not verified:
        raise ValueError("mechanism cannot PASS without evidence")
    return verified


def execute(
    *,
    canary_id: MandatoryCanaryId,
    run_id: str,
    repo: Path,
    runtime: Path,
    artifacts: Path,
    main_sha: str,
    tree_sha: str,
    runner_executable: Path,
    policy_path: Path = POLICY_PATH,
) -> MandatoryCanaryResult:
    started = datetime.now(UTC)
    runner_digest: str | None = None
    try:
        repo, runtime, artifacts = (
            item.resolve(strict=True) for item in (repo, runtime, artifacts)
        )
        validate_disposable_roots(repo, runtime, artifacts)
        if artifacts.name != canary_id.value:
            raise ValueError("canary artifact root does not match the requested canary")
        if _git(repo, "rev-parse", "HEAD") != main_sha:
            raise ValueError("disposable repository SHA mismatch")
        if _git(repo, "rev-parse", f"{main_sha}^{{tree}}") != tree_sha:
            raise ValueError("disposable repository tree mismatch")
        runner_digest = sha256_digest(runner_executable.read_bytes())
        policy = _load_policy(policy_path, runner_executable)
        mechanism = policy.mechanisms[canary_id]
        executable = Path(mechanism.executable)
        _regular(executable, executable=True)
        if sha256_digest(executable.read_bytes()) != mechanism.executable_digest:
            raise ValueError("mechanism executable digest mismatch")
        command = [
            str(executable),
            "probe",
            "--canary",
            canary_id.value,
            "--run-id",
            run_id,
            "--repo",
            str(repo),
            "--runtime-root",
            str(runtime),
            "--artifact-root",
            str(artifacts),
            "--main-sha",
            main_sha,
            "--tree-sha",
            tree_sha,
        ]
        if not mechanism.network_allowed:
            unshare = Path("/usr/bin/unshare")
            _regular(unshare, executable=True)
            command = [str(unshare), "--net", "--", *command]
        result = subprocess.run(
            command,
            cwd=artifacts,
            check=False,
            capture_output=True,
            timeout=mechanism.timeout_seconds,
            env={
                "HOME": str(artifacts),
                "LANG": "C.UTF-8",
                "PATH": "/usr/bin:/bin",
                "TCF_RUNTIME_ROOT": str(runtime),
            },
        )
        if len(result.stdout) > MAX_OUTPUT or len(result.stderr) > MAX_OUTPUT:
            raise ValueError("mechanism output exceeded bound")
        if result.returncode not in {0, 2, 3}:
            raise ValueError(f"mechanism exited unexpectedly: {result.returncode}")
        outcome = MechanismOutcome.model_validate_json(result.stdout, strict=True)
        if (
            outcome.canary_id is not canary_id
            or outcome.run_id != run_id
            or outcome.exact_main_sha != main_sha
            or outcome.exact_tree_sha != tree_sha
        ):
            raise ValueError("mechanism outcome identity mismatch")
        expected_code = {
            CanaryStatus.PASS: 0,
            CanaryStatus.BLOCKED_PREREQUISITE: 2,
            CanaryStatus.FAIL: 3,
        }[outcome.status]
        if result.returncode != expected_code:
            raise ValueError("mechanism status/exit mismatch")
        evidence = _evidence(outcome, artifacts)
        observation = json.dumps(
            {
                "canaryId": canary_id.value,
                "mechanismDigest": mechanism.executable_digest,
                "runnerDistributionDigest": policy.distribution_digest,
                "networkAllowed": mechanism.network_allowed,
                "returnCode": result.returncode,
                "stderrDigest": sha256_digest(result.stderr),
                "stdoutDigest": sha256_digest(result.stdout),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode() + b"\n"
        evidence["runner-observation.json"] = _write_evidence(
            artifacts, "runner-observation.json", observation
        )
        return MandatoryCanaryResult(
            schema_version="3.1",
            run_id=run_id,
            canary_id=canary_id,
            exact_main_sha=main_sha,
            exact_tree_sha=tree_sha,
            runner_digest=runner_digest,
            status=outcome.status,
            evidence_artifacts=evidence,
            started_at=started,
            completed_at=datetime.now(UTC),
            failure_reason=outcome.failure_reason,
        )
    except (KeyError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        evidence: dict[str, str] = {}
        try:
            if artifacts.is_dir() and not artifacts.is_symlink():
                diagnostic = json.dumps(
                    {"canaryId": canary_id.value, "blockedReason": str(exc)[:1000]},
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode() + b"\n"
                evidence["runner-blocked.json"] = _write_evidence(
                    artifacts, "runner-blocked.json", diagnostic
                )
        except OSError:
            evidence = {}
        return MandatoryCanaryResult(
            schema_version="3.1",
            run_id=run_id,
            canary_id=canary_id,
            exact_main_sha=main_sha,
            exact_tree_sha=tree_sha,
            runner_digest=runner_digest,
            status=CanaryStatus.BLOCKED_PREREQUISITE,
            evidence_artifacts=evidence,
            started_at=started,
            completed_at=datetime.now(UTC),
            failure_reason=f"trusted canary mechanism unavailable: {exc}"[:2000],
        )
