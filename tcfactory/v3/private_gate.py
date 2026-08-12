"""Trusted, candidate-bound private-gate installation and receipt verification."""

from __future__ import annotations

import os
import subprocess
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from tcfactory.util import sha256_file
from tcfactory.v3.base import SHA_PATTERN, V3Model

PRIVATE_GATE_ROOT = Path("/var/lib/traincapsule-factory/private-gates")
PRIVATE_GATE_RUNNER = PRIVATE_GATE_ROOT / "run_private_gate.sh"
PRIVATE_GATE_PUBLIC_KEY = PRIVATE_GATE_ROOT / "trusted-public-key.pem"
PRIVATE_GATE_HEALTH_REJECTION = (
    "PRIVATE_GATE_REJECTED: candidate worktree does not match the exact candidate SHA\n"
)
FULL_RELEASE_SCOPE = (
    "factory-quality",
    "product-unit",
    "product-contract",
    "security",
    "source-of-truth-integrity",
    "packaging-install",
    "docs-and-schemas",
    "source-freshness",
)


class PrivateGateVerificationError(RuntimeError):
    pass


class PrivateGateHealthCheck(V3Model):
    version: Literal[3] = 3
    schema_id: Literal["traincapsule.private-gate-health/v3"] = (
        "traincapsule.private-gate-health/v3"
    )
    status: Literal["PASS_FAIL_CLOSED_PROBE"] = "PASS_FAIL_CLOSED_PROBE"
    expected_exit_code: Literal[1] = 1
    receipt_created: Literal[False] = False
    signature_created: Literal[False] = False


class PrivateGateReceipt(V3Model):
    version: Literal[3] = 3
    schema_id: Literal["traincapsule.private-gate-receipt/v3"] = (
        "traincapsule.private-gate-receipt/v3"
    )
    receipt_id: str = Field(pattern=r"^PGATE-[A-Z0-9_-]{8,96}$")
    candidate_sha: str = Field(pattern=SHA_PATTERN.pattern)
    work_item_id: str = Field(min_length=1, max_length=128)
    suite: Literal["full-release"] = "full-release"
    scope: list[str] = Field(min_length=len(FULL_RELEASE_SCOPE), max_length=len(FULL_RELEASE_SCOPE))
    runner_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runner_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    result_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision: Literal["PASSED"] = "PASSED"
    issued_at: datetime
    expires_at: datetime
    signature_algorithm: Literal["ed25519"] = "ed25519"
    key_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_scope_and_expiry(self) -> PrivateGateReceipt:
        if tuple(self.scope) != FULL_RELEASE_SCOPE:
            raise ValueError("private-gate scope must be the complete ordered release scope")
        issued = self.issued_at.astimezone(UTC)
        expires = self.expires_at.astimezone(UTC)
        if expires <= issued or expires - issued > timedelta(hours=24):
            raise ValueError("private-gate receipt expiry must be positive and at most 24 hours")
        return self


def _outside_repository(path: Path, repo_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return resolved
    raise PrivateGateVerificationError("private-gate trust material must be outside the repository")


def _assert_privileged_read_only(path: Path) -> None:
    for protected in (path, *path.parents):
        try:
            metadata = protected.stat()
        except OSError as exc:
            raise PrivateGateVerificationError(
                f"private-gate trust path is unavailable: {protected}"
            ) from exc
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise PrivateGateVerificationError(
                "private-gate runner/key and every parent must be root-owned and not writable"
            )


def _validate_public_key(public_key: Path) -> None:
    key_type = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkey",
            "-pubin",
            "-in",
            str(public_key),
            "-text",
            "-noout",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if key_type.returncode != 0 or "ED25519" not in (
        key_type.stdout + key_type.stderr
    ).upper():
        raise PrivateGateVerificationError("private-gate public key is not Ed25519")


def _verify_signature(receipt: Path, signature: Path, public_key: Path) -> None:
    _validate_public_key(public_key)
    verified = subprocess.run(
        [
            "/usr/bin/openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-rawin",
            "-in",
            str(receipt),
            "-sigfile",
            str(signature),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if verified.returncode != 0:
        raise PrivateGateVerificationError("private-gate receipt signature is invalid")


def validate_private_gate_installation(
    repo_root: Path,
    *,
    runner: Path = PRIVATE_GATE_RUNNER,
    public_key: Path = PRIVATE_GATE_PUBLIC_KEY,
) -> tuple[Path, Path]:
    resolved_runner = _outside_repository(runner, repo_root)
    resolved_key = _outside_repository(public_key, repo_root)
    for path in (resolved_runner, resolved_key):
        if not path.is_file():
            raise PrivateGateVerificationError(f"mandatory private-gate file is missing: {path}")
        _assert_privileged_read_only(path)
    if not resolved_runner.stat().st_mode & 0o111:
        raise PrivateGateVerificationError("private-gate runner is not executable")
    _validate_public_key(resolved_key)
    return resolved_runner, resolved_key


def validate_private_gate_runtime_health(
    repo_root: Path,
    runtime_state_root: Path,
    *,
    runner: Path = PRIVATE_GATE_RUNNER,
) -> PrivateGateHealthCheck:
    """Exercise the installed privileged helper without running gates or minting evidence."""

    resolved_runner, _ = validate_private_gate_installation(repo_root, runner=runner)
    probe_parent = runtime_state_root.resolve() / ".private-gate-health"
    probe_root = probe_parent / f"probe-{uuid4().hex}"
    probe_root.mkdir(parents=True, exist_ok=False)
    receipt = probe_root / "receipt.json"
    signature = probe_root / "receipt.json.sig"
    environment = os.environ.copy()
    environment.update(
        {
            "TCF_TASK_ID": "V3-HEALTH-000",
            "TCF_RUN_ID": f"private-gate-health-{uuid4().hex}",
            "TCF_CANDIDATE_SHA": "0" * 40,
            "TCF_CANDIDATE_WORKTREE": str(repo_root.resolve()),
            "TCF_PRIVATE_GATE_RECEIPT": str(receipt),
            "TCF_PRIVATE_GATE_SIGNATURE": str(signature),
        }
    )
    result = subprocess.run(
        [str(resolved_runner), "full-release", str(repo_root.resolve())],
        cwd=repo_root.resolve(),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    expected = (
        result.returncode == 1
        and result.stdout == ""
        and result.stderr == PRIVATE_GATE_HEALTH_REJECTION
        and not receipt.exists()
        and not signature.exists()
        and not any(probe_root.iterdir())
    )
    if not expected:
        if not any(probe_root.iterdir()):
            probe_root.rmdir()
            with suppress(OSError):
                probe_parent.rmdir()
        raise PrivateGateVerificationError(
            "private-gate runtime health probe did not fail closed with the exact contract"
        )
    probe_root.rmdir()
    with suppress(OSError):
        probe_parent.rmdir()
    return PrivateGateHealthCheck()


def verify_private_gate_receipt(
    *,
    repo_root: Path,
    runner: Path,
    public_key: Path,
    receipt_path: Path,
    signature_path: Path,
    result_path: Path,
    expected_candidate_sha: str,
    expected_work_item_id: str,
    now: datetime | None = None,
) -> PrivateGateReceipt:
    resolved_runner, resolved_key = validate_private_gate_installation(
        repo_root, runner=runner, public_key=public_key
    )
    if not receipt_path.is_file() or not signature_path.is_file() or not result_path.is_file():
        raise PrivateGateVerificationError("private-gate receipt, signature, or result is missing")
    _verify_signature(receipt_path, signature_path, resolved_key)
    try:
        receipt = PrivateGateReceipt.model_validate_json(
            receipt_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise PrivateGateVerificationError("private-gate receipt schema is invalid") from exc
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    if receipt.expires_at.astimezone(UTC) <= observed:
        raise PrivateGateVerificationError("private-gate receipt is expired")
    if receipt.issued_at.astimezone(UTC) > observed + timedelta(minutes=5):
        raise PrivateGateVerificationError("private-gate receipt was issued in the future")
    if receipt.candidate_sha != expected_candidate_sha:
        raise PrivateGateVerificationError("private-gate receipt candidate SHA mismatch")
    if receipt.work_item_id != expected_work_item_id:
        raise PrivateGateVerificationError("private-gate receipt work-item scope mismatch")
    if receipt.runner_digest != f"sha256:{sha256_file(resolved_runner)}":
        raise PrivateGateVerificationError("private-gate runner digest mismatch")
    if receipt.result_digest != f"sha256:{sha256_file(result_path)}":
        raise PrivateGateVerificationError("private-gate result digest mismatch")
    return receipt
