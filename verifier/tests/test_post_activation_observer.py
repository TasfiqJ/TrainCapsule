from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError
from traincapsule_verifier import post_activation_observer as observer
from traincapsule_verifier.bootstrap import systemd_unit_content
from traincapsule_verifier.canonical import sha256_digest

DIGEST = "sha256:" + "a" * 64


def _sandbox_writable(unit: str, target: str) -> bool:
    target_path = Path(target)
    return any(
        target_path == Path(root) or target_path.is_relative_to(Path(root))
        for root in (
            line.split("=", 1)[1]
            for line in unit.splitlines()
            if line.startswith("ReadWritePaths=")
        )
    )


def _policy(tmp_path: Path) -> observer._Policy:  # pyright: ignore[reportPrivateUsage]
    return observer._Policy.model_construct(  # pyright: ignore[reportPrivateUsage]
        schema_version="3.1",
        service_name="traincapsule-controller.service",
        repository_root="/var/lib/traincapsule-verifier/repository-boundary",
        runtime_root=str(tmp_path / "runtime"),
        start_journal_root=str(tmp_path / "start"),
        observation_root=str(tmp_path / "observations"),
        refresh_completion_root=str(tmp_path / "refresh-inbox"),
        refresh_retirement_root=str(tmp_path / "retirement"),
        runtime_manifest_path=str(tmp_path / "runtime-manifest.json"),
        maximum_observation_seconds=3600,
    )


def test_observation_contract_rejects_missing_or_forged_roster() -> None:
    with pytest.raises(ValidationError, match="roster mismatch"):
        observer._Observation(  # pyright: ignore[reportPrivateUsage]
            observation_id="OBS-ACT-TEST",
            activation_receipt_id="ACT-TEST",
            activation_receipt_digest=DIGEST,
            exact_main_sha="a" * 40,
            exact_tree_sha="b" * 40,
            evidence_artifacts={},
            evidence_digests={},
            started_at="2026-08-12T18:00:00Z",
            completed_at="2026-08-12T18:00:01Z",
        )


def test_failure_is_journaled_then_stops_and_restores_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(tmp_path)
    calls: list[tuple[str, ...]] = []

    def systemctl(*args: str, timeout: int = 30) -> SimpleNamespace:
        del timeout
        calls.append(args)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(observer, "run_systemctl", systemctl)
    receipt = cast(object, SimpleNamespace(receipt_id="ACT-TEST"))
    observer._fail_closed(  # pyright: ignore[reportPrivateUsage]
        policy, cast(observer.ActivationReceipt, receipt), "missing mandatory event"
    )
    assert calls == [("stop", "traincapsule-controller.service")]
    assert (tmp_path / "runtime/STOP").read_bytes() == (
        b"controller start broker rollback\n"
    )
    journal = json.loads(
        (tmp_path / "observations/failure-journal/ACT-TEST.json").read_bytes()
    )
    assert journal["phase"] == "STOPPED"


def test_seven_events_require_exact_receipt_tree_monotonicity_and_artifact_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = _policy(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    issued_at = datetime.now(UTC) - timedelta(minutes=1)
    receipt = SimpleNamespace(
        receipt_id="ACT-TEST",
        issued_at=issued_at,
    )
    receipt_digest = DIGEST
    def digest_receipt(_receipt: object) -> str:
        return receipt_digest

    monkeypatch.setattr(observer, "model_digest", digest_receipt)
    lines: list[str] = []
    for sequence, event_id in enumerate(observer.ObservationId, start=1):
        artifact = runtime / f"{event_id.value}.json"
        artifact.write_text(f'{{"event":"{event_id.value}"}}\n', encoding="utf-8")
        event = observer._RuntimeEvent(  # pyright: ignore[reportPrivateUsage]
            schema_version="3.1",
            event_id=event_id,
            activation_receipt_id="ACT-TEST",
            activation_receipt_digest=receipt_digest,
            exact_main_sha="a" * 40,
            exact_tree_sha="b" * 40,
            sequence=sequence,
            occurred_at=issued_at + timedelta(seconds=sequence),
            artifact_path=str(artifact),
            artifact_digest=sha256_digest(artifact.read_bytes()),
        )
        lines.append(
            json.dumps(
                {"MESSAGE": "TCF_V31_EVENT " + event.model_dump_json(by_alias=True)}
            )
        )
    def run_journal(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="\n".join(lines))

    monkeypatch.setattr(observer.subprocess, "run", run_journal)
    artifacts, digests = observer._event_evidence(  # pyright: ignore[reportPrivateUsage]
        policy,
        cast(observer.ActivationReceipt, receipt),
        main_sha="a" * 40,
        tree_sha="b" * 40,
    )
    assert set(artifacts) == set(observer.ObservationId)
    assert set(digests) == set(observer.ObservationId)
    complete_lines = list(lines)
    lines.pop()
    with pytest.raises(ValueError, match="omits mandatory"):
        observer._event_evidence(  # pyright: ignore[reportPrivateUsage]
            policy,
            cast(observer.ActivationReceipt, receipt),
            main_sha="a" * 40,
            tree_sha="b" * 40,
        )

    lines[:] = complete_lines
    for index, sequence in ((0, 2), (1, 1)):
        outer = cast(dict[str, str], json.loads(lines[index]))
        event = cast(
            dict[str, object],
            json.loads(outer["MESSAGE"].removeprefix("TCF_V31_EVENT ")),
        )
        event["sequence"] = sequence
        lines[index] = json.dumps(
            {"MESSAGE": "TCF_V31_EVENT " + json.dumps(event, separators=(",", ":"))}
        )
    with pytest.raises(ValueError, match="sequence is not exact"):
        observer._event_evidence(  # pyright: ignore[reportPrivateUsage]
            policy,
            cast(observer.ActivationReceipt, receipt),
            main_sha="a" * 40,
            tree_sha="b" * 40,
        )
    lines[:] = complete_lines + [complete_lines[0]]
    with pytest.raises(ValueError, match="duplicate events"):
        observer._event_evidence(  # pyright: ignore[reportPrivateUsage]
            policy,
            cast(observer.ActivationReceipt, receipt),
            main_sha="a" * 40,
            tree_sha="b" * 40,
        )
    lines[:] = complete_lines
    outer = cast(dict[str, str], json.loads(lines[-1]))
    stale = cast(
        dict[str, object],
        json.loads(outer["MESSAGE"].removeprefix("TCF_V31_EVENT ")),
    )
    stale["occurredAt"] = (issued_at - timedelta(seconds=1)).isoformat()
    lines[-1] = json.dumps(
        {"MESSAGE": "TCF_V31_EVENT " + json.dumps(stale, separators=(",", ":"))}
    )
    with pytest.raises(ValueError, match="timestamps are not monotonic"):
        observer._event_evidence(  # pyright: ignore[reportPrivateUsage]
            policy,
            cast(observer.ActivationReceipt, receipt),
            main_sha="a" * 40,
            tree_sha="b" * 40,
        )


def test_post_activation_unit_is_root_owned_automatic_and_cannot_start_controller() -> None:
    service = systemd_unit_content(unit="post-activation-observer").decode()
    timer = systemd_unit_content(unit="post-activation-observer-timer").decode()
    assert "User=root" in service
    assert "traincapsule-verifier-post-activation observe" in service
    assert "systemctl start" not in service
    assert "Persistent=true" in timer
    assert "ReadWritePaths=/var/lib/traincapsule-verifier/activation-refresh-inbox" in service
    assert (
        "ReadWritePaths=/var/lib/traincapsule-verifier/activation-refresh-retirement"
        in service
    )
    activation = systemd_unit_content(unit="activation-supervisor").decode()
    required = (
        "ReadWritePaths=/var/lib/traincapsule-verifier/controller-start-outbox"
    )
    target = "/var/lib/traincapsule-verifier/controller-start-outbox/start.json"
    assert _sandbox_writable(activation, target)
    assert not _sandbox_writable(activation.replace(required + "\n", ""), target)


def test_refresh_completion_retires_only_after_observation_and_replays_crash(
    tmp_path: Path,
) -> None:
    policy = _policy(tmp_path)
    completion_root = Path(policy.refresh_completion_root)
    completion_root.mkdir()
    Path(policy.runtime_manifest_path).write_bytes(b"runtime-manifest\n")
    runtime_digest = sha256_digest(Path(policy.runtime_manifest_path).read_bytes())
    completion = observer._RefreshCompletion(  # pyright: ignore[reportPrivateUsage]
        transaction_id="a" * 40 + "-" + "1" * 16,
        handoff_digest=DIGEST,
        previous_main_sha="c" * 40,
        required_main_sha="a" * 40,
        required_main_tree_sha="b" * 40,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST,
        generation_manifest_digest=DIGEST,
        runtime_manifest_digest=runtime_digest,
        environment_digest=DIGEST,
        effective_config_digest=DIGEST,
        snapshot_manifest_digest=DIGEST,
        committed_at=datetime.now(UTC),
    )
    claim = completion_root / f"{'a' * 40}-{completion.transaction_id}.json"
    claim.write_bytes(observer.canonical_json_bytes(completion))
    claim.chmod(0o440)
    receipt = cast(
        observer.ActivationReceipt,
        SimpleNamespace(
            receipt_id="ACT-TEST",
            source_generation_id=completion.source_generation_id,
            source_generation_digest=completion.source_generation_digest,
            controller_config_digest=completion.effective_config_digest,
        ),
    )
    roster = {event_id: f"evidence/{event_id.value}.json" for event_id in observer.ObservationId}
    digests = {event_id: DIGEST for event_id in observer.ObservationId}
    observation = observer._Observation(  # pyright: ignore[reportPrivateUsage]
        observation_id="OBS-ACT-TEST",
        activation_receipt_id="ACT-TEST",
        activation_receipt_digest=DIGEST,
        exact_main_sha=completion.required_main_sha,
        exact_tree_sha=completion.required_main_tree_sha,
        evidence_artifacts=roster,
        evidence_digests=digests,
        started_at=datetime.now(UTC).isoformat(),
        completed_at=datetime.now(UTC).isoformat(),
    )

    def crash_after_copy(phase: str) -> None:
        if phase == "COPIED":
            raise RuntimeError("simulated crash")

    with pytest.raises(RuntimeError, match="simulated crash"):
        observer._retire_refresh_completion(  # pyright: ignore[reportPrivateUsage]
            policy,
            receipt,
            observation,
            fail_hook=crash_after_copy,
            authority_uid=os.geteuid(),
        )
    assert claim.exists()
    retired = observer._retire_refresh_completion(  # pyright: ignore[reportPrivateUsage]
        policy,
        receipt,
        observation,
        authority_uid=os.geteuid(),
    )
    assert retired is not None and retired.read_bytes() == observer.canonical_json_bytes(
        completion
    )
    assert not claim.exists()
    journal = json.loads(
        (
            Path(policy.refresh_retirement_root)
            / "journals"
            / f"{completion.transaction_id}.json"
        ).read_bytes()
    )
    assert journal["phase"] == "RETIRED"
