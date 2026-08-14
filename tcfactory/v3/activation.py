"""Receipt-gated, crash-recoverable V3.1 LIVE activation transition."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ..github_sync import load_github_config
from ..gitops import current_sha
from ..util import atomic_write_bytes, sha256_file
from .base import DIGEST_PATTERN, SHA_PATTERN, V3Model, sha256_digest
from .canaries import MandatoryCanarySuite, verify_mandatory_canary_suite
from .configuration import load_autonomy_v3
from .contracts_v31 import (
    ActivationMode,
    ActivationReceiptV31,
    ActivationRequestV31,
    MachinePolicyReceiptV31,
    PolicyDecision,
)
from .controller_lock import controller_process_lock
from .installed_runtime import (
    InstalledControllerRuntimeManifest,
    load_installed_controller_runtime,
)
from .runtime_paths import V3RuntimePaths, resolve_v3_runtime_paths
from .verifier_submission import create_and_submit_verification_request

ACTIVATION_POLICY_WORK_ITEM = "V3-MIG-019"
ACTIVATION_POLICY_PROFILE = Path(
    "/etc/traincapsule-verifier/request-profiles/activation_policy.json"
)
ACTIVATION_POLICY_RECEIPT_ROOT = Path(
    "/var/lib/traincapsule-verifier/receipts/machine-policy/V3-MIG-019"
)


def resolve_activation_policy_receipt_path(
    repo_root: Path, configured_path: Path | None = None
) -> Path:
    """Resolve the immutable public receipt selector for the exact current SHA."""

    selected = configured_path or ACTIVATION_POLICY_RECEIPT_ROOT
    if selected == ACTIVATION_POLICY_RECEIPT_ROOT or selected.is_dir():
        return selected / f"{current_sha(repo_root.resolve(strict=True))}.json"
    return selected


class ActivationPhase(StrEnum):
    PREPARED = "PREPARED"
    ACTIVATED = "ACTIVATED"


class ActivationTransaction(V3Model):
    schema_version: Literal["3.1"]
    transaction_id: str = Field(pattern=r"^ACTIVATE-[A-Z0-9._:-]{3,127}$")
    phase: ActivationPhase
    exact_main_sha: str = Field(pattern=SHA_PATTERN.pattern)
    exact_tree_sha: str = Field(pattern=SHA_PATTERN.pattern)
    activation_receipt_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._:-]{2,127}$")
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    canary_suite_path: str = Field(min_length=1, max_length=4096)
    canary_suite_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    preflight_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    autonomy_enabled: Literal[True] = True
    stop_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    stop_archive_path: str = Field(min_length=1, max_length=4096)
    prepared_at: AwareDatetime
    activated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_phase(self) -> ActivationTransaction:
        if self.phase is ActivationPhase.ACTIVATED and self.activated_at is None:
            raise ValueError("activated transaction requires activation time")
        if self.phase is ActivationPhase.PREPARED and self.activated_at is not None:
            raise ValueError("prepared transaction cannot claim activation time")
        if self.activated_at is not None and self.activated_at < self.prepared_at:
            raise ValueError("activation time precedes preparation")
        return self


InstalledRuntimeLoader = Callable[
    [Path], tuple[InstalledControllerRuntimeManifest, bytes, bytes]
]


def _activation_runtime_bundle(
    path: Path,
) -> tuple[InstalledControllerRuntimeManifest, bytes, bytes]:
    manifest, raw = load_installed_controller_runtime(path)
    return manifest, raw, Path(manifest.effective_config.path).read_bytes()


def stage_activation_request(
    *,
    repo_root: Path,
    canary_suite_path: Path,
    machine_policy_receipt_path: Path,
    installed_runtime_manifest_path: Path = Path(
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    installed_runtime_loader: InstalledRuntimeLoader = _activation_runtime_bundle,
    _outbox_root: Path = Path("/var/lib/traincapsule-verifier/activation-controller-outbox"),
) -> Path:
    """Create an unsigned, evidence-bound activation request; never authorize activation."""

    repo_root = repo_root.resolve(strict=True)
    paths = resolve_v3_runtime_paths(repo_root)
    if not paths.stop.is_file() or paths.stop.is_symlink():
        raise RuntimeError("activation request requires the durable STOP control")
    if paths.pause.exists() or paths.hard_stuck.exists():
        raise RuntimeError("activation request is forbidden while PAUSE or HARD_STUCK exists")
    if paths.activation_transactions.exists() and any(paths.activation_transactions.iterdir()):
        raise RuntimeError("activation request is forbidden with existing activation transactions")
    suite_path = canary_suite_path.resolve(strict=True)
    suite_raw = suite_path.read_bytes()
    suite = verify_mandatory_canary_suite(suite_path, repo_root=repo_root, require_pass=True)
    main_sha = current_sha(repo_root)
    tree_sha = _exact_tree(repo_root, main_sha)
    if suite.exact_main_sha != main_sha or suite.exact_tree_sha != tree_sha:
        raise RuntimeError("activation canary suite does not bind the exact current main/tree")
    receipt_raw = machine_policy_receipt_path.resolve(strict=True).read_bytes()
    receipt = MachinePolicyReceiptV31.model_validate_json(receipt_raw, strict=True)
    suite_digest = sha256_digest(suite_raw)
    if (
        receipt.decision is not PolicyDecision.PASS
        or receipt.candidate_sha != main_sha
        or receipt.candidate_tree_sha != tree_sha
        or receipt.source_generation_id != suite.source_generation_id
        or receipt.source_generation_digest != suite.source_generation_digest
        or receipt.context_manifest_digest != suite_digest
        or receipt.task_packet_digest != suite.controller_digest
        or receipt.candidate_manifest_digest != suite.factory_config_digest
        or "ACTIVATION" not in receipt.allowed_claims
    ):
        raise RuntimeError(
            "machine-policy receipt does not authorize the exact activation evidence"
        )
    installed_runtime, controller_raw, config_raw = installed_runtime_loader(
        installed_runtime_manifest_path
    )
    controller_digest = sha256_digest(controller_raw)
    config_digest = sha256_digest(config_raw)
    if controller_raw != installed_runtime.canonical_json_bytes():
        raise RuntimeError("installed runtime manifest bytes are not canonical")
    if config_digest != installed_runtime.effective_config.digest:
        raise RuntimeError("installed runtime config digest mismatch")
    identity = sha256_digest(
        b"\0".join(
            (
                main_sha.encode(),
                tree_sha.encode(),
                suite_digest.encode(),
                receipt.canonical_digest().encode(),
                controller_digest.encode(),
                config_digest.encode(),
            )
        )
    )
    request_id = f"ACTREQ:{identity[7:39].upper()}"
    request = ActivationRequestV31(
        schema_version="3.1",
        request_id=request_id,
        nonce=f"ACTIVATION-{identity[7:]}",
        verified_main_sha=main_sha,
        machine_environment_digest=suite_digest,
        source_generation_id=suite.source_generation_id,
        source_generation_digest=suite.source_generation_digest,
        controller_binary_digest=controller_digest,
        controller_config_digest=config_digest,
        machine_environment_path="canary-suite.json",
        controller_binary_path="installed-controller-runtime.json",
        controller_config_path="effective-config.yaml",
        machine_policy_receipt=receipt,
        mode=ActivationMode.LIVE,
    )
    outbox_root = _outbox_root
    if outbox_root.is_symlink():
        raise RuntimeError("activation controller outbox cannot be a symlink")
    outbox_fd = os.open(
        outbox_root,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    outbox_stat = os.fstat(outbox_fd)
    if (
        not stat.S_ISDIR(outbox_stat.st_mode)
        or outbox_stat.st_uid != os.geteuid()
        or outbox_stat.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        os.close(outbox_fd)
        raise RuntimeError("activation controller outbox ownership or mode is invalid")
    evidence = outbox_root / f"{request_id}.evidence"
    request_path = outbox_root / f"{request_id}.activation-request.json"
    payloads = {
        "canary-suite.json": suite_raw,
        "installed-controller-runtime.json": controller_raw,
        "effective-config.yaml": config_raw,
    }
    try:
        if evidence.exists():
            if evidence.is_symlink() or any(
                (evidence / name).read_bytes() != raw for name, raw in payloads.items()
            ):
                raise RuntimeError("activation request evidence identity conflicts")
        else:
            staging = Path(tempfile.mkdtemp(prefix=f".{request_id}.", dir=outbox_root))
            try:
                for name, raw in payloads.items():
                    atomic_write_bytes(staging / name, raw)
                os.rename(staging.name, evidence.name, src_dir_fd=outbox_fd, dst_dir_fd=outbox_fd)
                os.fsync(outbox_fd)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        request_raw = request.canonical_json_bytes()
        if request_path.exists():
            if request_path.is_symlink() or request_path.read_bytes() != request_raw:
                raise RuntimeError("activation request identity conflicts")
        else:
            temporary = f".{request_id}.{os.getpid()}.pending"
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=outbox_fd,
            )
            try:
                os.write(descriptor, request_raw)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                os.link(
                    temporary,
                    request_path.name,
                    src_dir_fd=outbox_fd,
                    dst_dir_fd=outbox_fd,
                )
            finally:
                os.unlink(temporary, dir_fd=outbox_fd)
            os.fsync(outbox_fd)
        return request_path
    finally:
        os.close(outbox_fd)


def coordinate_activation_request(
    *,
    repo_root: Path,
    machine_policy_receipt_path: Path | None = None,
) -> Path | None:
    """Automatically stage the newest exact passing suite, or remain safely stopped."""

    repo_root = repo_root.resolve(strict=True)
    paths = resolve_v3_runtime_paths(repo_root)
    if not paths.stop.is_file() or paths.pause.exists() or paths.hard_stuck.exists():
        return None
    machine_policy_receipt_path = resolve_activation_policy_receipt_path(
        repo_root, machine_policy_receipt_path
    )
    if not machine_policy_receipt_path.is_file() or machine_policy_receipt_path.is_symlink():
        return None
    suites = sorted(
        paths.canary_results.rglob("suite.json"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for suite_path in suites:
        try:
            return stage_activation_request(
                repo_root=repo_root,
                canary_suite_path=suite_path,
                machine_policy_receipt_path=machine_policy_receipt_path,
            )
        except (OSError, RuntimeError, ValueError):
            continue
    return None


def coordinate_activation_policy_request(
    *,
    repo_root: Path,
    canary_suite_path: Path,
    profile_path: Path = ACTIVATION_POLICY_PROFILE,
    machine_policy_receipt_path: Path | None = None,
    installed_runtime_manifest_path: Path = Path(
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    installed_runtime_loader: InstalledRuntimeLoader = _activation_runtime_bundle,
    controller_outbox: Path = Path(
        "/var/lib/traincapsule-verifier/controller-outbox"
    ),
) -> Path | None:
    """Submit exact stopped-state evidence for independent activation policy review."""

    repo_root = repo_root.resolve(strict=True)
    paths = resolve_v3_runtime_paths(repo_root)
    if (
        not paths.stop.is_file()
        or paths.stop.is_symlink()
        or paths.pause.exists()
        or paths.hard_stuck.exists()
    ):
        return None
    suite_path = canary_suite_path.resolve(strict=True)
    suite_raw = suite_path.read_bytes()
    suite = verify_mandatory_canary_suite(
        suite_path, repo_root=repo_root, require_pass=True
    )
    main_sha = current_sha(repo_root)
    tree_sha = _exact_tree(repo_root, main_sha)
    if suite.exact_main_sha != main_sha or suite.exact_tree_sha != tree_sha:
        return None
    receipt_path = resolve_activation_policy_receipt_path(
        repo_root, machine_policy_receipt_path
    )
    if receipt_path.is_file() and not receipt_path.is_symlink():
        return None
    installed_runtime, runtime_raw, config_raw = installed_runtime_loader(
        installed_runtime_manifest_path
    )
    suite_digest = sha256_digest(suite_raw)
    runtime_digest = sha256_digest(runtime_raw)
    config_digest = sha256_digest(config_raw)
    evidence_identity = sha256_digest(
        b"\0".join(
            (
                main_sha.encode(),
                tree_sha.encode(),
                suite_digest.encode(),
                installed_runtime.manifest_digest.encode(),
                config_digest.encode(),
            )
        )
    )
    evidence_root = (
        paths.state_root
        / "activation-policy-evidence"
        / evidence_identity.removeprefix("sha256:")
    )
    suite_root = suite_path.parent.resolve(strict=True)
    result_evidence: dict[str, Path] = {}
    for canary_id, relative in suite.result_artifacts.items():
        result_path = (suite_root / relative).resolve(strict=True)
        if not result_path.is_relative_to(suite_root):
            raise ValueError("canary result evidence escapes its suite root")
        result_evidence[f"CANARY-RESULT:{canary_id}"] = result_path
    return create_and_submit_verification_request(
        profile_path=profile_path,
        work_item_id=ACTIVATION_POLICY_WORK_ITEM,
        milestone_id="M0_SOURCE_INSTALLATION",
        lane="FACTORY",
        candidate_sha=main_sha,
        candidate_tree_sha=tree_sha,
        base_sha=main_sha,
        source_generation_id=suite.source_generation_id,
        source_generation_digest=suite.source_generation_digest,
        context_manifest_digest=suite_digest,
        task_packet_digest=suite.controller_digest,
        candidate_manifest_digest=suite.factory_config_digest,
        checkpoint_digest=runtime_digest,
        gate_evidence={"CANDIDATE-MANIFEST": suite_path},
        raw_evidence=result_evidence,
        evidence_root=evidence_root,
        controller_outbox=controller_outbox,
        now=suite.completed_at,
    )


def _transaction_path(paths: V3RuntimePaths, transaction_id: str) -> Path:
    return paths.activation_transactions / f"{transaction_id}.json"


def _write_transaction(path: Path, transaction: ActivationTransaction) -> None:
    atomic_write_bytes(path, transaction.canonical_json_bytes())


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _archive_stop(stop: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise RuntimeError("activation STOP archive target already exists")
    os.replace(stop, archive)
    _sync_directory(stop.parent)
    if archive.parent != stop.parent:
        _sync_directory(archive.parent)


def _load_transaction(path: Path) -> ActivationTransaction | None:
    if not path.exists():
        return None
    return ActivationTransaction.model_validate_json(path.read_bytes(), strict=True)


def _validate_archive(transaction: ActivationTransaction) -> None:
    archive = Path(transaction.stop_archive_path)
    observed = archive.lstat()
    if archive.is_symlink() or not archive.is_file() or observed.st_nlink != 1:
        raise RuntimeError("activation STOP archive is not a trusted regular file")
    if f"sha256:{sha256_file(archive)}" != transaction.stop_digest:
        raise RuntimeError("activation STOP archive digest mismatch")


def validate_activation_control_state(
    *,
    paths: V3RuntimePaths,
    exact_main_sha: str,
    activation_receipt_digest: str,
) -> ActivationTransaction | None:
    """When STOP is absent, require one complete matching activation journal."""

    if paths.stop.exists():
        return None
    if not paths.activation_transactions.is_dir():
        raise RuntimeError("STOP is absent without an activation transaction journal")
    candidates: list[ActivationTransaction] = []
    for path in sorted(paths.activation_transactions.glob("ACTIVATE-*.json")):
        transaction = _load_transaction(path)
        if (
            transaction is not None
            and transaction.exact_main_sha == exact_main_sha
            and transaction.activation_receipt_digest == activation_receipt_digest
        ):
            candidates.append(transaction)
    if len(candidates) != 1:
        raise RuntimeError("STOP absence has ambiguous or missing activation authority")
    transaction = candidates[0]
    if transaction.phase is not ActivationPhase.ACTIVATED:
        raise RuntimeError("activation transaction did not reach an auditable terminal phase")
    if transaction.autonomy_enabled is not True:
        raise RuntimeError("activation transaction did not enable protected autonomy state")
    _validate_archive(transaction)
    return transaction


def _exact_tree(repo_root: Path, sha: str) -> str:
    return current_sha(repo_root, f"{sha}^{{tree}}")


def _load_live_receipt(repo_root: Path) -> tuple[Path, bytes, ActivationReceiptV31]:
    github = load_github_config(repo_root / "config/github.yaml")
    path = Path(github.activation_receipt_path)
    raw = path.read_bytes()
    receipt = ActivationReceiptV31.model_validate_json(raw, strict=True)
    if receipt.mode is not ActivationMode.LIVE:
        raise RuntimeError("only an independently signed LIVE receipt may activate autonomy")
    return path, raw, receipt


def _activate_v31_locked(
    *,
    repo_root: Path,
    canary_suite_path: Path,
    now: datetime | None = None,
    preflight: Callable[..., dict[str, object]] | None = None,
    installed_runtime_manifest_path: Path = Path(
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    installed_runtime_loader: InstalledRuntimeLoader = _activation_runtime_bundle,
) -> ActivationTransaction:
    """Verify every prerequisite, then atomically archive STOP with a journal."""

    repo_root = repo_root.resolve()
    paths = resolve_v3_runtime_paths(repo_root)
    autonomy = load_autonomy_v3(repo_root / "config/autonomy.yaml")
    if autonomy.enabled:
        raise RuntimeError(
            "repository autonomy.enabled must remain false until the signed runtime transition"
        )
    if paths.hard_stuck.exists():
        raise RuntimeError("HARD_STUCK can never be cleared by activation")
    if paths.pause.exists():
        raise RuntimeError("PAUSE must receive an explicit disposition before activation")

    suite_path = canary_suite_path.resolve(strict=True)
    suite_before = suite_path.read_bytes()
    suite_stat = suite_path.lstat()
    suite: MandatoryCanarySuite = verify_mandatory_canary_suite(
        suite_path, repo_root=repo_root, require_pass=True
    )
    receipt_path, receipt_before, receipt = _load_live_receipt(repo_root)
    runtime_value, runtime_raw, _ = installed_runtime_loader(
        installed_runtime_manifest_path
    )
    installed_runtime = runtime_value
    if (
        receipt.controller_binary_digest != sha256_digest(runtime_raw)
        or receipt.controller_config_digest
        != installed_runtime.effective_config.digest
    ):
        raise RuntimeError("LIVE receipt does not bind the exact installed controller runtime")
    receipt_stat = receipt_path.lstat()
    suite_digest = sha256_digest(suite_before)
    if receipt.machine_environment_digest != suite_digest:
        raise RuntimeError("LIVE receipt does not bind the exact mandatory canary suite bytes")
    main_sha = current_sha(repo_root)
    tree_sha = _exact_tree(repo_root, main_sha)
    if suite.exact_main_sha != main_sha or suite.exact_tree_sha != tree_sha:
        raise RuntimeError("mandatory canaries are stale for activation HEAD/tree")

    if preflight is None:
        from ..supervisor import run_startup_preflight

        preflight = run_startup_preflight
    preflight_result = preflight(repo_root, allow_stop_for_activation=True)
    preflight_digest = sha256_digest(
        (json.dumps(preflight_result, sort_keys=True, default=str) + "\n").encode("utf-8")
    )
    expected_receipt_digest = receipt.canonical_digest()
    if preflight_result.get("activationReceiptDigest") != expected_receipt_digest:
        raise RuntimeError("startup preflight did not verify the exact activation receipt")
    suite_after = suite_path.lstat()
    if (
        (suite_after.st_dev, suite_after.st_ino) != (suite_stat.st_dev, suite_stat.st_ino)
        or suite_path.read_bytes() != suite_before
    ):
        raise RuntimeError("mandatory canary suite changed during activation preflight")
    receipt_after = receipt_path.lstat()
    if (
        (receipt_after.st_dev, receipt_after.st_ino)
        != (receipt_stat.st_dev, receipt_stat.st_ino)
        or receipt_path.read_bytes() != receipt_before
    ):
        raise RuntimeError("activation receipt changed during activation preflight")

    transaction_id = f"ACTIVATE-{receipt.receipt_id}"
    transaction_path = _transaction_path(paths, transaction_id)
    archive = paths.control_archive / f"STOP.{receipt.receipt_id}.{main_sha[:12]}"
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    existing = _load_transaction(transaction_path)
    if paths.stop.exists():
        if not paths.stop.is_file() or paths.stop.is_symlink():
            raise RuntimeError("activation requires a regular durable STOP control")
        stop_digest = sha256_digest(paths.stop.read_bytes())
    elif existing is not None:
        stop_digest = existing.stop_digest
    else:
        raise RuntimeError("activation requires durable STOP or a recoverable transaction")
    if existing is not None:
        expected = (
            existing.exact_main_sha == main_sha
            and existing.exact_tree_sha == tree_sha
            and existing.activation_receipt_digest == expected_receipt_digest
            and existing.canary_suite_digest == suite_digest
            and existing.stop_digest == stop_digest
            and existing.stop_archive_path == str(archive)
        )
        if not expected:
            raise RuntimeError("activation transaction identity was reused with different evidence")
        if existing.phase is ActivationPhase.ACTIVATED:
            if paths.stop.exists():
                raise RuntimeError("activated transaction conflicts with a recreated STOP control")
            _validate_archive(existing)
            return existing

    prepared = existing or ActivationTransaction(
        schema_version="3.1",
        transaction_id=transaction_id,
        phase=ActivationPhase.PREPARED,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        activation_receipt_id=receipt.receipt_id,
        activation_receipt_digest=expected_receipt_digest,
        canary_suite_path=str(suite_path),
        canary_suite_digest=suite_digest,
        preflight_digest=preflight_digest,
        stop_digest=stop_digest,
        stop_archive_path=str(archive),
        prepared_at=observed_now,
    )
    _write_transaction(transaction_path, prepared)
    if paths.stop.exists():
        _archive_stop(paths.stop, archive)
    else:
        _validate_archive(prepared)
    activated = prepared.model_copy(
        update={"phase": ActivationPhase.ACTIVATED, "activated_at": observed_now}
    )
    _write_transaction(transaction_path, activated)
    _validate_archive(activated)
    return activated


def activate_v31(
    *,
    repo_root: Path,
    canary_suite_path: Path,
    now: datetime | None = None,
    preflight: Callable[..., dict[str, object]] | None = None,
    installed_runtime_manifest_path: Path = Path(
        "/etc/traincapsule-controller/runtime-manifest.json"
    ),
    installed_runtime_loader: InstalledRuntimeLoader = _activation_runtime_bundle,
) -> ActivationTransaction:
    """Serialize the complete proof and STOP archival transition across processes."""

    resolved_root = repo_root.resolve()
    paths = resolve_v3_runtime_paths(resolved_root)
    with controller_process_lock(paths.state_root / "activation.lock"):
        return _activate_v31_locked(
            repo_root=resolved_root,
            canary_suite_path=canary_suite_path,
            now=now,
            preflight=preflight,
            installed_runtime_manifest_path=installed_runtime_manifest_path,
            installed_runtime_loader=installed_runtime_loader,
        )


ACTIVATION_CONTRACTS: dict[str, type[V3Model]] = {
    "activation-transaction": ActivationTransaction,
}
