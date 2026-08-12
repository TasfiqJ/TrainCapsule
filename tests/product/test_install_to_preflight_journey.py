from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from traincapsule_cli.cli import ExitCode, app
from traincapsule_core.models import CompletenessState
from traincapsule_qualify import (
    CostHypothesis,
    NativeBaseline,
    PreflightInputs,
    assess_completeness,
)
from typer.testing import CliRunner

from .test_identity import environment_material, workload_material

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "examples/product/flight-recorder/supported"
runner = CliRunner()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def invoke_to_file(arguments: list[str], output: Path) -> dict[str, object]:
    result = runner.invoke(app, [*arguments, "--output", str(output), "--json"])
    assert result.exit_code == ExitCode.OK, result.output
    raw: object = json.loads(output.read_bytes())
    payload = raw
    assert isinstance(payload, dict)
    return cast(dict[str, object], payload)


def test_clean_local_case_to_eligible_preflight_journey(tmp_path: Path) -> None:
    case = invoke_to_file(
        [
            "case",
            "init",
            "--case-id",
            "CASE-JOURNEY",
            "--decision-owner",
            "incident-owner",
            "--decision-type",
            "candidate approval",
            "--decision-deadline",
            "2026-08-12T20:00:00Z",
            "--incident-summary",
            "controlled collective timeout",
            "--pack-candidate",
            "ddp-hang-v1",
            "--privacy-policy",
            "LOCAL_ONLY",
        ],
        tmp_path / "case.json",
    )
    assert case["status"] == "DRAFT"

    workload_source = tmp_path / "workload-input.json"
    write_json(workload_source, workload_material())
    workload = invoke_to_file(
        ["identity", "workload", str(workload_source)],
        tmp_path / "workload.json",
    )
    environment_source = tmp_path / "environment-input.json"
    write_json(environment_source, environment_material())
    environment = invoke_to_file(
        ["identity", "environment", str(environment_source)],
        tmp_path / "environment.json",
    )
    assert str(workload["workloadId"]).startswith("sha256:")
    assert str(environment["environmentId"]).startswith("sha256:")

    imported = invoke_to_file(
        [
            "ingest",
            "pytorch-flight-recorder",
            str(TRACE),
            "--case-id",
            "CASE-JOURNEY",
            "--store",
            str(tmp_path / "evidence-store"),
            "--captured-at",
            "2026-08-11T20:00:00Z",
        ],
        tmp_path / "import.json",
    )
    artifacts = imported["artifacts"]
    findings = imported["nativeFindings"]
    assert isinstance(artifacts, list) and isinstance(findings, list)
    artifact_refs: list[str] = []
    for raw_artifact in cast(list[object], artifacts):
        assert isinstance(raw_artifact, dict)
        artifact = cast(dict[str, object], raw_artifact)
        artifact_refs.append(str(artifact["artifactId"]))
    finding_records = cast(list[object], findings)

    baseline_source = tmp_path / "native-baseline-input.json"
    write_json(
        baseline_source,
        {
            "schemaVersion": 1,
            "caseId": "CASE-JOURNEY",
            "toolName": "PyTorch Flight Recorder",
            "toolVersion": "2.5.1",
            "command": ["traincapsule", "ingest", "pytorch-flight-recorder"],
            "configuration": {"source": "customer-local"},
            "findings": finding_records,
            "evidenceRefs": artifact_refs,
            "limitations": ["Native observations do not establish candidate safety."],
            "unresolvedCustomerDecision": "Whether to approve the candidate environment.",
            "executedAt": "2026-08-11T20:00:00Z",
            "humanReviewed": True,
            "reviewer": "incident-owner",
        },
    )
    baseline_payload = invoke_to_file(
        ["native-baseline", str(baseline_source)],
        tmp_path / "native-baseline.json",
    )
    baseline = NativeBaseline.model_validate(baseline_payload)

    completeness = assess_completeness(
        case_id="CASE-JOURNEY",
        requirements={
            "flight_recorder": CompletenessState.PRESENT_VALID,
            "checkpoint": CompletenessState.NOT_APPLICABLE,
        },
        artifact_refs={"flight_recorder": artifact_refs},
    )
    preflight = PreflightInputs.model_validate(
        {
            "caseId": "CASE-JOURNEY",
            "decisionType": "candidate approval",
            "decisionDeadline": "2026-08-12T20:00:00Z",
            "evaluatedAt": "2026-08-11T20:05:00Z",
            "baselineAccess": True,
            "candidateAccess": True,
            "evidenceIdentityBound": True,
            "packFit": True,
            "localExecutionAvailable": True,
            "costHypothesis": CostHypothesis.VIABLE,
            "privacyPolicyAllowsProcessing": True,
            "exportPolicyAllowsRequiredFlow": True,
            "completeNativeBaseline": True,
            "nativeWorkflowResolvesDecision": False,
            "humanExpertiseAvailable": True,
            "sourceVersionSupported": True,
            "completenessReport": completeness,
            "nativeBaseline": baseline,
        }
    )
    preflight_source = tmp_path / "preflight-input.json"
    write_json(
        preflight_source,
        preflight.model_dump(mode="json", by_alias=True, exclude_none=False),
    )
    decision = invoke_to_file(
        ["preflight", str(preflight_source)],
        tmp_path / "eligibility.json",
    )
    assert decision["outcome"] == "ELIGIBLE_FOR_QUALIFICATION"
    assert decision["technicalResult"] == "PASS"
    assert decision["operationalDecision"] == "APPROVE_WITHIN_ENVELOPE"
