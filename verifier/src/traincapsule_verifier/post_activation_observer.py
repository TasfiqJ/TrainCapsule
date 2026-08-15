"""Independent root observer for the seven mandatory post-activation invariants."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Literal, cast

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .canonical import canonical_json_bytes, model_digest, sha256_digest
from .controller_start_broker import (
    controller_active_pid,
    restore_runtime_stop,
    run_systemctl,
)
from .filesystem import open_trusted_root, read_bounded_file
from .models import ActivationReceipt
from .public_verifier import PublicVerificationError, PublicVerifier

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


class _ObservationPending(ValueError):
    """The valid observation window is still open and its roster is incomplete."""


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
    refresh_completion_root: Literal[
        "/var/lib/traincapsule-verifier/activation-refresh-inbox"
    ]
    refresh_retirement_root: Literal[
        "/var/lib/traincapsule-verifier/activation-refresh-retirement"
    ]
    runtime_manifest_path: Literal[
        "/etc/traincapsule-controller/runtime-manifest.json"
    ]
    maximum_observation_seconds: int = Field(ge=60, le=86400)
    renewal_safety_window_seconds: int = Field(ge=60, le=3600)


class _RuntimeEvent(_Strict):
    schema_version: Literal["3.1"]
    event_id: ObservationId
    activation_receipt_id: str
    activation_receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    exact_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    exact_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    sequence: int = Field(ge=1)
    occurred_at: AwareDatetime
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


class _RefreshCompletion(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str = Field(pattern=r"^[0-9a-f]{40}-[0-9a-f]{16}$")
    handoff_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    previous_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    required_main_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_generation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    source_generation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generation_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    runtime_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    environment_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_config_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    committed_at: AwareDatetime


class _RetirementJournal(_Strict):
    schema_version: Literal["3.1"] = "3.1"
    transaction_id: str
    phase: Literal["PREPARED", "RETIRED"]
    completion_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    observation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    activation_receipt_id: str
    required_main_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    recorded_at: AwareDatetime


def _require_authority_renewal_margin(
    policy: _Policy,
    receipt: ActivationReceipt,
    *,
    machine_policy_expires_at: AwareDatetime,
    revocations_expire_at: AwareDatetime,
    now: datetime,
) -> None:
    deadline = min(
        receipt.expires_at.astimezone(UTC),
        machine_policy_expires_at.astimezone(UTC),
        revocations_expire_at.astimezone(UTC),
    )
    remaining = (deadline - now.astimezone(UTC)).total_seconds()
    if remaining <= policy.renewal_safety_window_seconds:
        raise PublicVerificationError(
            "active authority entered the mandatory pre-expiry renewal safety window"
        )


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


def _completion_at(
    path: Path, *, authority_uid: int = 0
) -> tuple[_RefreshCompletion, bytes]:
    metadata = path.stat(follow_symlinks=False)
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != authority_uid
        or stat.S_IMODE(metadata.st_mode) != 0o440
    ):
        raise ValueError("refresh completion claim boundary is invalid")
    raw = path.read_bytes()
    completion = _RefreshCompletion.model_validate_json(raw, strict=True)
    if raw != canonical_json_bytes(completion):
        raise ValueError("refresh completion claim is not canonical")
    if path.name != f"{completion.required_main_sha}-{completion.transaction_id}.json":
        raise ValueError("refresh completion claim filename is not exact")
    return completion, raw


def _matching_refresh_completion(
    policy: _Policy,
    receipt: ActivationReceipt,
    *,
    main_sha: str,
    tree_sha: str,
    authority_uid: int = 0,
) -> tuple[Path, _RefreshCompletion, bytes] | None:
    root = Path(policy.refresh_completion_root)
    matches: list[tuple[Path, _RefreshCompletion, bytes]] = []
    for path in sorted(root.glob("*.json")):
        completion, raw = _completion_at(path, authority_uid=authority_uid)
        if (
            completion.required_main_sha == main_sha
            and completion.required_main_tree_sha == tree_sha
            and completion.source_generation_id == receipt.source_generation_id
            and completion.source_generation_digest == receipt.source_generation_digest
            and completion.effective_config_digest == receipt.controller_config_digest
        ):
            matches.append((path, completion, raw))
    if len(matches) > 1:
        raise ValueError("multiple refresh completions match post-activation identity")
    return matches[0] if matches else None


def _retire_refresh_completion(
    policy: _Policy,
    receipt: ActivationReceipt,
    observation: _Observation,
    *,
    fail_hook: Callable[[str], None] | None = None,
    authority_uid: int = 0,
) -> Path | None:
    matched = _matching_refresh_completion(
        policy,
        receipt,
        main_sha=observation.exact_main_sha,
        tree_sha=observation.exact_tree_sha,
        authority_uid=authority_uid,
    )
    retirement_root = Path(policy.refresh_retirement_root)
    retired_root = retirement_root / "retired"
    journal_root = retirement_root / "journals"
    if matched is None:
        retired_candidates: list[tuple[Path, _RefreshCompletion, bytes]] = []
        for path in sorted(retired_root.glob("*.json")):
            completion, raw = _completion_at(path, authority_uid=authority_uid)
            if (
                completion.required_main_sha == observation.exact_main_sha
                and completion.required_main_tree_sha == observation.exact_tree_sha
                and completion.source_generation_id == receipt.source_generation_id
                and completion.source_generation_digest == receipt.source_generation_digest
                and completion.effective_config_digest == receipt.controller_config_digest
            ):
                retired_candidates.append((path, completion, raw))
        if not retired_candidates:
            return None
        if len(retired_candidates) != 1:
            raise ValueError("multiple retired refresh completions match activation")
        retired_path, completion, raw = retired_candidates[0]
        claim_path: Path | None = None
    else:
        claim_path, completion, raw = matched
        retired_path = retired_root / claim_path.name
    runtime_raw = Path(policy.runtime_manifest_path).read_bytes()
    if sha256_digest(runtime_raw) != completion.runtime_manifest_digest:
        raise ValueError("refresh completion runtime changed before retirement")
    completion_digest = sha256_digest(raw)
    observation_digest = model_digest(observation)
    journal_path = journal_root / f"{completion.transaction_id}.json"
    prepared = _RetirementJournal(
        transaction_id=completion.transaction_id,
        phase="PREPARED",
        completion_digest=completion_digest,
        observation_digest=observation_digest,
        activation_receipt_id=receipt.receipt_id,
        required_main_sha=completion.required_main_sha,
        recorded_at=datetime.now(UTC),
    )
    if journal_path.is_file():
        existing = _RetirementJournal.model_validate_json(
            journal_path.read_bytes(), strict=True
        )
        if existing.model_copy(
            update={"phase": prepared.phase, "recorded_at": prepared.recorded_at}
        ) != prepared:
            raise ValueError("refresh completion retirement identity conflicts")
        if existing.phase == "RETIRED":
            if not retired_path.is_file() or retired_path.read_bytes() != raw:
                raise ValueError("retired refresh completion bytes changed")
            if claim_path is not None:
                if claim_path.read_bytes() != raw:
                    raise ValueError("refresh completion claim changed during retirement")
                claim_path.unlink()
            return retired_path
    else:
        _atomic(journal_path, canonical_json_bytes(prepared))
    if fail_hook is not None:
        fail_hook("PREPARED")
    retired_path.parent.mkdir(parents=True, exist_ok=True)
    if retired_path.exists():
        if retired_path.read_bytes() != raw:
            raise ValueError("retired refresh completion identity conflicts")
    else:
        _atomic(retired_path, raw)
        retired_path.chmod(0o440)
    if fail_hook is not None:
        fail_hook("COPIED")
    retired = prepared.model_copy(
        update={"phase": "RETIRED", "recorded_at": datetime.now(UTC)}
    )
    _atomic(journal_path, canonical_json_bytes(retired))
    if fail_hook is not None:
        fail_hook("RETIRED")
    if claim_path is not None:
        if claim_path.read_bytes() != raw:
            raise ValueError("refresh completion claim changed during retirement")
        claim_path.unlink()
    return retired_path


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
    journal_since = receipt.issued_at.astimezone(UTC).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
    command = [
        "/usr/bin/journalctl",
        "--unit",
        policy.service_name,
        "--output=json",
        "--no-pager",
        f"--since={journal_since}",
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
            if prior is not None:
                raise ValueError("post-activation journal contains duplicate events")
            events[event.event_id] = event
    observed_now = datetime.now(UTC)
    if set(events) != set(ObservationId):
        elapsed = (
            observed_now - receipt.issued_at.astimezone(UTC)
        ).total_seconds()
        if elapsed < policy.maximum_observation_seconds:
            raise _ObservationPending(
                "post-activation journal is awaiting mandatory observed events"
            )
        raise ValueError(
            "post-activation journal omits mandatory observed events after "
            "the bounded observation window"
        )
    ordered = list(ObservationId)
    prior_time = receipt.issued_at
    for expected_sequence, event_id in enumerate(ordered, start=1):
        event = events[event_id]
        occurred_at = event.occurred_at.astimezone(UTC)
        if event.sequence != expected_sequence:
            raise ValueError("post-activation event sequence is not exact")
        if occurred_at < prior_time or occurred_at > observed_now:
            raise ValueError("post-activation event timestamps are not monotonic")
        prior_time = occurred_at
    if (
        prior_time - receipt.issued_at.astimezone(UTC)
    ).total_seconds() > policy.maximum_observation_seconds:
        raise ValueError("post-activation event timeline exceeded bounded window")
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


def _verified_existing_observation(
    policy: _Policy,
    receipt: ActivationReceipt,
    *,
    main_sha: str,
    tree_sha: str,
) -> tuple[Path, _Observation] | None:
    target = Path(policy.observation_root) / receipt.receipt_id / "observation.json"
    if not target.exists():
        return None
    if target.is_symlink() or not target.is_file():
        raise ValueError("post-activation observation path is indirect")
    raw = target.read_bytes()
    observation = _Observation.model_validate_json(raw, strict=True)
    if raw != canonical_json_bytes(observation):
        raise ValueError("post-activation observation is not canonical")
    if (
        observation.activation_receipt_id != receipt.receipt_id
        or observation.activation_receipt_digest != model_digest(receipt)
        or observation.exact_main_sha != main_sha
        or observation.exact_tree_sha != tree_sha
    ):
        raise ValueError("post-activation observation identity changed")
    evidence_root = target.parent
    for event_id in ObservationId:
        artifact = (evidence_root / observation.evidence_artifacts[event_id]).resolve(
            strict=True
        )
        if not artifact.is_relative_to(evidence_root) or artifact.is_symlink():
            raise ValueError("post-activation observation evidence escapes its root")
        if sha256_digest(artifact.read_bytes()) != observation.evidence_digests[event_id]:
            raise ValueError("post-activation observation evidence changed")
    return target, observation


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
            state_root=CONFIG,
            receipt_root=ROOT / "receipts",
            expected_owner_uid=0,
        ) as verifier:
            machine_receipt = verifier.load_machine_receipt(
                receipt.machine_policy_receipt_id
            )
            _require_authority_renewal_margin(
                policy,
                receipt,
                machine_policy_expires_at=machine_receipt.expires_at,
                revocations_expire_at=verifier.revocations.expires_at,
                now=started,
            )
            verifier.authorize_activation(
                receipt,
                main_sha=receipt.verified_main_sha,
                source_generation_id=receipt.source_generation_id,
                source_generation_digest=receipt.source_generation_digest,
                controller_binary_digest=receipt.controller_binary_digest,
                controller_config_digest=receipt.controller_config_digest,
            )
        repo = Path(policy.repository_root)
        main_sha = _git(repo, "rev-parse", "HEAD")
        tree_sha = _git(repo, "rev-parse", "HEAD^{tree}")
        if main_sha != receipt.verified_main_sha:
            raise ValueError("post-activation exact main changed")
        existing = _verified_existing_observation(
            policy, receipt, main_sha=main_sha, tree_sha=tree_sha
        )
        if existing is not None:
            target, observation = existing
            _retire_refresh_completion(policy, receipt, observation)
            return target
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
        _retire_refresh_completion(policy, receipt, observation)
        return target
    except _ObservationPending:
        raise
    except (
        OSError,
        ValueError,
        subprocess.TimeoutExpired,
        PublicVerificationError,
    ) as error:
        _fail_closed(policy, receipt, str(error))
        raise


def main() -> int:
    if sys.argv[1:] != ["observe"]:
        print("usage: traincapsule-verifier-post-activation observe", file=sys.stderr)
        return 2
    try:
        observe()
        return 0
    except _ObservationPending:
        print("post-activation observation is pending", file=sys.stderr)
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired, PublicVerificationError):
        print("post-activation observation failed closed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
