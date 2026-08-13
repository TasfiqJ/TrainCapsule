"""Stopped-state zero-human canary and activation-request supervisor."""

from __future__ import annotations

import json
import os
import pwd
import stat
from pathlib import Path
from typing import cast

from pydantic import Field

from ..util import atomic_write_bytes, sha256_file
from .activation import (
    ActivationTransaction,
    activate_v31,
    coordinate_activation_request,
)
from .base import DIGEST_PATTERN, V3Model
from .canaries import (
    CanaryStatus,
    MandatoryCanarySuite,
    run_mandatory_canaries,
    verify_mandatory_canary_suite,
)
from .runtime_paths import V3RuntimePaths, resolve_v3_runtime_paths

CONTROLLER_PRINCIPAL_POLICY = Path(
    "/etc/traincapsule-verifier/controller-principal.json"
)
CONTROLLER_START_OUTBOX = Path(
    "/var/lib/traincapsule-verifier/controller-start-outbox"
)


class ControllerStartRequest(V3Model):
    schema_version: str = Field(pattern=r"^3\.1$")
    transaction_id: str = Field(pattern=r"^ACTIVATE-[A-Z0-9._:-]{3,127}$")
    transaction_path: str = Field(min_length=1, max_length=4096)
    transaction_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    transaction: ActivationTransaction
    activation_receipt_id: str = Field(min_length=3, max_length=128)
    activation_receipt_digest: str = Field(pattern=DIGEST_PATTERN.pattern)
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")


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


def run_activation_supervisor(
    *,
    repo_root: Path,
    runner_executable: Path = Path("/usr/local/bin/traincapsule-v31-run-canary"),
) -> str:
    """Advance the receipt-gated stopped activation state machine without self-authority."""

    repo_root = repo_root.resolve(strict=True)
    paths = resolve_v3_runtime_paths(repo_root)
    if paths.pause.exists() or paths.hard_stuck.exists():
        return "STOPPED_CONTROL"
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
