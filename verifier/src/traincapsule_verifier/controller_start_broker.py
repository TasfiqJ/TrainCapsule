"""Root-only, public-authority-gated and crash-recoverable controller start broker."""

from __future__ import annotations

import os
import pwd
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .filesystem import open_trusted_root, read_bounded_file
from .models import ActivationReceipt
from .public_verifier import PublicVerifier

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")
ACTIVATION = ROOT / "activation"
RECEIPTS = ROOT / "receipts"


class _Strict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part.title() for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class _Artifact(_Strict):
    path: str
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    executable: bool = False


class _ReductionOracle(_Strict):
    oracle_id: Literal["TRAINCAPSULE_REDUCTION_ORACLE_V1"]
    executable: _Artifact
    public_key: _Artifact
    receipt_verifier: _Artifact
    public_receipt_root: Literal["/var/lib/traincapsule-verifier/receipts"]
    activation_receipt_path: Literal[
        "/var/lib/traincapsule-verifier/activation/current.json"
    ]

    @model_validator(mode="after")
    def exact_installation(self) -> _ReductionOracle:
        if (
            self.executable.path
            != "/usr/local/libexec/traincapsule-reduction-oracle"
            or not self.executable.executable
            or self.public_key.path
            != "/etc/traincapsule-verifier/keys/reduction-oracle.pub"
            or self.public_key.executable
            or self.receipt_verifier.path
            != "/usr/local/bin/traincapsule-verifier-verify-receipt"
            or not self.receipt_verifier.executable
        ):
            raise ValueError("reduction oracle installation contract mismatch")
        return self


class _RuntimeManifest(_Strict):
    schema_version: Literal["3.1"]
    manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    controller_principal: Literal["traincapsule-controller"]
    service_name: Literal["traincapsule-controller.service"]
    distribution_root: Literal["/opt/traincapsule-runtime"]
    repository_root: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    runtime_root: Literal["/var/lib/traincapsule-runtime"]
    python_runtime: _Artifact
    package_manifest: _Artifact
    dependency_lock: _Artifact
    controller_unit: _Artifact
    environment_file: _Artifact
    effective_config: _Artifact
    repository_snapshot_manifest: _Artifact
    reduction_oracle: _ReductionOracle | None = None
    repository_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    repository_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    mutable_git_root: Literal["/var/lib/traincapsule-runtime/git"]
    mutable_worktree_root: Literal["/var/lib/traincapsule-runtime/worktrees"]
    artifact_root: Literal["/var/lib/traincapsule-runtime/artifacts/v3"]
    entry_arguments: tuple[str, ...]

    @model_validator(mode="after")
    def exact_runtime(self) -> _RuntimeManifest:
        if (
            self.python_runtime.path != "/opt/traincapsule-runtime/python/bin/python3.12"
            or not self.python_runtime.executable
            or self.controller_unit.path
            != "/etc/systemd/system/traincapsule-controller.service"
            or self.environment_file.path
            != "/etc/traincapsule-controller/controller-runtime.env"
            or self.effective_config.path
            != "/etc/traincapsule-controller/effective-config.yaml"
            or not self.entry_arguments
            or len(self.entry_arguments) > 32
            or any(
                not argument
                or "\x00" in argument
                or "\n" in argument
                or "\r" in argument
                for argument in self.entry_arguments
            )
        ):
            raise ValueError("controller installed runtime contract mismatch")
        zero = self.model_copy(update={"manifest_digest": "sha256:" + "0" * 64})
        if self.manifest_digest != sha256_digest(canonical_json_bytes(zero)):
            raise ValueError("controller runtime manifest digest mismatch")
        return self


class _Transaction(_Strict):
    schema_version: Literal["3.1"]
    transaction_id: str
    phase: Literal["ACTIVATED"]
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    activation_receipt_id: str
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    canary_suite_path: str
    canary_suite_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preflight_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    autonomy_enabled: Literal[True]
    stop_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    stop_archive_path: str
    prepared_at: str
    activated_at: str


class _StartRequest(_Strict):
    schema_version: Literal["3.1"]
    transaction_id: str
    transaction_path: str
    transaction_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    transaction: _Transaction
    activation_receipt_id: str
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")

    @model_validator(mode="after")
    def exact_transaction(self) -> _StartRequest:
        if (
            self.transaction_id != self.transaction.transaction_id
            or self.activation_receipt_id != self.transaction.activation_receipt_id
            or self.activation_receipt_digest != self.transaction.activation_receipt_digest
            or self.exact_main_sha != self.transaction.exact_main_sha
            or self.transaction_digest
            != sha256_digest(canonical_json_bytes(self.transaction))
        ):
            raise ValueError("controller start request transaction binding mismatch")
        return self


class _Policy(_Strict):
    schema_version: Literal["3.1"]
    controller_principal: Literal["traincapsule-controller"]
    service_name: Literal["traincapsule-controller.service"]
    repository_root: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    runtime_root: Literal["/var/lib/traincapsule-runtime"]
    runtime_manifest_path: Literal[
        "/etc/traincapsule-controller/runtime-manifest.json"
    ]
    journal_root: Literal["/var/lib/traincapsule-verifier/controller-start-journal"]


class _StartJournal(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    phase: Literal["PREPARED", "STARTED", "ROLLED_BACK"]
    controller_pid: int | None = Field(default=None, gt=0)
    runtime_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    recorded_at: str
    reason: str | None = None


def _atomic_write(path: Path, raw: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def restore_runtime_stop(runtime_root: Path) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    runtime_stat = runtime_root.lstat()
    if runtime_root.is_symlink() or not stat.S_ISDIR(runtime_stat.st_mode):
        raise ValueError("runtime root is not a direct directory")
    stop = runtime_root / "STOP"
    if stop.exists():
        return
    descriptor = os.open(
        stop, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        os.fchown(descriptor, runtime_stat.st_uid, runtime_stat.st_gid)
        os.write(descriptor, b"controller start broker rollback\n")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_runtime_manifest(path: Path) -> tuple[_RuntimeManifest, bytes]:
    observed = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != 0
        or observed.st_nlink != 1
        or observed.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise ValueError("controller runtime manifest is not root-owned immutable data")
    raw = path.read_bytes()
    manifest = _RuntimeManifest.model_validate_json(raw, strict=True)
    if raw != canonical_json_bytes(manifest):
        raise ValueError("controller runtime manifest is not canonical")
    for artifact in (
        manifest.python_runtime,
        manifest.package_manifest,
        manifest.dependency_lock,
        manifest.controller_unit,
        manifest.environment_file,
        manifest.effective_config,
        manifest.repository_snapshot_manifest,
    ):
        target = Path(artifact.path)
        current = target.lstat()
        if (
            target.is_symlink()
            or not stat.S_ISREG(current.st_mode)
            or current.st_uid != 0
            or current.st_nlink != 1
            or current.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            or (artifact.executable and not current.st_mode & stat.S_IXUSR)
            or f"sha256:{__import__('hashlib').sha256(target.read_bytes()).hexdigest()}"
            != artifact.digest
        ):
            raise ValueError(f"controller runtime artifact failed attestation: {artifact.path}")
    return manifest, raw


def _runtime_manifest_authority_digest(raw: bytes) -> str:
    """Return the exact installed-file identity bound by activation receipts."""
    return sha256_digest(raw)


def run_systemctl(*arguments: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/systemctl", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def controller_active_pid(service: str) -> int | None:
    active = run_systemctl("is-active", "--quiet", service)
    if active.returncode != 0:
        return None
    shown = run_systemctl("show", "--property=MainPID", "--value", service)
    if shown.returncode != 0 or not shown.stdout.strip().isdigit():
        raise ValueError("controller service active without an exact MainPID")
    pid = int(shown.stdout.strip())
    if pid <= 1:
        raise ValueError("controller MainPID is invalid")
    return pid


def _attest_process(pid: int, manifest: _RuntimeManifest, controller_uid: int) -> None:
    process = Path("/proc") / str(pid)
    status_fields = dict(
        line.split(":", 1) for line in (process / "status").read_text().splitlines() if ":" in line
    )
    uid_field = status_fields.get("Uid", "").split()
    if not uid_field or int(uid_field[0]) != controller_uid:
        raise ValueError("controller process principal mismatch")
    executable = (process / "exe").resolve(strict=True)
    if executable != Path(manifest.python_runtime.path).resolve(strict=True):
        raise ValueError("controller process executable mismatch")
    arguments = tuple(
        part.decode("utf-8") for part in (process / "cmdline").read_bytes().split(b"\0") if part
    )
    if arguments != (manifest.python_runtime.path, *manifest.entry_arguments):
        raise ValueError("controller process arguments mismatch")


def _rollback(
    *,
    policy: _Policy,
    request: _StartRequest,
    runtime_manifest_digest: str,
    reason: str,
) -> None:
    run_systemctl("stop", policy.service_name, timeout=60)
    restore_runtime_stop(Path(policy.runtime_root))
    journal = _StartJournal(
        transaction_id=request.transaction_id,
        request_digest=sha256_digest(canonical_json_bytes(request)),
        phase="ROLLED_BACK",
        runtime_manifest_digest=runtime_manifest_digest,
        recorded_at=datetime.now(UTC).isoformat(),
        reason=reason[:1000],
    )
    _atomic_write(
        Path(policy.journal_root) / f"{request.transaction_id}.json",
        canonical_json_bytes(journal),
    )


def process() -> int:
    if os.geteuid() != 0:
        raise ValueError("controller start broker requires root")
    with open_trusted_root(CONFIG, expected_uid=0) as config:
        policy = _Policy.model_validate_json(
            read_bounded_file(config, "controller-start-policy.json"), strict=True
        )
    controller = pwd.getpwnam(policy.controller_principal)
    runtime_root = Path(policy.runtime_root)
    if (runtime_root / "HARD_STUCK.json").exists() or (runtime_root / "STOP").exists():
        raise ValueError("controller start is forbidden by runtime control state")
    manifest, runtime_manifest_raw = _read_runtime_manifest(
        Path(policy.runtime_manifest_path)
    )
    runtime_manifest_digest = _runtime_manifest_authority_digest(runtime_manifest_raw)
    journal_root = Path(policy.journal_root)
    with (
        open_trusted_root(
            ROOT / "controller-start-outbox", expected_uid=controller.pw_uid
        ) as outbox,
        open_trusted_root(ACTIVATION, expected_uid=0) as activation,
    ):
        receipt = ActivationReceipt.model_validate_json(
            read_bounded_file(activation, "current.json"), strict=True
        )
        with PublicVerifier.from_public_roots(
            repository_root=Path(policy.repository_root),
            config_root=CONFIG,
            state_root=CONFIG,
            receipt_root=RECEIPTS,
            expected_owner_uid=0,
        ) as verifier:
            names = tuple(
                sorted(
                    name
                    for name in os.listdir(outbox.descriptor)
                    if name.endswith(".controller-start.json")
                )
            )
            processed = False
            for name in names:
                raw = read_bounded_file(outbox, name, maximum_bytes=5_000_000)
                request = _StartRequest.model_validate_json(raw, strict=True)
                if raw != canonical_json_bytes(request):
                    raise ValueError("controller start request is not canonical")
                if name != f"{request.transaction_id}.controller-start.json":
                    raise ValueError("controller start request filename/identity mismatch")
                if (
                    request.activation_receipt_id != receipt.receipt_id
                    or request.activation_receipt_digest != model_digest(receipt)
                    or receipt.controller_binary_digest != runtime_manifest_digest
                    or receipt.controller_config_digest != manifest.effective_config.digest
                ):
                    continue
                verifier.authorize_activation(
                    receipt,
                    main_sha=request.exact_main_sha,
                    source_generation_id=receipt.source_generation_id,
                    source_generation_digest=receipt.source_generation_digest,
                    controller_binary_digest=runtime_manifest_digest,
                    controller_config_digest=manifest.effective_config.digest,
                )
                journal_path = journal_root / f"{request.transaction_id}.json"
                existing = (
                    _StartJournal.model_validate_json(journal_path.read_bytes(), strict=True)
                    if journal_path.exists()
                    else None
                )
                digest = sha256_digest(raw)
                if existing is not None and (
                    existing.request_digest != digest
                    or existing.runtime_manifest_digest != runtime_manifest_digest
                ):
                    raise ValueError("controller start journal identity mismatch")
                if existing is not None and existing.phase == "ROLLED_BACK":
                    raise ValueError("rolled-back controller start cannot be resumed")
                active_pid = controller_active_pid(policy.service_name)
                if active_pid is not None and existing is None:
                    run_systemctl("stop", policy.service_name, timeout=60)
                    restore_runtime_stop(runtime_root)
                    raise ValueError(
                        "unexpected preexisting controller was stopped; STOP restored"
                    )
                if existing is None:
                    prepared = _StartJournal(
                        transaction_id=request.transaction_id,
                        request_digest=digest,
                        phase="PREPARED",
                        runtime_manifest_digest=runtime_manifest_digest,
                        recorded_at=datetime.now(UTC).isoformat(),
                    )
                    _atomic_write(journal_path, canonical_json_bytes(prepared))
                try:
                    if active_pid is None:
                        started = run_systemctl("start", policy.service_name, timeout=60)
                        if started.returncode != 0:
                            raise ValueError("controller service start failed")
                        active_pid = controller_active_pid(policy.service_name)
                    if active_pid is None:
                        raise ValueError("controller service did not become active")
                    _attest_process(active_pid, manifest, controller.pw_uid)
                except (OSError, ValueError, subprocess.TimeoutExpired) as error:
                    _rollback(
                        policy=policy,
                        request=request,
                        runtime_manifest_digest=runtime_manifest_digest,
                        reason=str(error),
                    )
                    raise ValueError(
                        "controller start/identity attestation failed; STOP restored"
                    ) from error
                terminal = _StartJournal(
                    transaction_id=request.transaction_id,
                    request_digest=digest,
                    phase="STARTED",
                    controller_pid=active_pid,
                    runtime_manifest_digest=runtime_manifest_digest,
                    recorded_at=datetime.now(UTC).isoformat(),
                )
                _atomic_write(journal_path, canonical_json_bytes(terminal))
                processed = True
            if names and not processed:
                raise ValueError("no controller start request matches current activation")
    return 0


def main() -> int:
    if sys.argv[1:] != ["process-outbox"]:
        print("usage: traincapsule-verifier-controller-start process-outbox", file=sys.stderr)
        return 2
    try:
        return process()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        print("controller start broker rejected work", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
