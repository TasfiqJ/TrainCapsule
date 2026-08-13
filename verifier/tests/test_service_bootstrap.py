from __future__ import annotations

import os
import pwd
from pathlib import Path

import pytest
from test_public_boundary import PublicFixture
from test_public_boundary import public_fixture as public_fixture
from traincapsule_verifier.bootstrap import (
    CONTROLLER_USER,
    SERVICE_USER,
    production_install_manifest,
    render_systemd_units,
    staged_tree_digest,
    systemd_unit_content,
)
from traincapsule_verifier.canonical import canonical_json_bytes, sha256_digest
from traincapsule_verifier.filesystem import open_trusted_root
from traincapsule_verifier.receipt_broker import ReceiptPromotionError, RootReceiptBroker
from traincapsule_verifier.request_broker import (
    RequestSubmissionError,
    RequestSubmissionResult,
)
from traincapsule_verifier.request_broker_cli import (
    _process_names,  # pyright: ignore[reportPrivateUsage]
)


def _prepare_broker(fixture: PublicFixture, tmp_path: Path) -> tuple[Path, Path]:
    outbox = tmp_path / "service-outbox"
    public = tmp_path / "public-receipts"
    outbox.mkdir(mode=0o700)
    public.mkdir(mode=0o700)
    (outbox / f"{fixture.machine.receipt_id}.json").write_bytes(
        canonical_json_bytes(fixture.machine)
    )
    return outbox, public


def test_request_broker_rejection_does_not_block_later_valid_request() -> None:
    class Broker:
        def submit(self, request_name: str) -> RequestSubmissionResult:
            if request_name == "BAD.request.json":
                raise RequestSubmissionError("rejected")
            return RequestSubmissionResult(
                state="SUBMITTED",
                request_id="REQUEST:GOOD",
                request_digest="sha256:" + "a" * 64,
                evidence_digest="sha256:" + "b" * 64,
                issuer_request_name=request_name,
                issuer_evidence_name="REQUEST:GOOD.evidence",
            )

    results, rejected = _process_names(
        Broker(),
        ["BAD.request.json", "GOOD.request.json"],
        tolerate_rejections=True,
    )
    assert rejected == 1
    assert [item.request_id for item in results] == ["REQUEST:GOOD"]
    with pytest.raises(RequestSubmissionError):
        _process_names(
            Broker(), ["BAD.request.json"], tolerate_rejections=False
        )


def test_install_manifest_denies_controller_and_service_cross_authority() -> None:
    manifest = production_install_manifest()
    denied = {
        (item.principal, item.path, item.access)
        for item in manifest.access_assertions
        if not item.allowed
    }
    assert (CONTROLLER_USER, "/var/lib/traincapsule-verifier/private", "read") in denied
    assert (CONTROLLER_USER, "/var/lib/traincapsule-verifier/oracle", "execute") in denied
    assert (CONTROLLER_USER, "/var/lib/traincapsule-verifier/outbox", "read") in denied
    assert (
        CONTROLLER_USER,
        "/usr/libexec/traincapsule-verifier-issuer",
        "execute",
    ) in denied
    assert (SERVICE_USER, "/var/lib/traincapsule-verifier/receipts", "write") in denied
    assert manifest.state == "STAGED_NOT_ACTIVATED"
    assert not manifest.live_credentials_installed
    assert not manifest.live_oracles_installed
    assert not manifest.system_mutated


def test_runtime_consumers_use_the_installed_root_owned_authority_layout() -> None:
    import traincapsule_verifier.activation_issuer_service as activation_issuer
    import traincapsule_verifier.broker_cli as broker_cli
    import traincapsule_verifier.check_worker_cli as check_worker
    import traincapsule_verifier.controller_start_broker as controller_start
    import traincapsule_verifier.issuer_service as issuer_service
    import traincapsule_verifier.post_activation_observer as post_activation
    import traincapsule_verifier.public_cli as public_cli

    authority_root = Path("/etc/traincapsule-verifier")
    assert {
        activation_issuer.CONFIG_ROOT,
        broker_cli.CONFIG_ROOT,
        check_worker.CONFIG,
        controller_start.CONFIG,
        issuer_service.CONFIG_ROOT,
        post_activation.CONFIG,
        public_cli.CONFIG_ROOT,
    } == {authority_root}


def test_public_process_cold_imports_no_issuer_or_private_crypto() -> None:
    import subprocess
    import sys

    source = Path(__file__).resolve().parents[1] / "src"
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(source)!r}); "
                "import traincapsule_verifier.public_cli; "
                "assert 'traincapsule_verifier.issuer_service' not in sys.modules; "
                "assert 'traincapsule_verifier.evaluator' not in sys.modules; "
                "assert 'traincapsule_verifier.crypto' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert probe.returncode == 0, probe.stderr


def test_issuer_and_broker_entrypoints_fail_closed_for_wrong_identity(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    import traincapsule_verifier.activation_issuer_service as activation_issuer
    import traincapsule_verifier.broker_cli as broker_cli
    import traincapsule_verifier.check_worker_cli as check_worker
    import traincapsule_verifier.issuer_service as issuer_service

    monkeypatch.setattr(broker_cli.os, "geteuid", lambda: 12345)
    monkeypatch.setattr(broker_cli.sys, "argv", ["broker", "promote", "MPOL:X.json"])
    assert broker_cli.main() == 1
    broker_output = capfd.readouterr()
    assert broker_output.out == ""
    assert broker_output.err == "root receipt broker rejected execution\n"

    def service_identity(name: str) -> pwd.struct_passwd:
        assert name == "traincapsule-verifier"
        return pwd.struct_passwd((name, "x", 7, 7, "", "/nonexistent", "/usr/sbin/nologin"))

    monkeypatch.setattr(issuer_service.pwd, "getpwnam", service_identity)
    monkeypatch.setattr(issuer_service.os, "geteuid", lambda: 8)
    monkeypatch.setattr(issuer_service.sys, "argv", ["issuer", "process-inbox"])
    assert issuer_service.main() == 1
    issuer_output = capfd.readouterr()
    assert issuer_output.out == ""
    assert issuer_output.err == "independent issuer service rejected work\n"

    for module, argv, expected in (
        (
            activation_issuer,
            ["activation-issuer", "process-inbox"],
            "independent activation issuer rejected work\n",
        ),
        (
            check_worker,
            ["check-worker", "process-receipts"],
            "GitHub App check worker rejected execution\n",
        ),
    ):
        monkeypatch.setattr(module.pwd, "getpwnam", service_identity)
        monkeypatch.setattr(module.os, "geteuid", lambda: 8)
        monkeypatch.setattr(module.sys, "argv", argv)
        assert module.main() == 1
        output = capfd.readouterr()
        assert output.out == ""
        assert output.err == expected


def test_staged_installer_is_inert_exact_and_idempotently_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "stage"
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    paths = render_systemd_units(destination)
    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    assert after - before == {
        Path("stage"),
        Path("stage/install-manifest.json"),
        Path("stage/traincapsule-verifier-broker.service"),
        Path("stage/traincapsule-verifier-broker.path"),
        Path("stage/traincapsule-verifier-issuer.service"),
        Path("stage/traincapsule-verifier-issuer.path"),
        Path("stage/traincapsule-verifier-request-broker.service"),
        Path("stage/traincapsule-verifier-request-broker.path"),
        Path("stage/traincapsule-verifier-activation-issuer.service"),
        Path("stage/traincapsule-verifier-activation-issuer.path"),
        Path("stage/traincapsule-verifier-check-worker.service"),
        Path("stage/traincapsule-verifier-check-worker.path"),
        Path("stage/traincapsule-verifier-observed-main-selector.service"),
        Path("stage/traincapsule-verifier-observed-main-selector.path"),
        Path("stage/traincapsule-verifier-activation-selector-broker.service"),
        Path("stage/traincapsule-verifier-activation-selector-broker.path"),
        Path("stage/traincapsule-verifier-activation-request-broker.service"),
        Path("stage/traincapsule-verifier-activation-request-broker.path"),
        Path("stage/traincapsule-activation-supervisor.service"),
            Path("stage/traincapsule-activation-supervisor.timer"),
            Path("stage/traincapsule-verifier-controller-start.service"),
            Path("stage/traincapsule-verifier-controller-start.path"),
            Path("stage/traincapsule-verifier-post-activation-observer.service"),
            Path("stage/traincapsule-verifier-post-activation-observer.timer"),
        Path("stage/traincapsule-verifier-ruleset-observer.service"),
        Path("stage/traincapsule-verifier-ruleset-observer.timer"),
        Path("stage/traincapsule-verifier-ruleset-broker.service"),
        Path("stage/traincapsule-verifier-ruleset-broker.path"),
        Path("stage/traincapsule-verifier-git-anchor-updater.service"),
        Path("stage/traincapsule-verifier-git-anchor-updater.path"),
        Path("stage/traincapsule-verifier-git-anchor-job-broker.service"),
        Path("stage/traincapsule-verifier-git-anchor-job-broker.path"),
        Path("stage/traincapsule-verifier-git-anchor-producer.service"),
        Path("stage/traincapsule-verifier-git-anchor-producer.path"),
        Path("stage/traincapsule-verifier-git-anchor-promoter.service"),
        Path("stage/traincapsule-verifier-git-anchor-promoter.path"),
    }
    digest = staged_tree_digest(paths)
    assert digest.startswith("sha256:")
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in paths)
    with pytest.raises(ValueError, match="absent or empty"):
        render_systemd_units(destination)
    assert staged_tree_digest(paths) == digest


def test_activation_units_use_installed_environment_and_create_stop_fail_closed() -> None:
    supervisor = systemd_unit_content(unit="activation-supervisor").decode()
    observer = systemd_unit_content(unit="post-activation-observer").decode()
    assert "EnvironmentFile=/etc/traincapsule-controller/controller-runtime.env" in supervisor
    assert "EnvironmentFile=/etc/traincapsule-verifier/controller-runtime.env" not in supervisor
    assert "TimeoutStartSec=4h" in supervisor
    assert (
        "ReadWritePaths=/var/lib/traincapsule-verifier/controller-outbox" in supervisor
    )
    assert "ReadWritePaths=/var/lib/traincapsule-runtime\n" in observer
    assert "ReadWritePaths=/var/lib/traincapsule-runtime/STOP" not in observer
    assert (
        "ConditionPathExists=/var/lib/traincapsule-verifier/activation/current.json"
        in observer
    )
    assert "OnCalendar=*-*-* *:00/5:00" in systemd_unit_content(
        unit="activation-supervisor-timer"
    ).decode()
    assert "OnCalendar=*-*-* *:00/2:00" in systemd_unit_content(
        unit="post-activation-observer-timer"
    ).decode()


def test_unit_separation_and_rollback_are_explicit(tmp_path: Path) -> None:
    paths = render_systemd_units(tmp_path / "stage")
    issuer = next(path for path in paths if path.name.endswith("issuer.service")).read_text()
    broker = next(path for path in paths if path.name == "traincapsule-verifier-broker.service")
    broker_text = broker.read_text()
    request = next(
        path for path in paths if path.name == "traincapsule-verifier-request-broker.service"
    ).read_text()
    assert "User=traincapsule-verifier" in issuer
    assert "InaccessiblePaths=/var/lib/traincapsule-verifier/receipts" in issuer
    assert "User=root" in broker_text
    assert (
        "ReadOnlyPaths=/etc/traincapsule-verifier /var/lib/traincapsule-verifier/outbox"
        in broker_text
    )
    assert "ReadWritePaths=/var/lib/traincapsule-verifier/receipts" in broker_text
    assert "signing-key" not in broker_text
    assert "ReadOnlyPaths=/var/lib/traincapsule-verifier/controller-outbox" in request
    assert "InaccessiblePaths=/var/lib/traincapsule-verifier/private" in request
    rollback = production_install_manifest().rollback
    assert [(step.order, step.action) for step in rollback[:4]] == [
        (1, "stop"),
        (2, "stop"),
        (3, "stop"),
        (4, "stop"),
    ]
    assert any(step.target.endswith("receipts") and step.action == "retain" for step in rollback)
    assert any(step.target.endswith("outbox") and step.action == "retain" for step in rollback)


def _broker_with_distinct_owner_simulation(
    fixture: PublicFixture, outbox: Path, public: Path
) -> RootReceiptBroker:
    from traincapsule_verifier.public_verifier import PublicVerifier

    verifier = PublicVerifier.from_public_roots(
        repository_root=fixture.repository,
        config_root=fixture.config,
        state_root=fixture.state,
        receipt_root=public,
        expected_owner_uid=os.getuid(),
    )
    outbox_root = open_trusted_root(outbox, expected_uid=os.getuid())
    public_root = open_trusted_root(public, expected_uid=os.getuid())
    public_root.expected_uid = os.getuid() + 1
    broker = RootReceiptBroker(
        verifier=verifier, outbox_root=outbox_root, public_root=public_root
    )
    # Constructor observes distinct production principals; local tests run under one UID.
    public_root.expected_uid = os.getuid()
    return broker


def _close_broker(broker: RootReceiptBroker) -> None:
    broker.verifier.close()
    broker.outbox_root.close()
    broker.public_root.close()


def test_broker_promotion_replay_crash_and_partial_state(
    public_fixture: PublicFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outbox, public = _prepare_broker(public_fixture, tmp_path)
    broker = _broker_with_distinct_owner_simulation(public_fixture, outbox, public)
    try:
        first = broker.promote(f"{public_fixture.machine.receipt_id}.json")
        assert first.state == "PROMOTED"
        assert first.receipt_digest == sha256_digest(canonical_json_bytes(public_fixture.machine))
        assert (
            broker.promote(f"{public_fixture.machine.receipt_id}.json").state == "ALREADY_PROMOTED"
        )
    finally:
        _close_broker(broker)

    promoted = public / f"{public_fixture.machine.receipt_id}.json"
    promoted.unlink()
    import traincapsule_verifier.receipt_broker as broker_module

    original = broker_module.atomic_write_new

    def crash_after_commit(root: object, relative: str, data: bytes) -> Path:
        original(root, relative, data)  # type: ignore[arg-type]
        raise RuntimeError("simulated crash after durable link")

    monkeypatch.setattr(broker_module, "atomic_write_new", crash_after_commit)
    broker = _broker_with_distinct_owner_simulation(public_fixture, outbox, public)
    try:
        with pytest.raises(RuntimeError, match="simulated crash"):
            broker.promote(f"{public_fixture.machine.receipt_id}.json")
    finally:
        _close_broker(broker)
    monkeypatch.setattr(broker_module, "atomic_write_new", original)
    broker = _broker_with_distinct_owner_simulation(public_fixture, outbox, public)
    try:
        assert (
            broker.promote(f"{public_fixture.machine.receipt_id}.json").state == "ALREADY_PROMOTED"
        )
    finally:
        _close_broker(broker)


def test_broker_rejects_noncanonical_wrong_name_symlink_and_conflict(
    public_fixture: PublicFixture, tmp_path: Path
) -> None:
    outbox, public = _prepare_broker(public_fixture, tmp_path)
    name = f"{public_fixture.machine.receipt_id}.json"
    broker = _broker_with_distinct_owner_simulation(public_fixture, outbox, public)
    try:
        (outbox / name).write_bytes(
            canonical_json_bytes(public_fixture.machine).replace(b",", b", ", 1)
        )
        with pytest.raises(ReceiptPromotionError, match="not canonical"):
            broker.promote(name)
        (outbox / name).write_bytes(canonical_json_bytes(public_fixture.machine))
        wrong = outbox / "MPOL:WRONG-NAME.json"
        wrong.write_bytes(canonical_json_bytes(public_fixture.machine))
        with pytest.raises(ReceiptPromotionError, match="filename"):
            broker.promote(wrong.name)
        wrong.unlink()
        linked = outbox / "MPOL:LINKED.json"
        linked.symlink_to(outbox / name)
        with pytest.raises(ReceiptPromotionError, match="rejected"):
            broker.promote(linked.name)
        (public / name).write_bytes(b"conflicting-public-bytes")
        with pytest.raises(ReceiptPromotionError, match="different bytes"):
            broker.promote(name)
    finally:
        _close_broker(broker)


def test_broker_rejects_tamper_and_root_identity_alias(
    public_fixture: PublicFixture, tmp_path: Path
) -> None:
    outbox, public = _prepare_broker(public_fixture, tmp_path)
    name = f"{public_fixture.machine.receipt_id}.json"
    tampered = canonical_json_bytes(public_fixture.machine).replace(
        public_fixture.machine.candidate_sha.encode(), b"f" * 40
    )
    (outbox / name).write_bytes(tampered)
    broker = _broker_with_distinct_owner_simulation(public_fixture, outbox, public)
    try:
        with pytest.raises(ReceiptPromotionError, match="rejected"):
            broker.promote(name)
    finally:
        _close_broker(broker)

    alias = tmp_path / "outbox-alias"
    alias.symlink_to(outbox, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        open_trusted_root(alias, expected_uid=os.getuid())

    with (
        public_fixture.verifier() as verifier,
        open_trusted_root(outbox, expected_uid=os.getuid()) as root,
    ):
        public_alias = open_trusted_root(outbox, expected_uid=os.getuid())
        public_alias.expected_uid = os.getuid() + 1
        with pytest.raises(ReceiptPromotionError, match="distinct"):
            RootReceiptBroker(
                verifier=verifier,
                outbox_root=root,
                public_root=public_alias,
            )
        public_alias.close()


def test_no_live_secrets_or_receipts_in_staged_distribution() -> None:
    verifier_root = Path(__file__).resolve().parents[1]
    forbidden_suffixes = {".pem", ".key", ".p12", ".pfx"}
    assert not [
        path for path in verifier_root.rglob("*") if path.suffix.lower() in forbidden_suffixes
    ]
    assert not [
        path for path in verifier_root.rglob("*.json") if path.name.startswith(("MPOL:", "ACT:"))
    ]
