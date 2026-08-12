from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import tcfactory.v3.private_gate as private_gate
from tcfactory.util import sha256_file
from tcfactory.v3.private_gate import (
    FULL_RELEASE_SCOPE,
    PRIVATE_GATE_HEALTH_REJECTION,
    PrivateGateHealthCheck,
    PrivateGateReceipt,
    PrivateGateVerificationError,
    validate_private_gate_runtime_health,
    verify_private_gate_receipt,
)

CANDIDATE = "b" * 40


def _signed_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    runner = tmp_path / "run_private_gate.sh"
    runner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    runner.chmod(0o755)
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_key)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True,
        capture_output=True,
    )
    result = tmp_path / "result.txt"
    result.write_text("private gate passed\n", encoding="utf-8")
    issued = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    receipt = PrivateGateReceipt(
        receipt_id="PGATE-TEST_0001",
        candidate_sha=CANDIDATE,
        work_item_id="V3-TEST-001",
        scope=list(FULL_RELEASE_SCOPE),
        runner_digest=f"sha256:{sha256_file(runner)}",
        runner_version="3.1.0",
        result_digest=f"sha256:{sha256_file(result)}",
        issued_at=issued,
        expires_at=issued + timedelta(hours=1),
        key_id="test-ed25519",
    )
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_bytes(receipt.canonical_json_bytes())
    signature = tmp_path / "receipt.json.sig"
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-inkey",
            str(private_key),
            "-rawin",
            "-in",
            str(receipt_path),
            "-out",
            str(signature),
        ],
        check=True,
        capture_output=True,
    )
    return runner, public_key, receipt_path, signature, result


def test_private_gate_requires_valid_signed_candidate_bound_unexpired_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, key, receipt, signature, result = _signed_fixture(tmp_path)

    def ignore_privilege(_path: Path) -> None:
        return None

    monkeypatch.setattr(private_gate, "_assert_privileged_read_only", ignore_privilege)

    verified = verify_private_gate_receipt(
        repo_root=tmp_path / "repository",
        runner=runner,
        public_key=key,
        receipt_path=receipt,
        signature_path=signature,
        result_path=result,
        expected_candidate_sha=CANDIDATE,
        expected_work_item_id="V3-TEST-001",
        now=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
    )
    assert verified.runner_version == "3.1.0"

    with pytest.raises(PrivateGateVerificationError, match="candidate SHA mismatch"):
        verify_private_gate_receipt(
            repo_root=tmp_path / "repository",
            runner=runner,
            public_key=key,
            receipt_path=receipt,
            signature_path=signature,
            result_path=result,
            expected_candidate_sha="a" * 40,
            expected_work_item_id="V3-TEST-001",
            now=datetime(2026, 8, 12, 12, 30, tzinfo=UTC),
        )
    with pytest.raises(PrivateGateVerificationError, match="expired"):
        verify_private_gate_receipt(
            repo_root=tmp_path / "repository",
            runner=runner,
            public_key=key,
            receipt_path=receipt,
            signature_path=signature,
            result_path=result,
            expected_candidate_sha=CANDIDATE,
            expected_work_item_id="V3-TEST-001",
            now=datetime(2026, 8, 12, 14, 0, tzinfo=UTC),
        )


def test_private_gate_rejects_tamper_and_incomplete_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, key, receipt, signature, result = _signed_fixture(tmp_path)

    def ignore_privilege(_path: Path) -> None:
        return None

    monkeypatch.setattr(private_gate, "_assert_privileged_read_only", ignore_privilege)
    receipt.write_bytes(receipt.read_bytes() + b" ")
    with pytest.raises(PrivateGateVerificationError, match="signature is invalid"):
        verify_private_gate_receipt(
            repo_root=tmp_path / "repository",
            runner=runner,
            public_key=key,
            receipt_path=receipt,
            signature_path=signature,
            result_path=result,
            expected_candidate_sha=CANDIDATE,
            expected_work_item_id="V3-TEST-001",
        )
    with pytest.raises(ValueError, match="scope"):
        PrivateGateReceipt(
            receipt_id="PGATE-TEST_0002",
            candidate_sha=CANDIDATE,
            work_item_id="V3-TEST-001",
            scope=["factory-quality"],
            runner_digest="sha256:" + "a" * 64,
            runner_version="3.1.0",
            result_digest="sha256:" + "b" * 64,
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            key_id="test-ed25519",
        )


def test_installed_private_gate_health_probe_requires_exact_safe_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = tmp_path / "trusted/run_private_gate.sh"
    runner.parent.mkdir()
    runner.write_text("#!/bin/sh\n", encoding="utf-8")
    expected_runner = runner

    def trusted_installation(
        _repo_root: Path,
        *,
        runner: Path = private_gate.PRIVATE_GATE_RUNNER,
        public_key: Path = private_gate.PRIVATE_GATE_PUBLIC_KEY,
    ) -> tuple[Path, Path]:
        del runner, public_key
        return expected_runner, tmp_path / "trusted/key.pem"

    monkeypatch.setattr(
        private_gate,
        "validate_private_gate_installation",
        trusted_installation,
    )

    def safe_rejection(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        assert args == [str(runner), "full-release", str(repo)]
        assert environment["TCF_CANDIDATE_SHA"] == "0" * 40
        assert environment["TCF_CANDIDATE_WORKTREE"] == str(repo)
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout="",
            stderr=PRIVATE_GATE_HEALTH_REJECTION,
        )

    monkeypatch.setattr(private_gate.subprocess, "run", safe_rejection)
    result = validate_private_gate_runtime_health(repo, tmp_path / "runtime", runner=runner)

    assert result == PrivateGateHealthCheck()
    assert not (tmp_path / "runtime/.private-gate-health").exists()


@pytest.mark.parametrize(
    ("returncode", "stderr"),
    [
        (1, "Traceback: ImportError: cannot import name UTC\n"),
        (0, ""),
        (2, PRIVATE_GATE_HEALTH_REJECTION),
    ],
)
def test_installed_private_gate_health_probe_rejects_any_other_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stderr: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = tmp_path / "trusted/run_private_gate.sh"
    runner.parent.mkdir()
    runner.write_text("#!/bin/sh\n", encoding="utf-8")
    expected_runner = runner

    def trusted_installation(
        _repo_root: Path,
        *,
        runner: Path = private_gate.PRIVATE_GATE_RUNNER,
        public_key: Path = private_gate.PRIVATE_GATE_PUBLIC_KEY,
    ) -> tuple[Path, Path]:
        del runner, public_key
        return expected_runner, tmp_path / "trusted/key.pem"

    def rejected_run(
        args: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=args, returncode=returncode, stdout="", stderr=stderr
        )

    monkeypatch.setattr(
        private_gate,
        "validate_private_gate_installation",
        trusted_installation,
    )
    monkeypatch.setattr(
        private_gate.subprocess,
        "run",
        rejected_run,
    )

    with pytest.raises(PrivateGateVerificationError, match="exact contract"):
        validate_private_gate_runtime_health(repo, tmp_path / "runtime", runner=runner)
