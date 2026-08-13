"""Typed, exact-tree mandatory autonomy canary orchestration.

The repository orchestrator never declares a live canary successful itself.  A
separately installed, root-owned runner must return one strict result for each
required canary and materialize every cited evidence byte beneath the bounded
run directory.  In the absence of that runner the orchestrator writes an
explicit BLOCKED_PREREQUISITE suite, never a synthetic PASS.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field, model_validator

from ..gitops import current_sha
from ..util import (
    atomic_write_bytes,
    resolve_within,
    run_command,
    sanitized_subprocess_env,
    sha256_file,
)
from .base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .publication import PublicationError, trusted_external_path
from .source_authority import validate_active_source_generation

CANARY_PUBLICATION_REMOTE = "https://github.com/TasfiqJ/TrainCapsule-Canary.git"


class MandatoryCanaryId(StrEnum):
    REAL_CLAUDE_MECHANICAL_TASK = "real_claude_mechanical_task"
    PROCESS_KILL_AND_RESUME = "process_kill_and_resume"
    QUOTA_PAUSE_AND_RESUME = "quota_pause_and_resume"
    AUTHENTICATION_EXPIRY_AND_RECOVERY = "authentication_expiry_and_recovery"
    REPEATED_FINDING_FINITE_STOP = "repeated_finding_finite_stop"
    EXTERNAL_WAIT_LANE_ISOLATION = "external_wait_lane_isolation"
    BAD_CANDIDATE_REJECTED_BEFORE_MAIN = "bad_candidate_rejected_before_main"
    RELEASE_TRANSACTION_CRASH_IDEMPOTENCY = "release_transaction_crash_idempotency"
    AUTOMATIC_MILESTONE_ADVANCEMENT = "automatic_milestone_advancement"
    MACHINE_RECEIPT_MISSING_INVALID_EXPIRED_REVOKED = (
        "machine_receipt_missing_invalid_expired_revoked"
    )
    DUPLICATE_CONTROLLER_REJECTION = "duplicate_controller_rejection"
    LEASE_RENEWAL_FAILURE = "lease_renewal_failure"
    STALE_CURRENT_FACTS = "stale_current_facts"
    MISSING_SOURCE_AUTHORITY = "missing_source_authority"
    MALFORMED_REPORT = "malformed_report"
    PRIVATE_GATE_MISSING_FOR_TRUST_RISK = "private_gate_missing_for_trust_risk"
    MACHINE_VERIFIER_UNAVAILABLE = "machine_verifier_unavailable"
    ACTIVATION_RECEIPT_WRONG_SHA = "activation_receipt_wrong_sha"
    RUNTIME_ROOT_OUTSIDE_REPO = "runtime_root_outside_repo"
    POST_MERGE_INVARIANT_FAILURE_AND_AUTOMATED_REVERT_PR = (
        "post_merge_invariant_failure_and_automated_revert_pr"
    )


class PostActivationObservationId(StrEnum):
    COMPLETE_AUTONOMOUS_CYCLE = "complete_autonomous_cycle"
    IDLE_CYCLE = "idle_cycle"
    EXTERNAL_WAIT_ISOLATED_CYCLE = "external_wait_isolated_cycle"
    SERVICE_RESTART = "service_restart"
    NEXT_WORK_SCHEDULING = "next_work_scheduling"
    NO_DIRECT_MAIN_PUSH = "no_direct_main_push"
    NO_HUMAN_CLICK = "no_human_click"


class CanaryStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED_PREREQUISITE = "BLOCKED_PREREQUISITE"


class MandatoryCanaryResult(V3Model):
    schema_version: Literal["3.1"]
    run_id: str = Field(pattern=r"^CANARY-[A-Z0-9_-]{8,160}$")
    canary_id: MandatoryCanaryId
    exact_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    exact_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    runner_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    status: CanaryStatus
    evidence_artifacts: dict[str, str] = Field(default_factory=dict, max_length=128)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    failure_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_result(self) -> MandatoryCanaryResult:
        if self.completed_at < self.started_at:
            raise ValueError("canary completion precedes its start")
        if self.status is CanaryStatus.PASS:
            if self.runner_digest is None or not self.evidence_artifacts:
                raise ValueError("passing canary requires runner and evidence digests")
            if self.failure_reason is not None:
                raise ValueError("passing canary cannot carry a failure reason")
        elif not self.failure_reason:
            raise ValueError("non-passing canary requires a bounded failure reason")
        if len(self.evidence_artifacts) != len(set(self.evidence_artifacts)):
            raise ValueError("canary evidence paths must be unique")
        return self


class MandatoryCanarySuite(V3Model):
    schema_version: Literal["3.1"]
    run_id: str = Field(pattern=r"^CANARY-[A-Z0-9_-]{8,160}$")
    exact_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    exact_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    source_generation_id: str = Field(min_length=1, max_length=128)
    source_generation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    factory_config_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    controller_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    status: CanaryStatus
    result_artifacts: dict[MandatoryCanaryId, str]
    result_digests: dict[MandatoryCanaryId, str]
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_suite(self) -> MandatoryCanarySuite:
        expected = set(MandatoryCanaryId)
        if set(self.result_artifacts) != expected or set(self.result_digests) != expected:
            raise ValueError("canary suite must bind exactly the mandatory canary roster")
        if self.completed_at < self.started_at:
            raise ValueError("canary suite completion precedes its start")
        return self


class PostActivationObservation(V3Model):
    """Durable external observation of the exact required live autonomy sequence."""

    schema_version: Literal["3.1"]
    observation_id: str = Field(pattern=r"^OBS-[A-Z0-9_-]{8,160}$")
    activation_receipt_id: str = Field(min_length=3, max_length=128)
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    exact_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    exact_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    evidence_artifacts: dict[PostActivationObservationId, str]
    evidence_digests: dict[PostActivationObservationId, str]
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_observation(self) -> PostActivationObservation:
        expected = set(PostActivationObservationId)
        if set(self.evidence_artifacts) != expected or set(self.evidence_digests) != expected:
            raise ValueError("post-activation observation must bind the exact mandatory roster")
        if self.completed_at < self.started_at:
            raise ValueError("post-activation observation completion precedes its start")
        return self


def verify_post_activation_observation(
    observation_path: Path,
    *,
    repo_root: Path,
    activation_receipt_id: str,
    activation_receipt_digest: str,
) -> PostActivationObservation:
    observation = PostActivationObservation.model_validate_json(
        observation_path.read_bytes(), strict=True
    )
    main_sha = current_sha(repo_root)
    tree_sha = _git_tree(repo_root, main_sha)
    if (
        observation.activation_receipt_id != activation_receipt_id
        or observation.activation_receipt_digest != activation_receipt_digest
        or observation.exact_main_sha != main_sha
        or observation.exact_tree_sha != tree_sha
    ):
        raise RuntimeError("post-activation observation authority/exact-tree mismatch")
    root = observation_path.parent.resolve(strict=True)
    for observation_id in PostActivationObservationId:
        evidence = resolve_within(
            root, observation.evidence_artifacts[observation_id], require_exists=True
        )
        if evidence.is_symlink() or not evidence.is_file() or evidence.stat().st_nlink != 1:
            raise RuntimeError("post-activation evidence must be a single-link regular file")
        if f"sha256:{sha256_file(evidence)}" != observation.evidence_digests[observation_id]:
            raise RuntimeError(
                f"post-activation evidence digest mismatch: {observation_id.value}"
            )
    return observation


class CanaryRunner(Protocol):
    runner_digest: str

    def run(
        self,
        *,
        canary_id: MandatoryCanaryId,
        run_id: str,
        repo_root: Path,
        runtime_root: Path,
        artifact_root: Path,
        exact_main_sha: str,
        exact_tree_sha: str,
    ) -> MandatoryCanaryResult: ...


class ExternalCanaryRunner:
    """Narrow adapter for one separately installed root-owned canary runner."""

    def __init__(self, executable: Path) -> None:
        self.executable, observed = trusted_external_path(
            executable, directory=False, label="mandatory canary runner"
        )
        self._identity = (observed.st_dev, observed.st_ino)
        self.runner_digest = f"sha256:{sha256_file(self.executable)}"

    def run(
        self,
        *,
        canary_id: MandatoryCanaryId,
        run_id: str,
        repo_root: Path,
        runtime_root: Path,
        artifact_root: Path,
        exact_main_sha: str,
        exact_tree_sha: str,
    ) -> MandatoryCanaryResult:
        observed = self.executable.lstat()
        if (observed.st_dev, observed.st_ino) != self._identity:
            raise RuntimeError("mandatory canary runner identity changed")
        result = run_command(
            [
                str(self.executable),
                "run",
                "--canary",
                canary_id.value,
                "--run-id",
                run_id,
                "--repo",
                str(repo_root),
                "--artifact-root",
                str(artifact_root),
                "--runtime-root",
                str(runtime_root),
                "--main-sha",
                exact_main_sha,
                "--tree-sha",
                exact_tree_sha,
            ],
            cwd=self.executable.parent,
            check=False,
            timeout=14_400,
            env=sanitized_subprocess_env({"TCF_RUNTIME_ROOT": str(runtime_root)}),
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"external canary runner rejected {canary_id.value} with exit {result.returncode}"
            )
        if len(result.stdout.encode("utf-8")) > 65_536:
            raise RuntimeError("external canary runner output exceeded its bound")
        try:
            parsed: object = json.loads(result.stdout)
            observed_result = MandatoryCanaryResult.model_validate(parsed, strict=True)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("external canary runner returned an invalid result") from exc
        if observed_result.runner_digest != self.runner_digest:
            raise RuntimeError("external canary result runner digest mismatch")
        return observed_result


def _git_tree(repo_root: Path, sha: str) -> str:
    return current_sha(repo_root, f"{sha}^{{tree}}")


def _active_tree_is_exact(repo_root: Path) -> None:
    tracked = run_command(["git", "diff", "--quiet", "HEAD"], cwd=repo_root, check=False)
    if tracked.returncode != 0:
        raise RuntimeError("mandatory canaries require tracked bytes to match exact HEAD")
    active_roots = [
        ".github",
        "config",
        "docs",
        "packages",
        "prompts",
        "schemas",
        "scripts",
        "tcfactory",
        "tests",
        "verifier",
        "README.md",
        "SOURCE_PRECEDENCE.md",
    ]
    untracked = run_command(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *active_roots],
        cwd=repo_root,
        check=False,
    )
    if untracked.returncode != 0 or untracked.stdout.strip():
        raise RuntimeError("mandatory canaries reject untracked active implementation bytes")


def _prepare_isolated_canary_repo(
    *,
    repo_root: Path,
    run_root: Path,
    exact_main_sha: str,
    exact_tree_sha: str,
    publication_remote: str | None = None,
) -> tuple[Path, Path]:
    """Clone exact local bytes into a disposable repo/runtime without touching live state."""

    isolated_repo = run_root / "isolated-repo"
    isolated_runtime = run_root / "isolated-runtime"
    if publication_remote is not None and publication_remote != CANARY_PUBLICATION_REMOTE:
        raise RuntimeError("mandatory live canary publication remote is not trusted")
    origin = publication_remote or run_command(
        ["git", "remote", "get-url", "origin"], cwd=repo_root, check=False
    ).stdout.strip()
    if not origin:
        raise RuntimeError("mandatory live canaries require an explicit publication remote")
    bundle_path = run_root / "isolated-repository.bundle"
    bundled = run_command(
        ["git", "bundle", "create", str(bundle_path), "HEAD"],
        cwd=repo_root,
        check=False,
        timeout=300,
    )
    if bundled.returncode != 0:
        raise RuntimeError("disposable canary repository bundle failed")
    cloned = run_command(
        [
            "git",
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(bundle_path),
            str(isolated_repo),
        ],
        cwd=run_root,
        check=False,
        timeout=300,
    )
    if cloned.returncode != 0:
        raise RuntimeError("disposable canary repository clone failed")
    bundle_path.unlink()
    run_command(["git", "checkout", "--detach", exact_main_sha], cwd=isolated_repo)
    run_command(["git", "remote", "set-url", "origin", origin], cwd=isolated_repo)
    if (
        current_sha(isolated_repo) != exact_main_sha
        or _git_tree(isolated_repo, exact_main_sha) != exact_tree_sha
    ):
        raise RuntimeError("disposable canary repository exact-tree verification failed")
    isolated_runtime.mkdir(parents=True, exist_ok=False)
    (isolated_runtime / "STOP").write_text("isolated canary hold\n", encoding="utf-8")
    return isolated_repo, isolated_runtime


def _verify_evidence(result: MandatoryCanaryResult, canary_root: Path) -> None:
    for relative, expected in result.evidence_artifacts.items():
        path = resolve_within(canary_root, relative, require_exists=True)
        observed = path.lstat()
        if path.is_symlink() or not path.is_file() or observed.st_nlink != 1:
            raise RuntimeError("canary evidence must be a single-link regular file")
        if f"sha256:{sha256_file(path)}" != expected:
            raise RuntimeError(f"canary evidence digest mismatch: {relative}")


def verify_mandatory_canary_suite(
    suite_path: Path,
    *,
    repo_root: Path,
    require_pass: bool = True,
) -> MandatoryCanarySuite:
    """Reopen every result/evidence byte and bind it to current exact HEAD/tree."""

    raw = suite_path.read_bytes()
    suite = MandatoryCanarySuite.model_validate_json(raw, strict=True)
    main_sha = current_sha(repo_root)
    tree_sha = _git_tree(repo_root, main_sha)
    if suite.exact_main_sha != main_sha or suite.exact_tree_sha != tree_sha:
        raise RuntimeError("mandatory canary suite is stale for current exact HEAD/tree")
    active = validate_active_source_generation(repo_root)
    expected_bindings = {
        "source generation": (suite.source_generation_id, active.generation_id),
        "source digest": (suite.source_generation_digest, f"sha256:{active.manifest_digest}"),
        "factory config": (
            suite.factory_config_digest,
            f"sha256:{sha256_file(repo_root / 'config/factory.yaml')}",
        ),
        "controller": (
            suite.controller_digest,
            f"sha256:{sha256_file(repo_root / 'tcfactory/v3/controller.py')}",
        ),
    }
    for label, (observed, expected) in expected_bindings.items():
        if observed != expected:
            raise RuntimeError(f"mandatory canary suite {label} mismatch")
    observed_statuses: list[CanaryStatus] = []
    suite_root = suite_path.parent.resolve(strict=True)
    for canary_id in MandatoryCanaryId:
        result_path = resolve_within(
            suite_root, suite.result_artifacts[canary_id], require_exists=True
        )
        result_bytes = result_path.read_bytes()
        if sha256_digest(result_bytes) != suite.result_digests[canary_id]:
            raise RuntimeError(f"mandatory canary result substitution: {canary_id.value}")
        result = MandatoryCanaryResult.model_validate_json(result_bytes, strict=True)
        if (
            result.canary_id is not canary_id
            or result.run_id != suite.run_id
            or result.exact_main_sha != main_sha
            or result.exact_tree_sha != tree_sha
        ):
            raise RuntimeError(f"mandatory canary result binding mismatch: {canary_id.value}")
        _verify_evidence(result, result_path.parent)
        observed_statuses.append(result.status)
    expected_status = (
        CanaryStatus.PASS
        if all(status is CanaryStatus.PASS for status in observed_statuses)
        else CanaryStatus.BLOCKED_PREREQUISITE
        if all(status is CanaryStatus.BLOCKED_PREREQUISITE for status in observed_statuses)
        else CanaryStatus.FAIL
    )
    if suite.status is not expected_status:
        raise RuntimeError("mandatory canary suite status is self-inconsistent")
    if require_pass and suite.status is not CanaryStatus.PASS:
        raise RuntimeError("all mandatory live canaries have not passed")
    return suite


def _blocked_result(
    *,
    canary_id: MandatoryCanaryId,
    run_id: str,
    main_sha: str,
    tree_sha: str,
    now: datetime,
    reason: str,
) -> MandatoryCanaryResult:
    return MandatoryCanaryResult(
        schema_version="3.1",
        run_id=run_id,
        canary_id=canary_id,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        status=CanaryStatus.BLOCKED_PREREQUISITE,
        started_at=now,
        completed_at=now,
        failure_reason=reason[:2000],
    )


def run_mandatory_canaries(
    *,
    repo_root: Path,
    result_root: Path,
    runner_executable: Path = Path("/usr/local/bin/traincapsule-v31-run-canary"),
    runner_factory: Callable[[Path], CanaryRunner] = ExternalCanaryRunner,
    publication_remote: str | None = None,
    now: datetime | None = None,
) -> Path:
    """Run the exact mandatory roster or emit a typed blocked suite."""

    repo_root = repo_root.resolve()
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    main_sha = current_sha(repo_root)
    tree_sha = _git_tree(repo_root, main_sha)
    run_id = f"CANARY-{observed_now.strftime('%Y%m%dT%H%M%SZ')}-{main_sha[:12]}".upper()
    run_root = result_root / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    active = validate_active_source_generation(repo_root)
    runner: CanaryRunner | None
    runner_error: str | None = None
    try:
        _active_tree_is_exact(repo_root)
        runner = runner_factory(runner_executable)
    except (OSError, RuntimeError, PublicationError, ValueError) as exc:
        runner = None
        runner_error = f"live canary prerequisite unavailable: {exc}"

    isolated_repo: Path | None = None
    isolated_runtime: Path | None = None
    if runner is not None:
        try:
            isolated_repo, isolated_runtime = _prepare_isolated_canary_repo(
                repo_root=repo_root,
                run_root=run_root,
                exact_main_sha=main_sha,
                exact_tree_sha=tree_sha,
                publication_remote=publication_remote,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            runner = None
            runner_error = f"disposable canary environment unavailable: {exc}"

    results: list[MandatoryCanaryResult] = []
    for canary_id in MandatoryCanaryId:
        canary_root = run_root / canary_id.value
        canary_root.mkdir(parents=True, exist_ok=False)
        started = datetime.now(UTC)
        if runner is None:
            result = _blocked_result(
                canary_id=canary_id,
                run_id=run_id,
                main_sha=main_sha,
                tree_sha=tree_sha,
                now=started,
                reason=runner_error or "mandatory canary runner is unavailable",
            )
        elif isolated_repo is not None and isolated_runtime is not None:
            try:
                result = runner.run(
                    canary_id=canary_id,
                    run_id=run_id,
                    repo_root=isolated_repo,
                    runtime_root=isolated_runtime,
                    artifact_root=canary_root,
                    exact_main_sha=main_sha,
                    exact_tree_sha=tree_sha,
                )
                if (
                    result.canary_id is not canary_id
                    or result.run_id != run_id
                    or result.exact_main_sha != main_sha
                    or result.exact_tree_sha != tree_sha
                ):
                    raise RuntimeError("external canary result exact binding mismatch")
                _verify_evidence(result, canary_root)
            except (OSError, RuntimeError, ValueError) as exc:
                result = MandatoryCanaryResult(
                    schema_version="3.1",
                    run_id=run_id,
                    canary_id=canary_id,
                    exact_main_sha=main_sha,
                    exact_tree_sha=tree_sha,
                    runner_digest=runner.runner_digest,
                    status=CanaryStatus.FAIL,
                    started_at=started,
                    completed_at=datetime.now(UTC),
                    failure_reason=f"mandatory canary failed closed: {exc}"[:2000],
                )
        else:
            result = _blocked_result(
                canary_id=canary_id,
                run_id=run_id,
                main_sha=main_sha,
                tree_sha=tree_sha,
                now=started,
                reason="disposable canary environment was not established",
            )
        result_path = canary_root / "result.json"
        atomic_write_bytes(result_path, result.canonical_json_bytes())
        results.append(result)

    statuses = [result.status for result in results]
    suite_status = (
        CanaryStatus.PASS
        if all(status is CanaryStatus.PASS for status in statuses)
        else CanaryStatus.BLOCKED_PREREQUISITE
        if all(status is CanaryStatus.BLOCKED_PREREQUISITE for status in statuses)
        else CanaryStatus.FAIL
    )
    suite = MandatoryCanarySuite(
        schema_version="3.1",
        run_id=run_id,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        source_generation_id=active.generation_id,
        source_generation_digest=f"sha256:{active.manifest_digest}",
        factory_config_digest=f"sha256:{sha256_file(repo_root / 'config/factory.yaml')}",
        controller_digest=f"sha256:{sha256_file(repo_root / 'tcfactory/v3/controller.py')}",
        status=suite_status,
        result_artifacts={
            result.canary_id: f"{result.canary_id.value}/result.json" for result in results
        },
        result_digests={
            result.canary_id: sha256_digest(result.canonical_json_bytes()) for result in results
        },
        started_at=observed_now,
        completed_at=datetime.now(UTC),
    )
    suite_path = run_root / "suite.json"
    atomic_write_bytes(suite_path, suite.canonical_json_bytes())
    verify_mandatory_canary_suite(suite_path, repo_root=repo_root, require_pass=False)
    return suite_path


CANARY_CONTRACTS: dict[str, type[V3Model]] = {
    "mandatory-canary-result": MandatoryCanaryResult,
    "mandatory-canary-suite": MandatoryCanarySuite,
    "post-activation-observation": PostActivationObservation,
}
