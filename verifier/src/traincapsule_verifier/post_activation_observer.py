"""Independent root observer for the seven mandatory post-activation invariants."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .controller_start_broker import (
    controller_active_pid,
    restore_runtime_stop,
    run_systemctl,
)
from .filesystem import open_trusted_root, read_bounded_file
from .models import ActivationReceipt
from .public_verifier import PublicVerifier

ROOT = Path("/var/lib/traincapsule-verifier")
CONFIG = Path("/etc/traincapsule-verifier")


class _Strict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        alias_generator=lambda name: "".join(
            [name.split("_")[0], *(part.title() for part in name.split("_")[1:])]
        ),
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class ObservationId(StrEnum):
    COMPLETE_AUTONOMOUS_CYCLE = "complete_autonomous_cycle"
    IDLE_CYCLE = "idle_cycle"
    EXTERNAL_WAIT_ISOLATED_CYCLE = "external_wait_isolated_cycle"
    SERVICE_RESTART = "service_restart"
    NEXT_WORK_SCHEDULING = "next_work_scheduling"
    NO_DIRECT_MAIN_PUSH = "no_direct_main_push"
    NO_HUMAN_CLICK = "no_human_click"


class _Policy(_Strict):
    schema_version: Literal["3.1"]
    service_name: Literal["traincapsule-controller.service"]
    repository_root: Literal["/var/lib/traincapsule-verifier/repository-boundary"]
    runtime_root: Literal["/var/lib/traincapsule-runtime"]
    start_journal_root: Literal[
        "/var/lib/traincapsule-verifier/controller-start-journal"
    ]
    observation_root: Literal[
        "/var/lib/traincapsule-verifier/post-activation-observations"
    ]
    maximum_observation_seconds: int = Field(ge=60, le=86400)


class _RuntimeEvent(_Strict):
    schema_version: Literal["3.1"]
    event_id: ObservationId
    activation_receipt_id: str
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    sequence: int = Field(ge=1)
    occurred_at: str
    artifact_path: str
    artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class _Observation(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    observation_id: str
    activation_receipt_id: str
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    evidence_artifacts: dict[ObservationId, str]
    evidence_digests: dict[ObservationId, str]
    started_at: str
    completed_at: str

    @model_validator(mode="after")
    def exact_roster(self) -> _Observation:
        if set(self.evidence_artifacts) != set(ObservationId) or set(
            self.evidence_digests
        ) != set(ObservationId):
            raise ValueError("post-activation observation roster mismatch")
        return self


class _FailureJournal(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    activation_receipt_id: str
    phase: Literal["PREPARED", "STOPPED"]
    reason: str
    recorded_at: str


def _atomic(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.pending")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError("post-activation repository identity query failed")
    return result.stdout.strip()


def _fail_closed(policy: _Policy, receipt: ActivationReceipt, reason: str) -> None:
    journal_path = (
        Path(policy.observation_root)
        / "failure-journal"
        / f"{receipt.receipt_id}.json"
    )
    prepared = _FailureJournal(
        activation_receipt_id=receipt.receipt_id,
        phase="PREPARED",
        reason=reason[:1000],
        recorded_at=datetime.now(UTC).isoformat(),
    )
    _atomic(journal_path, canonical_json_bytes(prepared))
    run_systemctl("stop", policy.service_name, timeout=60)
    restore_runtime_stop(Path(policy.runtime_root))
    stopped = prepared.model_copy(
        update={"phase": "STOPPED", "recorded_at": datetime.now(UTC).isoformat()}
    )
    _atomic(journal_path, canonical_json_bytes(stopped))


def _event_evidence(
    policy: _Policy,
    receipt: ActivationReceipt,
    *,
    main_sha: str,
    tree_sha: str,
) -> tuple[dict[ObservationId, str], dict[ObservationId, str]]:
    command = [
        "/usr/bin/journalctl",
        "--unit",
        policy.service_name,
        "--output=json",
        "--no-pager",
        f"--since={receipt.issued_at.isoformat()}",
    ]
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise ValueError("controller journal observation failed")
    events: dict[ObservationId, _RuntimeEvent] = {}
    for line in result.stdout.splitlines():
        parsed: object = json.loads(line)
        if not isinstance(parsed, dict):
            continue
        message = cast(dict[str, object], parsed).get("MESSAGE")
        if not isinstance(message, str) or not message.startswith("TCF_V31_EVENT "):
            continue
        event = _RuntimeEvent.model_validate_json(
            message.removeprefix("TCF_V31_EVENT "), strict=True
        )
        if (
            event.activation_receipt_id == receipt.receipt_id
            and event.activation_receipt_digest == model_digest(receipt)
            and event.exact_main_sha == main_sha
            and event.exact_tree_sha == tree_sha
        ):
            prior = events.get(event.event_id)
            if prior is not None and event.sequence <= prior.sequence:
                raise ValueError("post-activation event sequence is not monotonic")
            events[event.event_id] = event
    if set(events) != set(ObservationId):
        raise ValueError("post-activation journal omits mandatory observed events")
    evidence_root = Path(policy.observation_root) / receipt.receipt_id / "evidence"
    artifacts: dict[ObservationId, str] = {}
    digests: dict[ObservationId, str] = {}
    for event_id, event in events.items():
        artifact = Path(event.artifact_path).resolve(strict=True)
        if not artifact.is_relative_to(Path(policy.runtime_root)) or artifact.is_symlink():
            raise ValueError("post-activation event artifact escapes runtime root")
        raw = artifact.read_bytes()
        if sha256_digest(raw) != event.artifact_digest:
            raise ValueError("post-activation event artifact digest mismatch")
        target = evidence_root / f"{event_id.value}.json"
        _atomic(target, raw)
        artifacts[event_id] = str(target.relative_to(evidence_root.parent))
        digests[event_id] = sha256_digest(raw)
    return artifacts, digests


def observe() -> Path:
    if os.geteuid() != 0:
        raise ValueError("post-activation observer requires root")
    with open_trusted_root(CONFIG, expected_uid=0) as config:
        policy = _Policy.model_validate_json(
            read_bounded_file(config, "post-activation-policy.json"), strict=True
        )
    with open_trusted_root(ROOT / "activation", expected_uid=0) as activation:
        receipt = ActivationReceipt.model_validate_json(
            read_bounded_file(activation, "current.json"), strict=True
        )
    started = datetime.now(UTC)
    try:
        with PublicVerifier.from_public_roots(
            repository_root=Path(policy.repository_root),
            config_root=CONFIG,
            state_root=ROOT,
            receipt_root=ROOT / "receipts",
            expected_owner_uid=0,
        ) as verifier:
            verifier.authorize_activation(
                receipt,
                main_sha=receipt.verified_main_sha,
                source_generation_id=receipt.source_generation_id,
                source_generation_digest=receipt.source_generation_digest,
                controller_binary_digest=receipt.controller_binary_digest,
                controller_config_digest=receipt.controller_config_digest,
            )
        if controller_active_pid(policy.service_name) is None:
            raise ValueError("controller service is not active")
        start_journal = (
            Path(policy.start_journal_root)
            / f"ACTIVATE-{receipt.receipt_id}.json"
        )
        start_payload: object = json.loads(start_journal.read_bytes())
        if not isinstance(start_payload, dict) or cast(
            dict[str, object], start_payload
        ).get("phase") != "STARTED":
            raise ValueError("root start broker has no terminal STARTED journal")
        repo = Path(policy.repository_root)
        main_sha = _git(repo, "rev-parse", "HEAD")
        tree_sha = _git(repo, "rev-parse", "HEAD^{tree}")
        if main_sha != receipt.verified_main_sha:
            raise ValueError("post-activation exact main changed")
        artifacts, digests = _event_evidence(
            policy, receipt, main_sha=main_sha, tree_sha=tree_sha
        )
        completed = datetime.now(UTC)
        if (completed - started).total_seconds() > policy.maximum_observation_seconds:
            raise ValueError("post-activation observation exceeded bounded window")
        observation = _Observation(
            observation_id=f"OBS-{receipt.receipt_id}",
            activation_receipt_id=receipt.receipt_id,
            activation_receipt_digest=model_digest(receipt),
            exact_main_sha=main_sha,
            exact_tree_sha=tree_sha,
            evidence_artifacts=artifacts,
            evidence_digests=digests,
            started_at=started.isoformat(),
            completed_at=completed.isoformat(),
        )
        target = Path(policy.observation_root) / receipt.receipt_id / "observation.json"
        _atomic(target, canonical_json_bytes(observation))
        return target
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        _fail_closed(policy, receipt, str(error))
        raise


def main() -> int:
    if sys.argv[1:] != ["observe"]:
        print("usage: traincapsule-verifier-post-activation observe", file=sys.stderr)
        return 2
    try:
        observe()
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("post-activation observation failed closed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
