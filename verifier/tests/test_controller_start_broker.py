from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from traincapsule_verifier import controller_start_broker as broker
from traincapsule_verifier.bootstrap import (
    controller_start_policy_content,
    post_activation_policy_content,
    production_install_manifest,
    systemd_unit_content,
)
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest

DIGEST = "sha256:" + "a" * 64


def _sandbox_writable(unit: str, target: str) -> bool:
    writable = [
        line.split("=", 1)[1]
        for line in unit.splitlines()
        if line.startswith("ReadWritePaths=")
    ]
    target_path = Path(target)
    return any(
        target_path == Path(root) or target_path.is_relative_to(Path(root))
        for root in writable
    )


def _transaction() -> dict[str, object]:
    return {
        "schemaVersion": "3.1",
        "transactionId": "ACTIVATE-ACT-TEST",
        "phase": "ACTIVATED",
        "exactMainSha": "a" * 40,
        "exactTreeSha": "b" * 40,
        "activationReceiptId": "ACT-TEST",
        "activationReceiptDigest": DIGEST,
        "canarySuitePath": "/var/lib/traincapsule-runtime/canary-results/RUN/suite.json",
        "canarySuiteDigest": DIGEST,
        "preflightDigest": DIGEST,
        "autonomyEnabled": True,
        "stopDigest": DIGEST,
        "stopArchivePath": "/var/lib/traincapsule-runtime/control-archive/STOP",
        "preparedAt": "2026-08-12T18:00:00Z",
        "activatedAt": "2026-08-12T18:00:01Z",
    }


def test_start_request_requires_exact_terminal_transaction_digest() -> None:
    transaction = broker._Transaction.model_validate(  # pyright: ignore[reportPrivateUsage]
        _transaction(), strict=True
    )
    payload = {
        "schemaVersion": "3.1",
        "transactionId": transaction.transaction_id,
        "transactionPath": "/var/lib/traincapsule-runtime/activation-transactions/a.json",
        "transactionDigest": sha256_digest(canonical_json_bytes(transaction)),
        "transaction": transaction.model_dump(mode="json", by_alias=True),
        "activationReceiptId": transaction.activation_receipt_id,
        "activationReceiptDigest": transaction.activation_receipt_digest,
        "exactMainSha": transaction.exact_main_sha,
    }
    broker._StartRequest.model_validate(payload, strict=True)  # pyright: ignore[reportPrivateUsage]
    payload["transactionDigest"] = "sha256:" + "b" * 64
    with pytest.raises(ValidationError, match="transaction binding mismatch"):
        broker._StartRequest.model_validate(payload, strict=True)  # pyright: ignore[reportPrivateUsage]
    payload["transactionDigest"] = DIGEST
    nested = dict(_transaction())
    nested["phase"] = "PREPARED"
    payload["transaction"] = nested
    with pytest.raises(ValidationError):
        broker._StartRequest.model_validate(payload, strict=True)  # pyright: ignore[reportPrivateUsage]


def test_start_failure_stop_restore_is_atomic_and_idempotent(tmp_path: Path) -> None:
    broker.restore_runtime_stop(tmp_path)
    assert (tmp_path / "STOP").read_bytes() == b"controller start broker rollback\n"
    assert (tmp_path / "STOP").stat().st_uid == tmp_path.stat().st_uid
    assert (tmp_path / "STOP").stat().st_gid == tmp_path.stat().st_gid
    broker.restore_runtime_stop(tmp_path)
    assert len(list(tmp_path.iterdir())) == 1


def test_activation_binds_runtime_manifest_file_not_inner_self_digest() -> None:
    raw = b'{"manifestDigest":"sha256:' + b"a" * 64 + b'"}\n'
    authority_digest = broker._runtime_manifest_authority_digest(  # pyright: ignore[reportPrivateUsage]
        raw
    )
    assert authority_digest == sha256_digest(raw)
    assert authority_digest != "sha256:" + "a" * 64


def test_started_controller_attestation_retries_transient_systemd_identity_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def attest(_pid: int, _manifest: object, _uid: int) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("controller process principal mismatch")

    def active(_service: str) -> int | None:
        return 4321

    def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(broker, "controller_active_pid", active)
    monkeypatch.setattr(broker, "_attest_process", attest)
    monkeypatch.setattr(broker.time, "sleep", no_sleep)

    observed = broker._attest_started_controller(  # pyright: ignore[reportPrivateUsage]
        "traincapsule-controller.service",
        object(),  # type: ignore[arg-type]
        994,
    )

    assert observed == 4321
    assert attempts == 2


def test_started_controller_attestation_keeps_fail_closed_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def active(_service: str) -> int | None:
        return 4321

    def fail(_pid: int, _manifest: object, _uid: int) -> None:
        raise ValueError("controller process executable mismatch")

    monkeypatch.setattr(broker, "controller_active_pid", active)
    monkeypatch.setattr(broker, "_attest_process", fail)

    with pytest.raises(ValueError, match="identity did not settle"):
        broker._attest_started_controller(  # pyright: ignore[reportPrivateUsage]
            "traincapsule-controller.service",
            object(),  # type: ignore[arg-type]
            994,
            maximum_wait_seconds=0,
        )


def test_runtime_manifest_accepts_exact_production_authority_shape() -> None:
    artifact = {"path": "/tmp/artifact", "digest": DIGEST, "executable": False}
    payload: dict[str, object] = {
        "schemaVersion": "3.1",
        "manifestDigest": "sha256:" + "0" * 64,
        "controllerPrincipal": "traincapsule-controller",
        "serviceName": "traincapsule-controller.service",
        "distributionRoot": "/opt/traincapsule-runtime",
        "repositoryRoot": "/var/lib/traincapsule-verifier/repository-boundary",
        "runtimeRoot": "/var/lib/traincapsule-runtime",
        "pythonRuntime": {
            "path": "/opt/traincapsule-runtime/python/bin/python3.12",
            "digest": DIGEST,
            "executable": True,
        },
        "packageManifest": artifact,
        "dependencyLock": artifact,
        "controllerUnit": {
            "path": "/etc/systemd/system/traincapsule-controller.service",
            "digest": DIGEST,
            "executable": False,
        },
        "environmentFile": {
            "path": "/etc/traincapsule-controller/controller-runtime.env",
            "digest": DIGEST,
            "executable": False,
        },
        "effectiveConfig": {
            "path": "/etc/traincapsule-controller/effective-config.yaml",
            "digest": DIGEST,
            "executable": False,
        },
        "repositorySnapshotManifest": artifact,
        "reductionOracle": {
            "oracleId": "TRAINCAPSULE_REDUCTION_ORACLE_V1",
            "executable": {
                "path": "/usr/local/libexec/traincapsule-reduction-oracle",
                "digest": DIGEST,
                "executable": True,
            },
            "publicKey": {
                "path": "/etc/traincapsule-verifier/keys/reduction-oracle.pub",
                "digest": DIGEST,
                "executable": False,
            },
            "receiptVerifier": {
                "path": "/usr/local/bin/traincapsule-verifier-verify-receipt",
                "digest": DIGEST,
                "executable": True,
            },
            "publicReceiptRoot": "/var/lib/traincapsule-verifier/receipts",
            "activationReceiptPath": (
                "/var/lib/traincapsule-verifier/activation/current.json"
            ),
        },
        "repositoryMainSha": "a" * 40,
        "repositoryTreeSha": "b" * 40,
        "mutableGitRoot": "/var/lib/traincapsule-runtime/git",
        "mutableWorktreeRoot": "/var/lib/traincapsule-runtime/worktrees",
        "artifactRoot": "/var/lib/traincapsule-runtime/artifacts/v3",
        "entryArguments": (
            "-m",
            "tcfactory.cli",
            "v3-controller",
            "--repo",
            "/var/lib/traincapsule-verifier/repository-boundary",
        ),
    }
    payload["manifestDigest"] = sha256_digest(canonical_json_bytes(payload))
    broker._RuntimeManifest.model_validate(  # pyright: ignore[reportPrivateUsage]
        payload, strict=True
    )


def test_systemd_path_has_one_root_broker_and_no_direct_controller_start() -> None:
    service = systemd_unit_content(unit="controller-start-broker").decode()
    trigger = systemd_unit_content(unit="controller-start-path").decode()
    assert "User=root" in service
    assert "traincapsule-verifier-controller-start process-outbox" in service
    assert "systemctl start" not in service
    assert "PathChanged=/var/lib/traincapsule-verifier/controller-start-outbox" in trigger
    assert "traincapsule-controller.service" not in trigger
    assert _sandbox_writable(
        service, "/var/lib/traincapsule-verifier/controller-start-journal/tx.json"
    )
    weakened = service.replace(
        "ReadWritePaths=/var/lib/traincapsule-verifier/controller-start-journal\n", ""
    )
    assert not _sandbox_writable(
        weakened, "/var/lib/traincapsule-verifier/controller-start-journal/tx.json"
    )


def test_install_manifest_binds_exact_start_and_observation_policies() -> None:
    files = {item.path: item for item in production_install_manifest().files}
    assert files[
        "/etc/traincapsule-verifier/controller-start-policy.json"
    ].content_digest == sha256_digest(controller_start_policy_content())
    assert files[
        "/etc/traincapsule-verifier/post-activation-policy.json"
    ].content_digest == sha256_digest(post_activation_policy_content())
    start = controller_start_policy_content().decode()
    observation = post_activation_policy_content().decode()
    assert '"runtimeManifestPath":"/etc/traincapsule-controller/runtime-manifest.json"' in start
    assert '"journalRoot":"/var/lib/traincapsule-verifier/controller-start-journal"' in start
    assert '"maximumObservationSeconds":3600' in observation
    assert (
        '"refreshCompletionRoot":"/var/lib/traincapsule-verifier/'
        'activation-refresh-inbox"' in observation
    )
    assert (
        '"refreshRetirementRoot":"/var/lib/traincapsule-verifier/'
        'activation-refresh-retirement"' in observation
    )
