from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Never

import pytest
from pydantic import ValidationError

import tcfactory.cli as cli
import tcfactory.v3.activation as activation
import tcfactory.v3.activation_supervisor as activation_supervisor
import tcfactory.v3.canaries as canaries
from tcfactory.v3.activation import (
    ActivationPhase,
    ActivationTransaction,
    activate_v31,
    stage_activation_request,
    validate_activation_control_state,
)
from tcfactory.v3.activation_supervisor import (
    RefreshActivationState,
    RefreshCompletionV31,
    run_activation_supervisor,
)
from tcfactory.v3.base import sha256_digest
from tcfactory.v3.canaries import (
    CanaryStatus,
    MandatoryCanaryId,
    MandatoryCanaryResult,
    PostActivationObservation,
    PostActivationObservationId,
    run_mandatory_canaries,
    verify_mandatory_canary_suite,
    verify_post_activation_observation,
)
from tcfactory.v3.contracts_v31 import (
    ActivationMode,
    ActivationReceiptV31,
    ActivationRequestV31,
    CommercialState,
    DecisionValueDisposition,
    GateResult,
    MachinePolicyReceiptV31,
    NativeSubstituteDisposition,
    PolicyDecision,
    TechnicalState,
)
from tcfactory.v3.controller_lock import ControllerLockError, controller_process_lock
from tcfactory.v3.enums import Lane, RiskTier
from tcfactory.v3.installed_runtime import (
    InstalledArtifact,
    InstalledControllerRuntimeManifest,
)
from tcfactory.v3.runtime_paths import V3RuntimePaths

NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64
RuntimeLoader = Callable[[Path], tuple[InstalledControllerRuntimeManifest, bytes, bytes]]


def test_activation_git_identity_pins_the_exact_trusted_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        value = "a" * 40 if command[-1] == "HEAD" else "b" * 40
        return subprocess.CompletedProcess(command, 0, f"{value}\n", "")

    monkeypatch.setattr(activation_supervisor.subprocess, "run", run)
    repo = tmp_path / "root-owned-repository"

    assert activation_supervisor._git_identity(repo) == (  # pyright: ignore[reportPrivateUsage]
        "a" * 40,
        "b" * 40,
    )
    assert all(
        command[:5] == ["git", "-c", f"safe.directory={repo}", "-C", str(repo)] for command in calls
    )


def _runtime_loader() -> tuple[InstalledControllerRuntimeManifest, RuntimeLoader]:
    artifact = InstalledArtifact(path="/opt/traincapsule-runtime/package.json", digest=DIGEST)
    config_raw = b"schemaVersion: '3.1'\n"
    provisional = InstalledControllerRuntimeManifest(
        manifest_digest=DIGEST,
        controller_principal="traincapsule-controller",
        service_name="traincapsule-controller.service",
        distribution_root="/opt/traincapsule-runtime",
        repository_root="/var/lib/traincapsule-verifier/repository-boundary",
        runtime_root="/var/lib/traincapsule-runtime",
        python_runtime=InstalledArtifact(
            path="/opt/traincapsule-runtime/python/bin/python3.12",
            digest=DIGEST,
            executable=True,
        ),
        package_manifest=artifact,
        dependency_lock=InstalledArtifact(
            path="/opt/traincapsule-runtime/dependency.lock", digest=DIGEST
        ),
        controller_unit=InstalledArtifact(
            path="/etc/systemd/system/traincapsule-controller.service", digest=DIGEST
        ),
        environment_file=InstalledArtifact(
            path="/etc/traincapsule-controller/controller-runtime.env", digest=DIGEST
        ),
        effective_config=InstalledArtifact(
            path="/etc/traincapsule-controller/effective-config.yaml",
            digest=sha256_digest(config_raw),
        ),
        repository_snapshot_manifest=InstalledArtifact(
            path=("/var/lib/traincapsule-verifier/repository-boundary/SNAPSHOT_MANIFEST.json"),
            digest=DIGEST,
        ),
        repository_main_sha="a" * 40,
        repository_tree_sha="b" * 40,
        mutable_git_root="/var/lib/traincapsule-runtime/git",
        mutable_worktree_root="/var/lib/traincapsule-runtime/worktrees",
        artifact_root="/var/lib/traincapsule-runtime/artifacts/v3",
        entry_arguments=(
            "-m",
            "tcfactory.cli",
            "v3-controller",
            "--repo",
            "/var/lib/traincapsule-verifier/repository-boundary",
        ),
    )
    manifest = provisional.model_copy(
        update={"manifest_digest": provisional.computed_manifest_digest()}
    )
    raw = manifest.canonical_json_bytes()

    def load(_: Path) -> tuple[InstalledControllerRuntimeManifest, bytes, bytes]:
        return manifest, raw, config_raw

    return manifest, load


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "config").mkdir(parents=True)
    (repo / "tcfactory/v3").mkdir(parents=True)
    (repo / "config/factory.yaml").write_text("schemaVersion: '3.1'\n", encoding="utf-8")
    (repo / "tcfactory/v3/controller.py").write_text("# controller\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=Canary Test",
        "-c",
        "user.email=canary@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    _git(repo, "remote", "add", "origin", "https://github.com/TasfiqJ/TrainCapsule.git")
    return repo


def _active() -> SimpleNamespace:
    return SimpleNamespace(generation_id="traincapsule-v3.1-zh", manifest_digest="b" * 64)


def _active_for_path(_: Path) -> SimpleNamespace:
    return _active()


class _PassingRunner:
    runner_digest = "sha256:" + "c" * 64

    def run(
        self,
        *,
        canary_id: MandatoryCanaryId,
        run_id: str,
        repo_root: Path,
        runtime_root: Path,
        artifact_root: Path,
        exact_main_sha: str,
        exact_tree_sha: str,
    ) -> MandatoryCanaryResult:
        assert repo_root.name == "isolated-repo"
        assert runtime_root.name == "isolated-runtime"
        assert (runtime_root / "STOP").is_file()
        evidence = artifact_root / "evidence.json"
        payload = json.dumps({"canary": canary_id.value}, sort_keys=True).encode()
        evidence.write_bytes(payload)
        return MandatoryCanaryResult(
            schema_version="3.1",
            run_id=run_id,
            canary_id=canary_id,
            exact_main_sha=exact_main_sha,
            exact_tree_sha=exact_tree_sha,
            runner_digest=self.runner_digest,
            status=CanaryStatus.PASS,
            evidence_artifacts={"evidence.json": sha256_digest(payload)},
            started_at=NOW,
            completed_at=NOW,
        )


def _passing_runner(_: Path) -> _PassingRunner:
    return _PassingRunner()


def _runtime_paths(root: Path) -> V3RuntimePaths:
    return V3RuntimePaths(
        state_root=root,
        queue=root / "v3-queue",
        checkpoints=root / "pipelines",
        controller_state=root / "controller.json",
        scheduler_decisions=root / "scheduler-decisions",
        milestone_state=root / "milestone-state.json",
        milestone_evidence=root / "milestone-evidence",
        milestone_decisions=root / "milestone-decisions",
        machine_policy_receipts=root / "machine-policy-receipts",
        source_proposals=root / "source-proposals",
        value_redesign_proposals=root / "value-redesign-proposals",
        quarantine=root / "quarantine",
        canary_results=root / "canary-results",
        activation_transactions=root / "activation-transactions",
        control_archive=root / "control-archive",
        migration_marker=root / "migration.json",
        supervisor_state=root / "supervisor.json",
        supervisor_lock=root / "supervisor.lock",
        controller_lock=root / "controller.lock",
        hard_stuck=root / "HARD_STUCK.json",
        stop=root / "STOP",
        pause=root / "PAUSE",
        git_root=root / "git",
        worktree_root=root / "worktrees",
        artifact_root=root / "artifacts/v3",
    )


def _suite(repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(canaries, "validate_active_source_generation", _active_for_path)
    return run_mandatory_canaries(
        repo_root=repo,
        result_root=tmp_path / "canary-results",
        runner_factory=_passing_runner,
        now=NOW,
    )


def _receipt(
    repo: Path,
    suite: Path,
    path: Path,
    runtime: InstalledControllerRuntimeManifest | None = None,
) -> ActivationReceiptV31:
    sha = _git(repo, "rev-parse", "HEAD")
    receipt = ActivationReceiptV31(
        schema_version="3.1",
        receipt_id="ACT-EXACT-CANARY",
        verified_main_sha=sha,
        machine_environment_digest=sha256_digest(suite.read_bytes()),
        source_generation_id="traincapsule-v3.1-zh",
        source_generation_digest="sha256:" + "b" * 64,
        controller_binary_digest=(
            sha256_digest(runtime.canonical_json_bytes()) if runtime else DIGEST
        ),
        controller_config_digest=(runtime.effective_config.digest if runtime else DIGEST),
        machine_environment_path="canary-suite.json",
        controller_binary_path="controller.py",
        controller_config_path="factory.yaml",
        machine_policy_receipt_id="MPR-EXACT",
        machine_policy_receipt_digest=DIGEST,
        mode=ActivationMode.LIVE,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        revocation_epoch=1,
        nonce="0123456789abcdef",
        issuer_id="VERIFIER",
        issuer_key_id="KEY-1",
        signature_algorithm="ed25519",
        signature="A" * 80,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(receipt.canonical_json_bytes())
    return receipt


def _activation_policy_receipt(
    repo: Path,
    suite_path: Path,
    path: Path,
    *,
    issued_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(minutes=30),
) -> Path:
    suite = verify_mandatory_canary_suite(suite_path, repo_root=repo)
    sha = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    receipt = MachinePolicyReceiptV31(
        schema_version="3.1",
        receipt_id="MPOL:ACTIVATION:EXACT",
        policy_id="POLICY:ACTIVATION",
        policy_version="3.1",
        issuer_id="ISSUER:INDEPENDENT",
        issuer_key_id="KEY:INDEPENDENT",
        issued_at=issued_at,
        expires_at=expires_at,
        revocation_epoch=1,
        nonce="activation-policy-nonce-0001",
        request_digest=DIGEST,
        work_item_id="V3-MIG-019",
        milestone_id="M0_SOURCE_INSTALLATION",
        lane=Lane.FACTORY,
        risk_tier=RiskTier.TRUST_CORE,
        candidate_sha=sha,
        candidate_tree_sha=tree,
        base_sha=sha,
        source_generation_id=suite.source_generation_id,
        source_generation_digest=suite.source_generation_digest,
        context_manifest_digest=sha256_digest(suite_path.read_bytes()),
        task_packet_digest=suite.controller_digest,
        candidate_manifest_digest=suite.factory_config_digest,
        checkpoint_digest=DIGEST,
        required_gate_results={"GATE:ACTIVATION": GateResult.PASS},
        private_gate_suite_id="GATES:PRIVATE",
        private_gate_runner_digest=DIGEST,
        independent_oracle_ids=["ORACLE:ACTIVATION"],
        raw_evidence_artifact_hashes=[sha256_digest(suite_path.read_bytes())],
        native_substitute_disposition=NativeSubstituteDisposition.INCREMENTAL_VALUE,
        decision_value_disposition=(
            DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
        ),
        engineering_maturity_ceiling=TechnicalState.PASSED,
        commercial_maturity_ceiling=CommercialState.PILOT_ELIGIBLE,
        allowed_claims=["ACTIVATION"],
        publication_scope=["factory/state"],
        decision=PolicyDecision.PASS,
        signature_algorithm="ed25519",
        signature="A" * 88,
    )
    path.write_bytes(receipt.canonical_json_bytes())
    return path


def test_activation_request_is_exact_idempotent_and_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    suite = _suite(repo, tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "STOP").write_text("stopped\n", encoding="utf-8")
    outbox = tmp_path / "activation-outbox"
    outbox.mkdir(mode=0o700)
    receipt = _activation_policy_receipt(repo, suite, tmp_path / "policy.json")
    paths = _runtime_paths(runtime)
    paths.activation_transactions.mkdir()
    consumed = ActivationTransaction(
        schema_version="3.1",
        transaction_id="ACTIVATE-CONSUMED",
        phase=ActivationPhase.ACTIVATED,
        exact_main_sha="a" * 40,
        exact_tree_sha="b" * 40,
        activation_receipt_id="ACT:CONSUMED",
        activation_receipt_digest=DIGEST,
        canary_suite_path=str(suite),
        canary_suite_digest=DIGEST,
        preflight_digest=DIGEST,
        stop_digest=DIGEST,
        stop_archive_path=str(runtime / "old-stop"),
        prepared_at=NOW,
        activated_at=NOW,
    )
    (paths.activation_transactions / "ACTIVATE-CONSUMED.json").write_bytes(
        consumed.canonical_json_bytes()
    )

    def resolve_paths(_root: Path) -> V3RuntimePaths:
        return paths

    monkeypatch.setattr(activation, "resolve_v3_runtime_paths", resolve_paths)
    _, runtime_loader = _runtime_loader()
    first = stage_activation_request(
        repo_root=repo,
        canary_suite_path=suite,
        machine_policy_receipt_path=receipt,
        _outbox_root=outbox,
        installed_runtime_loader=runtime_loader,
        now=NOW + timedelta(minutes=1),
    )
    second = stage_activation_request(
        repo_root=repo,
        canary_suite_path=suite,
        machine_policy_receipt_path=receipt,
        _outbox_root=outbox,
        installed_runtime_loader=runtime_loader,
        now=NOW + timedelta(minutes=1),
    )
    assert first == second
    assert (runtime / "STOP").is_file()
    assert not list(paths.activation_transactions.iterdir())
    archived = list((paths.control_archive / "activation-transactions").iterdir())
    assert len(archived) == 1
    assert archived[0].read_bytes() == consumed.canonical_json_bytes()
    assert len(list(outbox.glob("*.activation-request.json"))) == 1
    request = ActivationRequestV31.model_validate_json(first.read_bytes(), strict=True)
    controller_raw = (
        outbox / f"{request.request_id}.evidence" / request.controller_binary_path
    ).read_bytes()
    config_raw = (
        outbox / f"{request.request_id}.evidence" / request.controller_config_path
    ).read_bytes()
    assert request.controller_binary_digest == sha256_digest(controller_raw)
    assert request.controller_config_digest == sha256_digest(config_raw)
    receipt_value = MachinePolicyReceiptV31.model_validate_json(receipt.read_bytes(), strict=True)
    mismatched_receipt = tmp_path / "mismatched-policy.json"
    mismatched_receipt.write_bytes(
        receipt_value.model_copy(update={"context_manifest_digest": DIGEST}).canonical_json_bytes()
    )
    with pytest.raises(RuntimeError, match="does not authorize the exact activation evidence"):
        stage_activation_request(
            repo_root=repo,
            canary_suite_path=suite,
            machine_policy_receipt_path=mismatched_receipt,
            _outbox_root=outbox,
            installed_runtime_loader=runtime_loader,
            now=NOW + timedelta(minutes=1),
        )
    expired_receipt = tmp_path / "expired-policy.json"
    expired_receipt.write_bytes(
        receipt_value.model_copy(
            update={"expires_at": NOW + timedelta(minutes=10)}
        ).canonical_json_bytes()
    )
    with pytest.raises(RuntimeError, match="does not authorize the exact activation evidence"):
        stage_activation_request(
            repo_root=repo,
            canary_suite_path=suite,
            machine_policy_receipt_path=expired_receipt,
            _outbox_root=outbox,
            installed_runtime_loader=runtime_loader,
            now=NOW + timedelta(minutes=11),
        )
    manifest, _ = _runtime_loader()

    def tampered_loader(
        _: Path,
    ) -> tuple[InstalledControllerRuntimeManifest, bytes, bytes]:
        return manifest, manifest.canonical_json_bytes(), b"tampered: true\n"

    with pytest.raises(RuntimeError, match="installed runtime config digest mismatch"):
        stage_activation_request(
            repo_root=repo,
            canary_suite_path=suite,
            machine_policy_receipt_path=receipt,
            _outbox_root=outbox,
            installed_runtime_loader=tampered_loader,
            now=NOW + timedelta(minutes=1),
        )


def test_activation_request_retires_exact_prepared_receipt_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    suite = _suite(repo, tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    stop = runtime / "STOP"
    stop.write_text("stopped\n", encoding="utf-8")
    outbox = tmp_path / "activation-outbox"
    outbox.mkdir(mode=0o700)
    receipt = _activation_policy_receipt(repo, suite, tmp_path / "policy.json")
    paths = _runtime_paths(runtime)
    paths.activation_transactions.mkdir()
    stop_archive = paths.control_archive / "STOP.ACT:CONSUMED.aaaaaaaaaaaa"
    stop_archive.parent.mkdir(parents=True)
    stop_archive.write_bytes(stop.read_bytes())
    def transaction(
        phase: ActivationPhase, *, activated_at: datetime | None = None
    ) -> ActivationTransaction:
        return ActivationTransaction(
            schema_version="3.1",
            transaction_id="ACTIVATE-ACT:CONSUMED",
            phase=phase,
            exact_main_sha="a" * 40,
            exact_tree_sha="b" * 40,
            activation_receipt_id="ACT:CONSUMED",
            activation_receipt_digest=DIGEST,
            canary_suite_path=str(suite),
            canary_suite_digest=DIGEST,
            preflight_digest=DIGEST,
            stop_digest=sha256_digest(stop.read_bytes()),
            stop_archive_path=str(stop_archive),
            prepared_at=NOW,
            activated_at=activated_at,
        )

    activated = transaction(ActivationPhase.ACTIVATED, activated_at=NOW)
    archive = paths.control_archive / "activation-transactions"
    archive.mkdir()
    (archive / "ACTIVATE-ACT:CONSUMED-terminal.json").write_bytes(
        activated.canonical_json_bytes()
    )
    prepared = transaction(ActivationPhase.PREPARED)
    live = paths.activation_transactions / "ACTIVATE-ACT:CONSUMED.json"
    live.write_bytes(prepared.canonical_json_bytes())

    def resolve_paths(_root: Path) -> V3RuntimePaths:
        return paths

    monkeypatch.setattr(activation, "resolve_v3_runtime_paths", resolve_paths)
    _, runtime_loader = _runtime_loader()
    request = stage_activation_request(
        repo_root=repo,
        canary_suite_path=suite,
        machine_policy_receipt_path=receipt,
        _outbox_root=outbox,
        installed_runtime_loader=runtime_loader,
        now=NOW + timedelta(minutes=1),
    )

    assert request.is_file()
    assert stop.is_file()
    assert not live.exists()
    archived = list(archive.glob("ACTIVATE-ACT:CONSUMED-*.json"))
    assert len(archived) == 2
    assert any(path.read_bytes() == prepared.canonical_json_bytes() for path in archived)


def test_activation_policy_request_uses_independent_verifier_bridge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    suite = _suite(repo, tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "STOP").write_text("stopped\n", encoding="utf-8")
    outbox = tmp_path / "controller-outbox"
    outbox.mkdir(mode=0o700)
    profile = tmp_path / "activation-policy.json"
    profile.write_bytes(
        json.dumps(
            {
                "schemaVersion": "3.1",
                "riskTier": "TRUST_CORE",
                "requestedClaims": ["ACTIVATION"],
                "publicationScope": ["factory/state"],
                "nativeDisposition": "UNKNOWN",
                "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                "engineeringCeiling": "PASSED",
                "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                "privateGateSuiteId": "GATES:PRIVATE",
                "privateGateRunnerDigest": DIGEST,
                "oracles": {
                    "ORACLE:ACTIVATION": {
                        "runnerDigest": DIGEST,
                        "nativeDisposition": "UNKNOWN",
                        "valueDisposition": "EXTERNAL_EVIDENCE_REQUIRED",
                        "engineeringCeiling": "PASSED",
                        "commercialCeiling": "NATIVE_ADVANTAGE_UNPROVEN",
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        + b"\n"
    )

    def resolve_paths(_root: Path) -> V3RuntimePaths:
        return _runtime_paths(runtime)

    monkeypatch.setattr(activation, "resolve_v3_runtime_paths", resolve_paths)
    _, runtime_loader = _runtime_loader()
    receipt = tmp_path / "missing-policy-receipt.json"
    first = activation.coordinate_activation_policy_request(
        repo_root=repo,
        canary_suite_path=suite,
        profile_path=profile,
        machine_policy_receipt_path=receipt,
        installed_runtime_loader=runtime_loader,
        controller_outbox=outbox,
    )
    assert first is not None
    request = json.loads(first.read_bytes())
    assert request["workItemId"] == "V3-MIG-019"
    assert request["requestedClaims"] == ["ACTIVATION"]
    assert request["publicationScope"] == ["factory/state"]
    evidence_path = outbox / f"{request['requestId']}.evidence/evidence.json"
    assert evidence_path.is_file()
    evidence = json.loads(evidence_path.read_bytes())
    assert len(evidence["rawArtifacts"]) == 21
    assert len({item["digest"] for item in evidence["rawArtifacts"].values()}) == 21
    oracle_hashes = evidence["oracles"]["ORACLE:ACTIVATION"]["rawEvidenceArtifactHashes"]
    assert oracle_hashes == sorted(oracle_hashes)
    assert (
        activation.coordinate_activation_policy_request(
            repo_root=repo,
            canary_suite_path=suite,
            profile_path=profile,
            machine_policy_receipt_path=receipt,
            installed_runtime_loader=runtime_loader,
            controller_outbox=outbox,
        )
        == first
    )
    observed_now = datetime.now(UTC)
    _activation_policy_receipt(
        repo,
        suite,
        receipt,
        issued_at=observed_now - timedelta(hours=2),
        expires_at=observed_now - timedelta(hours=1),
    )
    renewal = activation.coordinate_activation_policy_request(
        repo_root=repo,
        canary_suite_path=suite,
        profile_path=profile,
        machine_policy_receipt_path=receipt,
        installed_runtime_loader=runtime_loader,
        controller_outbox=outbox,
    )
    assert renewal is not None
    assert renewal != first
    assert (
        activation.coordinate_activation_policy_request(
            repo_root=repo,
            canary_suite_path=suite,
            profile_path=profile,
            machine_policy_receipt_path=receipt,
            installed_runtime_loader=runtime_loader,
            controller_outbox=outbox,
        )
        == renewal
    )
    _activation_policy_receipt(
        repo,
        suite,
        receipt,
        issued_at=observed_now,
        expires_at=observed_now + timedelta(minutes=30),
    )
    assert (
        activation.coordinate_activation_policy_request(
            repo_root=repo,
            canary_suite_path=suite,
            profile_path=profile,
            machine_policy_receipt_path=receipt,
            installed_runtime_loader=runtime_loader,
            controller_outbox=outbox,
        )
        is None
    )


def test_stopped_activation_supervisor_runs_canaries_then_coordinates_without_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "STOP").write_text("stopped\n", encoding="utf-8")
    paths = _runtime_paths(runtime)
    calls: list[str] = []
    monkeypatch.setenv("TCF_CANARY_PUBLICATION_REMOTE", canaries.CANARY_PUBLICATION_REMOTE)

    def resolve_paths(_root: Path) -> V3RuntimePaths:
        return paths

    def run_canaries(**kwargs: object) -> Path:
        assert kwargs["publication_remote"] == canaries.CANARY_PUBLICATION_REMOTE
        calls.append("canaries")
        suite_path = tmp_path / "suite.json"
        suite_path.write_bytes(b"{}")
        return suite_path

    def parse_suite(_raw: bytes, *, strict: bool) -> SimpleNamespace:
        assert strict
        return SimpleNamespace(status=CanaryStatus.PASS)

    def coordinate(*, repo_root: Path, **_: object) -> Path:
        assert repo_root == repo.resolve()
        calls.append("coordinate")
        return tmp_path / "request.json"

    import tcfactory.v3.activation_supervisor as supervisor

    monkeypatch.setattr(supervisor, "resolve_v3_runtime_paths", resolve_paths)
    monkeypatch.setattr(supervisor, "run_mandatory_canaries", run_canaries)
    monkeypatch.setattr(supervisor.MandatoryCanarySuite, "model_validate_json", parse_suite)
    monkeypatch.setattr(supervisor, "coordinate_activation_request", coordinate)
    assert run_activation_supervisor(repo_root=repo) == "ACTIVATION_REQUEST_SUBMITTED"
    assert calls == ["canaries", "coordinate"]
    assert (runtime / "STOP").is_file()
    (runtime / "HARD_STUCK.json").write_text("{}", encoding="utf-8")
    calls.clear()
    assert run_activation_supervisor(repo_root=repo) == "STOPPED_CONTROL"
    assert calls == []


def test_activation_supervisor_consumes_delayed_live_receipt_and_stages_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "STOP").write_text("stopped\n", encoding="utf-8")
    paths = _runtime_paths(runtime)
    suite = paths.canary_results / "RUN" / "suite.json"
    suite.parent.mkdir(parents=True)
    suite.write_bytes(b"{}")
    paths.activation_transactions.mkdir()
    calls: list[str] = []
    transaction = ActivationTransaction(
        schema_version="3.1",
        transaction_id="ACTIVATE-ACT-TEST",
        phase=ActivationPhase.ACTIVATED,
        exact_main_sha="a" * 40,
        exact_tree_sha="b" * 40,
        activation_receipt_id="ACT-TEST",
        activation_receipt_digest=DIGEST,
        canary_suite_path=str(suite),
        canary_suite_digest=DIGEST,
        preflight_digest=DIGEST,
        stop_digest=DIGEST,
        stop_archive_path=str(runtime / "archive"),
        prepared_at=NOW,
        activated_at=NOW,
    )
    transaction_path = paths.activation_transactions / "ACTIVATE-ACT-TEST.json"

    import tcfactory.v3.activation_supervisor as supervisor

    def resolved_paths(_repo: Path) -> V3RuntimePaths:
        return paths

    def verify_suite(_path: Path, *, repo_root: Path, require_pass: bool) -> None:
        assert repo_root == repo.resolve()
        assert require_pass
        calls.append("verify")

    monkeypatch.setattr(supervisor, "resolve_v3_runtime_paths", resolved_paths)
    monkeypatch.setattr(
        supervisor,
        "verify_mandatory_canary_suite",
        verify_suite,
    )

    def activate(**_kwargs: object) -> ActivationTransaction:
        calls.append("activate")
        transaction_path.write_bytes(transaction.canonical_json_bytes())
        (runtime / "STOP").unlink(missing_ok=True)
        return transaction

    def stage(observed: ActivationTransaction, *, transaction_path: Path) -> Path:
        assert observed == transaction
        assert transaction_path == paths.activation_transactions / "ACTIVATE-ACT-TEST.json"
        calls.append("start")
        return tmp_path / "start.json"

    monkeypatch.setattr(supervisor, "activate_v31", activate)
    monkeypatch.setattr(supervisor, "stage_controller_start_request", stage)
    assert run_activation_supervisor(repo_root=repo) == (
        "ACTIVATED_START_REQUESTED:ACTIVATE-ACT-TEST"
    )
    assert calls == ["verify", "activate", "start"]
    # A timer replay with STOP absent resumes the journal and stages the same request.
    assert run_activation_supervisor(repo_root=repo) == (
        "ACTIVATED_START_REQUESTED:ACTIVATE-ACT-TEST"
    )
    assert calls[-2:] == ["activate", "start"]


def test_activation_supervisor_requests_fresh_policy_before_reusing_consumed_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "STOP").write_text("stopped\n", encoding="utf-8")
    paths = _runtime_paths(runtime)
    suite = paths.canary_results / "RUN" / "suite.json"
    suite.parent.mkdir(parents=True)
    suite.write_bytes(b"{}")
    calls: list[str] = []

    import tcfactory.v3.activation_supervisor as supervisor

    def resolved_paths(_repo: Path) -> V3RuntimePaths:
        return paths

    def accept_suite(
        _suite: Path, *, repo_root: Path, require_pass: bool
    ) -> None:
        assert repo_root == repo.resolve()
        assert require_pass

    monkeypatch.setattr(supervisor, "resolve_v3_runtime_paths", resolved_paths)
    monkeypatch.setattr(supervisor, "verify_mandatory_canary_suite", accept_suite)

    def no_unused_live_receipt(**_kwargs: object) -> Never:
        raise RuntimeError("the previous activation receipt was consumed")

    monkeypatch.setattr(supervisor, "activate_v31", no_unused_live_receipt)

    def request_policy(**_kwargs: object) -> Path:
        calls.append("policy")
        return tmp_path / "policy-request.json"

    def stale_activation_request(**_kwargs: object) -> Path:
        calls.append("stale-activation")
        return tmp_path / "old-request.json"

    monkeypatch.setattr(supervisor, "coordinate_activation_policy_request", request_policy)
    monkeypatch.setattr(supervisor, "coordinate_activation_request", stale_activation_request)
    assert run_activation_supervisor(repo_root=repo) == ("ACTIVATION_POLICY_REQUEST_SUBMITTED")
    assert calls == ["policy"]


def test_refresh_completion_forces_fresh_exact_canaries_and_never_reuses_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "HEAD")
    tree_sha = _git(repo, "rev-parse", "HEAD^{tree}")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    paths = _runtime_paths(runtime)
    paths.canary_results.mkdir(parents=True)
    old_suite = paths.canary_results / "OLD" / "suite.json"
    old_suite.parent.mkdir()
    old_suite.write_bytes(b"old suite must never be opened\n")
    completion = RefreshCompletionV31(
        transaction_id=main_sha + "-" + "1" * 16,
        handoff_digest=DIGEST,
        previous_main_sha="c" * 40,
        required_main_sha=main_sha,
        required_main_tree_sha=tree_sha,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST,
        generation_manifest_digest=DIGEST,
        runtime_manifest_digest=DIGEST,
        environment_digest=DIGEST,
        effective_config_digest=DIGEST,
        snapshot_manifest_digest=DIGEST,
        committed_at=NOW,
    )
    completion_root = tmp_path / "completion-inbox"
    completion_root.mkdir()
    completion_path = completion_root / f"{main_sha}-{completion.transaction_id}.json"
    completion_raw = completion.canonical_json_bytes()
    completion_path.write_bytes(completion_raw)
    calls: list[str] = []
    fresh_suite = tmp_path / "fresh-suite.bin"
    fresh_suite.write_bytes(b"fresh\n")
    runtime_manifest, runtime_loader = _runtime_loader()

    import tcfactory.v3.activation_supervisor as supervisor

    def resolved_paths(_repo: Path) -> V3RuntimePaths:
        return paths

    monkeypatch.setattr(supervisor, "resolve_v3_runtime_paths", resolved_paths)

    def accept_completion(**_kwargs: object) -> str:
        return "sha256:" + "f" * 64

    monkeypatch.setattr(
        supervisor,
        "_validate_refresh_completion",
        accept_completion,
    )

    def run_canaries(**kwargs: object) -> Path:
        result_root = kwargs["result_root"]
        assert isinstance(result_root, Path)
        assert "deployment-refresh" in result_root.parts
        calls.append("fresh-canaries")
        return fresh_suite

    fresh = SimpleNamespace(
        status=CanaryStatus.PASS,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        source_generation_id=completion.source_generation_id,
        source_generation_digest=completion.source_generation_digest,
    )
    monkeypatch.setattr(supervisor, "run_mandatory_canaries", run_canaries)

    def parse_fresh(_raw: bytes, *, strict: bool) -> SimpleNamespace:
        assert strict
        return fresh

    monkeypatch.setattr(supervisor.MandatoryCanarySuite, "model_validate_json", parse_fresh)

    def stage(**kwargs: object) -> Path:
        assert kwargs["canary_suite_path"] == fresh_suite
        assert kwargs["installed_runtime_loader"] is runtime_loader
        calls.append("fresh-request")
        request = tmp_path / "request.json"
        request.write_bytes(b"request\n")
        return request

    monkeypatch.setattr(supervisor, "stage_activation_request", stage)

    def no_policy_request(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        supervisor,
        "coordinate_activation_policy_request",
        no_policy_request,
    )

    def receipt_pending(**_kwargs: object) -> Never:
        raise RuntimeError("receipt pending")

    monkeypatch.setattr(supervisor, "activate_v31", receipt_pending)
    state = run_activation_supervisor(
        repo_root=repo,
        refresh_completion_root=completion_root,
        refresh_completion_loader=lambda _path: (completion, completion_raw),
        installed_runtime_loader=runtime_loader,
        installed_runtime_manifest_path=tmp_path / "runtime-manifest.json",
    )
    assert state == "ACTIVATION_REQUEST_SUBMITTED"
    assert calls == ["fresh-canaries", "fresh-request"]
    assert paths.stop.is_file()
    state_files = list((paths.state_root / "refresh-activation").glob("*.json"))
    assert len(state_files) == 1
    assert old_suite.read_bytes() == b"old suite must never be opened\n"
    assert runtime_manifest.repository_main_sha == "a" * 40
    fresh_suite.write_bytes(b"substituted\n")
    with pytest.raises(RuntimeError, match="evidence digest changed"):
        run_activation_supervisor(
            repo_root=repo,
            refresh_completion_root=completion_root,
            refresh_completion_loader=lambda _path: (completion, completion_raw),
            installed_runtime_loader=runtime_loader,
            installed_runtime_manifest_path=tmp_path / "runtime-manifest.json",
        )


def test_refresh_activation_recovers_broker_rollback_with_fresh_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "HEAD")
    tree_sha = _git(repo, "rev-parse", "HEAD^{tree}")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    paths = _runtime_paths(runtime)
    paths.stop.write_bytes(b"controller start broker rollback\n")
    paths.activation_transactions.mkdir()
    completion = RefreshCompletionV31(
        transaction_id=main_sha + "-" + "3" * 16,
        handoff_digest=DIGEST,
        previous_main_sha="c" * 40,
        required_main_sha=main_sha,
        required_main_tree_sha=tree_sha,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST,
        generation_manifest_digest=DIGEST,
        runtime_manifest_digest=DIGEST,
        environment_digest=DIGEST,
        effective_config_digest=DIGEST,
        snapshot_manifest_digest=DIGEST,
        committed_at=NOW,
    )
    completion_root = tmp_path / "completion-inbox"
    completion_root.mkdir()
    completion_path = completion_root / f"{main_sha}-{completion.transaction_id}.json"
    completion_raw = completion.canonical_json_bytes()
    completion_path.write_bytes(completion_raw)
    old_suite = (
        paths.canary_results
        / "deployment-refresh"
        / f"{completion.required_main_sha}-{completion.transaction_id}"
        / "OLD"
        / "suite.json"
    )
    old_suite.parent.mkdir(parents=True)
    old_suite.write_bytes(b"old suite\n")
    old_request = tmp_path / "old-request.json"
    old_request.write_bytes(b"old request\n")
    transaction = ActivationTransaction(
        schema_version="3.1",
        transaction_id="ACTIVATE-ACT-ROLLED-BACK",
        phase=ActivationPhase.ACTIVATED,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        activation_receipt_id="ACT-ROLLED-BACK",
        activation_receipt_digest=DIGEST,
        canary_suite_path=str(old_suite),
        canary_suite_digest=sha256_digest(old_suite.read_bytes()),
        preflight_digest=DIGEST,
        stop_digest=DIGEST,
        stop_archive_path=str(runtime / "old-stop"),
        prepared_at=NOW,
        activated_at=NOW,
    )
    transaction_path = paths.activation_transactions / f"{transaction.transaction_id}.json"
    transaction_raw = transaction.canonical_json_bytes()
    transaction_path.write_bytes(transaction_raw)
    state = RefreshActivationState(
        completion_path=str(completion_path),
        completion_digest=sha256_digest(completion_raw),
        completion=completion,
        phase="START_REQUESTED",
        canary_suite_path=str(old_suite),
        canary_suite_digest=sha256_digest(old_suite.read_bytes()),
        activation_request_path=str(old_request),
        activation_request_digest=sha256_digest(old_request.read_bytes()),
        activation_transaction_path=str(transaction_path),
        activation_transaction_digest=sha256_digest(transaction_raw),
        updated_at=NOW,
    )
    state_path = activation_supervisor._refresh_state_path(  # pyright: ignore[reportPrivateUsage]
        paths, completion
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(state.canonical_json_bytes())
    fresh_suite = tmp_path / "fresh-suite.json"
    fresh_suite.write_bytes(b"fresh suite\n")
    _runtime, runtime_loader = _runtime_loader()
    calls: list[str] = []

    def resolved_paths(_repo: Path) -> V3RuntimePaths:
        return paths

    monkeypatch.setattr(activation_supervisor, "resolve_v3_runtime_paths", resolved_paths)

    def validate_completion(**_kwargs: object) -> str:
        return sha256_digest(completion_raw)

    monkeypatch.setattr(
        activation_supervisor,
        "_validate_refresh_completion",
        validate_completion,
    )

    def run_canaries(**_kwargs: object) -> Path:
        calls.append("fresh-canaries")
        return fresh_suite

    monkeypatch.setattr(activation_supervisor, "run_mandatory_canaries", run_canaries)
    fresh = SimpleNamespace(
        status=CanaryStatus.PASS,
        exact_main_sha=main_sha,
        exact_tree_sha=tree_sha,
        source_generation_id=completion.source_generation_id,
        source_generation_digest=completion.source_generation_digest,
    )
    def parse_fresh(_raw: bytes, *, strict: bool) -> SimpleNamespace:
        assert strict
        return fresh

    monkeypatch.setattr(
        activation_supervisor.MandatoryCanarySuite,
        "model_validate_json",
        parse_fresh,
    )

    def request_policy(**kwargs: object) -> Path:
        assert kwargs["canary_suite_path"] == fresh_suite
        calls.append("fresh-policy")
        return tmp_path / "policy-request.json"

    monkeypatch.setattr(
        activation_supervisor,
        "coordinate_activation_policy_request",
        request_policy,
    )
    def reject_old_authority(**_kwargs: object) -> Never:
        pytest.fail("old authority must not be reused")

    def reject_direct_start(*_args: object, **_kwargs: object) -> Never:
        pytest.fail("controller must remain stopped")

    monkeypatch.setattr(
        activation_supervisor,
        "stage_activation_request",
        reject_old_authority,
    )
    monkeypatch.setattr(
        activation_supervisor,
        "stage_controller_start_request",
        reject_direct_start,
    )

    assert (
        run_activation_supervisor(
            repo_root=repo,
            refresh_completion_root=completion_root,
            refresh_completion_loader=lambda _path: (completion, completion_raw),
            installed_runtime_loader=runtime_loader,
            installed_runtime_manifest_path=tmp_path / "runtime-manifest.json",
        )
        == "ACTIVATION_POLICY_REQUEST_SUBMITTED"
    )
    assert calls == ["fresh-canaries", "fresh-policy"]
    assert paths.stop.read_bytes() == b"controller start broker rollback\n"
    recovered = RefreshActivationState.model_validate_json(
        state_path.read_bytes(), strict=True
    )
    assert recovered.phase == "CANARIES_PASSED"
    assert recovered.canary_suite_path == str(fresh_suite)
    assert recovered.activation_request_path is None
    assert recovered.activation_transaction_path is None


def test_refresh_completion_substitution_and_ambiguity_fail_before_canaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    main_sha = _git(repo, "rev-parse", "HEAD")
    tree_sha = _git(repo, "rev-parse", "HEAD^{tree}")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    paths = _runtime_paths(runtime)
    completion = RefreshCompletionV31(
        transaction_id=main_sha + "-" + "2" * 16,
        handoff_digest=DIGEST,
        previous_main_sha="c" * 40,
        required_main_sha=main_sha,
        required_main_tree_sha=tree_sha,
        source_generation_id="traincapsule-v3.1-zh-2026-08-12",
        source_generation_digest=DIGEST,
        generation_manifest_digest=DIGEST,
        runtime_manifest_digest=DIGEST,
        environment_digest=DIGEST,
        effective_config_digest=DIGEST,
        snapshot_manifest_digest=DIGEST,
        committed_at=NOW,
    )
    raw = completion.canonical_json_bytes()
    for suffix in ("one", "two"):
        (tmp_path / f"claim-{suffix}.json").write_bytes(raw)
    import tcfactory.v3.activation_supervisor as supervisor

    def resolved_paths(_repo: Path) -> V3RuntimePaths:
        return paths

    monkeypatch.setattr(supervisor, "resolve_v3_runtime_paths", resolved_paths)
    called = False

    def no_canaries(**_kwargs: object) -> Path:
        nonlocal called
        called = True
        raise AssertionError

    monkeypatch.setattr(supervisor, "run_mandatory_canaries", no_canaries)
    with pytest.raises(RuntimeError, match="multiple refresh completions"):
        run_activation_supervisor(
            repo_root=repo,
            refresh_completion_root=tmp_path,
            refresh_completion_loader=lambda path: (completion, path.read_bytes()),
        )
    assert not called


def test_activation_receipt_contract_matches_independent_verifier() -> None:
    verifier_src = Path(__file__).resolve().parents[1] / "verifier/src"
    sys.path.insert(0, str(verifier_src))
    try:
        from traincapsule_verifier.models import ActivationReceipt

        verifier_schema = ActivationReceipt.model_json_schema(by_alias=True)
    finally:
        sys.path.remove(str(verifier_src))
    factory_schema = ActivationReceiptV31.model_json_schema(by_alias=True)
    assert set(verifier_schema["properties"]) == set(factory_schema["properties"])
    assert set(verifier_schema["required"]) == set(factory_schema["required"])
    assert factory_schema["properties"]["signature"] == verifier_schema["properties"]["signature"]
    invalid_lifetime = {
        "schemaVersion": "3.1",
        "receiptId": "ACT-TEST",
        "verifiedMainSha": "a" * 40,
        "machineEnvironmentDigest": DIGEST,
        "sourceGenerationId": "traincapsule-v3.1-zh-2026-08-12",
        "sourceGenerationDigest": DIGEST,
        "controllerBinaryDigest": DIGEST,
        "controllerConfigDigest": DIGEST,
        "machineEnvironmentPath": "machine.json",
        "controllerBinaryPath": "controller.py",
        "controllerConfigPath": "factory.yaml",
        "machinePolicyReceiptId": "MPR-TEST",
        "machinePolicyReceiptDigest": DIGEST,
        "mode": ActivationMode.LIVE,
        "issuedAt": NOW,
        "expiresAt": NOW + timedelta(hours=2),
        "revocationEpoch": 1,
        "nonce": "0123456789abcdef",
        "issuerId": "ISSUER",
        "issuerKeyId": "KEY-1",
        "signatureAlgorithm": "ed25519",
        "signature": "A" * 80,
    }
    with pytest.raises(ValidationError, match="at most 1:00:00"):
        ActivationReceiptV31.model_validate(
            invalid_lifetime,
            strict=True,
        )

    valid = invalid_lifetime | {"expiresAt": NOW + timedelta(minutes=30)}
    factory_receipt = ActivationReceiptV31.model_validate(valid, strict=True)
    verifier_receipt = ActivationReceipt.model_validate_json(
        factory_receipt.canonical_json_bytes(), strict=True
    )
    assert factory_receipt.source_generation_id == "traincapsule-v3.1-zh-2026-08-12"
    assert verifier_receipt.source_generation_id == factory_receipt.source_generation_id
    for substituted in (
        "Traincapsule-v3.1-zh-2026-08-12",
        "../traincapsule-v3.1-zh-2026-08-12",
        " traincapsule-v3.1-zh-2026-08-12",
        "traincapsule-v3.1-zh-2026-08-12 ",
    ):
        candidate = valid | {"sourceGenerationId": substituted}
        with pytest.raises(ValidationError):
            ActivationReceiptV31.model_validate(candidate, strict=True)
        with pytest.raises(ValidationError):
            ActivationReceipt.model_validate(candidate, strict=True)


def test_missing_live_runner_emits_only_typed_blocked_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.setattr(canaries, "validate_active_source_generation", _active_for_path)

    def unavailable(_: Path) -> _PassingRunner:
        raise OSError("not installed")

    suite_path = run_mandatory_canaries(
        repo_root=repo,
        result_root=tmp_path / "blocked-results",
        runner_factory=unavailable,
        now=NOW,
    )
    suite = verify_mandatory_canary_suite(suite_path, repo_root=repo, require_pass=False)
    assert suite.status is CanaryStatus.BLOCKED_PREREQUISITE
    assert set(suite.result_artifacts) == set(MandatoryCanaryId)
    assert len(MandatoryCanaryId) == 20
    with pytest.raises(RuntimeError, match="have not passed"):
        verify_mandatory_canary_suite(suite_path, repo_root=repo, require_pass=True)


def test_external_canary_runner_validates_strict_json_at_the_process_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "runner"
    executable.write_bytes(b"runner")
    observed = executable.lstat()
    runner_digest = f"sha256:{canaries.sha256_file(executable)}"
    payload: dict[str, object] = {
        "schemaVersion": "3.1",
        "runId": "CANARY-STRICT-JSON-001",
        "canaryId": MandatoryCanaryId.PROCESS_KILL_AND_RESUME.value,
        "exactMainSha": "a" * 40,
        "exactTreeSha": "b" * 40,
        "runnerDigest": runner_digest,
        "status": CanaryStatus.BLOCKED_PREREQUISITE.value,
        "evidenceArtifacts": {},
        "startedAt": NOW.isoformat(),
        "completedAt": NOW.isoformat(),
        "failureReason": "blocked test result",
    }

    def trust(path: Path, **_kwargs: object) -> tuple[Path, os.stat_result]:
        return path, observed

    def command(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    monkeypatch.setattr(canaries, "trusted_external_path", trust)
    monkeypatch.setattr(canaries, "run_command", command)
    runner = canaries.ExternalCanaryRunner(executable)
    result = runner.run(
        canary_id=MandatoryCanaryId.PROCESS_KILL_AND_RESUME,
        run_id="CANARY-STRICT-JSON-001",
        repo_root=tmp_path,
        runtime_root=tmp_path,
        artifact_root=tmp_path,
        exact_main_sha="a" * 40,
        exact_tree_sha="b" * 40,
    )
    assert result.status is CanaryStatus.BLOCKED_PREREQUISITE


def test_canary_publication_remote_is_explicit_and_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    _git(repo, "remote", "remove", "origin")
    monkeypatch.setattr(canaries, "validate_active_source_generation", _active_for_path)
    suite_path = run_mandatory_canaries(
        repo_root=repo,
        result_root=tmp_path / "explicit-remote-results",
        runner_factory=_passing_runner,
        publication_remote=canaries.CANARY_PUBLICATION_REMOTE,
        now=NOW,
    )
    assert verify_mandatory_canary_suite(suite_path, repo_root=repo).status is CanaryStatus.PASS
    with pytest.raises(RuntimeError, match="publication remote is not trusted"):
        canaries._prepare_isolated_canary_repo(  # pyright: ignore[reportPrivateUsage]
            repo_root=repo,
            run_root=tmp_path / "untrusted-remote",
            exact_main_sha=_git(repo, "rev-parse", "HEAD"),
            exact_tree_sha=_git(repo, "rev-parse", "HEAD^{tree}"),
            publication_remote="https://github.com/attacker/repository.git",
        )


def test_relative_canary_result_root_keeps_bundle_clone_addressable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(canaries, "validate_active_source_generation", _active_for_path)

    suite_path = run_mandatory_canaries(
        repo_root=repo,
        result_root=Path("relative-results"),
        runner_factory=_passing_runner,
        now=NOW,
    )

    assert suite_path.is_absolute()
    assert verify_mandatory_canary_suite(
        suite_path, repo_root=repo
    ).status is CanaryStatus.PASS
    assert (suite_path.parent / "isolated-repo/.git").is_dir()


def test_canary_suite_reopens_every_exact_result_and_evidence_byte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    suite_path = _suite(repo, tmp_path, monkeypatch)
    suite = verify_mandatory_canary_suite(suite_path, repo_root=repo)
    assert suite.status is CanaryStatus.PASS
    result = (
        suite_path.parent / suite.result_artifacts[MandatoryCanaryId.REAL_CLAUDE_MECHANICAL_TASK]
    )
    result.write_bytes(result.read_bytes() + b" ")
    with pytest.raises(RuntimeError, match="substitution"):
        verify_mandatory_canary_suite(suite_path, repo_root=repo)


def test_post_activation_observation_binds_exact_roster_tree_and_evidence(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    observation_root = tmp_path / "observation"
    observation_root.mkdir()
    artifacts: dict[PostActivationObservationId, str] = {}
    digests: dict[PostActivationObservationId, str] = {}
    for observation_id in PostActivationObservationId:
        relative = f"{observation_id.value}.json"
        payload = json.dumps({"observation": observation_id.value}).encode()
        (observation_root / relative).write_bytes(payload)
        artifacts[observation_id] = relative
        digests[observation_id] = sha256_digest(payload)
    activation_digest = "sha256:" + "d" * 64
    observation = PostActivationObservation(
        schema_version="3.1",
        observation_id="OBS-AUTONOMY-20260812",
        activation_receipt_id="ACT-EXACT-CANARY",
        activation_receipt_digest=activation_digest,
        exact_main_sha=_git(repo, "rev-parse", "HEAD"),
        exact_tree_sha=_git(repo, "rev-parse", "HEAD^{tree}"),
        evidence_artifacts=artifacts,
        evidence_digests=digests,
        started_at=NOW,
        completed_at=NOW,
    )
    path = observation_root / "observation.json"
    path.write_bytes(observation.canonical_json_bytes())
    assert (
        verify_post_activation_observation(
            path,
            repo_root=repo,
            activation_receipt_id=observation.activation_receipt_id,
            activation_receipt_digest=activation_digest,
        )
        == observation
    )
    (observation_root / next(iter(artifacts.values()))).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        verify_post_activation_observation(
            path,
            repo_root=repo,
            activation_receipt_id=observation.activation_receipt_id,
            activation_receipt_digest=activation_digest,
        )


def test_canary_suite_rejects_a_later_head_or_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    suite_path = _suite(repo, tmp_path, monkeypatch)
    (repo / "config/factory.yaml").write_text(
        "schemaVersion: '3.1'\nchanged: true\n", encoding="utf-8"
    )
    _git(repo, "add", "config/factory.yaml")
    _git(
        repo,
        "-c",
        "user.name=Canary Test",
        "-c",
        "user.email=canary@example.invalid",
        "commit",
        "-m",
        "new exact tree",
    )
    with pytest.raises(RuntimeError, match="stale for current exact HEAD/tree"):
        verify_mandatory_canary_suite(suite_path, repo_root=repo)


def _activation_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, V3RuntimePaths, ActivationReceiptV31, RuntimeLoader]:
    repo = _repo(tmp_path)
    suite = _suite(repo, tmp_path, monkeypatch)
    paths = _runtime_paths(tmp_path / "runtime")
    paths.state_root.mkdir()
    paths.stop.write_bytes(b"migration hold\n")
    receipt_path = tmp_path / "external/activation.json"
    runtime_manifest, runtime_loader = _runtime_loader()
    receipt = _receipt(repo, suite, receipt_path, runtime_manifest)

    def runtime_paths(_: Path) -> V3RuntimePaths:
        return paths

    def github_config(_: Path) -> SimpleNamespace:
        return SimpleNamespace(activation_receipt_path=str(receipt_path))

    def disabled_autonomy(_: Path) -> SimpleNamespace:
        return SimpleNamespace(enabled=False)

    monkeypatch.setattr(activation, "resolve_v3_runtime_paths", runtime_paths)
    monkeypatch.setattr(
        activation,
        "load_github_config",
        github_config,
    )
    monkeypatch.setattr(activation, "load_autonomy_v3", disabled_autonomy)
    return repo, suite, paths, receipt, runtime_loader


def test_activation_is_atomic_auditable_idempotent_and_crash_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, suite, paths, receipt, runtime_loader = _activation_fixture(tmp_path, monkeypatch)

    def preflight(_: Path, *, allow_stop_for_activation: bool) -> dict[str, object]:
        assert allow_stop_for_activation is True
        return {"activationReceiptDigest": receipt.canonical_digest(), "ready": True}

    original_write = activation._write_transaction  # pyright: ignore[reportPrivateUsage]
    crashed = False

    def crash_after_archive(path: Path, transaction: ActivationTransaction) -> None:
        nonlocal crashed
        if transaction.phase is ActivationPhase.ACTIVATED and not crashed:
            crashed = True
            raise OSError("injected post-archive crash")
        original_write(path, transaction)

    monkeypatch.setattr(activation, "_write_transaction", crash_after_archive)
    with pytest.raises(OSError, match="injected"):
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=preflight,
            now=NOW,
            installed_runtime_loader=runtime_loader,
        )
    assert not paths.stop.exists()
    prepared_path = next(paths.activation_transactions.glob("*.json"))
    prepared = ActivationTransaction.model_validate_json(prepared_path.read_bytes(), strict=True)
    assert prepared.phase is ActivationPhase.PREPARED
    assert Path(prepared.stop_archive_path).read_bytes() == b"migration hold\n"

    monkeypatch.setattr(activation, "_write_transaction", original_write)
    completed = activate_v31(
        repo_root=repo,
        canary_suite_path=suite,
        preflight=preflight,
        now=NOW,
        installed_runtime_loader=runtime_loader,
    )
    assert completed.phase is ActivationPhase.ACTIVATED
    assert (
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=preflight,
            now=NOW,
            installed_runtime_loader=runtime_loader,
        )
        == completed
    )
    assert (
        validate_activation_control_state(
            paths=paths,
            exact_main_sha=completed.exact_main_sha,
            activation_receipt_digest=receipt.canonical_digest(),
        )
        == completed
    )


def test_activation_failure_or_hard_stuck_never_moves_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, suite, paths, receipt, runtime_loader = _activation_fixture(tmp_path, monkeypatch)

    def rejected(_: Path, *, allow_stop_for_activation: bool) -> dict[str, object]:
        del allow_stop_for_activation
        raise RuntimeError("ruleset missing")

    with pytest.raises(RuntimeError, match="ruleset missing"):
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=rejected,
            installed_runtime_loader=runtime_loader,
        )
    assert paths.stop.read_bytes() == b"migration hold\n"
    assert not paths.activation_transactions.exists()
    paths.hard_stuck.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="HARD_STUCK"):
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=lambda *_args, **_kwargs: {
                "activationReceiptDigest": receipt.canonical_digest()
            },
            installed_runtime_loader=runtime_loader,
        )
    assert paths.stop.exists()


def test_activation_process_lock_prevents_competing_stop_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, suite, paths, receipt, runtime_loader = _activation_fixture(tmp_path, monkeypatch)
    with (
        controller_process_lock(paths.state_root / "activation.lock"),
        pytest.raises(ControllerLockError, match="already active"),
    ):
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=lambda *_args, **_kwargs: {
                "activationReceiptDigest": receipt.canonical_digest()
            },
            now=NOW,
            installed_runtime_loader=runtime_loader,
        )
    assert paths.stop.read_bytes() == b"migration hold\n"
    assert not paths.activation_transactions.exists()


def test_activation_rejects_a_stale_or_substituted_live_receipt_before_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, suite, paths, receipt, runtime_loader = _activation_fixture(tmp_path, monkeypatch)
    receipt_path = tmp_path / "external/activation.json"
    substituted = receipt.model_copy(update={"machine_environment_digest": DIGEST})
    receipt_path.write_bytes(substituted.canonical_json_bytes())
    called = False

    def preflight_must_not_run(_: Path, *, allow_stop_for_activation: bool) -> dict[str, object]:
        nonlocal called
        del allow_stop_for_activation
        called = True
        return {}

    with pytest.raises(RuntimeError, match="exact mandatory canary suite bytes"):
        activate_v31(
            repo_root=repo,
            canary_suite_path=suite,
            preflight=preflight_must_not_run,
            now=NOW,
            installed_runtime_loader=runtime_loader,
        )
    assert called is False
    assert paths.stop.read_bytes() == b"migration hold\n"
    assert not paths.activation_transactions.exists()


def test_direct_controller_entry_runs_full_supervisor_preflight_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def reject(repo: Path) -> dict[str, object]:
        calls.append(repo)
        raise RuntimeError("full preflight sentinel")

    monkeypatch.setattr(cli, "run_startup_preflight", reject)

    def publisher_must_not_run(**_: object) -> Never:
        pytest.fail("publisher constructed before full preflight")

    monkeypatch.setattr(cli, "build_automated_pr_publisher", publisher_must_not_run)
    with pytest.raises(RuntimeError, match="full preflight sentinel"):
        cli.v3_controller(repo=tmp_path, once=True)
    assert calls == [tmp_path.resolve()]
