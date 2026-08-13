"""Stopped-state zero-human canary and activation-request supervisor."""

from __future__ import annotations

import fcntl
import json
import os
import pwd
import stat
import subprocess
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import AwareDatetime, Field, model_validator

from ..util import atomic_write_bytes, sha256_file
from .activation import (
    ActivationTransaction,
    InstalledRuntimeLoader,
    activate_v31,
    coordinate_activation_request,
    stage_activation_request,
)
from .base import DIGEST_PATTERN, V3Model
from .canaries import (
    CanaryStatus,
    MandatoryCanarySuite,
    run_mandatory_canaries,
    verify_mandatory_canary_suite,
)
from .installed_runtime import InstalledControllerRuntimeManifest
from .runtime_paths import V3RuntimePaths, resolve_v3_runtime_paths

CONTROLLER_PRINCIPAL_POLICY = Path(
    "/etc/traincapsule-verifier/controller-principal.json"
)
CONTROLLER_START_OUTBOX = Path(
    "/var/lib/traincapsule-verifier/controller-start-outbox"
)
REFRESH_COMPLETION_INBOX = Path(
    "/var/lib/traincapsule-verifier/activation-refresh-inbox"
)
ACTIVATION_POLICY_RECEIPT = Path(
    "/var/lib/traincapsule-verifier/receipts/activation-policy/current.json"
)


def _refresh_runtime_bundle(
    path: Path,
) -> tuple[InstalledControllerRuntimeManifest, bytes, bytes]:
    raw = path.read_bytes()
    manifest = InstalledControllerRuntimeManifest.model_validate_json(raw, strict=True)
    return manifest, raw, Path(manifest.effective_config.path).read_bytes()


class ControllerStartRequest(V3Model):
    schema_version: str = Field(pattern=r"^3\.1$")
    transaction_id: str = Field(pattern=r"^ACTIVATE-[A-Z0-9._:-]{3,127}$")
    transaction_path: str = Field(min_length=1, max_length=4096)
    transaction_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    transaction: ActivationTransaction
    activation_receipt_id: str = Field(min_length=3, max_length=128)
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


class RefreshCompletionV31(V3Model):
    """Exact controller-readable projection of a root-attested refresh completion."""

    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str = Field(pattern=r"^[0-9a-f]{40}-[0-9a-f]{16}$")
    handoff_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    previous_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    source_generation_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    generation_manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    runtime_manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    environment_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    effective_config_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    snapshot_manifest_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    committed_at: AwareDatetime


class RefreshActivationState(V3Model):
    schema_version: Literal["3.1"] = "3.1"
    completion_path: str
    completion_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    completion: RefreshCompletionV31
    phase: Literal[
        "RECEIVED",
        "CANARIES_PASSED",
        "REQUEST_SUBMITTED",
        "ACTIVATED",
        "START_REQUESTED",
    ]
    canary_suite_path: str | None = None
    canary_suite_digest: str | None = Field(default=None, pattern=DIGEST_PATTERN.pattern)
    activation_request_path: str | None = None
    activation_request_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    activation_transaction_path: str | None = None
    activation_transaction_digest: str | None = Field(
        default=None, pattern=DIGEST_PATTERN.pattern
    )
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def phase_evidence_is_complete(self) -> RefreshActivationState:
        phase_order = (
            "RECEIVED",
            "CANARIES_PASSED",
            "REQUEST_SUBMITTED",
            "ACTIVATED",
            "START_REQUESTED",
        )
        phase_index = phase_order.index(self.phase)
        if phase_index >= 1 and (
            self.canary_suite_path is None or self.canary_suite_digest is None
        ):
            raise ValueError("refresh activation state is missing canary evidence")
        if phase_index >= 2 and (
            self.activation_request_path is None
            or self.activation_request_digest is None
        ):
            raise ValueError("refresh activation state is missing request evidence")
        if phase_index >= 3 and (
            self.activation_transaction_path is None
            or self.activation_transaction_digest is None
        ):
            raise ValueError("refresh activation state is missing transaction evidence")
        return self


RefreshCompletionLoader = Callable[[Path], tuple[RefreshCompletionV31, bytes]]


def _load_refresh_completion(path: Path) -> tuple[RefreshCompletionV31, bytes]:
    """Read one immutable root-brokered claim through its exact access boundary."""

    controller = pwd.getpwnam("traincapsule-controller")
    parent = path.parent.stat(follow_symlinks=False)
    metadata = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != controller.pw_gid
        or stat.S_IMODE(metadata.st_mode) != 0o440
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != 0
        or parent.st_gid != controller.pw_gid
        or stat.S_IMODE(parent.st_mode) != 0o750
    ):
        raise RuntimeError("refresh completion claim boundary is invalid")
    raw = path.read_bytes()
    completion = RefreshCompletionV31.model_validate_json(raw, strict=True)
    if raw != completion.canonical_json_bytes():
        raise RuntimeError("refresh completion claim is not canonical")
    expected_name = (
        f"{completion.required_main_sha}-{completion.transaction_id}.json"
    )
    if path.name != expected_name:
        raise RuntimeError("refresh completion claim filename is not exact")
    return completion, raw


def _git_identity(repo_root: Path) -> tuple[str, str]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1"},
        )
        return completed.stdout.strip()

    main_sha = run("rev-parse", "HEAD")
    return main_sha, run("rev-parse", f"{main_sha}^{{tree}}")


def _validate_refresh_completion(
    *,
    repo_root: Path,
    completion: RefreshCompletionV31,
    raw: bytes,
    installed_runtime_manifest_path: Path,
    installed_runtime_loader: InstalledRuntimeLoader,
) -> str:
    main_sha, tree_sha = _git_identity(repo_root)
    if (main_sha, tree_sha) != (
        completion.required_main_sha,
        completion.required_main_tree_sha,
    ):
        raise RuntimeError("refresh completion does not bind the installed repository")
    manifest, manifest_raw, effective_config_raw = installed_runtime_loader(
        installed_runtime_manifest_path
    )
    if manifest.computed_manifest_digest() != manifest.manifest_digest:
        raise RuntimeError("installed runtime manifest self-digest is invalid")
    exact_bindings = (
        manifest.repository_main_sha == completion.required_main_sha,
        manifest.repository_tree_sha == completion.required_main_tree_sha,
        f"sha256:{sha256_file(installed_runtime_manifest_path)}"
        == completion.runtime_manifest_digest,
        manifest.package_manifest.digest == completion.generation_manifest_digest,
        f"sha256:{sha256_file(Path(manifest.package_manifest.path))}"
        == completion.generation_manifest_digest,
        manifest.environment_file.digest == completion.environment_digest,
        f"sha256:{sha256_file(Path(manifest.environment_file.path))}"
        == completion.environment_digest,
        manifest.effective_config.digest == completion.effective_config_digest,
        f"sha256:{sha256_file(Path(manifest.repository_snapshot_manifest.path))}"
        == completion.snapshot_manifest_digest,
        manifest.repository_snapshot_manifest.digest
        == completion.snapshot_manifest_digest,
    )
    if not all(exact_bindings):
        raise RuntimeError("refresh completion does not bind the installed runtime")
    if manifest_raw != installed_runtime_manifest_path.read_bytes():
        raise RuntimeError("installed runtime manifest changed while validating refresh")
    if (
        f"sha256:{sha256_file(Path(manifest.effective_config.path))}"
        != completion.effective_config_digest
        or effective_config_raw != Path(manifest.effective_config.path).read_bytes()
    ):
        raise RuntimeError("effective configuration changed while validating refresh")
    return f"sha256:{sha256_file_bytes(raw)}"


def sha256_file_bytes(raw: bytes) -> str:
    import hashlib

    return hashlib.sha256(raw).hexdigest()


def _refresh_state_path(
    paths: V3RuntimePaths, completion: RefreshCompletionV31
) -> Path:
    return (
        paths.state_root
        / "refresh-activation"
        / f"{completion.required_main_sha}-{completion.transaction_id}.json"
    )


def _write_refresh_state(path: Path, state: RefreshActivationState) -> None:
    atomic_write_bytes(path, state.canonical_json_bytes())


@contextmanager
def _activation_supervisor_lock(paths: V3RuntimePaths) -> Generator[None, None, None]:
    lock_path = paths.state_root / "activation-supervisor.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _reopen_bound_file(path_value: str, digest: str) -> Path:
    path = Path(path_value)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("refresh activation evidence is missing or indirect")
    if f"sha256:{sha256_file(path)}" != digest:
        raise RuntimeError("refresh activation evidence digest changed")
    return path


def stage_controller_start_request(
    transaction: ActivationTransaction,
    *,
    transaction_path: Path,
    outbox: Path = CONTROLLER_START_OUTBOX,
) -> Path:
    """Stage an unsigned root-broker request only after durable ACTIVATED state."""

    if transaction.phase.value != "ACTIVATED" or transaction.activated_at is None:
        raise RuntimeError("controller start requires a terminal ACTIVATED transaction")
    raw = transaction_path.read_bytes()
    reopened = ActivationTransaction.model_validate_json(raw, strict=True)
    if reopened != transaction:
        raise RuntimeError("activation transaction changed before controller start request")
    request = ControllerStartRequest(
        schema_version="3.1",
        transaction_id=transaction.transaction_id,
        transaction_path=str(transaction_path.resolve(strict=True)),
        transaction_digest=f"sha256:{sha256_file(transaction_path)}",
        transaction=transaction,
        activation_receipt_id=transaction.activation_receipt_id,
        activation_receipt_digest=transaction.activation_receipt_digest,
        exact_main_sha=transaction.exact_main_sha,
    )
    target = outbox / f"{transaction.transaction_id}.controller-start.json"
    encoded = request.canonical_json_bytes()
    if target.exists():
        if target.is_symlink() or target.read_bytes() != encoded:
            raise RuntimeError("controller start request identity conflicts")
        return target
    atomic_write_bytes(target, encoded)
    return target


def _resume_or_stage_activated(
    *, repo_root: Path, paths: V3RuntimePaths
) -> str | None:
    transactions = sorted(paths.activation_transactions.glob("ACTIVATE-*.json"))
    if len(transactions) != 1:
        return None
    observed = ActivationTransaction.model_validate_json(
        transactions[0].read_bytes(), strict=True
    )
    transaction = activate_v31(
        repo_root=repo_root,
        canary_suite_path=Path(observed.canary_suite_path),
    )
    stage_controller_start_request(transaction, transaction_path=transactions[0])
    return f"ACTIVATED_START_REQUESTED:{transaction.transaction_id}"


def validate_controller_principal(
    policy_path: Path = CONTROLLER_PRINCIPAL_POLICY,
) -> str:
    """Require the root-owned policy to name the exact executing account."""

    metadata = policy_path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or policy_path.is_symlink()
    ):
        raise RuntimeError("controller principal policy ownership or mode is invalid")
    payload: object = json.loads(policy_path.read_bytes())
    if not isinstance(payload, dict):
        raise RuntimeError("controller principal policy shape is invalid")
    typed = cast(dict[str, object], payload)
    if set(typed) != {"schemaVersion", "principal"}:
        raise RuntimeError("controller principal policy shape is invalid")
    if typed.get("schemaVersion") != "3.1" or not isinstance(typed.get("principal"), str):
        raise RuntimeError("controller principal policy value is invalid")
    principal = cast(str, typed["principal"])
    current = pwd.getpwuid(os.geteuid()).pw_name
    if current != principal:
        raise RuntimeError("activation supervisor is not running as the attested controller")
    return principal


def _select_refresh_completion(
    *,
    repo_root: Path,
    completion_root: Path,
    loader: RefreshCompletionLoader,
) -> tuple[Path, RefreshCompletionV31, bytes] | None:
    if not completion_root.exists():
        return None
    main_sha, tree_sha = _git_identity(repo_root)
    matches: list[tuple[Path, RefreshCompletionV31, bytes]] = []
    for path in sorted(completion_root.glob("*.json")):
        completion, raw = loader(path)
        if (
            completion.required_main_sha == main_sha
            and completion.required_main_tree_sha == tree_sha
        ):
            matches.append((path, completion, raw))
    if len(matches) > 1:
        raise RuntimeError("multiple refresh completions bind the installed repository")
    return matches[0] if matches else None


def _process_refresh_activation(
    *,
    repo_root: Path,
    paths: V3RuntimePaths,
    runner_executable: Path,
    completion_root: Path,
    completion_loader: RefreshCompletionLoader,
    installed_runtime_manifest_path: Path,
    installed_runtime_loader: InstalledRuntimeLoader,
    activation_policy_receipt_path: Path,
) -> str | None:
    selected = _select_refresh_completion(
        repo_root=repo_root,
        completion_root=completion_root,
        loader=completion_loader,
    )
    if selected is None:
        return None
    completion_path, completion, completion_raw = selected
    completion_digest = _validate_refresh_completion(
        repo_root=repo_root,
        completion=completion,
        raw=completion_raw,
        installed_runtime_manifest_path=installed_runtime_manifest_path,
        installed_runtime_loader=installed_runtime_loader,
    )
    state_path = _refresh_state_path(paths, completion)
    if state_path.is_file():
        state_raw = state_path.read_bytes()
        state = RefreshActivationState.model_validate_json(state_raw, strict=True)
        if state_raw != state.canonical_json_bytes():
            raise RuntimeError("refresh activation state is not canonical")
        if (
            state.completion != completion
            or state.completion_digest != completion_digest
            or Path(state.completion_path) != completion_path
        ):
            raise RuntimeError("refresh activation completion identity changed")
    else:
        if state_path.exists():
            raise RuntimeError("refresh activation state path is indirect")
        if paths.stop.exists() and (
            paths.stop.is_symlink() or not paths.stop.is_file()
        ):
            raise RuntimeError("STOP control is indirect")
        if not paths.stop.exists():
            stop_payload = (
                json.dumps(
                    {
                        "completionDigest": completion_digest,
                        "reason": "DEPLOYMENT_REFRESH_ACTIVATION",
                        "requiredMainSha": completion.required_main_sha,
                        "schemaVersion": "3.1",
                        "transactionId": completion.transaction_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            atomic_write_bytes(paths.stop, stop_payload)
        state = RefreshActivationState(
            completion_path=str(completion_path),
            completion_digest=completion_digest,
            completion=completion,
            phase="RECEIVED",
            updated_at=datetime.now(UTC),
        )
        _write_refresh_state(state_path, state)

    if state.phase == "START_REQUESTED":
        if paths.stop.exists():
            return "STOPPED_POST_ACTIVATION"
        transaction_path = _reopen_bound_file(
            cast(str, state.activation_transaction_path),
            cast(str, state.activation_transaction_digest),
        )
        transaction = ActivationTransaction.model_validate_json(
            transaction_path.read_bytes(), strict=True
        )
        stage_controller_start_request(transaction, transaction_path=transaction_path)
        return f"ACTIVATED_START_REQUESTED:{transaction.transaction_id}"

    if state.canary_suite_path is None:
        result_root = (
            paths.canary_results
            / "deployment-refresh"
            / f"{completion.required_main_sha}-{completion.transaction_id}"
        )
        candidates = sorted(result_root.rglob("suite.json")) if result_root.exists() else []
        suite_path: Path | None = None
        suite: MandatoryCanarySuite | None = None
        for candidate in reversed(candidates):
            try:
                observed = verify_mandatory_canary_suite(
                    candidate, repo_root=repo_root, require_pass=True
                )
            except (OSError, RuntimeError, ValueError):
                continue
            if (
                observed.exact_main_sha == completion.required_main_sha
                and observed.exact_tree_sha == completion.required_main_tree_sha
                and observed.source_generation_id == completion.source_generation_id
                and observed.source_generation_digest
                == completion.source_generation_digest
            ):
                suite_path, suite = candidate, observed
                break
        if suite_path is None:
            suite_path = run_mandatory_canaries(
                repo_root=repo_root,
                result_root=result_root,
                runner_executable=runner_executable,
            )
            suite = MandatoryCanarySuite.model_validate_json(
                suite_path.read_bytes(), strict=True
            )
        if suite is None or suite.status is not CanaryStatus.PASS:
            return "STOPPED_CANARY_PREREQUISITE"
        if (
            suite.exact_main_sha != completion.required_main_sha
            or suite.exact_tree_sha != completion.required_main_tree_sha
            or suite.source_generation_id != completion.source_generation_id
            or suite.source_generation_digest != completion.source_generation_digest
        ):
            raise RuntimeError("fresh canary suite does not bind the refresh completion")
        state = state.model_copy(
            update={
                "phase": "CANARIES_PASSED",
                "canary_suite_path": str(suite_path),
                "canary_suite_digest": f"sha256:{sha256_file(suite_path)}",
                "updated_at": datetime.now(UTC),
            }
        )
        _write_refresh_state(state_path, state)
    else:
        suite_path = _reopen_bound_file(
            state.canary_suite_path, cast(str, state.canary_suite_digest)
        )
        suite = verify_mandatory_canary_suite(
            suite_path, repo_root=repo_root, require_pass=True
        )
        if (
            suite.exact_main_sha != completion.required_main_sha
            or suite.exact_tree_sha != completion.required_main_tree_sha
            or suite.source_generation_id != completion.source_generation_id
            or suite.source_generation_digest != completion.source_generation_digest
        ):
            raise RuntimeError("bound canary suite no longer matches refresh completion")

    if state.activation_request_path is None:
        request_path = stage_activation_request(
            repo_root=repo_root,
            canary_suite_path=suite_path,
            machine_policy_receipt_path=activation_policy_receipt_path,
            installed_runtime_manifest_path=installed_runtime_manifest_path,
            installed_runtime_loader=installed_runtime_loader,
        )
        state = state.model_copy(
            update={
                "phase": "REQUEST_SUBMITTED",
                "activation_request_path": str(request_path),
                "activation_request_digest": f"sha256:{sha256_file(request_path)}",
                "updated_at": datetime.now(UTC),
            }
        )
        _write_refresh_state(state_path, state)
    else:
        _reopen_bound_file(
            state.activation_request_path,
            cast(str, state.activation_request_digest),
        )

    if state.activation_transaction_path is None:
        try:
            transaction = activate_v31(
                repo_root=repo_root,
                canary_suite_path=suite_path,
                installed_runtime_manifest_path=installed_runtime_manifest_path,
                installed_runtime_loader=installed_runtime_loader,
            )
        except (OSError, RuntimeError, ValueError):
            return "ACTIVATION_REQUEST_SUBMITTED"
        transaction_path = (
            paths.activation_transactions / f"{transaction.transaction_id}.json"
        )
        state = state.model_copy(
            update={
                "phase": "ACTIVATED",
                "activation_transaction_path": str(transaction_path),
                "activation_transaction_digest": (
                    f"sha256:{sha256_file(transaction_path)}"
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        _write_refresh_state(state_path, state)
    else:
        transaction_path = _reopen_bound_file(
            state.activation_transaction_path,
            cast(str, state.activation_transaction_digest),
        )
        transaction = ActivationTransaction.model_validate_json(
            transaction_path.read_bytes(), strict=True
        )
    if (
        transaction.exact_main_sha != completion.required_main_sha
        or transaction.exact_tree_sha != completion.required_main_tree_sha
        or Path(transaction.canary_suite_path) != suite_path
        or transaction.canary_suite_digest != f"sha256:{sha256_file(suite_path)}"
    ):
        raise RuntimeError("activation transaction does not bind fresh refresh evidence")
    stage_controller_start_request(transaction, transaction_path=transaction_path)
    state = state.model_copy(
        update={"phase": "START_REQUESTED", "updated_at": datetime.now(UTC)}
    )
    _write_refresh_state(state_path, state)
    return f"ACTIVATED_START_REQUESTED:{transaction.transaction_id}"


def run_activation_supervisor(
    *,
    repo_root: Path,
    runner_executable: Path = Path("/usr/local/bin/traincapsule-v31-run-canary"),
    refresh_completion_root: Path = REFRESH_COMPLETION_INBOX,
    refresh_completion_loader: RefreshCompletionLoader = _load_refresh_completion,
    installed_runtime_manifest_path: Path = Path(
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    installed_runtime_loader: InstalledRuntimeLoader = _refresh_runtime_bundle,
    activation_policy_receipt_path: Path = ACTIVATION_POLICY_RECEIPT,
) -> str:
    """Advance the receipt-gated stopped activation state machine without self-authority."""

    repo_root = repo_root.resolve(strict=True)
    paths = resolve_v3_runtime_paths(repo_root)
    with _activation_supervisor_lock(paths):
        return _run_activation_supervisor_locked(
            repo_root=repo_root,
            paths=paths,
            runner_executable=runner_executable,
            refresh_completion_root=refresh_completion_root,
            refresh_completion_loader=refresh_completion_loader,
            installed_runtime_manifest_path=installed_runtime_manifest_path,
            installed_runtime_loader=installed_runtime_loader,
            activation_policy_receipt_path=activation_policy_receipt_path,
        )


def _run_activation_supervisor_locked(
    *,
    repo_root: Path,
    paths: V3RuntimePaths,
    runner_executable: Path,
    refresh_completion_root: Path,
    refresh_completion_loader: RefreshCompletionLoader,
    installed_runtime_manifest_path: Path,
    installed_runtime_loader: InstalledRuntimeLoader,
    activation_policy_receipt_path: Path,
) -> str:
    if paths.pause.exists() or paths.hard_stuck.exists():
        return "STOPPED_CONTROL"
    refreshed = _process_refresh_activation(
        repo_root=repo_root,
        paths=paths,
        runner_executable=runner_executable,
        completion_root=refresh_completion_root,
        completion_loader=refresh_completion_loader,
        installed_runtime_manifest_path=installed_runtime_manifest_path,
        installed_runtime_loader=installed_runtime_loader,
        activation_policy_receipt_path=activation_policy_receipt_path,
    )
    if refreshed is not None:
        return refreshed
    if not paths.stop.is_file() or paths.stop.is_symlink():
        resumed = _resume_or_stage_activated(repo_root=repo_root, paths=paths)
        return resumed or "INACTIVE_NOT_STOPPED"
    # A delayed independent LIVE receipt is consumed on a later timer tick.  Re-open
    # the newest exact passing suite before the atomic STOP transition.
    suites = sorted(
        paths.canary_results.rglob("suite.json"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for existing_suite in suites:
        try:
            verify_mandatory_canary_suite(
                existing_suite,
                repo_root=repo_root,
                require_pass=True,
            )
            transaction = activate_v31(
                repo_root=repo_root,
                canary_suite_path=existing_suite,
            )
            transaction_path = (
                paths.activation_transactions / f"{transaction.transaction_id}.json"
            )
            stage_controller_start_request(
                transaction,
                transaction_path=transaction_path,
            )
            return f"ACTIVATED_START_REQUESTED:{transaction.transaction_id}"
        except (OSError, RuntimeError, ValueError):
            continue
    suite_path = run_mandatory_canaries(
        repo_root=repo_root,
        result_root=paths.canary_results,
        runner_executable=runner_executable,
    )
    suite = MandatoryCanarySuite.model_validate_json(suite_path.read_bytes(), strict=True)
    if suite.status is not CanaryStatus.PASS:
        return "STOPPED_CANARY_PREREQUISITE"
    request = coordinate_activation_request(repo_root=repo_root)
    return "ACTIVATION_REQUEST_SUBMITTED" if request is not None else "STOPPED_POLICY_PREREQUISITE"


def main() -> int:
    validate_controller_principal()
    configured_repo = os.environ.get("TCF_REPO_PATH")
    if not configured_repo or not Path(configured_repo).is_absolute():
        raise RuntimeError("activation supervisor requires an absolute attested repository path")
    repo = Path(configured_repo)
    state = run_activation_supervisor(repo_root=repo)
    print(state)
    return (
        0
        if state in {"INACTIVE_NOT_STOPPED", "ACTIVATION_REQUEST_SUBMITTED"}
        or state.startswith("ACTIVATED_START_REQUESTED:")
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
