from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from traincapsule_core import build_workload_identity, sha256_digest
from traincapsule_core.evidence import LocalEvidenceStore
from traincapsule_core.models import (
    CompletenessState,
    EligibilityDecision,
    EligibilityOutcome,
    EvidenceRole,
    ExperimentEconomics,
)
from traincapsule_ingest_pytorch import (
    FlightRecorderImportError,
    ImportErrorCode,
    PyTorchFlightRecorderImporter,
)
from traincapsule_qualify import PreflightInputs, assess_completeness, evaluate_preflight

from .test_identity import workload_material
from .test_qualification import PAYLOADS, artifact, make_inputs, native_baseline

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "examples/product/flight-recorder"
UV = Path.home() / ".local/bin/uv"


def evaluate(inputs: PreflightInputs) -> EligibilityDecision:
    return evaluate_preflight(inputs, artifact_reader=lambda item: PAYLOADS[item.content_digest])


def _run_installed_journey(cli: Path, python: Path, tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"

    def run(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [str(cli), *arguments],
            check=False,
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == expected, completed.stdout + completed.stderr
        return completed

    module_probe = subprocess.run(
        [
            str(python),
            "-c",
            "import json,traincapsule_core,traincapsule_ingest_pytorch,traincapsule_qualify;"
            "print(json.dumps([traincapsule_core.__file__,traincapsule_ingest_pytorch.__file__,"
            "traincapsule_qualify.__file__]))",
        ],
        check=True,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    source_roots = [
        ROOT / "packages/traincapsule-core/src",
        ROOT / "packages/traincapsule-ingest-pytorch/src",
        ROOT / "packages/traincapsule-qualify/src",
        ROOT / "packages/traincapsule-cli/src",
    ]
    assert all(
        not any(Path(path).resolve().is_relative_to(root) for root in source_roots)
        for path in json.loads(module_probe.stdout)
    )
    assert json.loads(run("doctor", "--json").stdout)["ok"] is True

    case_path = tmp_path / "case.json"
    run(
        "case",
        "init",
        "--case-id",
        "CASE-INSTALLED",
        "--decision-owner",
        "machine-policy",
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
        "--output",
        str(case_path),
        "--json",
    )
    workload_path = tmp_path / "workload.json"
    baseline_environment_path = tmp_path / "baseline-environment.json"
    candidate_input = tmp_path / "candidate-input.json"
    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    shutil.copy2(ROOT / "examples/product/workload-identity-input.json", fixture_root)
    shutil.copy2(ROOT / "examples/product/environment-identity-input.json", fixture_root)
    shutil.copytree(TRACE, fixture_root / "flight-recorder")
    baseline_recipe = tmp_path / "baseline.recipe"
    candidate_recipe = tmp_path / "candidate.recipe"
    baseline_recipe.write_bytes(b"installed-baseline-materialization-v1")
    candidate_recipe.write_bytes(b"installed-candidate-materialization-v1")
    baseline_material = json.loads(
        (fixture_root / "environment-identity-input.json").read_text(encoding="utf-8")
    )
    baseline_material["materializationRecipeDigest"] = sha256_digest(
        baseline_recipe.read_bytes()
    )
    (fixture_root / "environment-identity-input.json").write_text(
        json.dumps(baseline_material), encoding="utf-8"
    )
    candidate_material = json.loads(
        (fixture_root / "environment-identity-input.json").read_text(encoding="utf-8")
    )
    candidate_material["scheduler"] = "local"
    candidate_material["materializationRecipeDigest"] = sha256_digest(
        candidate_recipe.read_bytes()
    )
    candidate_input.write_text(json.dumps(candidate_material), encoding="utf-8")
    run(
        "identity",
        "workload",
        str(fixture_root / "workload-identity-input.json"),
        "--output",
        str(workload_path),
        "--json",
    )
    run(
        "identity",
        "environment",
        str(fixture_root / "environment-identity-input.json"),
        "--output",
        str(baseline_environment_path),
        "--json",
    )
    candidate_environment_path = tmp_path / "candidate-environment.json"
    run(
        "identity",
        "environment",
        str(candidate_input),
        "--output",
        str(candidate_environment_path),
        "--json",
    )

    trace = tmp_path / "same-state-trace"
    shutil.copytree(fixture_root / "flight-recorder/real-format", trace)
    rank_one = json.loads((trace / "rank-1.json").read_text(encoding="utf-8"))
    rank_one["entries"][0]["state"] = "completed"
    (trace / "rank-1.json").write_text(json.dumps(rank_one), encoding="utf-8")
    store = tmp_path / "store"
    imported_path = tmp_path / "import.json"
    run(
        "ingest",
        "pytorch-flight-recorder",
        str(trace),
        "--case-id",
        "CASE-INSTALLED",
        "--store",
        str(store),
        "--captured-at",
        "2026-08-11T20:00:00Z",
        "--workload-id",
        json.loads(workload_path.read_text())["workloadId"],
        "--baseline-environment-id",
        json.loads(baseline_environment_path.read_text())["environmentId"],
        "--candidate-environment-id",
        json.loads(candidate_environment_path.read_text())["environmentId"],
        "--baseline-recipe",
        str(baseline_recipe),
        "--candidate-recipe",
        str(candidate_recipe),
        "--output",
        str(imported_path),
        "--json",
    )
    baseline_path = tmp_path / "native.json"
    human_path = tmp_path / "native.md"
    run(
        "native-baseline",
        str(imported_path),
        "--store",
        str(store),
        "--executed-at",
        "2026-08-11T20:01:00Z",
        "--elapsed-seconds",
        "10",
        "--operator-effort-seconds",
        "0",
        "--unresolved-question",
        "Whether to approve the candidate.",
        "--output",
        str(baseline_path),
        "--human-output",
        str(human_path),
        "--json",
    )
    preflight_path = tmp_path / "preflight.json"
    # ruff: noqa: E501
    assembler = """
import json,sys
from pathlib import Path
from traincapsule_core.models import EnvironmentIdentity, EvidenceArtifact, ExperimentEconomics, IncidentCase, WorkloadIdentity
from traincapsule_qualify import NativeBaseline, PreflightInputs, assess_completeness
from traincapsule_core.models import CompletenessState, EvidenceRole
case=IncidentCase.model_validate_json(Path(sys.argv[1]).read_text())
workload=WorkloadIdentity.model_validate_json(Path(sys.argv[2]).read_text())
baseline=EnvironmentIdentity.model_validate_json(Path(sys.argv[3]).read_text())
candidate=EnvironmentIdentity.model_validate_json(Path(sys.argv[4]).read_text())
native=NativeBaseline.model_validate_json(Path(sys.argv[5]).read_text())
artifacts=[*native.artifacts,*native.binding_artifacts]
case=case.model_copy(update={'workload_id':workload.workload_id,'baseline_environment_id':baseline.environment_id,'candidate_environment_id':candidate.environment_id,'evidence_refs':[a.artifact_id for a in artifacts],'native_findings':native.findings,'status':'PREFLIGHT'})
requirements={name:CompletenessState.PRESENT_VALID for name in ('flight_recorder_raw','collective_lifecycle','rank_process_group_inventory','workload_identity','environment_identity')}
roles={name:EvidenceRole.MANDATORY_FOR_ELIGIBILITY for name in requirements}
refs={name:[a.artifact_id for a in artifacts] for name in requirements}
completeness=assess_completeness(case_id=case.case_id,requirements=requirements,roles=roles,verified_artifacts=artifacts,artifact_refs=refs,details={'rank_process_group_inventory':'rank/process-group inventory captured'})
inputs=PreflightInputs(evaluated_at='2026-08-11T20:02:00Z',incident_case=case,workload_identity=workload,baseline_environment=baseline,candidate_environment=candidate,verified_artifacts=artifacts,completeness_report=completeness,native_baseline=native,original_experiment_economics=ExperimentEconomics(estimated_cost=100,currency='CAD',basis='measured'),proposed_experiment_economics=ExperimentEconomics(estimated_cost=10,currency='CAD',basis='bounded'))
Path(sys.argv[6]).write_text(inputs.model_dump_json(by_alias=True))
"""
    subprocess.run(
        [
            str(python),
            "-c",
            assembler,
            str(case_path),
            str(workload_path),
            str(baseline_environment_path),
            str(candidate_environment_path),
            str(baseline_path),
            str(preflight_path),
        ],
        check=True,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    decision = json.loads(
        run(
            "preflight", str(preflight_path), "--store", str(store), "--json", expected=20
        ).stdout
    )
    assert decision["outcome"] == "ELIGIBLE_FOR_QUALIFICATION"

    variants = """
import json,sys
from pathlib import Path
from traincapsule_core.models import CompletenessState, EvidenceRole, ExperimentEconomics
from traincapsule_qualify import PreflightInputs, assess_completeness
base=PreflightInputs.model_validate_json(Path(sys.argv[1]).read_text())
def write(name,value): Path(sys.argv[2],name+'.json').write_text(value.model_dump_json(by_alias=True))
missing=assess_completeness(case_id=base.incident_case.case_id,requirements={'flight_recorder':CompletenessState.MISSING_NOT_CAPTURED},roles={'flight_recorder':EvidenceRole.MANDATORY_FOR_ELIGIBILITY},verified_artifacts=base.verified_artifacts)
write('missing',base.model_copy(update={'completeness_report':missing}))
write('policy',base.model_copy(update={'incident_case':base.incident_case.model_copy(update={'privacy_policy':'EXPORT_ALLOWED'})}))
write('unknown',base.model_copy(update={'proposed_experiment_economics':ExperimentEconomics(basis='unknown')}))
write('uneconomic',base.model_copy(update={'proposed_experiment_economics':ExperimentEconomics(estimated_cost=101,currency='CAD',basis='bounded')}))
write('unsupported-source',base.model_copy(update={'native_baseline':base.native_baseline.model_copy(update={'tool_version':'9.0'})}))
write('expired',base.model_copy(update={'evaluated_at':'2026-08-13T20:02:00Z'}))
"""
    subprocess.run(
        [str(python), "-c", variants, str(preflight_path), str(tmp_path)],
        check=True,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    expected_outcomes = {
        "missing": "NEEDS_MORE_EVIDENCE",
        "policy": "POLICY_BLOCKED",
        "unknown": "UNKNOWN",
        "uneconomic": "TECHNICALLY_POSSIBLE_BUT_UNECONOMIC",
        "unsupported-source": "NEEDS_MORE_EVIDENCE",
        "expired": "UNKNOWN",
    }
    expected_codes = {
        "missing": 11,
        "policy": 13,
        "unknown": 22,
        "uneconomic": 21,
        "unsupported-source": 11,
        "expired": 24,
    }
    for name, outcome in expected_outcomes.items():
        payload = json.loads(
            run(
                "preflight",
                str(tmp_path / f"{name}.json"),
                "--store",
                str(store),
                "--json",
                expected=expected_codes[name],
            ).stdout
        )
        assert payload["outcome"] == outcome

    native_store = tmp_path / "native-store"
    native_import = tmp_path / "native-import.json"
    run(
        "ingest",
        "pytorch-flight-recorder",
        str(fixture_root / "flight-recorder/real-format"),
        "--case-id",
        "CASE-INSTALLED",
        "--store",
        str(native_store),
        "--captured-at",
        "2026-08-11T20:00:00Z",
        "--workload-id",
        json.loads(workload_path.read_text())["workloadId"],
        "--baseline-environment-id",
        json.loads(baseline_environment_path.read_text())["environmentId"],
        "--candidate-environment-id",
        json.loads(candidate_environment_path.read_text())["environmentId"],
        "--baseline-recipe",
        str(baseline_recipe),
        "--candidate-recipe",
        str(candidate_recipe),
        "--output",
        str(native_import),
        "--json",
    )
    native_sufficient_baseline = tmp_path / "native-sufficient.json"
    run(
        "native-baseline",
        str(native_import),
        "--store",
        str(native_store),
        "--executed-at",
        "2026-08-11T20:01:00Z",
        "--elapsed-seconds",
        "10",
        "--operator-effort-seconds",
        "0",
        "--output",
        str(native_sufficient_baseline),
        "--json",
    )
    native_preflight = tmp_path / "native-preflight.json"
    subprocess.run(
        [
            str(python),
            "-c",
            assembler,
            str(case_path),
            str(workload_path),
            str(baseline_environment_path),
            str(candidate_environment_path),
            str(native_sufficient_baseline),
            str(native_preflight),
        ],
        check=True,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    native_decision = json.loads(
        run(
            "preflight",
            str(native_preflight),
            "--store",
            str(native_store),
            "--json",
            expected=20,
        ).stdout
    )
    assert native_decision["outcome"] == "NATIVE_WORKFLOW_SUFFICIENT"

    unsupported = run(
        "ingest",
        "pytorch-flight-recorder",
        str(fixture_root / "flight-recorder/unsupported"),
        "--case-id",
        "CASE-UNSUPPORTED",
        "--store",
        str(tmp_path / "unsupported-store"),
        "--captured-at",
        "2026-08-11T20:00:00Z",
        "--workload-id",
        json.loads(workload_path.read_text())["workloadId"],
        "--baseline-environment-id",
        json.loads(baseline_environment_path.read_text())["environmentId"],
        "--candidate-environment-id",
        json.loads(candidate_environment_path.read_text())["environmentId"],
        "--baseline-recipe",
        str(baseline_recipe),
        "--candidate-recipe",
        str(candidate_recipe),
        "--json",
        expected=10,
    )
    assert json.loads(unsupported.stderr)["code"] == "UNSUPPORTED_VERSION"

    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../../escape.json", "{}")
    run(
        "ingest",
        "pytorch-flight-recorder",
        str(archive),
        "--case-id",
        "../ESCAPE",
        "--store",
        str(tmp_path / "archive-store"),
        "--captured-at",
        "2026-08-11T20:00:00Z",
        "--json",
        expected=2,
    )
    assert not (tmp_path / "escape.json").exists()


def test_clean_independent_product_wheel_install_has_no_factory_dependency(
    tmp_path: Path,
) -> None:
    installed_cli = os.environ.get("TRAINCAPSULE_INSTALLED_CLI")
    if installed_cli:
        cli = Path(installed_cli).resolve(strict=True)
        python = cli.parent / "python"
        assert python.is_file()
        doctor = subprocess.run(
            [str(cli), "doctor", "--json"],
            check=True,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert json.loads(doctor.stdout)["ok"] is True
        metadata = subprocess.run(
            [
                str(python),
                "-c",
                "import importlib.metadata,json; "
                "print(json.dumps(importlib.metadata.requires('traincapsule-cli')))",
            ],
            check=True,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        requirements = " ".join(json.loads(metadata.stdout)).lower()
        assert "tcfactory" not in requirements and "claude" not in requirements
        _run_installed_journey(cli, python, tmp_path / "installed-full-journey")
        return
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    factory_wheels = tmp_path / "factory-wheel"
    subprocess.run(
        [
            str(UV),
            "build",
            "--offline",
            "--wheel",
            "--out-dir",
            str(factory_wheels),
            str(ROOT),
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    factory_wheel = next(factory_wheels.glob("*.whl"))
    with zipfile.ZipFile(factory_wheel) as archive:
        roots = {name.split("/", 1)[0] for name in archive.namelist()}
        entry = next(name for name in archive.namelist() if name.endswith("entry_points.txt"))
        entry_points = archive.read(entry).decode("utf-8")
    assert "tcfactory" in roots
    assert not any(
        root.startswith("traincapsule_") and not root.endswith(".dist-info") for root in roots
    )
    assert "traincapsule =" not in entry_points
    packages = [
        ROOT / "packages/traincapsule-core",
        ROOT / "packages/traincapsule-ingest-pytorch",
        ROOT / "packages/traincapsule-qualify",
        ROOT / "packages/traincapsule-cli",
    ]
    for package in packages:
        subprocess.run(
            [
                str(UV),
                "build",
                "--offline",
                "--wheel",
                "--out-dir",
                str(wheelhouse),
                str(package),
            ],
            check=True,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
    environment = tmp_path / "product-venv"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / "bin/python"
    subprocess.run(
        [
            str(UV),
            "pip",
            "install",
            "--offline",
            "--python",
            str(python),
            "--find-links",
            str(wheelhouse),
            "traincapsule-cli",
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata,json,subprocess,sys; "
            "r=subprocess.run([sys.prefix+'/bin/traincapsule','doctor','--json'],"
            "capture_output=True,text=True); "
            "print(json.dumps({'exit':r.returncode,'doctor':json.loads(r.stdout),"
            "'requirements':importlib.metadata.requires('traincapsule-cli')}))",
        ],
        check=True,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    payload = json.loads(probe.stdout)
    assert payload["exit"] == 0 and payload["doctor"]["ok"] is True
    requirements = " ".join(payload["requirements"]).lower()
    assert "tcfactory" not in requirements and "claude" not in requirements
    _run_installed_journey(environment / "bin/traincapsule", python, tmp_path / "full-journey")


def test_bound_case_to_preflight_required_outcome_matrix() -> None:
    eligible = evaluate(make_inputs())
    assert eligible.outcome is EligibilityOutcome.ELIGIBLE_FOR_QUALIFICATION

    missing = assess_completeness(
        case_id="CASE-QUALIFY",
        requirements={"trace": CompletenessState.MISSING_NOT_CAPTURED},
        roles={"trace": EvidenceRole.MANDATORY_FOR_ELIGIBILITY},
        verified_artifacts=[artifact()],
    )
    assert (
        evaluate(make_inputs(completeness_report=missing)).outcome
        is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    )
    sufficient = native_baseline(decision_reached=True)
    assert (
        evaluate(
            make_inputs(
                native_baseline=sufficient,
                verified_artifacts=[*sufficient.artifacts, *sufficient.binding_artifacts],
            )
        ).outcome
        is EligibilityOutcome.NATIVE_WORKFLOW_SUFFICIENT
    )
    assert (
        evaluate(
            make_inputs().model_copy(
                update={
                    "incident_case": make_inputs().incident_case.model_copy(
                        update={"privacy_policy": "EXPORT_ALLOWED"}
                    )
                }
            )
        ).outcome
        is EligibilityOutcome.POLICY_BLOCKED
    )
    assert (
        evaluate(
            make_inputs(proposed_experiment_economics=ExperimentEconomics(basis="unknown"))
        ).outcome
        is EligibilityOutcome.UNKNOWN
    )
    assert (
        evaluate(
            make_inputs(
                native_baseline=native_baseline().model_copy(update={"tool_version": "9.0"})
            )
        ).outcome
        is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    )

    weak_material = workload_material()
    weak_material["dataIdentity"] = {"policy": "CUSTOMER_ATTESTED", "manifestDigest": None}
    weak = build_workload_identity(weak_material)
    inputs = make_inputs()
    case = inputs.incident_case.model_copy(update={"workload_id": weak.workload_id})
    weak_result = evaluate(
        inputs.model_copy(update={"workload_identity": weak, "incident_case": case})
    )
    assert weak_result.outcome is EligibilityOutcome.NEEDS_MORE_EVIDENCE
    assert weak_result.operational_decision.value == "REQUIRE_MORE_EVIDENCE"


def test_unsupported_version_and_malicious_archive_path_are_fail_closed(
    tmp_path: Path,
) -> None:
    importer = PyTorchFlightRecorderImporter()
    with pytest.raises(FlightRecorderImportError) as unsupported:
        importer.import_trace(
            trace_dir=TRACE / "unsupported",
            case_id="CASE-UNSUPPORTED",
            store=LocalEvidenceStore(tmp_path / "unsupported-store"),
            captured_at=make_inputs().evaluated_at,
        )
    assert unsupported.value.code is ImportErrorCode.UNSUPPORTED_VERSION

    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../../escape.json", "{}")
    with pytest.raises(FlightRecorderImportError) as malicious:
        importer.import_trace(
            trace_dir=archive,
            case_id="../ESCAPE",
            store=LocalEvidenceStore(tmp_path / "archive-store"),
            captured_at=make_inputs().evaluated_at,
        )
    assert malicious.value.code is ImportErrorCode.MALFORMED_EVIDENCE
    assert not (tmp_path / "escape.json").exists()
