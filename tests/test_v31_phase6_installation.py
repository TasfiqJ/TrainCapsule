from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tcfactory import cli
from tcfactory.util import sha256_file, write_json
from tcfactory.v3.contracts_v31 import (
    CommercialState,
    DecisionValueDisposition,
    GateResult,
    MachinePolicyReceiptV31,
    NativeSubstituteDisposition,
    PolicyDecision,
    TechnicalState,
)
from tcfactory.v3.enums import (
    Lane,
    RiskTier,
)
from tcfactory.v3.external_actions import (
    ExternalActionChannel,
    ExternalActionInstallation,
    ExternalActionRequest,
    ExternalActionTemplate,
    external_action_authorization_digest,
    external_action_digest,
)
from tcfactory.v3.phase6_installation import (
    ExternalActionItemInstallation,
    InstalledFile,
    Phase6InstallationError,
    Phase6InstallationManifest,
    ResearchItemInstallation,
    build_phase6_runtime,
    load_phase6_runtime,
)
from tcfactory.v3.phase6_runtime import (
    Phase6ControllerRuntime,
    ResearchOutputDeclaration,
    ResearchOutputKind,
    _trusted_controller_json,  # pyright: ignore[reportPrivateUsage]
)

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)
SHA = "a" * 40
DIGEST = "sha256:" + "c" * 64


def _digest(path: Path) -> str:
    return f"sha256:{sha256_file(path)}"


def _machine_receipt(request_digest: str = DIGEST) -> MachinePolicyReceiptV31:
    return MachinePolicyReceiptV31.model_validate(
        {
            "schema_version": "3.1",
            "receipt_id": "RECEIPT:EXTERNAL:001",
            "policy_id": "POLICY:EXTERNAL:001",
            "policy_version": "3.1.0",
            "issuer_id": "VERIFIER:LOCAL:001",
            "issuer_key_id": "KEY:ED25519:001",
            "issued_at": NOW - timedelta(minutes=1),
            "expires_at": NOW + timedelta(hours=1),
            "revocation_epoch": 1,
            "nonce": "0123456789abcdef",
            "request_digest": request_digest,
            "work_item_id": "V3-MKT-003",
            "milestone_id": "M1_NATIVE_PREFLIGHT",
            "lane": Lane.MARKET,
            "risk_tier": RiskTier.EXTERNAL,
            "candidate_sha": SHA,
            "candidate_tree_sha": "b" * 40,
            "base_sha": "e" * 40,
            "source_generation_id": "traincapsule-v3.1-zh-2026-08-12",
            "source_generation_digest": DIGEST,
            "context_manifest_digest": DIGEST,
            "task_packet_digest": DIGEST,
            "candidate_manifest_digest": DIGEST,
            "checkpoint_digest": DIGEST,
            "required_gate_results": {"EXTERNAL-ACTION": GateResult.PASS},
            "private_gate_suite_id": "EXTERNAL-ACTION-V31",
            "private_gate_runner_digest": DIGEST,
            "independent_oracle_ids": ["ORACLE:EXTERNAL:001"],
            "raw_evidence_artifact_hashes": ["sha256:" + "d" * 64],
            "native_substitute_disposition": NativeSubstituteDisposition.INCREMENTAL_VALUE,
            "decision_value_disposition": (
                DecisionValueDisposition.INCREMENTAL_DECISION_VALUE_DEMONSTRATED
            ),
            "engineering_maturity_ceiling": TechnicalState.PASSED,
            "commercial_maturity_ceiling": CommercialState.PILOT_ELIGIBLE,
            "allowed_claims": ["EXTERNAL_ACTION"],
            "forbidden_claims": [],
            "publication_scope": ["factory/actions/**"],
            "decision": PolicyDecision.PASS,
            "signature_algorithm": "ed25519",
            "signature": "f" * 128,
        },
        strict=True,
    )


def _action_models() -> tuple[ExternalActionInstallation, ExternalActionRequest]:
    template = ExternalActionTemplate(
        schema_version="3.1",
        template_id="TEMPLATE:EMAIL:001",
        channel=ExternalActionChannel.EMAIL,
        subject_template="Hello {name}",
        body_template="Approved {message} for {name}",
        variable_names=["name", "message"],
    )

    def installation(receipt: MachinePolicyReceiptV31) -> ExternalActionInstallation:
        return ExternalActionInstallation(
            schema_version="3.1",
            machine_policy_receipt=receipt,
            independent_verifier_receipt_digest="sha256:" + "d" * 64,
            credential_reference="CREDREF:MAIL/PROD",
            backend_id="BACKEND:MAIL:001",
            recipient_allowlist=["allowed@example.test"],
            legal_policy_id="LEGAL:OUTREACH:001",
            legal_policy_digest=DIGEST,
            safety_policy_id="SAFETY:OUTREACH:001",
            safety_policy_digest="sha256:" + "d" * 64,
            machine_policy_scope=["factory/actions/**"],
            channel=ExternalActionChannel.EMAIL,
            template=template,
        )

    def request(receipt: MachinePolicyReceiptV31) -> ExternalActionRequest:
        return ExternalActionRequest(
            schema_version="3.1",
            action_id="ACTION:EMAIL:001",
            work_item_id=receipt.work_item_id,
            candidate_sha=receipt.candidate_sha,
            channel=ExternalActionChannel.EMAIL,
            recipient="allowed@example.test",
            template_id=template.template_id,
            variables={"name": "Ada", "message": "bounded outreach"},
            machine_policy_receipt_id=receipt.receipt_id,
            machine_policy_receipt_digest=external_action_digest(receipt),
            requested_at=NOW,
        )

    initial = _machine_receipt()
    bound = _machine_receipt(
        external_action_authorization_digest(request(initial), installation(initial))
    )
    return installation(bound), request(bound)


def _write_executable(path: Path) -> None:
    path.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    path.chmod(0o500)


def _installed_file(path: Path) -> InstalledFile:
    return InstalledFile(path=path, digest=_digest(path))


def _installation_fixture(
    tmp_path: Path, repo_root: Path
) -> tuple[Path, Path, Phase6InstallationManifest, Ed25519PrivateKey]:
    install = tmp_path / "etc" / "traincapsule-factory" / "phase6"
    service = tmp_path / "var" / "lib" / "traincapsule-factory" / "phase6"
    plans = install / "plans"
    actions = install / "actions"
    for path in (plans, actions, service / "cas", service / "journal", service / "outcomes"):
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.chmod(0o700)
    service.chmod(0o700)
    policy = install / "source-policy.json"
    write_json(
        policy,
        {
            "schemaVersion": "3.1",
            "policyId": "POLICY:RESEARCH:001",
            "allowedHostnames": ["docs.example.test"],
            "timeoutSeconds": 10.0,
            "maxResponseBytes": 100000,
            "maxSourcesPerPlan": 8,
            "allowedContentTypes": ["application/json"],
            "userAgent": "TrainCapsule/3.1",
            "allowedMethods": ["GET"],
            "maxRedirects": 2,
            "maximumFreshnessSeconds": 86400,
        },
    )
    authority = install / "source-authority"
    control_oracle = install / "research-control-oracle"
    verifier = install / "public-verifier"
    backend = install / "action-backend"
    for executable in (authority, control_oracle, verifier, backend):
        _write_executable(executable)
    legal = install / "legal.json"
    safety = install / "safety.json"
    legal.write_text("legal\n", encoding="utf-8")
    safety.write_text("safety\n", encoding="utf-8")
    installation, request = _action_models()
    installation = installation.model_copy(
        update={
            "legal_policy_digest": _digest(legal),
            "safety_policy_digest": _digest(safety),
        }
    )
    # Rebind the independent authorization after installed policy digests change.
    receipt = installation.machine_policy_receipt.model_copy(
        update={"request_digest": external_action_authorization_digest(request, installation)}
    )
    installation = installation.model_copy(update={"machine_policy_receipt": receipt})
    request = request.model_copy(
        update={
            "machine_policy_receipt_digest": external_action_digest(receipt),
            "machine_policy_receipt_id": receipt.receipt_id,
        }
    )
    installation_path = install / "external-installation.json"
    receipt_path = install / "external-receipt.json"
    request_path = actions / "V3-MKT-003.json"
    for path, model in (
        (installation_path, installation),
        (receipt_path, receipt),
        (request_path, request),
    ):
        path.write_bytes(model.canonical_json_bytes())

    roadmap_raw = cast(dict[str, object], __import__("yaml").safe_load(
        (repo_root / "factory/roadmap/work_items.yaml").read_text(encoding="utf-8")
    ))
    research_rows = [
        cast(dict[str, object], value)
        for value in cast(list[object], roadmap_raw["workItems"])
        if cast(dict[str, object], value).get("kind") == "RESEARCH"
        and cast(dict[str, object], value).get("lane") in {"MARKET", "COMPETITOR"}
    ]
    research: dict[str, ResearchItemInstallation] = {}
    for row in research_rows:
        work_id = cast(str, row["workItemId"])
        plan = plans / f"{work_id}.json"
        controls = plans / f"{work_id}.controls.json"
        plan.write_text("{}\n", encoding="utf-8")
        controls.write_text("[]\n", encoding="utf-8")
        outputs: list[ResearchOutputDeclaration] = []
        kinds = (
            [ResearchOutputKind.REACHABLE_ACCOUNT_MAP]
            if work_id == "V3-MKT-001"
            else [
                ResearchOutputKind.DISCOVERY_INTERVIEW_GUIDE,
                ResearchOutputKind.PILOT_QUALIFICATION_RUBRIC,
            ]
            if work_id == "V3-MKT-002"
            else []
        )
        suffixes = {
            ResearchOutputKind.REACHABLE_ACCOUNT_MAP: ".reachable-account-map.json",
            ResearchOutputKind.DISCOVERY_INTERVIEW_GUIDE: ".discovery-interview-guide.json",
            ResearchOutputKind.PILOT_QUALIFICATION_RUBRIC: ".pilot-qualification-rubric.json",
        }
        for kind in kinds:
            record = plans / f"{work_id}{suffixes[kind]}"
            record.write_text("{}\n", encoding="utf-8")
            outputs.append(
                ResearchOutputDeclaration(
                    kind=kind,
                    record_suffix=suffixes[kind],
                    record_digest=_digest(record),
                )
            )
        research[work_id] = ResearchItemInstallation(
            plan=_installed_file(plan),
            controls=_installed_file(controls),
            outputs=tuple(outputs),
        )

    manifest = Phase6InstallationManifest(
        schema_version="3.1",
        installation_id="PHASE6:TEST:001",
        service_owner_uid=os.getuid(),
        research_policy=_installed_file(policy),
        source_receipt_authority_executable=_installed_file(authority),
        research_control_oracle_executable=_installed_file(control_oracle),
        source_receipt_issuer_id="SOURCE:AUTHORITY:001",
        source_receipt_key_id="KEY:SOURCE:001",
        research_cas_root=service / "cas",
        research_items=research,
        external_action_installation=_installed_file(installation_path),
        external_machine_receipt=_installed_file(receipt_path),
        external_legal_policy=_installed_file(legal),
        external_safety_policy=_installed_file(safety),
        external_public_verifier_executable=_installed_file(verifier),
        external_backend_executable=_installed_file(backend),
        external_action_items={
            "V3-MKT-003": ExternalActionItemInstallation(
                request=_installed_file(request_path)
            )
        },
        external_journal_root=service / "journal",
        external_outcome_root=service / "outcomes",
    )
    private = Ed25519PrivateKey.generate()
    manifest_path = install / "installation.json"
    manifest_path.write_bytes(manifest.canonical_json_bytes())
    (install / "installation.json.sig").write_text(
        private.sign(manifest_path.read_bytes()).hex() + "\n", encoding="utf-8"
    )
    (install / "manifest-public-key.pem").write_bytes(
        private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return install, service, manifest, private


def test_valid_install_covers_all_seven_research_rows_and_uses_explicit_outputs(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    install, service, _, _ = _installation_fixture(tmp_path, repo)

    runtime = load_phase6_runtime(
        repo_root=repo,
        install_root=install,
        service_root=service,
        expected_root_uid=os.getuid(),
    )

    assert set(runtime.research_output_declarations) == {
        "V3-COMP-002",
        "V3-COMP-004",
        "V3-MKT-001",
        "V3-MKT-002",
        "V3-MKT-009",
        "V3-REPEAT-005",
        "V3-REPEAT-006",
    }
    assert {
        value.kind for value in runtime.research_output_declarations["V3-MKT-001"]
    } == {ResearchOutputKind.REACHABLE_ACCOUNT_MAP}
    assert runtime.handles_external_action(
        cast(Any, type("Item", (), {"work_item_id": "V3-MKT-003"})())
    )


def test_trusted_install_owner_is_independent_of_controller_process_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Path(__file__).resolve().parents[1]
    install, service, _, _ = _installation_fixture(tmp_path, repo)
    runtime = load_phase6_runtime(
        repo_root=repo,
        install_root=install,
        service_root=service,
        expected_root_uid=os.getuid(),
    )
    assert runtime.trusted_input_owner_uid == os.getuid()
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1000)
    # Explicit installed-owner binding remains stable and the service process can
    # actually reopen/read the root-owned (simulated by expected_root_uid) record.
    assert runtime.trusted_input_owner_uid != os.geteuid()
    _, raw = _trusted_controller_json(  # pyright: ignore[reportPrivateUsage]
        runtime.research_plan_root,
        "V3-MKT-001",
        ".json",
        expected_owner_uid=runtime.trusted_input_owner_uid,
    )
    assert raw == {}


def test_service_root_wrong_owner_and_manifest_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    install, service, manifest, private = _installation_fixture(tmp_path, repo)
    manifest.service_owner_uid = os.getuid() + 1
    manifest_path = install / "installation.json"
    manifest_path.write_bytes(manifest.canonical_json_bytes())
    (install / "installation.json.sig").write_text(
        private.sign(manifest_path.read_bytes()).hex() + "\n", encoding="utf-8"
    )
    # Even a correctly signed manifest cannot misdeclare the service-owned root.
    with pytest.raises(Phase6InstallationError, match="wrong type or owner"):
        load_phase6_runtime(
            repo_root=repo,
            install_root=install,
            service_root=service,
            expected_root_uid=os.getuid(),
        )


def test_service_roots_require_owner_only_mode_and_reject_path_replacement(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[1]
    install, service, _, _ = _installation_fixture(tmp_path, repo)
    (service / "cas").chmod(0o770)
    with pytest.raises(Phase6InstallationError, match="0700"):
        load_phase6_runtime(
            repo_root=repo,
            install_root=install,
            service_root=service,
            expected_root_uid=os.getuid(),
        )
    (service / "cas").chmod(0o700)
    runtime = load_phase6_runtime(
        repo_root=repo,
        install_root=install,
        service_root=service,
        expected_root_uid=os.getuid(),
    )
    original = service / "journal"
    moved = service / "journal-original"
    original.rename(moved)
    original.mkdir(mode=0o700)
    journal = cast(Any, runtime.external_action_adapter).journal
    with pytest.raises(Exception, match="identity changed"):
        journal.reserve("sha256:" + "a" * 64)


def test_cli_construction_receives_non_inert_runtime_and_missing_install_is_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Path(__file__).resolve().parents[1]
    install, service, _, _ = _installation_fixture(tmp_path, repo)
    runtime = load_phase6_runtime(
        repo_root=repo,
        install_root=install,
        service_root=service,
        expected_root_uid=os.getuid(),
    )
    captured: dict[str, object] = {}

    class Controller:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("tcfactory.v3.controller.V3Controller", Controller)
    def installed_runtime(*, repo_root: Path) -> Phase6ControllerRuntime:
        del repo_root
        return runtime

    def backend(_: object) -> object:
        return object()

    def credentials(**_: object) -> object:
        return object()

    monkeypatch.setattr(
        "tcfactory.v3.phase6_installation.build_phase6_runtime", installed_runtime
    )
    monkeypatch.setattr("tcfactory.backends.claude.ClaudeBackend", backend)
    monkeypatch.setattr("tcfactory.backends.claude.ClaudeCredentialProvider", credentials)
    cli._construct_live_v3_controller(  # pyright: ignore[reportPrivateUsage]
        root=repo, publisher=object()
    )
    assert captured["phase6_runtime"] is runtime
    assert cast(Phase6ControllerRuntime, captured["phase6_runtime"]).research_acquirer

    monkeypatch.setattr(
        "tcfactory.v3.phase6_installation.PHASE6_INSTALL_ROOT", tmp_path / "missing"
    )
    missing = build_phase6_runtime(repo_root=repo)
    assert isinstance(missing, Phase6ControllerRuntime)
    assert missing.research_acquirer is None
