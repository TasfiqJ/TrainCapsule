from __future__ import annotations

import json
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


def _policy(tmp_path: Path) -> observer._Policy:  # pyright: ignore[reportPrivateUsage]
    return observer._Policy.model_construct(  # pyright: ignore[reportPrivateUsage]
        schema_version="3.1",
        service_name="traincapsule-controller.service",
        repository_root="/var/lib/traincapsule-verifier/repository-boundary",
        runtime_root=str(tmp_path / "runtime"),
        start_journal_root=str(tmp_path / "start"),
        observation_root=str(tmp_path / "observations"),
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
    receipt = SimpleNamespace(
        receipt_id="ACT-TEST",
        issued_at=datetime.now(UTC) - timedelta(minutes=1),
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
            occurred_at="2026-08-12T18:00:00Z",
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
    lines.pop()
    with pytest.raises(ValueError, match="omits mandatory"):
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
